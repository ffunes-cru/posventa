# Part of Crucianelli Posventa Module
import io
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from werkzeug.datastructures import FileStorage
from .common import TestPosventaCommon, DUMMY_PDF_BASE64
from odoo.exceptions import UserError
from odoo import fields


class TestMultimediaUpload(TestPosventaCommon):

    def setUp(self):
        super().setUp()
        self.maquina = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-MULTIMEDIA-01',
            'concesionario_id': self.concesionario_a.id,
        })
        self.fru = self.env['pv.certificado'].create({
            'maquina_id': self.maquina.id,
            'tipo': 'fru',
            'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru.pdf',
        })
        self.ticket = self.env['pv.ticket'].with_user(self.user_concesionario_a).create({
            'maquina_id': self.maquina.id,
            'desvio_tipo_id': self.desvio_rotura.id,
            'descripcion': 'Falla en cilindro hidráulico',
        })

    def test_01_multimedia_model_and_computes(self):
        """Valida el cálculo de tamaños legibles, detección de video y contador en ticket."""
        self.assertEqual(self.ticket.multimedia_count, 0)

        # Archivo 1: Video de 850 MB
        video_850mb = self.env['pv.ticket.multimedia'].create({
            'ticket_id': self.ticket.id,
            'name': 'falla_cilindro.mp4',
            'file_size': 850 * 1024 * 1024,
            'mimetype': 'video/mp4',
        })
        self.assertTrue(video_850mb.is_video)
        self.assertIn('850.0 MB', video_850mb.file_size_display)

        # Archivo 2: Video de 1 GB
        video_1gb = self.env['pv.ticket.multimedia'].create({
            'ticket_id': self.ticket.id,
            'name': 'recorrido_campo.mov',
            'file_size': 1024 * 1024 * 1024,
            'mimetype': 'video/quicktime',
        })
        self.assertTrue(video_1gb.is_video)
        self.assertIn('1.0 GB', video_1gb.file_size_display)

        # Archivo 3: Archivo comprimido ZIP (no video)
        log_zip = self.env['pv.ticket.multimedia'].create({
            'ticket_id': self.ticket.id,
            'name': 'telemetria_sensores.zip',
            'file_size': 250 * 1024 * 1024,
            'mimetype': 'application/zip',
        })
        self.assertFalse(log_zip.is_video)
        self.assertIn('250.0 MB', log_zip.file_size_display)

        self.ticket.invalidate_recordset(['multimedia_count'])
        self.assertEqual(self.ticket.multimedia_count, 3)

    def test_02_actions_and_links(self):
        """Valida la apertura de enlaces de Google Drive y excepciones cuando no existen."""
        multimedia = self.env['pv.ticket.multimedia'].create({
            'ticket_id': self.ticket.id,
            'name': 'prueba.mp4',
            'file_size': 1000,
        })
        # Sin URL levanta UserError
        with self.assertRaises(UserError):
            multimedia.action_abrir_drive()

        with self.assertRaises(UserError):
            self.ticket.action_abrir_carpeta_drive()

        # Con URL devuelve acción URL
        multimedia.write({
            'drive_url': 'https://drive.google.com/file/d/12345/view',
            'drive_folder_url': 'https://drive.google.com/drive/folders/abcdef',
        })
        action_file = multimedia.action_abrir_drive()
        self.assertEqual(action_file['type'], 'ir.actions.act_url')
        self.assertEqual(action_file['url'], 'https://drive.google.com/file/d/12345/view')

        action_folder = self.ticket.action_abrir_carpeta_drive()
        self.assertEqual(action_folder['type'], 'ir.actions.act_url')
        self.assertEqual(action_folder['url'], 'https://drive.google.com/drive/folders/abcdef')

    def test_03_rclone_sync_execution_mocked(self):
        """Valida _sync_to_drive simulando llamadas exitosas de rclone."""
        temp_dir = tempfile.mkdtemp(prefix='pv_test_')
        temp_file = os.path.join(temp_dir, 'video_diagnostico.mp4')
        with open(temp_file, 'wb') as f:
            f.write(b"MOCK_LARGE_VIDEO_BYTES_FOR_RCLONE_TEST")

        multimedia = self.env['pv.ticket.multimedia'].create({
            'ticket_id': self.ticket.id,
            'name': 'video_diagnostico.mp4',
            'file_size': os.path.getsize(temp_file),
            'mimetype': 'video/mp4',
        })

        def fake_subprocess_run(cmd, capture_output=True, text=True, timeout=None):
            mock_res = MagicMock()
            mock_res.returncode = 0
            if "link" in cmd:
                if "video_diagnostico.mp4" in cmd[-1]:
                    mock_res.stdout = "https://drive.google.com/file/d/mock_video_id/view\n"
                else:
                    mock_res.stdout = "https://drive.google.com/drive/folders/mock_folder_id\n"
            else:
                # rclone move
                mock_res.stdout = ""
            mock_res.stderr = ""
            return mock_res

        with patch('subprocess.run', side_effect=fake_subprocess_run), \
             patch('odoo.addons.posventa.models.pv_ticket_multimedia.PvTicketMultimedia._is_rclone_configured', return_value=(True, "OK")):
            # La sincronización la ejecuta el cron como sistema, no el concesionario
            multimedia.staging_path = temp_file
            success = multimedia.sudo()._sync_to_drive()
            self.assertTrue(success)

        self.assertEqual(multimedia.estado_sync, 'disponible')
        self.assertEqual(multimedia.drive_url, "https://drive.google.com/file/d/mock_video_id/view")
        self.assertEqual(self.ticket.multimedia_url, "https://drive.google.com/file/d/mock_video_id/view")

        # Comprobar que se creó ir.attachment de tipo URL para el chatter
        self.assertTrue(multimedia.ir_attachment_id)
        self.assertEqual(multimedia.ir_attachment_id.type, 'url')
        self.assertEqual(multimedia.ir_attachment_id.url, "https://drive.google.com/file/d/mock_video_id/view")
        self.assertEqual(multimedia.ir_attachment_id.res_model, 'pv.ticket')
        self.assertEqual(multimedia.ir_attachment_id.res_id, self.ticket.id)

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_04_chunked_streaming_controller_assembly(self):
        """Valida el controlador HTTP de fragmentos: subida en 3 partes, ensamblado y suma de verificación."""
        from odoo.addons.posventa.controllers.multimedia import PosventaMultimediaController
        controller = PosventaMultimediaController()

        original_content = b"CHUNKBINARY_DATA_PART_1_AAAA" + b"CHUNKBINARY_DATA_PART_2_BBBB" + b"CHUNKBINARY_DATA_PART_3_CCCC"
        chunk_1 = b"CHUNKBINARY_DATA_PART_1_AAAA"
        chunk_2 = b"CHUNKBINARY_DATA_PART_2_BBBB"
        chunk_3 = b"CHUNKBINARY_DATA_PART_3_CCCC"

        file_uuid = "test_uuid_12345"
        filename = "prueba_ensamblado.mp4"

        # Mock request context
        mock_request = MagicMock()
        mock_request.env = self.env(user=self.user_concesionario_a)

        # Mock make_json_response
        import json
        from odoo.http import Response

        def fake_make_json_response(data, status=200):
            res = Response(json.dumps(data), status=status, content_type='application/json')
            res.json_data = data
            return res
        mock_request.make_json_response = fake_make_json_response

        with patch('odoo.addons.posventa.controllers.multimedia.request', mock_request), \
             patch('odoo.addons.posventa.models.pv_ticket_multimedia.PvTicketMultimedia._encolar_sync') as mock_trigger, \
             patch('odoo.addons.posventa.models.pv_ticket_multimedia.PvTicketMultimedia._is_rclone_configured', return_value=(True, "OK")), \
             patch('odoo.addons.posventa.models.pv_ticket_multimedia.PvTicketMultimedia._get_chunk_size_bytes', return_value=len(chunk_1)):

            # Enviar Chunk 0
            storage_1 = FileStorage(stream=io.BytesIO(chunk_1), filename='part_0')
            mock_request.httprequest.files.get.return_value = storage_1
            resp1 = controller.upload_chunk(
                ticket_id=self.ticket.id,
                file_uuid=file_uuid,
                filename=filename,
                chunk_index=0,
                total_chunks=3,
                file_size=len(original_content),
            )
            self.assertEqual(resp1.json_data['status'], 'chunk_received')

            # Enviar Chunk 1
            storage_2 = FileStorage(stream=io.BytesIO(chunk_2), filename='part_1')
            mock_request.httprequest.files.get.return_value = storage_2
            resp2 = controller.upload_chunk(
                ticket_id=self.ticket.id,
                file_uuid=file_uuid,
                filename=filename,
                chunk_index=1,
                total_chunks=3,
                file_size=len(original_content),
            )
            self.assertEqual(resp2.json_data['status'], 'chunk_received')

            # Enviar Chunk 2 (Final)
            storage_3 = FileStorage(stream=io.BytesIO(chunk_3), filename='part_2')
            mock_request.httprequest.files.get.return_value = storage_3
            resp3 = controller.upload_chunk(
                ticket_id=self.ticket.id,
                file_uuid=file_uuid,
                filename=filename,
                chunk_index=2,
                total_chunks=3,
                file_size=len(original_content),
            )
            self.assertEqual(resp3.json_data['status'], 'completed')
            multimedia_id = resp3.json_data['multimedia_id']

            # Validar que se creó el registro
            multimedia = self.env['pv.ticket.multimedia'].browse(multimedia_id)
            self.assertTrue(multimedia.exists())
            self.assertEqual(multimedia.file_size, len(original_content))
            self.assertTrue(mock_trigger.called)

    def test_05_backend_multimedia_wizard_and_retry(self):
        """Valida el asistente backend pv.ticket.multimedia.wizard y el reintento de sincronización."""
        # 1. Apertura de wizard desde ticket
        action = self.ticket.action_adjuntar_multimedia()
        self.assertEqual(action['res_model'], 'pv.ticket.multimedia.wizard')
        self.assertEqual(action['target'], 'new')

        # 2. Carga vía enlace de Google Drive
        wizard_drive = self.env['pv.ticket.multimedia.wizard'].create({
            'ticket_id': self.ticket.id,
            'tipo_carga': 'enlace_drive',
            'name': 'Carpeta Externa Fotos',
            'drive_url': 'https://drive.google.com/drive/folders/test12345',
        })
        wizard_drive.action_adjuntar()
        
        multimedia_drive = self.env['pv.ticket.multimedia'].search([
            ('ticket_id', '=', self.ticket.id),
            ('name', '=', 'Carpeta Externa Fotos'),
        ], limit=1)
        self.assertTrue(multimedia_drive.exists())
        self.assertEqual(multimedia_drive.estado_sync, 'disponible')
        self.assertEqual(multimedia_drive.drive_url, 'https://drive.google.com/drive/folders/test12345')

        # 3. Confirmar sin haber subido el archivo (el widget no terminó) -> error
        wizard_file = self.env['pv.ticket.multimedia.wizard'].create({
            'ticket_id': self.ticket.id, 'tipo_carga': 'archivo', 'name': 'Prueba de campo',
        })
        with self.assertRaises(UserError):
            wizard_file.action_adjuntar()

        # 3b. Archivo ya subido por el widget: el título lo renombra conservando la extensión
        staging_dir = tempfile.mkdtemp(prefix='pv_test_')
        staging_file = os.path.join(staging_dir, 'prueba_wizard.mp4')
        with open(staging_file, 'wb') as f:
            f.write(b"TEST_VIDEO_BYTES_WIZARD")
        multimedia_file = self.env['pv.ticket.multimedia'].create({
            'ticket_id': self.ticket.id, 'name': 'prueba_wizard.mp4',
            'estado_sync': 'procesando', 'staging_path': staging_file,
        })
        wizard_file.uploaded_multimedia_id = multimedia_file
        wizard_file.action_adjuntar()
        self.assertEqual(multimedia_file.name, 'Prueba de campo.mp4')

        # 4. Simulación de reintento de sincronización cuando está en error
        multimedia_file.write({
            'estado_sync': 'error',
            'error_message': 'Conexión interrumpida con rclone',
        })
        multimedia_file.write({'sync_intentos': 5})
        with patch('odoo.addons.base.models.ir_cron.IrCron._trigger') as mock_cron_trigger:
            multimedia_file.action_reintentar_sync()
            self.assertEqual(multimedia_file.estado_sync, 'procesando')
            self.assertFalse(multimedia_file.error_message)
            # El reintento manual reinicia el contador y encola en el cron (sin threads)
            self.assertEqual(multimedia_file.sync_intentos, 0)
            self.assertTrue(mock_cron_trigger.called)


    def test_06_error_sync_con_backoff_y_aviso_unico(self):
        """Los errores programan reintentos con backoff y avisan en el chatter solo en el primer y último fallo."""
        multimedia = self.env['pv.ticket.multimedia'].create({
            'ticket_id': self.ticket.id, 'name': 'falla.mp4', 'estado_sync': 'procesando',
        })
        ticket = self.ticket.sudo()  # el cron corre como sistema; las notas internas no las ve el concesionario
        mensajes_iniciales = len(ticket.message_ids)
        with patch('odoo.addons.posventa.models.pv_ticket_multimedia.PvTicketMultimedia._is_rclone_configured', return_value=(False, "rclone no configurado")):
            for intento in range(1, 6):
                multimedia.sync_intentos = intento
                self.assertFalse(multimedia.sudo()._sync_to_drive())
                self.assertEqual(multimedia.estado_sync, 'error')
                if intento < 5:
                    self.assertTrue(multimedia.sync_proximo_intento)
        self.assertFalse(multimedia.sync_proximo_intento)  # agotado: sin reintento automático
        ticket.invalidate_recordset(['message_ids'])
        self.assertEqual(len(ticket.message_ids) - mensajes_iniciales, 2)

    def test_07_controller_rechaza_archivo_excedido(self):
        """El tamaño máximo se valida en el servidor."""
        from odoo.addons.posventa.controllers.multimedia import PosventaMultimediaController
        import json
        from odoo.http import Response
        mock_request = MagicMock()
        mock_request.env = self.env(user=self.user_concesionario_a)

        def fake_make_json_response(data, status=200):
            res = Response(json.dumps(data), status=status, content_type='application/json')
            res.json_data = data
            return res
        mock_request.make_json_response = fake_make_json_response
        with patch('odoo.addons.posventa.controllers.multimedia.request', mock_request), \
             patch('odoo.addons.posventa.models.pv_ticket_multimedia.PvTicketMultimedia._get_max_upload_bytes', return_value=100):
            resp = PosventaMultimediaController().upload_chunk(
                ticket_id=self.ticket.id, file_uuid='uuid_grande', filename='grande.mp4',
                chunk_index=0, total_chunks=1, file_size=101,
            )
        self.assertEqual(resp.status_code, 413)
