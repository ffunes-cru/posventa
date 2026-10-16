/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

// Valor del selector de problema cuando la falla no figura en el catálogo
const PROBLEMA_NO_LISTADO = "no_listado";

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
            desvioTipoId: false,
            tiposDesvio: [],
            storageMode: "drive",
            ubicacionActual: "",
            hectareas: "",
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
            heavyFiles: [], // [{ file, name, size, type, uuid, progress, status }]
            isUploadingHeavy: false,
            uploadProgressText: "",
            createdTicketId: false,
            uploadError: null, // { filename, error, fileItem }
            wantsSendDirect: false,
        });

        this.chunkSizeBytes = 768 * 1024;
        this.maxFileSizeBytes = 1024 * 1024 * 1024;
        this.rcloneConfigured = true;

        onWillStart(async () => {
            await this.loadCatalogs();
        });
    }

    get problemaNoListadoValue() {
        return PROBLEMA_NO_LISTADO;
    }

    get borradoresExistentes() {
        return ((this.props.maquina && this.props.maquina.tickets) || []).filter(t => t.estado === "borrador");
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
            this.state.tiposDesvio = data.tipos_desvio || [];
            this.state.storageMode = data.storage_mode || "drive";
            if (this.state.tiposDesvio.length > 0 && !this.state.desvioTipoId) {
                const match = this.state.tiposDesvio.find(t => t.codigo === this.state.desvioTipo) || this.state.tiposDesvio[0];
                this.state.desvioTipoId = match.id;
                this.state.desvioTipo = match.codigo || "rotura";
            }
            if (data.chunk_size_bytes) {
                this.chunkSizeBytes = data.chunk_size_bytes;
            }
            if (data.max_file_size_bytes) {
                this.maxFileSizeBytes = data.max_file_size_bytes;
            }
            if (data.rclone_configured !== undefined) {
                this.rcloneConfigured = data.rclone_configured;
                this.rcloneMsg = data.rclone_msg;
            }
        } catch (e) {
            console.error("Error loading wizard catalogs", e);
        }
    }

    onDesvioTipoChange(ev) {
        const selectedCode = ev.target.value;
        this.state.desvioTipo = selectedCode;
        const found = this.state.tiposDesvio.find(t => t.codigo === selectedCode);
        this.state.desvioTipoId = found ? found.id : false;
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
        const MAX_STANDARD_SIZE = 20 * 1024 * 1024; // 20 MB

        for (const file of files) {
            // Si el archivo supera 20MB, redirigir automáticamente a la carga pesada (Drive) para evitar OOM
            if (file.size > MAX_STANDARD_SIZE) {
                this.addHeavyFileDirect(file);
                this.notification.add(
                    _t("El archivo '%s' supera los 20 MB y se procesará mediante carga optimizada a Google Drive.", file.name),
                    { type: "info" }
                );
                continue;
            }

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

    addHeavyFileDirect(file) {
        const MAX_HEAVY_SIZE = this.maxFileSizeBytes || (1024 * 1024 * 1024);
        if (file.size > MAX_HEAVY_SIZE) {
            this.notification.add(
                _t("El archivo '%s' supera el tamaño máximo permitido de %s (%s).", file.name, this.formatFileSize(MAX_HEAVY_SIZE), this.formatFileSize(file.size)),
                { type: "danger" }
            );
            return;
        }
        const uuid = "file_" + Math.random().toString(36).substring(2, 10) + "_" + Date.now();
        this.state.heavyFiles.push({
            file: file,
            name: file.name,
            size: file.size,
            type: file.type || "application/octet-stream",
            uuid: uuid,
            progress: 0,
            status: "pending",
        });
    }

    onHeavyFilesChange(ev) {
        const files = Array.from(ev.target.files || []);
        for (const file of files) {
            this.addHeavyFileDirect(file);
        }
        ev.target.value = "";
    }

    removeAttachment(index) {
        this.state.attachments.splice(index, 1);
    }

    removeHeavyFile(index) {
        this.state.heavyFiles.splice(index, 1);
    }

    async uploadHeavyFile(ticketId, item) {
        const CHUNK_SIZE = this.chunkSizeBytes || (768 * 1024);
        const file = item.file;
        const totalChunks = Math.ceil(file.size / CHUNK_SIZE) || 1;

        item.status = "uploading";
        item.progress = 0;

        for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
            const start = chunkIndex * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, file.size);
            const blobChunk = file.slice(start, end);

            const formData = new FormData();
            formData.append("ticket_id", ticketId);
            formData.append("file_uuid", item.uuid);
            formData.append("filename", item.name);
            formData.append("chunk_index", chunkIndex);
            formData.append("total_chunks", totalChunks);
            formData.append("file_size", file.size);
            formData.append("chunk", blobChunk, item.name);

            this.state.uploadProgressText = _t(
                "Subiendo %s (%s)... Bloque %s de %s",
                item.name,
                this.formatFileSize(file.size),
                chunkIndex + 1,
                totalChunks
            );

            let success = false;
            let retries = 3;
            let lastError = null;

            while (!success && retries > 0) {
                try {
                    const response = await fetch("/posventa/ticket/upload_chunk", {
                        method: "POST",
                        body: formData,
                    });
                    if (!response.ok) {
                        let errMsg = `Error del servidor (HTTP ${response.status})`;
                        if (response.status === 413) {
                            errMsg = _t("El archivo o bloque supera el límite admitido por el servidor (HTTP 413).");
                        } else {
                            try {
                                const errData = await response.json();
                                if (errData.error) errMsg = errData.error;
                            } catch (_) {}
                        }
                        throw new Error(errMsg);
                    }
                    const data = await response.json();
                    if (data.error) {
                        throw new Error(data.error);
                    }
                    success = true;
                } catch (err) {
                    retries--;
                    lastError = err;
                    if (retries === 0) {
                        item.status = "error";
                        throw err;
                    }
                    await new Promise(r => setTimeout(r, 1000));
                }
            }

            item.progress = Math.round(((chunkIndex + 1) / totalChunks) * 100);
        }

        item.status = "completed";
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
                if (!this.state.problemaId) {
                    this.notification.add(_t("Seleccione el problema o indique que no está en la lista."), { type: "warning" });
                    return false;
                }
                if (!(parseFloat(this.state.hectareas) > 0)) {
                    this.notification.add(_t("Indique las hectáreas trabajadas por la máquina."), { type: "warning" });
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
            const hasAttachments = (this.state.attachments && this.state.attachments.length > 0) ||
                                  (this.state.heavyFiles && this.state.heavyFiles.length > 0) ||
                                  (this.state.multimediaUrl && this.state.multimediaUrl.trim().length > 0);
            if (!hasAttachments) {
                this.notification.add(
                    _t("Es obligatorio adjuntar al menos una imagen o video donde se observe la problemática antes de continuar."),
                    { type: "warning" }
                );
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
        if (this.state.problemaId === PROBLEMA_NO_LISTADO) {
            return _t("No está en la lista (ver descripción)");
        }
        const p = this.state.problemas.find(x => x.id === parseInt(this.state.problemaId));
        return p ? p.name : "";
    }

    get desvioTipoLabel() {
        if (this.state.tiposDesvio && this.state.tiposDesvio.length > 0) {
            const found = this.state.tiposDesvio.find(t => t.codigo === this.state.desvioTipo || t.id === this.state.desvioTipoId);
            if (found) return found.name;
        }
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
        this.state.uploadError = null;
        this.state.wantsSendDirect = Boolean(enviarDirecto);

        try {
            let ticketId = this.state.createdTicketId;
            if (!ticketId) {
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
                    if (this.state.problemaId === PROBLEMA_NO_LISTADO) {
                        ticketVals.problema_no_listado = true;
                    } else {
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
                    if (this.state.desvioTipoId) {
                        ticketVals.desvio_tipo_id = parseInt(this.state.desvioTipoId);
                    }
                    ticketVals.desvio_tipo = this.state.desvioTipo;
                }

                const resIds = await this.orm.create("pv.ticket", [ticketVals]);
                ticketId = resIds[0];
                this.state.createdTicketId = ticketId;
            }

            // Adjuntos estándar de Odoo: si uno falla se detiene el envío (el ticket queda en Borrador)
            for (const att of this.state.attachments) {
                if (att.uploaded || att.skipped) continue;
                try {
                    await this.orm.create("ir.attachment", [{
                        name: att.name,
                        datas: att.data,
                        res_model: "pv.ticket",
                        res_id: ticketId,
                        mimetype: att.type,
                    }]);
                    att.uploaded = true;
                } catch (attErr) {
                    console.error("Error al subir adjunto:", att.name, attErr);
                    this.state.uploadError = {
                        filename: att.name,
                        error: attErr.data?.message || attErr.message || _t("Error al subir el archivo."),
                        fileItem: att,
                    };
                    this.state.submitting = false;
                    return;
                }
            }

            // Subida por fragmentos de archivos pesados (hasta 1 GB)
            if (this.state.heavyFiles.length > 0) {
                this.state.isUploadingHeavy = true;
                for (let i = 0; i < this.state.heavyFiles.length; i++) {
                    const hf = this.state.heavyFiles[i];
                    if (hf.status === "completed" || hf.skipped) continue;
                    try {
                        await this.uploadHeavyFile(ticketId, hf);
                    } catch (uploadErr) {
                        console.error("Error al subir archivo pesado:", hf.name, uploadErr);
                        this.state.isUploadingHeavy = false;
                        this.state.uploadProgressText = "";
                        this.state.uploadError = {
                            filename: hf.name,
                            error: uploadErr.message || _t("Error en la transmisión de red o proxy."),
                            fileItem: hf,
                        };
                        this.state.submitting = false;
                        // DETENEMOS: no enviamos a abierto ni cerramos el modal
                        return;
                    }
                }
                this.state.isUploadingHeavy = false;
                this.state.uploadProgressText = "";
            }

            await this.finalizeTicket(enviarDirecto);

        } catch (e) {
            console.error("Error creating ticket", e);
            const msg = e.data?.message || e.message || _t("Error al crear el ticket.");
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.state.submitting = false;
        }
    }

    async finalizeTicket(enviarDirecto = false) {
        const ticketId = this.state.createdTicketId;
        if (!ticketId) return;

        if (enviarDirecto) {
            await this.orm.call("pv.ticket", "action_enviar_ticket", [[ticketId]]);
            this.notification.add(_t("Ticket creado y enviado a revisión técnica."), { type: "success" });
        } else {
            this.notification.add(_t("Ticket guardado en estado Borrador."), { type: "info" });
        }

        this.props.onSuccess(ticketId);
    }

    async retryUpload() {
        if (!this.state.uploadError || !this.state.createdTicketId) return;
        this.state.uploadError = null;
        await this.submitTicket(this.state.wantsSendDirect);
    }

    async proceedWithoutFailedFile() {
        if (!this.state.uploadError || !this.state.createdTicketId) return;
        // Se omite solo el archivo que falló; el resto se sigue subiendo
        this.state.uploadError.fileItem.skipped = true;
        this.state.uploadError = null;
        await this.submitTicket(this.state.wantsSendDirect);
    }

    async keepInDraft() {
        if (!this.state.createdTicketId) return;
        this.state.uploadError = null;
        this.notification.add(
            _t("El ticket quedó guardado en estado Borrador. Podrá adjuntar el archivo multimedia directamente desde Odoo."),
            { type: "info" }
        );
        this.props.onSuccess(this.state.createdTicketId);
    }
}
