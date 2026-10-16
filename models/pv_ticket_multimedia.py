# Part of Crucianelli Posventa Module
import math
import os
import shutil
import time
from datetime import timedelta
from markupsafe import Markup, escape
from odoo import models, fields, api, _
from odoo.exceptions import UserError

STAGING_DIR_NAME = 'posventa_staging'

# Reintentos automáticos de sincronización a Drive (backoff: 5, 10, 20, 40 min)
MAX_SYNC_INTENTOS = 5
SYNC_BACKOFF_MINUTOS = 5

# Horas tras las cuales se borra una carpeta de staging abandonada (subida incompleta)
STAGING_TTL_HORAS = 24


def get_staging_root():
    path = os.path.expanduser(f"~/{STAGING_DIR_NAME}")
    os.makedirs(path, exist_ok=True)
    return path

ESTADO_SYNC = [
    ('subiendo', 'Subiendo fragmentos'),
    ('procesando', 'Sincronizando a Drive'),
    ('disponible', 'Disponible en Google Drive'),
    ('error', 'Error de sincronización'),
]


class PvTicketMultimedia(models.Model):
    _name = 'pv.ticket.multimedia'
    _description = 'Archivo Multimedia Pesado de Ticket (Google Drive)'
    _order = 'create_date desc, id desc'

    ticket_id = fields.Many2one(
        'pv.ticket',
        string='Ticket de Reclamo',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string='Nombre de Archivo',
        required=True,
    )
    file_size = fields.Integer(
        string='Tamaño (Bytes)',
        default=0,
    )
    file_size_display = fields.Char(
        string='Tamaño',
        compute='_compute_file_size_display',
        store=True,
    )
    mimetype = fields.Char(
        string='Tipo MIME',
        default='application/octet-stream',
    )
    is_video = fields.Boolean(
        string='Es Video',
        compute='_compute_is_video',
        store=True,
    )
    drive_url = fields.Char(
        string='Enlace Google Drive',
    )
    drive_file_id = fields.Char(
        string='ID Archivo en Drive',
    )
    drive_folder_url = fields.Char(
        string='Carpeta en Drive',
    )
    estado_sync = fields.Selection(
        ESTADO_SYNC,
        string='Estado de Sincronización',
        default='subiendo',
        required=True,
    )
    error_message = fields.Text(
        string='Detalle de Error',
    )
    usuario_id = fields.Many2one(
        'res.users',
        string='Cargado por',
        default=lambda self: self.env.user,
        readonly=True,
    )
    fecha_subida = fields.Datetime(
        string='Fecha de Carga',
        default=fields.Datetime.now,
        readonly=True,
    )
    ir_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Adjunto Odoo',
        ondelete='set null',
    )
    staging_path = fields.Char(
        string='Ruta Temporal Staging',
    )
    sync_intentos = fields.Integer(
        string='Intentos de Sincronización',
        default=0,
        readonly=True,
    )
    sync_proximo_intento = fields.Datetime(
        string='Próximo Reintento',
        readonly=True,
    )

    @api.depends('file_size')
    def _compute_file_size_display(self):
        for rec in self:
            size = rec.file_size or 0
            if size <= 0:
                rec.file_size_display = "0 B"
                continue
            units = ['B', 'KB', 'MB', 'GB', 'TB']
            i = int(math.floor(math.log(size, 1024)))
            i = min(i, len(units) - 1)
            p = math.pow(1024, i)
            s = round(size / p, 2)
            rec.file_size_display = f"{s} {units[i]}"

    @api.depends('name', 'mimetype')
    def _compute_is_video(self):
        video_exts = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.3gp', '.m4v')
        for rec in self:
            name_lower = (rec.name or '').lower()
            mime_lower = (rec.mimetype or '').lower()
            rec.is_video = mime_lower.startswith('video/') or name_lower.endswith(video_exts)

    def action_abrir_drive(self):
        """Abre el archivo en Google Drive en una nueva pestaña."""
        self.ensure_one()
        url = self.drive_url or self.ticket_id.multimedia_url
        if not url:
            raise UserError(_("Este archivo aún no cuenta con un enlace de Google Drive generado."))
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_reintentar_sync(self):
        """Reencola la sincronización (reinicia el contador de reintentos automáticos)."""
        for rec in self:
            if rec.estado_sync == 'disponible':
                raise UserError(_("Este archivo ya se encuentra sincronizado y disponible en Google Drive."))
            if not rec.staging_path or not os.path.exists(rec.staging_path):
                if not rec.ticket_id._is_file_in_drive(rec):
                    raise UserError(_(
                        "No se encontró el archivo temporal en el servidor para reintentar la sincronización. "
                        "Puede adjuntarlo nuevamente mediante el botón 'Adjuntar Video / Multimedia'."
                    ))
            rec.ticket_id._trigger_drive_sync(rec)
        return True

    def _registrar_error_sync(self, mensaje):
        """Marca el error, programa el próximo reintento y avisa en el chatter solo en el primer y último fallo."""
        self.ensure_one()
        agotado = self.sync_intentos >= MAX_SYNC_INTENTOS
        espera = SYNC_BACKOFF_MINUTOS * 2 ** max(self.sync_intentos - 1, 0)
        self.write({
            'estado_sync': 'error',
            'error_message': mensaje,
            'sync_proximo_intento': False if agotado else fields.Datetime.now() + timedelta(minutes=espera),
        })
        if self.sync_intentos <= 1 or agotado:
            detalle = (_("Se agotaron los reintentos automáticos; puede reintentar manualmente desde la pestaña Multimedia.")
                       if agotado else _("Se reintentará automáticamente."))
            self.ticket_id.message_post(
                body=Markup(_("⚠️ <b>Fallo en sincronización a Google Drive:</b> %s<br/>Archivo: <i>%s</i>. %s")) % (
                    escape(mensaje), escape(self.name or ''), escape(detalle)),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )

    @api.model
    def _cleanup_staging(self):
        """Borra carpetas de staging abandonadas (subidas por chunks que nunca se completaron)."""
        root = get_staging_root()
        en_uso = {
            os.path.dirname(p) for p in self.search([('staging_path', '!=', False)]).mapped('staging_path')
        }
        limite = time.time() - STAGING_TTL_HORAS * 3600
        for nombre in os.listdir(root):
            path = os.path.join(root, nombre)
            if os.path.isdir(path) and path not in en_uso and os.path.getmtime(path) < limite:
                shutil.rmtree(path, ignore_errors=True)
