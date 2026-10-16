/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import {
    adjuntarArchivo,
    fileToBase64,
    formatFileSize,
    newUploadUuid,
    uploadFileInChunks,
} from "@posventa/shared/chunk_upload";

/** Certificados vigentes que pueden respaldar el reclamo: CPM en Post-PM; FRU o FEU en Pre-PM. */
function certificadosParaReclamo(maquina, tipoTicket) {
    const tipos = tipoTicket === "post_pm" ? ["cpm"] : ["fru", "feu"];
    return (maquina.certificados || []).filter(
        (c) => c.active && c.estado_certificado === "vigente" && tipos.includes(c.tipo)
    );
}

function nombreDe(lista, id) {
    return lista.find((x) => x.id === parseInt(id))?.name || "";
}

function mensajeDeError(error, porDefecto) {
    return error.data?.message || error.message || porDefecto;
}

// Valor del selector de problema cuando la falla no figura en el catálogo
const PROBLEMA_NO_LISTADO = "no_listado";

/**
 * Asistente de alta de reclamo en el portal. Pasos: máquina y certificado, clasificación,
 * información adicional (solo Post-PM con campos del subsistema), descripción y archivos, confirmación.
 * Al confirmar crea el ticket en Borrador, sube los archivos (chicos como adjunto, pesados por
 * fragmentos) y, si se pidió, lo envía. Si falla una subida el ticket queda creado y se ofrece
 * reintentar, omitir ese archivo o dejarlo en Borrador.
 */
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
        this.formatFileSize = formatFileSize;
        this.problemaNoListadoValue = PROBLEMA_NO_LISTADO;
        this.limites = {}; // de get_upload_config, vía loadCatalogs

        const tipoTicket = this.props.maquina.tiene_cpm ? "post_pm" : "pre_pm";
        const [certificadoInicial] = certificadosParaReclamo(this.props.maquina, tipoTicket);
        this.state = useState({
            currentStepIndex: 0,
            submitting: false,
            tipoTicket,
            certificadoId: certificadoInicial?.id || false,
            // Clasificación
            sistemaId: false,
            subsistemaId: false,
            problemaId: false,
            desvioTipoId: false,
            ubicacionActual: "",
            hectareas: "",
            camposValues: {}, // { campo_id: valor }
            // Catálogos (get_wizard_catalog_data)
            sistemas: [],
            subsistemas: [],
            problemas: [],
            camposExtras: [],
            tiposDesvio: [],
            storageMode: "drive",
            // Descripción y archivos
            placeholderDescripcion: "",
            descripcion: "",
            accionesRealizadas: "",
            multimediaUrl: "",
            attachments: [], // archivos chicos: { name, size, type, data, status }
            heavyFiles: [], // archivos pesados: { file, name, size, type, uuid, progress, status }
            isUploadingHeavy: false,
            uploadProgressText: "",
            // Envío
            createdTicketId: false,
            uploadError: null, // { filename, error, fileItem }
            wantsSendDirect: false,
        });

        onWillStart(() => this.loadCatalogs());
    }

    // --- Catálogos ---
    async loadCatalogs() {
        try {
            const data = await this.orm.call("pv.ticket", "get_wizard_catalog_data", [], {
                sistema_id: parseInt(this.state.sistemaId) || null,
                subsistema_id: parseInt(this.state.subsistemaId) || null,
            });
            Object.assign(this.state, {
                sistemas: data.sistemas,
                subsistemas: data.subsistemas,
                problemas: data.problemas,
                camposExtras: data.campos_extras,
                tiposDesvio: data.tipos_desvio,
                storageMode: data.storage_mode,
            });
            this.state.desvioTipoId ||= data.tipos_desvio[0]?.id || false;
            this.limites = {
                adjunto: data.max_adjunto_bytes,
                archivoPesado: data.max_file_size_bytes,
                fragmento: data.chunk_size_bytes,
            };
        } catch (e) {
            this.notification.add(mensajeDeError(e, _t("No se pudo cargar el catálogo de reclamos.")), {
                type: "danger",
            });
        }
    }

    onDesvioTipoChange(ev) {
        this.state.desvioTipoId = parseInt(ev.target.value) || false;
    }

    async onSistemaChange(ev) {
        Object.assign(this.state, {
            sistemaId: parseInt(ev.target.value) || false,
            subsistemaId: false,
            problemaId: false,
            camposExtras: [],
            camposValues: {},
        });
        await this.loadCatalogs();
    }

    async onSubsistemaChange(ev) {
        const subsistemaId = parseInt(ev.target.value) || false;
        const subsistema = this.state.subsistemas.find((s) => s.id === subsistemaId);
        Object.assign(this.state, {
            subsistemaId,
            problemaId: false,
            placeholderDescripcion: subsistema?.placeholder_descripcion || "",
        });
        await this.loadCatalogs();
        this.state.camposValues = Object.fromEntries(
            this.state.camposExtras.map((c) => [c.id, c.tipo_campo === "booleano" ? "false" : ""])
        );
    }

    setCampoValue(campoId, val) {
        this.state.camposValues[campoId] = val;
    }

    // --- Archivos ---
    async onFilesChange(ev) {
        for (const file of ev.target.files || []) {
            if (file.size > this.limites.adjunto) {
                // Los pesados van por fragmentos para no cargarlos enteros en memoria
                this.agregarArchivoPesado(file);
                this.notification.add(
                    _t("El archivo '%s' supera %s y se subirá como archivo pesado.", file.name, formatFileSize(this.limites.adjunto)),
                    { type: "info" }
                );
                continue;
            }
            this.state.attachments.push({
                name: file.name,
                size: file.size,
                type: file.type || "application/octet-stream",
                data: await fileToBase64(file),
                status: "pending",
            });
        }
        ev.target.value = "";
    }

    onHeavyFilesChange(ev) {
        for (const file of ev.target.files || []) {
            this.agregarArchivoPesado(file);
        }
        ev.target.value = "";
    }

    agregarArchivoPesado(file) {
        if (file.size > this.limites.archivoPesado) {
            this.notification.add(
                _t("El archivo '%s' supera el tamaño máximo permitido de %s (%s).",
                    file.name, formatFileSize(this.limites.archivoPesado), formatFileSize(file.size)),
                { type: "danger" }
            );
            return;
        }
        this.state.heavyFiles.push({
            file,
            name: file.name,
            size: file.size,
            type: file.type || "application/octet-stream",
            uuid: newUploadUuid(),
            progress: 0,
            status: "pending",
        });
    }

    removeAttachment(index) {
        this.state.attachments.splice(index, 1);
    }

    removeHeavyFile(index) {
        this.state.heavyFiles.splice(index, 1);
    }

    // --- Pasos ---
    get steps() {
        const pasos = [
            { key: "machine", label: _t("Máquina y Certificado") },
            { key: "classification", label: _t("Clasificación") },
        ];
        if (this.state.tipoTicket === "post_pm" && this.state.camposExtras.length) {
            pasos.push({ key: "extra_fields", label: _t("Info Adicional") });
        }
        pasos.push({ key: "description", label: _t("Descripción y Fotos") }, { key: "summary", label: _t("Confirmar") });
        return pasos.map((paso, i) => ({ ...paso, label: `${i + 1}. ${paso.label}` }));
    }

    get currentStepKey() {
        return this.steps[this.state.currentStepIndex]?.key || "machine";
    }

    /** Mensaje que impide avanzar desde el paso dado, o "" si está completo. */
    stepError(key) {
        const s = this.state;
        switch (key) {
            case "machine":
                return s.certificadoId ? "" : _t("Debe seleccionar un Certificado Vigente para asociar al reclamo.");
            case "classification":
                if (s.tipoTicket !== "post_pm") {
                    return s.desvioTipoId ? "" : _t("Por favor seleccione el Tipo de Desvío.");
                }
                if (!s.sistemaId) {
                    return _t("Por favor seleccione un Sistema.");
                }
                if (!s.subsistemaId) {
                    return _t("Por favor seleccione un Subsistema.");
                }
                if (!s.problemaId) {
                    return _t("Seleccione el problema o indique que no está en la lista.");
                }
                return parseFloat(s.hectareas) > 0 ? "" : _t("Indique las hectáreas trabajadas por la máquina.");
            case "extra_fields": {
                const faltante = s.camposExtras.find((c) => c.obligatorio && !s.camposValues[c.id]);
                return faltante ? _t("El campo '%s' es obligatorio.", faltante.name) : "";
            }
            case "description":
                if (!s.descripcion.trim()) {
                    return _t("La descripción del reclamo es obligatoria.");
                }
                if (!s.attachments.length && !s.heavyFiles.length && !s.multimediaUrl.trim()) {
                    return _t("Es obligatorio adjuntar al menos una imagen o video donde se observe la problemática antes de continuar.");
                }
        }
        return "";
    }

    nextStep() {
        const error = this.stepError(this.currentStepKey);
        if (error) {
            this.notification.add(error, { type: "warning" });
        } else if (this.state.currentStepIndex < this.steps.length - 1) {
            this.state.currentStepIndex++;
        }
    }

    prevStep() {
        if (this.state.currentStepIndex > 0) {
            this.state.currentStepIndex--;
        }
    }

    // --- Datos para el paso de confirmación ---
    get borradoresExistentes() {
        return (this.props.maquina.tickets || []).filter((t) => t.estado === "borrador");
    }

    get availableCertificates() {
        return certificadosParaReclamo(this.props.maquina, this.state.tipoTicket);
    }

    get selectedCertificado() {
        return (this.props.maquina.certificados || []).find((c) => c.id === parseInt(this.state.certificadoId));
    }

    get selectedSistemaName() {
        return nombreDe(this.state.sistemas, this.state.sistemaId);
    }

    get selectedSubsistemaName() {
        return nombreDe(this.state.subsistemas, this.state.subsistemaId);
    }

    get selectedProblemaName() {
        if (this.state.problemaId === PROBLEMA_NO_LISTADO) {
            return _t("No está en la lista (ver descripción)");
        }
        return nombreDe(this.state.problemas, this.state.problemaId);
    }

    get desvioTipoLabel() {
        return nombreDe(this.state.tiposDesvio, this.state.desvioTipoId);
    }

    // --- Envío ---
    ticketVals() {
        const s = this.state;
        const vals = {
            maquina_id: this.props.maquina.id,
            certificado_id: parseInt(s.certificadoId),
            descripcion: s.descripcion,
            acciones_realizadas: s.accionesRealizadas,
            multimedia_url: s.multimediaUrl,
        };
        if (s.tipoTicket !== "post_pm") {
            return { ...vals, desvio_tipo_id: s.desvioTipoId };
        }
        const problema = s.problemaId === PROBLEMA_NO_LISTADO
            ? { problema_no_listado: true }
            : { problema_id: parseInt(s.problemaId) };
        return {
            ...vals,
            ...problema,
            sistema_id: parseInt(s.sistemaId),
            subsistema_id: parseInt(s.subsistemaId),
            ubicacion_actual: s.ubicacionActual,
            hectareas: parseFloat(s.hectareas) || 0,
            campo_extra_ids: s.camposExtras.map((c) => [0, 0, {
                campo_id: c.id,
                campo_nombre: c.name,
                valor: String(s.camposValues[c.id] || ""),
            }]),
        };
    }

    async subirArchivo(ticketId, item) {
        if (!item.file) {
            return adjuntarArchivo(this.orm, ticketId, item, item.data);
        }
        this.state.isUploadingHeavy = true;
        item.progress = 0;
        await uploadFileInChunks({
            ticketId,
            file: item.file,
            uuid: item.uuid,
            name: item.name,
            chunkSize: this.limites.fragmento,
            onProgress: (done, total) => {
                item.progress = Math.round((done / total) * 100);
                this.state.uploadProgressText = _t(
                    "Subiendo %s (%s)... Bloque %s de %s", item.name, formatFileSize(item.size), done, total
                );
            },
        });
    }

    /** Sube los archivos pendientes en orden. Si uno falla lo deja en uploadError y devuelve false. */
    async subirArchivosPendientes(ticketId) {
        const pendientes = [...this.state.attachments, ...this.state.heavyFiles].filter(
            (item) => item.status !== "completed" && !item.skipped
        );
        try {
            for (const item of pendientes) {
                item.status = "uploading";
                try {
                    await this.subirArchivo(ticketId, item);
                } catch (e) {
                    item.status = "error";
                    this.state.uploadError = {
                        filename: item.name,
                        error: mensajeDeError(e, _t("Error al subir el archivo.")),
                        fileItem: item,
                    };
                    return false;
                }
                item.status = "completed";
            }
            return true;
        } finally {
            this.state.isUploadingHeavy = false;
            this.state.uploadProgressText = "";
        }
    }

    async submitTicket(enviarDirecto = false) {
        if (this.state.submitting) {
            return;
        }
        Object.assign(this.state, { submitting: true, uploadError: null, wantsSendDirect: Boolean(enviarDirecto) });
        try {
            if (!this.state.createdTicketId) {
                [this.state.createdTicketId] = await this.orm.create("pv.ticket", [this.ticketVals()]);
            }
            const ticketId = this.state.createdTicketId;
            // Si falla una subida no se envía: el ticket queda en Borrador hasta que el usuario decida
            if (!(await this.subirArchivosPendientes(ticketId))) {
                return;
            }
            if (enviarDirecto) {
                await this.orm.call("pv.ticket", "action_enviar_ticket", [[ticketId]]);
                this.notification.add(_t("Ticket creado y enviado a revisión técnica."), { type: "success" });
            } else {
                this.notification.add(_t("Ticket guardado en estado Borrador."), { type: "info" });
            }
            this.props.onSuccess(ticketId);
        } catch (e) {
            this.notification.add(mensajeDeError(e, _t("Error al crear el ticket.")), { type: "danger" });
        } finally {
            this.state.submitting = false;
        }
    }

    // --- Opciones ante una subida fallida ---
    async retryUpload() {
        await this.submitTicket(this.state.wantsSendDirect);
    }

    async proceedWithoutFailedFile() {
        this.state.uploadError.fileItem.skipped = true;
        await this.submitTicket(this.state.wantsSendDirect);
    }

    keepInDraft() {
        this.notification.add(
            _t("El ticket quedó guardado en estado Borrador. Podrá adjuntar el archivo desde el detalle del reclamo."),
            { type: "info" }
        );
        this.props.onSuccess(this.state.createdTicketId);
    }
}
