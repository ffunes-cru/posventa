# Part of Crucianelli Posventa Module
"""Archivos pesados de un reclamo y su sincronización con Google Drive (rclone).

La subida por fragmentos (controllers/multimedia.py) deja el archivo en staging y lo
encola; el cron lo transfiere a Drive, con reintentos acotados y backoff.
"""
import logging
import math
import mimetypes
import os
import shutil
import subprocess
import time
from datetime import timedelta

from markupsafe import Markup, escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

STAGING_DIR_NAME = 'posventa_staging'

# Horas tras las cuales se borra una carpeta de staging abandonada (subida incompleta)
STAGING_TTL_HORAS = 24

# Reintentos automáticos de sincronización a Drive (backoff: 5, 10, 20, 40 min)
MAX_SYNC_INTENTOS = 5
SYNC_BACKOFF_MINUTOS = 5

# En modo de almacenamiento 'odoo' el archivo se carga entero en memoria del worker: tope propio
ODOO_STORAGE_MAX_MB = 200

# Fotos/archivos chicos van como adjunto del ticket; los mayores, por fragmentos (Drive o almacenamiento Odoo)
MAX_ADJUNTO_MB = 20

ESTADO_SYNC = [
    ('procesando', 'Sincronizando a Drive'),
    ('disponible', 'Disponible en Google Drive'),
    ('error', 'Error de sincronización'),
]

VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.3gp', '.m4v')


def get_staging_root():
    path = os.path.expanduser(f"~/{STAGING_DIR_NAME}")
    os.makedirs(path, exist_ok=True)
    return path


def _rclone_bin():
    return shutil.which('rclone') or os.path.expanduser('~/.local/bin/rclone')


def _rclone(*args, timeout=60):
    return subprocess.run([_rclone_bin(), *args], capture_output=True, text=True, timeout=timeout)


def _rclone_link(destino):
    """Enlace compartido de un archivo o carpeta de Drive ('' si rclone no lo devuelve)."""
    res = _rclone("link", destino)
    return res.stdout.strip() if res.returncode == 0 else ""


