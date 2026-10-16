# Part of Crucianelli Posventa Module
import base64
import mimetypes
import os
import re
import time
from markupsafe import Markup, escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from ..models.pv_ticket_multimedia import get_staging_root


class PvTicketMultimediaWizard(models.TransientModel):
    _name = 'pv.ticket.multimedia.wizard'
    _description = 'Asistente para Adjuntar Archivo Multimedia / Video Drive'

    ticket_id = fields.Many2one(
        'pv.ticket',
        string='Ticket',
        required=True,
        default=lambda self: self.env.context.get('default_ticket_id') or self.env.context.get('active_id'),
    )
    tipo_carga = fields.Selection([
        ('archivo', 'Subir Archivo Local / Video'),
        ('enlace_drive', 'Vincular Enlace Directo (Google Drive / URL Externa)'),
    ], string='Tipo de Carga', default='archivo', required=True)

    name = fields.Char(
        string='Título o Nombre Descriptivo',
        help='Nombre visible para identificar este archivo multimedia en el ticket.',
    )
    file = fields.Binary(
        string='Archivo Multimedia',
    )
    filename = fields.Char(
        string='Nombre del Archivo',
    )
    drive_url = fields.Char(
        string='Enlace Google Drive / URL',
    )
    chunk_file_uploader = fields.Char(
        string='Carga de Archivo Pesado',
    )
    uploaded_multimedia_id = fields.Many2one(
        'pv.ticket.multimedia',
        string='Archivo Multimedia Cargado',
    )
    uploaded_multimedia_id_int = fields.Integer(
        string='ID Multimedia Cargado',
    )

    def action_adjuntar(self):
        self.ensure_one()
        ticket = self.ticket_id
        if not ticket:
            raise UserError(_("No se especificó el ticket destino."))

        if self.tipo_carga == 'enlace_drive':
            if not self.drive_url or not self.drive_url.strip():
                raise UserError(_("Debe ingresar un enlace válido de Google Drive o URL externa."))
            
            url = self.drive_url.strip()
            display_name = (self.name or '').strip() or f"Enlace Google Drive - {fields.Date.today()}"

            multimedia = self.env['pv.ticket.multimedia'].create({
                'ticket_id': ticket.id,
                'name': display_name,
                'drive_url': url,
                'estado_sync': 'disponible',
                'usuario_id': self.env.uid,
                'mimetype': 'text/html',
            })

            # Crear ir.attachment de tipo URL
            att = self.env['ir.attachment'].sudo().create({
                'name': display_name,
                'type': 'url',
                'url': url,
                'res_model': 'pv.ticket',
                'res_id': ticket.id,
            })
            multimedia.ir_attachment_id = att.id

            if not ticket.multimedia_url:
                ticket.multimedia_url = url

            ticket.message_post(
                body=Markup(_(
                    "🔗 <b>Se vinculó un enlace de Google Drive:</b> %s<br/>"
                    "<a href='%s' target='_blank' class='btn btn-sm btn-outline-primary mt-1'>▶ Abrir en Google Drive</a>"
                )) % (escape(display_name), escape(url)),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        elif self.tipo_carga == 'archivo':
            # 1. Si viene con self.file explícito (ej. pruebas automatizadas o llamada directa)
            if self.file:
                is_configured, err_msg = ticket._is_rclone_configured()
                if not is_configured:
                    raise UserError(err_msg)

                fname = (self.filename or self.name or 'adjunto_multimedia').strip()
                fname = os.path.basename(fname)
                fname = re.sub(r'[^a-zA-Z0-9_.\-\s]', '_', fname).strip() or 'adjunto_multimedia'

                file_bytes = base64.b64decode(self.file)
                actual_size = len(file_bytes)
                mimetype, _enc = mimetypes.guess_type(fname)
                if fname.lower().endswith('.webm'):
                    mimetype = 'video/webm'

                # Guardar en staging
                target_dir = os.path.join(get_staging_root(), f"backend_{ticket.id}_{int(time.time())}")
                os.makedirs(target_dir, exist_ok=True)
                target_filepath = os.path.join(target_dir, fname)

                with open(target_filepath, 'wb') as f:
                    f.write(file_bytes)

                multimedia = self.env['pv.ticket.multimedia'].create({
                    'ticket_id': ticket.id,
                    'name': fname,
                    'file_size': actual_size,
                    'mimetype': mimetype or 'application/octet-stream',
                    'estado_sync': 'procesando',
                    'staging_path': target_filepath,
                    'usuario_id': self.env.uid,
                })

                ticket._trigger_drive_sync(multimedia, temp_filepath=target_filepath)

                ticket.message_post(
                    body=Markup(_(
                        "📤 <b>Archivo multimedia cargado desde Odoo:</b> %s (%s).<br/>"
                        "Iniciando transferencia a Google Drive..."
                    )) % (escape(fname), escape(multimedia.file_size_display or '')),
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
                return {'type': 'ir.actions.client', 'tag': 'reload'}

            # 2. Carga interactiva por fragmentos (frontend web uploader)
            multimedia_rec = None
            if self.uploaded_multimedia_id:
                multimedia_rec = self.uploaded_multimedia_id
            elif self.uploaded_multimedia_id_int:
                multimedia_rec = self.env['pv.ticket.multimedia'].browse(self.uploaded_multimedia_id_int)

            if not multimedia_rec or not multimedia_rec.exists():
                from datetime import datetime, timedelta
                ten_mins_ago = datetime.now() - timedelta(minutes=10)
                recent = self.env['pv.ticket.multimedia'].search([
                    ('ticket_id', '=', ticket.id),
                    ('create_uid', '=', self.env.uid),
                    ('create_date', '>=', ten_mins_ago),
                ], order='id desc', limit=1)
                if recent:
                    multimedia_rec = recent

            if multimedia_rec and multimedia_rec.exists():
                if self.name and self.name.strip():
                    clean_name = self.name.strip()
                    _base, orig_ext = os.path.splitext(multimedia_rec.name or '')
                    _new_base, new_ext = os.path.splitext(clean_name)
                    if not new_ext and orig_ext:
                        clean_name = f"{clean_name}{orig_ext}"
                    if clean_name != multimedia_rec.name:
                        multimedia_rec.name = clean_name
                return {'type': 'ir.actions.client', 'tag': 'reload'}

            raise UserError(_("Por favor seleccione un archivo y aguarde a que finalice la subida antes de confirmar."))

        return {'type': 'ir.actions.client', 'tag': 'reload'}
