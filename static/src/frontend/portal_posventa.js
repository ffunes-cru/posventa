/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { redirect } from "@web/core/utils/urls";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Interaction } from "@web/public/interaction";
import { TicketWizard } from "@posventa/frontend/wizards/ticket_wizard";
import { CertificadoWizard } from "@posventa/frontend/wizards/certificado_wizard";
import { adjuntarArchivo, newUploadUuid, uploadFileInChunks } from "@posventa/shared/chunk_upload";

/** Carga los datos de la máquina con las mismas reglas que el portal backend. */
function useMaquinaDetail(maquinaId) {
    const orm = useService("orm");
    const state = useState({ maquina: null, error: null });
    onWillStart(async () => {
        try {
            state.maquina = await orm.call("pv.maquina", "get_portal_detail_data", [maquinaId]);
        } catch (e) {
            state.error = e.data?.message || e.message || _t("No se pudo cargar la máquina.");
        }
    });
    return state;
}

export class PortalTicketWizard extends Component {
    static template = "posventa.PortalTicketWizard";
    static components = { TicketWizard };
    static props = { maquinaId: Number };

    setup() {
        this.state = useMaquinaDetail(this.props.maquinaId);
    }

    get maquinaUrl() {
        return `/my/posventa/maquina/${this.props.maquinaId}`;
    }

    onClose() {
        redirect(this.maquinaUrl);
    }

    onSuccess(ticketId) {
        redirect(`/my/posventa/ticket/${ticketId}`);
    }
}

export class PortalCertificadoWizard extends Component {
    static template = "posventa.PortalCertificadoWizard";
    static components = { CertificadoWizard };
    static props = { maquinaId: Number };

    setup() {
        this.state = useMaquinaDetail(this.props.maquinaId);
    }

    get maquinaUrl() {
        return `/my/posventa/maquina/${this.props.maquinaId}`;
    }

    onClose() {
        redirect(this.maquinaUrl);
    }

    onSuccess() {
        redirect(this.maquinaUrl);
    }
}

/** Adjuntar fotos/videos a un ticket existente (archivos chicos como adjunto, pesados por fragmentos). */
export class PortalTicketUploader extends Component {
    static template = "posventa.PortalTicketUploader";
    static props = { ticketId: Number };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ files: [], uploading: false, progressText: "" });
        onWillStart(async () => {
            this.config = await this.orm.call("pv.ticket.multimedia", "get_upload_config", []);
        });
    }

    onFilesChange(ev) {
        for (const file of ev.target.files || []) {
            if (file.size > this.config.max_file_size_bytes) {
                this.notification.add(_t("El archivo '%s' supera el tamaño máximo permitido.", file.name), {
                    type: "danger",
                });
                continue;
            }
            this.state.files.push(file);
        }
        ev.target.value = "";
    }

    removeFile(index) {
        this.state.files.splice(index, 1);
    }

    async upload() {
        if (!this.state.files.length || this.state.uploading) {
            return;
        }
        this.state.uploading = true;
        try {
            for (const file of [...this.state.files]) {
                this.state.progressText = _t("Subiendo %s...", file.name);
                if (file.size <= this.config.max_adjunto_bytes) {
                    await adjuntarArchivo(this.orm, this.props.ticketId, file);
                } else {
                    await uploadFileInChunks({
                        ticketId: this.props.ticketId,
                        file,
                        uuid: newUploadUuid(),
                        chunkSize: this.config.chunk_size_bytes,
                        onProgress: (done, total) => {
                            this.state.progressText = _t("Subiendo %s... bloque %s de %s", file.name, done, total);
                        },
                    });
                }
                this.state.files.splice(this.state.files.indexOf(file), 1);
            }
            window.location.reload();
        } catch (e) {
            this.notification.add(e.data?.message || e.message || _t("Error al subir el archivo."), {
                type: "danger",
            });
            this.state.uploading = false;
            this.state.progressText = "";
        }
    }
}

registry.category("public_components").add("posventa.portal_ticket_wizard", PortalTicketWizard);
registry.category("public_components").add("posventa.portal_certificado_wizard", PortalCertificadoWizard);
registry.category("public_components").add("posventa.portal_ticket_uploader", PortalTicketUploader);

/** Botones de formulario con confirmación: <button data-pv-confirm="¿Seguro?"> */
export class PosventaConfirm extends Interaction {
    static selector = ".o_pv_portal [data-pv-confirm]";
    dynamicContent = {
        _root: { "t-on-click.prevent": this.onClick },
    };

    onClick() {
        this.services.dialog.add(ConfirmationDialog, {
            body: this.el.dataset.pvConfirm,
            confirmLabel: _t("Continuar"),
            confirm: () => this.el.closest("form").submit(),
            cancel: () => {},
        });
    }
}

registry.category("public.interactions").add("posventa.confirm", PosventaConfirm);
