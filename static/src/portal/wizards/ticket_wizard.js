/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class TicketWizard extends Component {
    static template = "posventa.TicketWizard";
    static props = {
        maquina: Object,
        onClose: Function,
        onSuccess: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        const maquina = this.props.maquina;
        const tipoTicket = maquina.tiene_cpm ? "post_pm" : "pre_pm";

        const availableCerts = (maquina && maquina.certificados) ?
            maquina.certificados.filter(c => c.active && c.estado_certificado === "vigente" && (tipoTicket === "post_pm" ? c.tipo === "cpm" : (c.tipo === "fru" || c.tipo === "feu"))) : [];
        const initialCertId = availableCerts.length > 0 ? availableCerts[0].id : false;

        this.state = useState({
            currentStepIndex: 0, // 0-indexed: 0..N
            submitting: false,
            tipoTicket: tipoTicket,
            certificadoId: initialCertId,
            // Step Classification
            sistemaId: false,
            subsistemaId: false,
            problemaId: false,
            desvioTipo: "rotura",
            ubicacionActual: "",
            hectareas: 0,
            // Catalogs
            sistemas: [],
            subsistemas: [],
            problemas: [],
            camposExtras: [],
            camposValues: {}, // { campo_id: val }
            // Details
            placeholderDescripcion: "",
            descripcion: "",
            accionesRealizadas: "",
            multimediaUrl: "",
            attachments: [], // [{ name, size, type, data }]
        });

        onWillStart(async () => {
            await this.loadCatalogs();
        });
    }

    get availableCertificates() {
        const certs = (this.props.maquina && this.props.maquina.certificados) || [];
        if (this.state.tipoTicket === "post_pm") {
            return certs.filter(c => c.active && c.estado_certificado === "vigente" && c.tipo === "cpm");
        } else {
            return certs.filter(c => c.active && c.estado_certificado === "vigente" && (c.tipo === "fru" || c.tipo === "feu"));
        }
    }

    get selectedCertificado() {
        const certs = (this.props.maquina && this.props.maquina.certificados) || [];
        return certs.find(c => c.id === parseInt(this.state.certificadoId));
    }

    async loadCatalogs() {
        try {
            const data = await this.orm.call("pv.ticket", "get_wizard_catalog_data", [], {
                sistema_id: this.state.sistemaId ? parseInt(this.state.sistemaId) : null,
                subsistema_id: this.state.subsistemaId ? parseInt(this.state.subsistemaId) : null,
            });
            this.state.sistemas = data.sistemas || [];
            this.state.subsistemas = data.subsistemas || [];
            this.state.problemas = data.problemas || [];
            this.state.camposExtras = data.campos_extras || [];
        } catch (e) {
            console.error("Error loading wizard catalogs", e);
        }
    }

    async onSistemaChange(ev) {
        const val = parseInt(ev.target.value) || false;
        this.state.sistemaId = val;
        this.state.subsistemaId = false;
        this.state.problemaId = false;
        this.state.camposExtras = [];
        this.state.camposValues = {};
        await this.loadCatalogs();
    }

    async onSubsistemaChange(ev) {
        const val = parseInt(ev.target.value) || false;
        this.state.subsistemaId = val;
        this.state.problemaId = false;
        this.state.camposValues = {};

        const sub = this.state.subsistemas.find(s => s.id === val);
        this.state.placeholderDescripcion = sub ? (sub.placeholder_descripcion || "") : "";

        await this.loadCatalogs();

        for (const c of this.state.camposExtras) {
            if (c.tipo_campo === 'booleano') {
                this.state.camposValues[c.id] = 'false';
            } else {
                this.state.camposValues[c.id] = '';
            }
        }
    }

    setCampoValue(campoId, val) {
        this.state.camposValues[campoId] = val;
    }

    // Attachments Handling
    async onFilesChange(ev) {
        const files = Array.from(ev.target.files || []);
        for (const file of files) {
            const base64Data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    const res = reader.result;
                    const base64 = res.split(",")[1] || "";
                    resolve(base64);
                };
                reader.onerror = error => reject(error);
                reader.readAsDataURL(file);
            });
            this.state.attachments.push({
                name: file.name,
                size: file.size,
                type: file.type || "application/octet-stream",
                data: base64Data,
            });
        }
        ev.target.value = "";
    }

    removeAttachment(index) {
        this.state.attachments.splice(index, 1);
    }

    formatFileSize(bytes) {
        if (!bytes) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    }

    // Dynamic Step Definitions
    get steps() {
        const list = [
            { key: "machine", label: _t("1. Máquina y Certificado") },
            { key: "classification", label: _t("2. Clasificación") },
        ];
        let idx = 3;
        if (this.state.tipoTicket === "post_pm" && this.state.camposExtras.length > 0) {
            list.push({ key: "extra_fields", label: `${idx}. Info Adicional` });
            idx++;
        }
        list.push({ key: "description", label: `${idx}. Descripción y Fotos` });
        idx++;
        list.push({ key: "summary", label: `${idx}. Confirmar` });
        return list;
    }

    get currentStepKey() {
        const s = this.steps[this.state.currentStepIndex];
        return s ? s.key : "machine";
    }

    validateCurrentStep() {
        const key = this.currentStepKey;
        if (key === "machine") {
            if (!this.state.certificadoId) {
                this.notification.add(_t("Debe seleccionar un Certificado Vigente para asociar al reclamo."), { type: "warning" });
                return false;
            }
            return true;
        }

        if (key === "classification") {
            if (this.state.tipoTicket === "post_pm") {
                if (!this.state.sistemaId) {
                    this.notification.add(_t("Por favor seleccione un Sistema."), { type: "warning" });
                    return false;
                }
                if (!this.state.subsistemaId) {
                    this.notification.add(_t("Por favor seleccione un Subsistema."), { type: "warning" });
                    return false;
                }
            } else {
                if (!this.state.desvioTipo) {
                    this.notification.add(_t("Por favor seleccione el Tipo de Desvío."), { type: "warning" });
                    return false;
                }
            }
            return true;
        }

        if (key === "extra_fields") {
            for (const c of this.state.camposExtras) {
                if (c.obligatorio && !this.state.camposValues[c.id]) {
                    this.notification.add(_t("El campo '%s' es obligatorio.", c.name), { type: "warning" });
                    return false;
                }
            }
            return true;
        }

        if (key === "description") {
            if (!this.state.descripcion || !this.state.descripcion.trim()) {
                this.notification.add(_t("La descripción del reclamo es obligatoria."), { type: "warning" });
                return false;
            }
            return true;
        }

        return true;
    }

    nextStep() {
        if (this.validateCurrentStep()) {
            if (this.state.currentStepIndex < this.steps.length - 1) {
                this.state.currentStepIndex++;
            }
        }
    }

    prevStep() {
        if (this.state.currentStepIndex > 0) {
            this.state.currentStepIndex--;
        }
    }

    // Helper getters for summary step display
    get selectedSistemaName() {
        const s = this.state.sistemas.find(x => x.id === parseInt(this.state.sistemaId));
        return s ? s.name : "";
    }

    get selectedSubsistemaName() {
        const sub = this.state.subsistemas.find(x => x.id === parseInt(this.state.subsistemaId));
        return sub ? sub.name : "";
    }

    get selectedProblemaName() {
        const p = this.state.problemas.find(x => x.id === parseInt(this.state.problemaId));
        return p ? p.name : "";
    }

    get desvioTipoLabel() {
        const map = {
            rotura: _t("Rotura en transporte / recepción"),
            faltante: _t("Faltante de piezas o componentes"),
            otro: _t("Otro desvío"),
        };
        return map[this.state.desvioTipo] || this.state.desvioTipo;
    }

    // Submit Action
    async submitTicket(enviarDirecto = false) {
        if (this.state.submitting) return;
        this.state.submitting = true;

        try {
            const ticketVals = {
                maquina_id: this.props.maquina.id,
                certificado_id: parseInt(this.state.certificadoId),
                tipo_ticket: this.state.tipoTicket,
                descripcion: this.state.descripcion,
                acciones_realizadas: this.state.accionesRealizadas || "",
                multimedia_url: this.state.multimediaUrl || "",
            };

            if (this.state.tipoTicket === "post_pm") {
                ticketVals.sistema_id = parseInt(this.state.sistemaId);
                ticketVals.subsistema_id = parseInt(this.state.subsistemaId);
                if (this.state.problemaId) {
                    ticketVals.problema_id = parseInt(this.state.problemaId);
                }
                ticketVals.ubicacion_actual = this.state.ubicacionActual || "";
                ticketVals.hectareas = parseFloat(this.state.hectareas) || 0.0;

                if (this.state.camposExtras.length > 0) {
                    const extraLines = [];
                    for (const c of this.state.camposExtras) {
                        const val = this.state.camposValues[c.id] || "";
                        extraLines.push([0, 0, {
                            campo_id: c.id,
                            campo_nombre: c.name,
                            valor: String(val),
                        }]);
                    }
                    ticketVals.campo_extra_ids = extraLines;
                }
            } else {
                ticketVals.desvio_tipo = this.state.desvioTipo;
            }

            const resIds = await this.orm.create("pv.ticket", [ticketVals]);
            const ticketId = resIds[0];

            // Guardamos adjuntos reales en el documento como en el estándar
            for (const att of this.state.attachments) {
                try {
                    await this.orm.create("ir.attachment", [{
                        name: att.name,
                        datas: att.data,
                        res_model: "pv.ticket",
                        res_id: ticketId,
                        mimetype: att.type,
                    }]);
                } catch (attErr) {
                    console.warn("Error uploading attachment", att.name, attErr);
                }
            }

            if (enviarDirecto) {
                // Invocamos el método público sin guion bajo
                await this.orm.call("pv.ticket", "action_enviar_ticket_direct", [[ticketId]]);
                this.notification.add(_t("Ticket creado y enviado a revisión técnica."), { type: "success" });
            } else {
                this.notification.add(_t("Ticket guardado en estado Borrador."), { type: "info" });
            }

            this.props.onSuccess(ticketId);
        } catch (e) {
            console.error("Error creating ticket", e);
            const msg = e.data?.message || e.message || _t("Error al crear el ticket.");
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.state.submitting = false;
        }
    }
}
