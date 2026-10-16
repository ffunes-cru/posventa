/** @odoo-module **/
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { formatFileSize, newUploadUuid, uploadFileInChunks } from "@posventa/shared/chunk_upload";

/** Widget del asistente "Adjuntar Video" (staff): sube el archivo por fragmentos a Google Drive. */
export class PvMultimediaChunkUploader extends Component {
    static template = "posventa.MultimediaChunkUploader";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.fileInputRef = useRef("fileInput");
        this.formatFileSize = formatFileSize;
        this.state = useState({
            status: "idle", // idle | uploading | success | error
            filename: "",
            fileSizeDisplay: "",
            progress: 0,
            errorMessage: "",
        });
        onWillStart(async () => {
            this.config = await this.orm.call("pv.ticket.multimedia", "get_upload_config", []);
        });
    }

    get ticketId() {
        return this.props.record.data.ticket_id?.id;
    }

    triggerFileSelect() {
        this.fileInputRef.el.click();
    }

    async onFileSelected(ev) {
        const file = ev.target.files?.[0];
        if (!file) {
            return;
        }
        if (!this.config.rclone_configured) {
            this.notification.add(this.config.rclone_msg, { type: "danger" });
            return;
        }
        if (file.size > this.config.max_file_size_bytes) {
            this.notification.add(
                _t("El archivo '%s' supera el límite máximo de %s.", file.name, formatFileSize(this.config.max_file_size_bytes)),
                { type: "danger" }
            );
            return;
        }
        this.currentFile = file;
        this.state.filename = file.name;
        this.state.fileSizeDisplay = formatFileSize(file.size);
        await this.startUpload();
    }

    async startUpload() {
        this.state.status = "uploading";
        this.state.progress = 0;
        this.state.errorMessage = "";
        try {
            const data = await uploadFileInChunks({
                ticketId: this.ticketId,
                file: this.currentFile,
                uuid: newUploadUuid(),
                chunkSize: this.config.chunk_size_bytes,
                onProgress: (done, total) => (this.state.progress = Math.round((done / total) * 100)),
            });
            await this.props.record.update({
                uploaded_multimedia_id: { id: data.multimedia_id, display_name: data.filename },
            });
            this.state.status = "success";
        } catch (err) {
            this.state.status = "error";
            this.state.errorMessage = err.message;
        }
    }

    async onFinish() {
        this.env.dialogData?.close();
        await this.action.doAction({ type: "ir.actions.client", tag: "reload" });
    }
}

registry.category("fields").add("pv_multimedia_chunk_uploader", {
    component: PvMultimediaChunkUploader,
    displayName: _t("Uploader Multimedia por Fragmentos"),
    supportedTypes: ["char"],
});
