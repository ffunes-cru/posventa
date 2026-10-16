# Part of Crucianelli Posventa Module
import json
import logging
import mimetypes
import os
import re
import shutil
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)

STAGING_DIR_NAME = "posventa_staging"


def _get_staging_root():
    path = os.path.expanduser(f"~/{STAGING_DIR_NAME}")
    os.makedirs(path, exist_ok=True)
    return path


def _sanitize_filename(name):
    # Remueve caracteres peligrosos para evitar traversal
    clean = os.path.basename(name)
    clean = re.sub(r'[^a-zA-Z0-9_.\-\s]', '_', clean).strip()
    return clean or "archivo_adjunto"


class PosventaMultimediaController(http.Controller):

    @http.route('/posventa/ticket/upload_chunk', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_chunk(self, **post):
        """Recibe un chunk binario de un archivo de hasta 1GB y lo almacena en staging."""
        try:
            raw_ticket_id = post.get('ticket_id', 0)
            try:
                ticket_id = int(raw_ticket_id)
            except (ValueError, TypeError):
                ticket_id = 0

            file_uuid = post.get('file_uuid', '').strip()
            filename = _sanitize_filename(post.get('filename', 'adjunto'))
            chunk_index = int(post.get('chunk_index', -1))
            total_chunks = int(post.get('total_chunks', 0))
            file_size = int(post.get('file_size', 0))
            chunk_file = request.httprequest.files.get('chunk')

            if not ticket_id or not file_uuid or chunk_index < 0 or total_chunks <= 0:
                return request.make_json_response({
                    'error': 'Parámetros de subida inválidos (se requiere un ticket válido).'
                }, status=400)

            # Verificar acceso al ticket (ACL + record rules del usuario)
            ticket = request.env['pv.ticket'].browse(ticket_id).exists()
            if not ticket or not ticket.has_access('write'):
                return request.make_json_response({'error': 'El ticket no existe o no tiene acceso.'}, status=404)

            # Verificar si rclone y Google Drive están configurados en el servidor
            is_configured, rclone_err = ticket._is_rclone_configured()
            if not is_configured:
                return request.make_json_response({'error': rclone_err}, status=400)

            # Verificar pertenencia para concesionarios
            if not request.env.user.has_group('posventa.group_pv_staff') and not ticket.concesionario_id._is_member():
                return request.make_json_response({'error': 'Acceso denegado a este reclamo.'}, status=403)

            # Directorio staging del upload
            safe_uuid = re.sub(r'[^a-zA-Z0-9_\-]', '', file_uuid)
            staging_session_dir = os.path.join(_get_staging_root(), safe_uuid)
            os.makedirs(staging_session_dir, exist_ok=True)

            # Guardar fragmento
            part_filename = f"part_{chunk_index:05d}"
            part_path = os.path.join(staging_session_dir, part_filename)

            with open(part_path, 'wb') as f:
                if chunk_file and hasattr(chunk_file, 'stream'):
                    shutil.copyfileobj(chunk_file.stream, f)
                elif chunk_file and hasattr(chunk_file, 'read'):
                    f.write(chunk_file.read())
                else:
                    f.write(request.httprequest.get_data())

            # Comprobar si es el último fragmento
            if chunk_index == total_chunks - 1:
                # Verificar que todos los fragmentos estén presentes
                missing = []
                for i in range(total_chunks):
                    p = os.path.join(staging_session_dir, f"part_{i:05d}")
                    if not os.path.exists(p):
                        missing.append(i)

                if missing:
                    return request.make_json_response({
                        'error': f'Faltan fragmentos para completar el archivo: {missing[:5]}'
                    }, status=400)

                # Ensamblar archivo final
                final_file_path = os.path.join(staging_session_dir, filename)
                with open(final_file_path, 'wb') as outfile:
                    for i in range(total_chunks):
                        part_file = os.path.join(staging_session_dir, f"part_{i:05d}")
                        with open(part_file, 'rb') as infile:
                            shutil.copyfileobj(infile, outfile)
                        try:
                            os.remove(part_file)
                        except Exception:
                            pass

                actual_size = os.path.getsize(final_file_path)
                mimetype, _enc = mimetypes.guess_type(filename)
                if filename.lower().endswith('.webm'):
                    mimetype = 'video/webm'

                # Registrar multimedia en base de datos
                multimedia = request.env['pv.ticket.multimedia'].sudo().create({
                    'ticket_id': ticket.id,
                    'name': filename,
                    'file_size': actual_size,
                    'mimetype': mimetype or 'application/octet-stream',
                    'estado_sync': 'procesando',
                    'staging_path': final_file_path,
                    'usuario_id': request.env.uid,
                })

                # Disparar sincronización hacia Google Drive mediante rclone
                ticket._trigger_drive_sync(multimedia, final_file_path)

                return request.make_json_response({
                    'status': 'completed',
                    'multimedia_id': multimedia.id,
                    'filename': filename,
                    'file_size': multimedia.file_size,
                    'file_size_display': multimedia.file_size_display,
                    'estado_sync': multimedia.estado_sync,
                    'message': 'Archivo ensamblado exitosamente. Iniciando transferencia a Google Drive.',
                })

            return request.make_json_response({
                'status': 'chunk_received',
                'chunk_index': chunk_index,
                'total_chunks': total_chunks,
            })

        except Exception as e:
            _logger.exception("Error al recibir chunk de multimedia: %s", e)
            return request.make_json_response({'error': str(e)}, status=500)

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
