# Part of Crucianelli Posventa Module
"""Subida por fragmentos (controllers/multimedia.py): cada camino de error, los controles de acceso, el modo
Odoo y la consulta de estado. Además, los valores que trae el asistente de cierre desde el reclamo."""
import io
import json
import os
import re
import shutil
import unittest
import uuid
from unittest.mock import MagicMock, patch

from werkzeug.datastructures import FileStorage

from odoo import fields
from odoo.http import Response

from odoo.addons.posventa.controllers.multimedia import PosventaMultimediaController, _sanitize_filename
from odoo.addons.posventa.models.pv_ticket_multimedia import get_staging_root

from .common import DUMMY_PDF_BASE64, TestPosventaCommon

MODELO = 'odoo.addons.posventa.models.pv_ticket_multimedia.PvTicketMultimedia'


class TestSubidaFragmentos(TestPosventaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.maquina = cls.env['pv.maquina'].create({
            'tipo': 'plantor', 'of': 'OF-SUBIDA-01', 'concesionario_id': cls.concesionario_a.id,
        })
        cls.env['pv.certificado'].create({
            'maquina_id': cls.maquina.id, 'tipo': 'fru', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'fru.pdf',
        })
        cls.ticket = cls.env['pv.ticket'].with_user(cls.user_concesionario_a).create({
            'maquina_id': cls.maquina.id, 'desvio_tipo_id': cls.desvio_rotura.id, 'descripcion': 'Falla',
        })

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].set_param('posventa.storage_mode', 'drive')
        # El cron de Drive no corre en los tests: la subida solo lo encola
        patcher = patch('odoo.addons.base.models.ir_cron.IrCron._trigger')
        patcher.start()
        self.addCleanup(patcher.stop)

    # --- Ayudas ---

    def _subir(self, usuario=None, contenido=b'VIDEO', archivo='presente', **params):
        """Llama al controlador como `usuario` (por defecto, el concesionario A) con un fragmento.

        @param contenido Bytes del fragmento.
        @param archivo 'presente' (multipart con stream), 'solo_read' (objeto sin stream) o 'ausente'
               (sin multipart: el fragmento viaja en el cuerpo crudo).
        @param params Parámetros del formulario; los que falten se completan para un archivo de un fragmento.
        @return Response con `json_data`.
        """
        file_uuid = params.setdefault('file_uuid', uuid.uuid4().hex)
        self._limpiar_staging(file_uuid)
        params = {'ticket_id': self.ticket.id, 'filename': 'video.mp4', 'chunk_index': 0, 'total_chunks': 1,
                  'file_size': len(contenido), **params}

        request = MagicMock()
        request.env = self.env(user=usuario or self.user_concesionario_a)

        def make_json_response(data, status=200):
            respuesta = Response(json.dumps(data), status=status, content_type='application/json')
            respuesta.json_data = data
            return respuesta
        request.make_json_response = make_json_response
        if archivo == 'presente':
            request.httprequest.files.get.return_value = FileStorage(stream=io.BytesIO(contenido), filename='p')
        elif archivo == 'solo_read':
            request.httprequest.files.get.return_value = MagicMock(spec=['read'], read=lambda: contenido)
        else:
            request.httprequest.files.get.return_value = None
            request.httprequest.get_data.return_value = contenido
        with patch('odoo.addons.posventa.controllers.multimedia.request', request):
            return PosventaMultimediaController().upload_chunk(**params)

    def _limpiar_staging(self, file_uuid):
        """Borra al final la carpeta de staging de la subida, saneando el uuid como el controlador."""
        carpeta = re.sub(r'[^a-zA-Z0-9_\-]', '', file_uuid)
        if carpeta:  # un uuid vacío apuntaría a la raíz de staging
            self.addCleanup(shutil.rmtree, os.path.join(get_staging_root(), carpeta), True)

    def _assertError(self, respuesta, status, texto):
        self.assertEqual(respuesta.status_code, status, respuesta.json_data)
        self.assertIn(texto, respuesta.json_data['error'])

    # --- Parámetros ---

    def test_parametros_no_numericos(self):
        self._assertError(self._subir(chunk_index='uno'), 400, 'Parámetros de subida inválidos.')

    def test_parametros_fuera_de_rango(self):
        for caso in ({'ticket_id': 0}, {'file_uuid': '../..'}, {'total_chunks': 0},
                     {'chunk_index': -1}, {'chunk_index': 1, 'total_chunks': 1}):
            with self.subTest(**caso):
                self._assertError(self._subir(**caso), 400, 'se requiere un ticket válido')

    def test_cantidad_de_fragmentos_no_coincide_con_el_tamano(self):
        with patch(f'{MODELO}._get_chunk_size_bytes', return_value=4):
            # 10 bytes en fragmentos de 4 son 3 fragmentos, no 2
            respuesta = self._subir(contenido=b'1234', file_size=10, total_chunks=2)
        self._assertError(respuesta, 400, 'no coincide con el tamaño')

    # --- Acceso ---

    def test_ticket_inexistente(self):
        self._assertError(self._subir(ticket_id=999999), 404, 'no existe o no tiene acceso')

    def test_ticket_de_otro_concesionario(self):
        """Las reglas de registro ocultan el reclamo ajeno: para el concesionario B no existe."""
        respuesta = self._subir(usuario=self.user_concesionario_b)
        self._assertError(respuesta, 404, 'no existe o no tiene acceso')
        self.assertFalse(self.env['pv.ticket.multimedia'].search([('ticket_id', '=', self.ticket.id)]))

    def test_usuario_que_no_pertenece_al_concesionario(self):
        """Segundo control, por si una regla de registro dejara pasar a alguien que no es del concesionario."""
        with patch('odoo.addons.posventa.models.pv_concesionario.PvConcesionario._is_member', return_value=False):
            self._assertError(self._subir(), 403, 'Acceso denegado')

    def test_staff_sube_a_reclamos_enviados(self):
        """El Staff no es miembro del concesionario y sube igual, pero no ve los borradores."""
        self._assertError(self._subir(usuario=self.user_staff), 404, 'no existe o no tiene acceso')
        enviado = self.env['pv.ticket'].with_user(self.user_concesionario_a).create({
            'maquina_id': self.maquina.id, 'desvio_tipo_id': self.desvio_rotura.id, 'descripcion': 'Enviado',
            'multimedia_url': 'https://drive.google.com/enviado',
        })
        enviado.with_user(self.user_concesionario_a).action_enviar_ticket()
        respuesta = self._subir(usuario=self.user_staff, ticket_id=enviado.id)
        self.assertEqual(respuesta.json_data.get('status'), 'completed', respuesta.json_data)

    # --- Tamaños y fragmentos ---

    def test_fragmento_mas_grande_que_lo_configurado(self):
        file_uuid = uuid.uuid4().hex
        with patch(f'{MODELO}._get_chunk_size_bytes', return_value=4):
            respuesta = self._subir(contenido=b'123456', file_size=8, total_chunks=2, file_uuid=file_uuid)
        self._assertError(respuesta, 413, 'supera el tamaño configurado')
        self.assertFalse(os.path.exists(os.path.join(get_staging_root(), file_uuid)), 'no deja basura en staging')

    def test_fragmentos_intermedios_y_faltantes(self):
        """Un fragmento intermedio se guarda y espera; si llega el último y falta alguno, se rechaza."""
        file_uuid = uuid.uuid4().hex
        with patch(f'{MODELO}._get_chunk_size_bytes', return_value=4):
            primero = self._subir(contenido=b'1234', file_size=12, total_chunks=3, chunk_index=0, file_uuid=file_uuid)
            self.assertEqual(primero.json_data, {'status': 'chunk_received', 'chunk_index': 0, 'total_chunks': 3})
            ultimo = self._subir(contenido=b'9012', file_size=12, total_chunks=3, chunk_index=2, file_uuid=file_uuid)
        self._assertError(ultimo, 400, 'Faltan fragmentos para completar el archivo: [1]')

    def test_archivo_final_de_otro_tamano(self):
        file_uuid = uuid.uuid4().hex
        respuesta = self._subir(contenido=b'12345', file_size=10, file_uuid=file_uuid)
        self._assertError(respuesta, 400, 'incompleto o dañado')
        self.assertFalse(os.path.exists(os.path.join(get_staging_root(), file_uuid)), 'no deja basura en staging')

    # --- Cómo llega el fragmento ---

    def test_fragmento_sin_stream_o_en_el_cuerpo(self):
        for archivo in ('solo_read', 'ausente'):
            with self.subTest(archivo=archivo):
                respuesta = self._subir(archivo=archivo, contenido=b'CUERPO')
                self.assertEqual(respuesta.json_data['status'], 'completed')
                self.assertEqual(respuesta.json_data['file_size'], 6)

    def test_nombre_y_uuid_no_salen_de_staging(self):
        """Un nombre o un uuid con rutas no escapan de la carpeta de staging."""
        self.assertEqual(_sanitize_filename('../../etc/passwd'), 'passwd')
        self.assertEqual(_sanitize_filename('../'), 'archivo_adjunto')
        respuesta = self._subir(filename='../../../tmp/fuera.mp4', file_uuid='abc/../../def')
        multimedia = self.env['pv.ticket.multimedia'].browse(respuesta.json_data['multimedia_id'])
        self.assertEqual(multimedia.name, 'fuera.mp4')
        self.assertEqual(multimedia.staging_path, os.path.join(get_staging_root(), 'abcdef', 'fuera.mp4'))

    def test_webm_es_video(self):
        respuesta = self._subir(filename='grabacion.webm')
        multimedia = self.env['pv.ticket.multimedia'].browse(respuesta.json_data['multimedia_id'])
        self.assertEqual(multimedia.mimetype, 'video/webm')
        self.assertTrue(multimedia.is_video)

    # --- Destino ---

    def test_modo_odoo_guarda_un_adjunto(self):
        self.env['ir.config_parameter'].set_param('posventa.storage_mode', 'odoo')
        file_uuid = uuid.uuid4().hex
        respuesta = self._subir(contenido=b'FOTO', filename='foto.jpg', file_uuid=file_uuid)
        self.assertEqual(respuesta.json_data.get('storage_mode'), 'odoo', respuesta.json_data)
        adjunto = self.env['ir.attachment'].browse(respuesta.json_data['attachment_id'])
        self.assertEqual((adjunto.res_model, adjunto.res_id, adjunto.raw), ('pv.ticket', self.ticket.id, b'FOTO'))
        self.assertTrue(self._notas('foto.jpg'), 'deja una nota en el chatter')
        self.assertFalse(self.env['pv.ticket.multimedia'].search([('ticket_id', '=', self.ticket.id)]))
        self.assertFalse(os.path.exists(os.path.join(get_staging_root(), file_uuid)))

    @unittest.skip("Bug ffunes-cru/posventa#8: message_post descarta el adjunto si sube un usuario portal")
    def test_modo_odoo_la_nota_lleva_el_archivo(self):
        self.env['ir.config_parameter'].set_param('posventa.storage_mode', 'odoo')
        respuesta = self._subir(contenido=b'FOTO', filename='foto.jpg')
        adjunto = self.env['ir.attachment'].browse(respuesta.json_data['attachment_id'])
        self.assertEqual(self._notas('foto.jpg').attachment_ids, adjunto)

    def _notas(self, texto):
        """Mensajes del chatter del reclamo que mencionan `texto`."""
        return self.env['mail.message'].search([
            ('model', '=', 'pv.ticket'), ('res_id', '=', self.ticket.id), ('body', 'ilike', texto)])

    def test_error_inesperado_responde_500(self):
        with patch('odoo.addons.posventa.controllers.multimedia.shutil.copyfileobj', side_effect=OSError('Disco lleno')):
            self._assertError(self._subir(), 500, 'Disco lleno')

    # --- Consulta de estado ---

    def _estado(self, usuario, multimedia_id):
        request = MagicMock()
        request.env = self.env(user=usuario)
        with patch('odoo.addons.posventa.controllers.multimedia.request', request):
            return PosventaMultimediaController().upload_status(multimedia_id)

    def test_estado_de_la_subida(self):
        multimedia = self.env['pv.ticket.multimedia'].create({
            'ticket_id': self.ticket.id, 'name': 'video.mp4', 'estado_sync': 'procesando',
        })
        estado = self._estado(self.user_concesionario_a, multimedia.id)
        self.assertEqual((estado['id'], estado['estado_sync']), (multimedia.id, 'procesando'))
        self.assertEqual(self._estado(self.user_concesionario_b, multimedia.id), {'error': 'Archivo no encontrado.'})
        self.assertEqual(self._estado(self.user_concesionario_a, 999999), {'error': 'Archivo no encontrado.'})

    # --- Asistente de cierre ---

    def test_cierre_trae_los_datos_del_reclamo(self):
        motivo = self.env.ref('posventa.rechazo_mal_uso')
        self.ticket.with_user(self.user_admin).write({
            'sap_numero_orden': 'OS-123', 'tipo_garantia': 'comercial',
            'garantia_rechazo_tag_ids': [(6, 0, motivo.ids)], 'solucion_aplicada': 'Cambio de válvula',
        })
        Wizard = self.env['pv.cerrar.ticket.wizard'].with_user(self.user_staff).with_context(active_id=self.ticket.id)
        valores = Wizard.default_get(['ticket_id', 'sap_numero_orden', 'tipo_garantia',
                                      'garantia_rechazo_tag_ids', 'solucion_aplicada'])
        self.assertEqual(valores['sap_numero_orden'], 'OS-123')
        self.assertEqual(valores['tipo_garantia'], 'comercial')
        self.assertEqual(valores['garantia_rechazo_tag_ids'], [(6, 0, motivo.ids)])
        self.assertEqual(valores['solucion_aplicada'], 'Cambio de válvula')
        # Sin reclamo en el contexto no inventa nada
        vacio = self.env['pv.cerrar.ticket.wizard'].with_user(self.user_staff).default_get(['sap_numero_orden'])
        self.assertFalse(vacio.get('sap_numero_orden'))
