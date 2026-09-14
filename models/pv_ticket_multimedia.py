# Part of Crucianelli Posventa Module
import math
from odoo import models, fields, api, _
from odoo.exceptions import UserError

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
        """Permite reintentar la sincronización si quedó en estado de error o pendiente."""
        import os
        for rec in self:
            if rec.estado_sync == 'disponible':
                raise UserError(_("Este archivo ya se encuentra sincronizado y disponible en Google Drive."))

            target_path = rec.staging_path
            if not target_path or not os.path.exists(target_path):
                # Búsqueda de respaldo en directorio staging
                staging_root = os.path.expanduser('~/posventa_staging')
                candidate = os.path.join(staging_root, str(rec.id), rec.name)
                if os.path.exists(candidate):
                    target_path = candidate

            if not target_path or not os.path.exists(target_path):
                raise UserError(_(
                    "No se encontró el archivo temporal en el servidor para reintentar la sincronización. "
                    "Puede adjuntarlo nuevamente mediante el botón 'Adjuntar Video / Multimedia'."
                ))

            rec.write({
                'estado_sync': 'procesando',
                'error_message': False,
                'staging_path': target_path,
            })
            rec.ticket_id._trigger_drive_sync(rec, temp_filepath=target_path)
        return True