class PvTicketMultimedia(models.Model):
    _name = 'pv.ticket.multimedia'
    _description = 'Archivo Multimedia Pesado de Ticket (Google Drive)'
    _order = 'create_date desc, id desc'

    ticket_id = fields.Many2one('pv.ticket', string='Ticket de Reclamo', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Nombre de Archivo', required=True)
    file_size = fields.Integer(string='Tamaño (Bytes)', default=0)
    file_size_display = fields.Char(string='Tamaño', compute='_compute_file_size_display', store=True)
    mimetype = fields.Char(string='Tipo MIME', default='application/octet-stream')
    is_video = fields.Boolean(string='Es Video', compute='_compute_is_video', store=True)
    drive_url = fields.Char(string='Enlace Google Drive')
    drive_folder_url = fields.Char(string='Carpeta en Drive')
    estado_sync = fields.Selection(ESTADO_SYNC, string='Estado de Sincronización', default='procesando', required=True)
    error_message = fields.Text(string='Detalle de Error')
    usuario_id = fields.Many2one('res.users', string='Cargado por', default=lambda self: self.env.user, readonly=True)
    ir_attachment_id = fields.Many2one('ir.attachment', string='Adjunto Odoo', ondelete='set null')
    staging_path = fields.Char(string='Ruta Temporal Staging')
    sync_intentos = fields.Integer(string='Intentos de Sincronización', default=0, readonly=True)
    sync_proximo_intento = fields.Datetime(string='Próximo Reintento', readonly=True)

    @api.depends('file_size')
    def _compute_file_size_display(self):
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        for rec in self:
            size = rec.file_size or 0
            i = min(int(math.floor(math.log(size, 1024))), len(units) - 1) if size > 0 else 0
            rec.file_size_display = f"{round(size / 1024 ** i, 2)} {units[i]}"

    @api.depends('name', 'mimetype')
    def _compute_is_video(self):
        for rec in self:
            rec.is_video = (rec.mimetype or '').lower().startswith('video/') or (rec.name or '').lower().endswith(VIDEO_EXTS)

    # --- Configuración de almacenamiento ---
    @api.model
    def _get_param(self, key, default):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    @api.model
    def _get_storage_mode(self):
        mode = self._get_param('posventa.storage_mode', 'drive')
        return mode if mode in ('drive', 'odoo') else 'drive'

    @api.model
    def get_upload_config(self):
        """Límites y destino de subida que usan los asistentes JS (portal y backend)."""
        storage_mode = self._get_storage_mode()
        rclone_configured, rclone_msg = self._is_rclone_configured() if storage_mode == 'drive' else (True, 'OK')
        return {
            'storage_mode': storage_mode,
            'chunk_size_bytes': self._get_chunk_size_bytes(),
            'max_adjunto_bytes': MAX_ADJUNTO_MB * 1024 * 1024,
            'max_file_size_bytes': self._get_max_upload_bytes(),
            'rclone_configured': rclone_configured,
            'rclone_msg': rclone_msg,
        }

    @api.model
    def _get_chunk_size_bytes(self):
        return int(self._get_param('posventa.chunk_size_kb', 768)) * 1024

    @api.model
    def _get_max_upload_bytes(self):
        max_mb = int(self._get_param('posventa.max_file_size_mb', 1024))
        if self._get_storage_mode() == 'odoo':
            max_mb = min(max_mb, ODOO_STORAGE_MAX_MB)
        return max_mb * 1024 * 1024

    @api.model
    def _is_rclone_configured(self):
        """(configurado, mensaje): el binario de rclone existe y el remoto de Google Drive está definido."""
        if not os.path.exists(_rclone_bin()):
            return False, _("Binario rclone no encontrado en el servidor (~/.local/bin/rclone).")
        remote = self._get_param('posventa.rclone_remote', 'crucianelli_drive')
        try:
            remotes = [r.strip().rstrip(':') for r in _rclone('listremotes', timeout=10).stdout.splitlines()]
        except Exception as e:
            return False, _("Error al consultar configuración de rclone: %s", str(e))
        if remote not in remotes:
            return False, _("El almacenamiento de Google Drive no está configurado en el servidor (el remoto '%s' no "
                            "existe en rclone). Debe ejecutar 'rclone config' para vincular la cuenta de Google Drive.", remote)
        return True, "OK"

    # --- Acciones ---
    def action_abrir_drive(self):
        self.ensure_one()
        url = self.drive_url or self.ticket_id.multimedia_url
        if not url:
            raise UserError(_("Este archivo aún no cuenta con un enlace de Google Drive generado."))
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}

    def action_reintentar_sync(self):
        """Reencola la sincronización (reinicia el contador de reintentos automáticos)."""
        for rec in self:
            if rec.estado_sync == 'disponible':
                raise UserError(_("Este archivo ya se encuentra sincronizado y disponible en Google Drive."))
            if not rec._staging_existe() and not rec._esta_en_drive():
                raise UserError(_(
                    "No se encontró el archivo temporal en el servidor para reintentar la sincronización. "
                    "Puede adjuntarlo nuevamente mediante el botón 'Adjuntar Video / Multimedia'."
                ))
        self._encolar_sync()
        return True

    # --- Sincronización con Drive ---
    def _encolar_sync(self):
        """Deja los archivos listos para el cron de sincronización y lo dispara (fuera de la request HTTP)."""
        self.sudo().write({
            'estado_sync': 'procesando',
            'error_message': False,
            'sync_intentos': 0,
            'sync_proximo_intento': False,
        })
        self.env.ref('posventa.cron_pv_sync_multimedia_drive').sudo()._trigger()

    @api.model
    def _cron_sync_pending(self):
        """Sincroniza a Drive los archivos encolados o con error recuperable (uno por commit)."""
        self._cleanup_staging()
        pendientes = self.search([
            ('estado_sync', 'in', ('procesando', 'error')),
            ('sync_intentos', '<', MAX_SYNC_INTENTOS),
            '|', ('sync_proximo_intento', '=', False), ('sync_proximo_intento', '<=', fields.Datetime.now()),
        ], order='id')
        IrCron = self.env['ir.cron']
        IrCron._commit_progress(remaining=len(pendientes))
        for multimedia in pendientes:
            # El intento se cuenta antes de correr: si el cron muere por timeout no se reintenta indefinidamente
            multimedia.sync_intentos += 1
            IrCron._commit_progress()
            try:
                multimedia._sync_to_drive()
            except Exception as e:
                _logger.exception("Error sincronizando multimedia %s a Drive", multimedia.id)
                self.env.cr.rollback()
                multimedia._registrar_error_sync(_("Error interno al sincronizar: %s", str(e)[:400]))
            if not IrCron._commit_progress(1):
                break

    def _get_drive_dest_dir(self):
        """Carpeta del reclamo en Drive: <remoto>:<base>/<OF>_<TICKET>."""
        ticket = self.ticket_id
        remote = self._get_param('posventa.rclone_remote', 'crucianelli_drive')
        base = self._get_param('posventa.rclone_drive_folder', 'Crucianelli_Posventa/Reclamos')
        carpeta = f"{ticket.maquina_id.of or 'MAQ'}_{ticket.name or f'TICKET_{ticket.id}'}"
        return f"{remote}:{base}/{carpeta.replace(' ', '_').replace('/', '_')}"

    def _staging_existe(self):
        return bool(self.staging_path) and os.path.exists(self.staging_path)

    def _esta_en_drive(self):
        """True si el archivo ya existe en la carpeta de Drive del reclamo (subida previa exitosa)."""
        try:
            res = _rclone("lsf", self._get_drive_dest_dir(), "--include", self.name, timeout=30)
            return res.returncode == 0 and self.name in res.stdout
        except Exception as err:
            _logger.warning("Error verificando archivo en Drive: %s", err)
            return False

    def _get_mimetype(self):
        mime = (self.mimetype or '').lower()
        if self.name.lower().endswith('.webm') and ('audio' in mime or not mime):
            return 'video/webm'
        return mime or mimetypes.guess_type(self.name)[0] or 'application/octet-stream'

    def _sync_to_drive(self):
        """Sube el archivo a Drive con rclone y registra los enlaces. Devuelve True si quedó disponible."""
        self.ensure_one()
        configurado, mensaje = self._is_rclone_configured()
        if not configurado:
            self._registrar_error_sync(mensaje)
            return False
        ya_en_drive = self._esta_en_drive()
        if not ya_en_drive and not self._staging_existe():
            self._registrar_error_sync(_("Archivo temporal no encontrado para sincronización."))
            return False

        dest_dir = self._get_drive_dest_dir()
        mime = self._get_mimetype()
        if not ya_en_drive:
            # rclone copy: el archivo local se borra recién cuando el registro quedó disponible
            res = _rclone("copy", self.staging_path, dest_dir, "-M", "--metadata-set", f"content-type={mime}", timeout=1200)
            if res.returncode != 0:
                self._registrar_error_sync((res.stderr or res.stdout or _("Error al ejecutar rclone copy."))[:500])
                return False

        # Enlaces del archivo y de la carpeta (se muestran solo al concesionario dueño y al staff)
        folder_url = _rclone_link(dest_dir)
        drive_url = _rclone_link(f"{dest_dir}/{self.name}") or folder_url or f"https://drive.google.com/drive/search?q={self.name}"

        staging_path = self.staging_path
        self.write({
            'estado_sync': 'disponible',
            'drive_url': drive_url,
            'drive_folder_url': folder_url,
            'staging_path': False,
            'mimetype': mime,
            'error_message': False,
            'sync_proximo_intento': False,
        })
        self._publicar_en_ticket(drive_url, folder_url)
        self._borrar_staging(staging_path)
        return True

    def _publicar_en_ticket(self, drive_url, folder_url):
        """Enlaces en el ticket, adjunto tipo URL para el chatter y aviso de disponibilidad."""
        ticket = self.ticket_id.sudo()
        vals = {}
        if not ticket.multimedia_url:
            vals['multimedia_url'] = drive_url
        if folder_url and not ticket.drive_folder_url:
            vals['drive_folder_url'] = folder_url
        if vals:
            ticket.write(vals)
        Attachment = self.env['ir.attachment'].sudo()
        if not Attachment.search_count([('res_model', '=', 'pv.ticket'), ('res_id', '=', ticket.id), ('name', '=', self.name)]):
            self.ir_attachment_id = Attachment.create({
                'name': self.name, 'type': 'url', 'url': drive_url, 'mimetype': self.mimetype,
                'res_model': 'pv.ticket', 'res_id': ticket.id,
            })
        ticket.message_post(
            body=Markup(_(
                "📁 <b>Archivo multimedia disponible en Google Drive:</b> %s (%s)<br/>"
                "<a href='%s' target='_blank' class='btn btn-sm btn-primary mt-1'>▶ Ver en Google Drive</a>"
            )) % (escape(self.name or ''), escape(self.file_size_display or ''), escape(drive_url)),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

    @staticmethod
    def _borrar_staging(path):
        if not path or not os.path.exists(path):
            return
        try:
            os.remove(path)
            carpeta = os.path.dirname(path)
            if not os.listdir(carpeta):
                os.rmdir(carpeta)
        except OSError as err:
            _logger.warning("No se pudo limpiar archivo staging %s: %s", path, err)

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
            self.ticket_id.sudo().message_post(
                body=Markup(_("⚠️ <b>Fallo en sincronización a Google Drive:</b> %s<br/>Archivo: <i>%s</i>. %s")) % (
                    escape(mensaje), escape(self.name or ''), escape(detalle)),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )

    @api.model
    def _cleanup_staging(self):
        """Borra carpetas de staging abandonadas (subidas por fragmentos que nunca se completaron)."""
        root = get_staging_root()
        en_uso = {os.path.dirname(p) for p in self.search([('staging_path', '!=', False)]).mapped('staging_path')}
        limite = time.time() - STAGING_TTL_HORAS * 3600
        for nombre in os.listdir(root):
            path = os.path.join(root, nombre)
            if os.path.isdir(path) and path not in en_uso and os.path.getmtime(path) < limite:
                shutil.rmtree(path, ignore_errors=True)
