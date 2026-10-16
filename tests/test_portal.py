# Part of Crucianelli Posventa Module
from odoo import fields, http
from odoo.tests import HttpCase, tagged

from .common import TestPosventaCommon, DUMMY_PDF_BASE64


@tagged('post_install', '-at_install')
class TestPortalPosventa(TestPosventaCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.maquina_a = cls.env['pv.maquina'].create({
            'tipo': 'plantor', 'of': 'OF-PORTAL-A', 'concesionario_id': cls.concesionario_a.id,
        })
        cls.env['pv.certificado'].create({
            'maquina_id': cls.maquina_a.id, 'tipo': 'fru', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'fru.pdf',
        })
        cls.maquina_b = cls.env['pv.maquina'].create({
            'tipo': 'drilor', 'of': 'OF-PORTAL-B', 'concesionario_id': cls.concesionario_b.id,
        })
        cls.env['pv.certificado'].create({
            'maquina_id': cls.maquina_b.id, 'tipo': 'fru', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'fru.pdf',
        })
        cls.ticket_a = cls.env['pv.ticket'].with_user(cls.user_concesionario_a).create({
            'maquina_id': cls.maquina_a.id, 'desvio_tipo_id': cls.desvio_faltante.id, 'descripcion': 'Falta manual A',
            'multimedia_url': 'https://drive.google.com/test-a',
        })
        cls.ticket_b = cls.env['pv.ticket'].with_user(cls.user_concesionario_b).create({
            'maquina_id': cls.maquina_b.id, 'desvio_tipo_id': cls.desvio_faltante.id, 'descripcion': 'Falta manual B',
        })

    def _post(self, url, **data):
        return self.url_open(url, data=dict(data, csrf_token=http.Request.csrf_token(self)))

    def test_01_paginas_y_aislamiento(self):
        self.authenticate('concesionario_a', 'concesionario_a')
        home = self.url_open('/my/posventa')
        self.assertEqual(home.status_code, 200)
        self.assertIn('Portal de Posventa', home.text)
        self.assertIn('/my/posventa', self.url_open('/my').text)

        maquinas = self.url_open('/my/posventa/maquinas').text
        self.assertIn('OF-PORTAL-A', maquinas)
        self.assertNotIn('OF-PORTAL-B', maquinas)
        self.assertIn('OF-PORTAL-A', self.url_open(f'/my/posventa/maquina/{self.maquina_a.id}').text)
        self.assertIn(self.ticket_a.name, self.url_open('/my/posventa/tickets').text)
        self.assertIn('Falta manual A', self.url_open(f'/my/posventa/ticket/{self.ticket_a.id}').text)
        self.assertEqual(self.url_open('/my/posventa/certificados').status_code, 200)

        # Registros de otro concesionario: vuelve al listado sin mostrar datos
        res = self.url_open(f'/my/posventa/maquina/{self.maquina_b.id}')
        self.assertTrue(res.url.endswith('/my/posventa/maquinas'))
        self.assertNotIn('OF-PORTAL-B', res.text)
        res = self.url_open(f'/my/posventa/ticket/{self.ticket_b.id}')
        self.assertTrue(res.url.endswith('/my/posventa/tickets'))
        self.assertNotIn('Falta manual B', res.text)

    def test_02_acciones_via_formularios(self):
        self.authenticate('concesionario_a', 'concesionario_a')
        res = self._post(f'/my/posventa/maquina/{self.maquina_a.id}/solicitar_liberacion', motivo='Canje')
        self.assertTrue(self.maquina_a.liberacion_solicitada)
        self.assertIn('Solicitud de liberación enviada', res.text)

        # Error de negocio: se muestra el mensaje y no se modifica nada
        res = self._post(f'/my/posventa/maquina/{self.maquina_a.id}/solicitar_liberacion', motivo='Otra vez')
        self.assertIn('Ya existe una solicitud de liberación pendiente', res.text)

        res = self._post(f'/my/posventa/ticket/{self.ticket_a.id}/enviar')
        self.assertEqual(self.ticket_a.estado, 'abierto')
        self.assertIn('Ticket enviado a revisión técnica', res.text)

    def test_03_no_opera_registros_ajenos(self):
        self.authenticate('concesionario_b', 'concesionario_b')
        self._post(f'/my/posventa/maquina/{self.maquina_a.id}/solicitar_liberacion', motivo='No es mía')
        self._post(f'/my/posventa/maquina/{self.maquina_a.id}/trasladar',
                   concesionario_destino_id=self.concesionario_b.id,
                   provincia_destino_id=self.env['res.country.state'].search([], limit=1).id,
                   ciudad_destino='Córdoba')
        self._post(f'/my/posventa/ticket/{self.ticket_a.id}/enviar')
        self.assertFalse(self.maquina_a.liberacion_solicitada)
        self.assertEqual(self.maquina_a.estado, 'stock')
        self.assertEqual(self.ticket_a.estado, 'borrador')

    def test_04_usuario_sin_concesionario(self):
        self.authenticate('staff_pv', 'staff_pv')
        self.assertIn('no está asociado a un concesionario', self.url_open('/my/posventa').text)

    def test_05_tour_nuevo_ticket(self):
        """El wizard OWL funciona en el frontend: crea y envía un reclamo y redirige a su detalle."""
        self.start_tour(f'/my/posventa/maquina/{self.maquina_a.id}/ticket/nuevo',
                        'posventa_portal_nuevo_ticket', login='concesionario_a')
        nuevo = self.env['pv.ticket'].search([('descripcion', 'like', 'tour portal')])
        self.assertEqual(len(nuevo), 1)
        self.assertEqual(nuevo.estado, 'abierto')
        self.assertEqual(nuevo.concesionario_id, self.concesionario_a)

    def test_06_tour_cargar_certificado(self):
        maquina = self.env['pv.maquina'].create({
            'tipo': 'gringa', 'of': 'OF-PORTAL-CERT', 'concesionario_id': self.concesionario_a.id,
        })
        self.start_tour(f'/my/posventa/maquina/{maquina.id}/certificado/nuevo',
                        'posventa_portal_cargar_certificado', login='concesionario_a')
        self.assertEqual(maquina.estado, 'stock')
        self.assertEqual(maquina.certificado_ids.archivo_nombre, 'fru_tour.pdf')
        self.assertEqual(maquina.certificado_ids.concesionario_id, self.concesionario_a)

    def test_07_tour_adjuntar_foto(self):
        self.start_tour(f'/my/posventa/ticket/{self.ticket_a.id}', 'posventa_portal_adjuntar_foto',
                        login='concesionario_a')
        adjunto = self.env['ir.attachment'].search([
            ('res_model', '=', 'pv.ticket'), ('res_id', '=', self.ticket_a.id), ('name', '=', 'foto_tour.png')])
        self.assertTrue(adjunto)

    def test_08_mails_al_concesionario_linkean_al_portal(self):
        template = self.env.ref('posventa.mail_template_ticket_rechazado')
        body = template._render_field('body_html', self.ticket_a.ids)[self.ticket_a.id]
        self.assertIn(f'/my/posventa/ticket/{self.ticket_a.id}', body)
        staff_body = self.env.ref('posventa.mail_template_ticket_creado')._render_field(
            'body_html', self.ticket_a.ids)[self.ticket_a.id]
        self.assertIn(f'/odoo/pv.ticket/{self.ticket_a.id}', staff_body)
