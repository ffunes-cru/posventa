# Part of Crucianelli Posventa Module
import logging
import mimetypes
import os
import re
import shutil
from markupsafe import Markup, escape
from odoo import http, _
from odoo.http import request
from odoo.addons.posventa.models.pv_ticket_multimedia import get_staging_root

_logger = logging.getLogger(__name__)


def _sanitize_filename(name):
    # Remueve caracteres peligrosos para evitar traversal
    clean = os.path.basename(name)
    clean = re.sub(r'[^a-zA-Z0-9_.\-\s]', '_', clean).strip()
    return clean or "archivo_adjunto"


def _error(message, status=400):
    return request.make_json_response({'error': message}, status=status)


class PosventaMultimediaController(http.Controller):

    @http.route('/posventa/ticket/upload_chunk', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_chunk(self, **post):
        """Recibe un chunk binario de un archivo pesado y lo almacena en staging.

        Al recibir el último chunk ensambla el archivo y, según el modo de almacenamiento,
        lo encola para Google Drive (cron) o lo guarda como adjunto estándar de Odoo.
        """
        try:
            try:
                ticket_id = int(post.get('ticket_id', 0))
                chunk_index = int(post.get('chunk_index', -1))
                total_chunks = int(post.get('total_chunks', 0))
                file_size = int(post.get('file_size', 0))
            except (ValueError, TypeError):
                return _error('Parámetros de subida inválidos.')
            file_uuid = re.sub(r'[^a-zA-Z0-9_\-]', '', post.get('file_uuid', ''))
            filename = _sanitize_filename(post.get('filename', 'adjunto'))
            chunk_file = request.httprequest.files.get('chunk')

            if not ticket_id or not file_uuid or total_chunks <= 0 or not 0 <= chunk_index < total_chunks:
                return _error('Parámetros de subida inválidos (se requiere un ticket válido).')

            # Verificar acceso al ticket (ACL + record rules del usuario)
            ticket = request.env['pv.ticket'].browse(ticket_id).exists()
            if not ticket or not ticket.has_access('write'):
                return _error('El ticket no existe o no tiene acceso.', status=404)

            # Verificar pertenencia para concesionarios
            if not request.env.user.has_group('posventa.group_pv_staff') and not ticket.concesionario_id._is_member():
                return _error('Acceso denegado a este reclamo.', status=403)

            # Límites validados en el servidor (no solo en el navegador)
            Multimedia = request.env['pv.ticket.multimedia']
            storage_mode = Multimedia._get_storage_mode()
            max_bytes = Multimedia._get_max_upload_bytes()
            chunk_bytes = Multimedia._get_chunk_size_bytes()
            if file_size <= 0 or file_size > max_bytes:
                return _error(f'El archivo supera el tamaño máximo permitido ({max_bytes // (1024 * 1024)} MB).', status=413)
            if total_chunks != -(-file_size // chunk_bytes):
                return _error('La cantidad de fragmentos no coincide con el tamaño del archivo.')

            if chunk_index == 0 and storage_mode == 'drive':
                is_configured, rclone_err = Multimedia._is_rclone_configured()
                if not is_configured:
                    return _error(rclone_err)

            staging_session_dir = os.path.join(get_staging_root(), file_uuid)
            os.makedirs(staging_session_dir, exist_ok=True)

            # Guardar fragmento (sin superar el tamaño de chunk configurado)
            part_path = os.path.join(staging_session_dir, f"part_{chunk_index:05d}")
            with open(part_path, 'wb') as f:
                source = chunk_file.stream if chunk_file and hasattr(chunk_file, 'stream') else None
                if source is not None:
                    shutil.copyfileobj(source, f)
                elif chunk_file and hasattr(chunk_file, 'read'):
                    f.write(chunk_file.read())
                else:
                    f.write(request.httprequest.get_data())
            if os.path.getsize(part_path) > chunk_bytes:
                shutil.rmtree(staging_session_dir, ignore_errors=True)
                return _error('El fragmento supera el tamaño configurado.', status=413)

            if chunk_index < total_chunks - 1:
                return request.make_json_response({
                    'status': 'chunk_received',
                    'chunk_index': chunk_index,
                    'total_chunks': total_chunks,
                })

            # Último fragmento: verificar que estén todos y ensamblar
            missing = [i for i in range(total_chunks)
                       if not os.path.exists(os.path.join(staging_session_dir, f"part_{i:05d}"))]
            if missing:
                return _error(f'Faltan fragmentos para completar el archivo: {missing[:5]}')

            final_file_path = os.path.join(staging_session_dir, filename)
            with open(final_file_path, 'wb') as outfile:
                for i in range(total_chunks):
                    part_file = os.path.join(staging_session_dir, f"part_{i:05d}")
                    with open(part_file, 'rb') as infile:
                        shutil.copyfileobj(infile, outfile)
                    os.remove(part_file)

            actual_size = os.path.getsize(final_file_path)
            if actual_size != file_size:
                shutil.rmtree(staging_session_dir, ignore_errors=True)
                return _error('El archivo recibido está incompleto o dañado. Vuelva a intentar la subida.')

            mimetype, _enc = mimetypes.guess_type(filename)
            if filename.lower().endswith('.webm'):
                mimetype = 'video/webm'
            mimetype = mimetype or 'application/octet-stream'

            if storage_mode == 'odoo':
                return self._store_as_attachment(ticket, final_file_path, filename, mimetype, staging_session_dir)

            multimedia = Multimedia.sudo().create({
                'ticket_id': ticket.id,
                'name': filename,
                'file_size': actual_size,
                'mimetype': mimetype,
                'estado_sync': 'procesando',
                'staging_path': final_file_path,
                'usuario_id': request.env.uid,
            })
            # La transferencia a Drive la hace el cron, fuera de esta request
            multimedia._encolar_sync()

            return request.make_json_response({
                'status': 'completed',
                'storage_mode': 'drive',
                'multimedia_id': multimedia.id,
                'filename': filename,
                'file_size': multimedia.file_size,
                'file_size_display': multimedia.file_size_display,
                'estado_sync': multimedia.estado_sync,
                'message': 'Archivo ensamblado exitosamente. Se transferirá a Google Drive en segundo plano.',
            })

        except Exception as e:
            _logger.exception("Error al recibir chunk de multimedia: %s", e)
            return _error(str(e), status=500)

    def _store_as_attachment(self, ticket, file_path, filename, mimetype, staging_dir):
        """Modo contingencia: guarda el archivo ensamblado como adjunto estándar de Odoo."""
        with open(file_path, 'rb') as f:
            raw = f.read()
        attachment = request.env['ir.attachment'].sudo().create({
            'name': filename,
            'raw': raw,
            'res_model': 'pv.ticket',
            'res_id': ticket.id,
            'mimetype': mimetype,
        })
        shutil.rmtree(staging_dir, ignore_errors=True)
        ticket.sudo().message_post(
            body=Markup(_("📎 <b>Archivo adjuntado:</b> %s")) % escape(filename),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
            attachment_ids=[attachment.id],
        )
        return request.make_json_response({
            'status': 'completed',
            'storage_mode': 'odoo',
            'attachment_id': attachment.id,
            'filename': filename,
            'file_size': attachment.file_size,
            'estado_sync': 'disponible',
            'message': 'Archivo adjuntado al ticket.',
        })

    @http.route('/posventa/ticket/upload_status', type='jsonrpc', auth='user')
    def upload_status(self, multimedia_id):
        """Consulta el estado actual de sincronización de un archivo."""
        multimedia = request.env['pv.ticket.multimedia'].browse(int(multimedia_id)).exists()
        if not multimedia or not multimedia.has_access('read'):
            return {'error': 'Archivo no encontrado.'}

        return {
            'id': multimedia.id,
            'name': multimedia.name,
            'estado_sync': multimedia.estado_sync,
            'file_size_display': multimedia.file_size_display,
            'drive_url': multimedia.drive_url,
            'drive_folder_url': multimedia.drive_folder_url or multimedia.ticket_id.drive_folder_url,
            'error_message': multimedia.error_message,
        }
