/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const { DateTime } = luxon;

export class CertificadoWizard extends Component {
    static template = "posventa.CertificadoWizard";
    static props = {
        maquina: Object,
        onClose: Function,
        onSuccess: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        const maquina = this.props.maquina;

        // Determine default recommended tipo
        const certs = maquina.certificados || [];
        const hasFeuVigente = certs.some(c => c.active !== false && c.tipo === "feu" && c.estado_certificado === "vigente");
        let defaultTipo = "fru";
        if (maquina.tiene_fru && !maquina.tiene_feu) {
            defaultTipo = "feu";
        } else if (maquina.tiene_feu && !hasFeuVigente) {
            defaultTipo = "feu";
        } else if (maquina.tiene_feu && hasFeuVigente && !maquina.tiene_cpm) {
            defaultTipo = "cpm";
        }

        this.state = useState({
            currentStep: 1,
            submitting: false,
            tipo: defaultTipo,
            fecha: DateTime.local().toISODate(),
            archivo: "",
            archivoNombre: "",
            notas: "",
        });
    }

    get fechaMax() {
        return DateTime.local().toISODate();
    }

    get fechaMin() {
        return this.props.maquina.fecha_liberacion || "";
    }

    get showFeuWarning() {
        const m = this.props.maquina;
        const certs = (m && m.certificados) || [];
        // Only warn if there is already an active-cycle FEU (vigente or vencido), ignoring archived certificates
        const hasCurrentCycleFeu = certs.some(
            c => c.active !== false && c.tipo === "feu" && ["vigente", "vencido"].includes(c.estado_certificado)
        );
        return this.state.tipo === "feu" && hasCurrentCycleFeu;
    }

    get stepLabels() {
        return [
            _t("1. Tipo de Certificado"),
            _t("2. Documento y Notas"),
            _t("3. Confirmar"),
        ];
    }

    // Check availability of each certificate type
    get certificateTypes() {
        const m = this.props.maquina;
        const certs = m.certificados || [];
        const activeCerts = certs.filter(c => c.active !== false && c.estado_certificado === "vigente");
        const activeTypes = activeCerts.map(c => c.tipo);
        const hasCurrentCycleFeu = certs.some(
            c => c.active !== false && c.tipo === "feu" && ["vigente", "vencido"].includes(c.estado_certificado)
        );
        const hasFeuVigente = activeTypes.includes("feu");
        const hasFeuVencido = hasCurrentCycleFeu && !hasFeuVigente;

        return [
            {
                value: "fru",
                label: _t("FRU — Formulario de Recepción de Unidad"),
                disabled: Boolean(m.tiene_fru),
                reason: m.tiene_fru ? _t("El FRU ya fue cargado y no se puede renovar. Debe cargar el FEU.") : "",
            },
            {
                value: "feu",
                label: activeTypes.includes("feu")
                    ? _t("FEU — Formulario de Entrega de Unidad")
                    : (hasCurrentCycleFeu
                        ? _t("FEU — Formulario de Entrega de Unidad (Renovación)")
                        : _t("FEU — Formulario de Entrega de Unidad")),
                disabled: activeTypes.includes("feu") || !m.tiene_fru,
                reason: activeTypes.includes("feu") ? _t("Ya existe un FEU vigente cargado") : (!m.tiene_fru ? _t("Requiere cargar primero el FRU") : ""),
            },
            {
                value: "cpm",
                label: _t("CPM — Certificado de Puesta en Marcha"),
                disabled: activeTypes.includes("cpm") || !m.tiene_feu || hasFeuVencido,
                reason: activeTypes.includes("cpm")
                    ? _t("La máquina ya está completa (CPM activo)")
                    : (!m.tiene_feu
                        ? _t("Requiere cargar primero el FEU")
                        : (hasFeuVencido ? _t("El Formulario de Entrega (FEU) está vencido. Debe renovarlo antes de cargar el CPM.") : "")),
            },
            {
                value: "informe_servicio",
                label: _t("Informe de Servicio"),
                disabled: false,
                reason: "",
            },
            {
                value: "recall",
                label: _t("Recall"),
                disabled: false,
                reason: "",
            },
        ];
    }

    onFileChange(ev) {
        const file = ev.target.files[0];
        if (!file) return;

        const validExts = [".pdf", ".jpg", ".jpeg", ".png"];
        const nameLower = file.name.toLowerCase();
        const isValid = validExts.some(ext => nameLower.endsWith(ext));

        if (!isValid) {
            this.notification.add(_t("El archivo debe ser un PDF o imagen (.jpg, .jpeg, .png)."), { type: "danger" });
            ev.target.value = "";
            this.state.archivo = "";
            this.state.archivoNombre = "";
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            // Extract base64 part
            const result = reader.result;
            const base64 = result.split(",")[1] || result;
            this.state.archivo = base64;
            this.state.archivoNombre = file.name;
        };
        reader.readAsDataURL(file);
    }

    validateStep(step) {
        if (step === 1) {
            if (!this.state.tipo) {
                this.notification.add(_t("Seleccione el Tipo de Certificado."), { type: "warning" });
                return false;
            }
            const selected = this.certificateTypes.find(t => t.value === this.state.tipo);
            if (selected && selected.disabled) {
                this.notification.add(selected.reason || _t("Este tipo de certificado no se puede seleccionar."), { type: "warning" });
                return false;
            }
            if (!this.state.fecha) {
                this.notification.add(_t("Indique la fecha del certificado."), { type: "warning" });
                return false;
            }
            if (this.state.fecha > this.fechaMax) {
                this.notification.add(_t("La fecha del certificado no puede ser posterior a hoy."), { type: "warning" });
                return false;
            }
            if (this.fechaMin && this.state.fecha < this.fechaMin) {
                this.notification.add(_t("La fecha del certificado no puede ser anterior a la liberación de la máquina (%s).", this.fechaMin), { type: "warning" });
                return false;
            }
            return true;
        }
        if (step === 2) {
            if (!this.state.archivo) {
                this.notification.add(_t("Debe adjuntar el archivo del certificado (PDF o Imagen)."), { type: "warning" });
                return false;
            }
            return true;
        }
        return true;
    }

    nextStep() {
        if (this.validateStep(this.state.currentStep)) {
            this.state.currentStep += 1;
        }
    }

    prevStep() {
        if (this.state.currentStep > 1) {
            this.state.currentStep -= 1;
        }
    }

    async submitCertificado() {
        if (this.state.submitting) return;
        this.state.submitting = true;

        try {
            const certVals = {
                maquina_id: this.props.maquina.id,
                tipo: this.state.tipo,
                fecha: this.state.fecha,
                archivo: this.state.archivo,
                archivo_nombre: this.state.archivoNombre,
                notas: this.state.notas || "",
            };

            const resIds = await this.orm.create("pv.certificado", [certVals]);
            this.notification.add(_t("Certificado cargado exitosamente."), { type: "success" });
            this.props.onSuccess(resIds[0]);
        } catch (e) {
            console.error("Error loading certificate", e);
            const msg = e.data?.message || e.message || _t("Error al guardar el certificado.");
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.state.submitting = false;
        }
    }
}
