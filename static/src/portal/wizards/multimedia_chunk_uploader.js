/** @odoo-module **/
import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class PvMultimediaChunkUploader extends Component {
    static template = "posventa.MultimediaChunkUploader";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.fileInputRef = useRef("fileInput");

        this.state = useState({
            status: "idle", // 'idle' | 'uploading' | 'success' | 'error'
            filename: "",
            fileSize: 0,
            fileSizeDisplay: "",
            progress: 0,
            progressText: "",
            errorMessage: "",
            chunkSizeBytes: 768 * 1024,
            maxFileSizeBytes: 1024 * 1024 * 1024,
            rcloneConfigured: true,
            rcloneMsg: "",
        });

        onWillStart(async () => {
            try {
                const data = await this.orm.call("pv.ticket", "get_wizard_catalog_data", []);
                if (data.chunk_size_bytes) {
                    this.state.chunkSizeBytes = data.chunk_size_bytes;
                }
                if (data.max_file_size_bytes) {
                    this.state.maxFileSizeBytes = data.max_file_size_bytes;
                }
                if (data.rclone_configured !== undefined) {
                    this.state.rcloneConfigured = data.rclone_configured;
                    this.state.rcloneMsg = data.rclone_msg;
                }
            } catch (e) {
                console.warn("Could not fetch catalog config for uploader", e);
            }
        });
    }

    get ticketId() {
        const t = this.props.record.data.ticket_id;
        if (Array.isArray(t) && t.length > 0) {
            return typeof t[0] === "number" ? t[0] : (t[0].id || parseInt(t[0]) || false);
        }
        if (t && typeof t === "object") {
            if (t.id) return t.id;
            if (t.resId) return t.resId;
            if (t.currentId) return t.currentId;
            if (typeof t.raw === "number") return t.raw;
        }
        if (typeof t === "number") {
            return t;
        }
        if (typeof t === "string" && !isNaN(parseInt(t))) {
            return parseInt(t);
        }
        const ctx = (this.props.record && this.props.record.context) || {};
        const fallback = ctx.default_ticket_id || ctx.active_id;
        if (fallback) {
            return parseInt(fallback) || false;
        }
        return false;
    }

    triggerFileSelect() {
        if (this.fileInputRef.el) {
            this.fileInputRef.el.click();
        }
    }

    formatFileSize(bytes) {
        if (!bytes) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    }

    async onFileSelected(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) return;

        if (!this.state.rcloneConfigured) {
            this.notification.add(
                this.state.rcloneMsg || _t("Google Drive / rclone no está configurado en el servidor."),
                { type: "danger" }
            );
            return;
        }

        if (file.size > this.state.maxFileSizeBytes) {
            this.notification.add(
                _t("El archivo '%s' supera el límite máximo de %s (%s).", file.name, this.formatFileSize(this.state.maxFileSizeBytes), this.formatFileSize(file.size)),
                { type: "danger" }
            );
            return;
        }

        this.currentFile = file;
        this.state.filename = file.name;
        this.state.fileSize = file.size;
        this.state.fileSizeDisplay = this.formatFileSize(file.size);
        this.state.errorMessage = "";

        await this.startUpload();
    }

    async startUpload() {
        if (!this.currentFile) return;
        const file = this.currentFile;
        const ticketId = this.ticketId;
        if (!ticketId) {
            this.state.status = "error";
            this.state.errorMessage = _t("No se encontró el ID del ticket destino.");
            return;
        }

        const chunkSize = this.state.chunkSizeBytes || (768 * 1024);
        const totalChunks = Math.ceil(file.size / chunkSize) || 1;
        const fileUuid = "backend_" + Math.random().toString(36).substring(2, 10) + "_" + Date.now();

        this.state.status = "uploading";
        this.state.progress = 0;
        this.state.progressText = _t("Iniciando subida optimizada...");

        for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
            const start = chunkIndex * chunkSize;
            const end = Math.min(start + chunkSize, file.size);
            const blobChunk = file.slice(start, end);

            const formData = new FormData();
            formData.append("ticket_id", ticketId);
            formData.append("file_uuid", fileUuid);
            formData.append("filename", file.name);
            formData.append("chunk_index", chunkIndex);
            formData.append("total_chunks", totalChunks);
            formData.append("file_size", file.size);
            formData.append("chunk", blobChunk, file.name);

            this.state.progressText = _t(
                "Subiendo fragmento %s de %s (%s)...",
                chunkIndex + 1,
                totalChunks,
                this.formatFileSize(file.size)
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
                            errMsg = _t("El bloque supera el límite del proxy (HTTP 413).");
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

                    // Si completó el último fragmento
                    if (chunkIndex === totalChunks - 1) {
                        this.state.progress = 100;
                        this.state.status = "success";
                        this.state.progressText = _t("¡Archivo ensamblado exitosamente!");
                        if (data.multimedia_id) {
                            try {
                                await this.props.record.update({
                                    uploaded_multimedia_id_int: data.multimedia_id,
                                    uploaded_multimedia_id: [data.multimedia_id, data.filename || file.name],
                                });
                            } catch (updateErr) {
                                try {
                                    await this.props.record.update({
                                        uploaded_multimedia_id_int: data.multimedia_id,
                                    });
                                } catch (_) {}
                            }
                        }
                        this.notification.add(
                            _t("Archivo '%s' subido correctamente. Se inició la sincronización a Google Drive.", file.name),
                            { type: "success" }
                        );
                        return;
                    }

                } catch (err) {
                    retries--;
                    lastError = err;
                    if (retries === 0) {
                        this.state.status = "error";
                        this.state.errorMessage = err.message || _t("Error en la conexión o subida de fragmentos.");
                        return;
                    }
                    await new Promise(r => setTimeout(r, 1000));
                }
            }

            this.state.progress = Math.round(((chunkIndex + 1) / totalChunks) * 100);
        }
    }

    async retryUpload() {
        this.state.errorMessage = "";
        await this.startUpload();
    }

    async onFinish() {
        if (this.env.dialogData && this.env.dialogData.close) {
            this.env.dialogData.close();
        }
        await this.action.doAction({ type: "ir.actions.client", tag: "reload" });
    }
}

export const pvMultimediaChunkUploaderField = {
    component: PvMultimediaChunkUploader,
    displayName: _t("Uploader Multimedia por Fragmentos"),
    supportedTypes: ["char"],
};

registry.category("fields").add("pv_multimedia_chunk_uploader", pvMultimediaChunkUploaderField);
