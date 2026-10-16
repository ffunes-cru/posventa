# Part of Crucianelli Posventa Module
from .common import TestPosventaCommon, DUMMY_PDF_BASE64
from odoo.exceptions import AccessError, UserError
from odoo import fields


class TestSecurityHardening(TestPosventaCommon):
    """Intentos de saltear reglas de negocio llamando métodos/RPC directamente."""

    def setUp(self):
        super().setUp()
        self.state = self.env['res.country.state'].search([], limit=1)
        self.maquina_a = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-HARD-A',
            'concesionario_id': self.concesionario_a.id,
        })
        self.env['pv.certificado'].create({
            'maquina_id': self.maquina_a.id, 'tipo': 'fru', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'fru.pdf',
        })
        self.assertEqual(self.maquina_a.estado, 'stock')

    def _ticket_a(self, **vals):
        values = {
            'maquina_id': self.maquina_a.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'faltante',
            'descripcion': 'Falta manual',
            'multimedia_url': 'https://drive.google.com/test-file',
        }
        values.update(vals)
        return self.env['pv.ticket'].with_user(self.user_concesionario_a).create(values)

    # --- Máquinas ---
    def test_01_otro_concesionario_no_opera_maquina_ajena(self):
        maquina_como_b = self.maquina_a.with_user(self.user_concesionario_b)
        with self.assertRaises(AccessError):
            maquina_como_b.action_solicitar_liberacion('No es mía')
        with self.assertRaises(AccessError):
            maquina_como_b.action_iniciar_transferencia_portal(
                self.concesionario_b.id, self.state.id, 'Córdoba')
        with self.assertRaises(AccessError):
            self.env['pv.transferir.maquina.wizard'].with_user(self.user_concesionario_b).create({
                'maquina_id': self.maquina_a.id,
                'concesionario_destino_id': self.concesionario_b.id,
                'provincia_destino_id': self.state.id,
                'ciudad_destino_id': 'Córdoba',
            }).action_transferir()
        self.assertEqual(self.maquina_a.estado, 'stock')
        self.assertFalse(self.maquina_a.liberacion_solicitada)

    def test_02_solo_admin_libera(self):
        with self.assertRaises(AccessError):
            self.maquina_a.with_user(self.user_concesionario_a).action_liberar_maquina('Reset')
        with self.assertRaises(AccessError):
            self.maquina_a.with_user(self.user_staff).action_liberar_maquina('Reset')

        with self.assertRaises(UserError):
            self.maquina_a.with_user(self.user_concesionario_a).action_solicitar_liberacion('   ')
        self.maquina_a.with_user(self.user_concesionario_a).action_solicitar_liberacion('Canje')
        with self.assertRaises(UserError):
            self.maquina_a.with_user(self.user_concesionario_a).action_solicitar_liberacion('Otra vez')
        # Con una liberación pendiente no se puede trasladar
        with self.assertRaises(UserError):
            self.maquina_a.with_user(self.user_concesionario_a).action_iniciar_transferencia_portal(
                self.concesionario_b.id, self.state.id, 'Córdoba')

        self.maquina_a.with_user(self.user_admin).action_rechazar_liberacion()
        self.assertFalse(self.maquina_a.liberacion_solicitada)
        self.assertEqual(self.maquina_a.estado, 'stock')

        self.maquina_a.with_user(self.user_admin).action_liberar_maquina('Canje de unidad')
        self.assertEqual(self.maquina_a.estado, 'liberada')

    def test_03_transferencia_solo_desde_stock(self):
        self.maquina_a.with_user(self.user_concesionario_a).action_iniciar_transferencia_portal(
            self.concesionario_b.id, self.state.id, 'Córdoba')
        # Ya está pendiente: no se puede volver a proponer
        with self.assertRaises(UserError):
            self.maquina_a.with_user(self.user_concesionario_a).action_iniciar_transferencia_portal(
                self.concesionario_b.id, self.state.id, 'Córdoba')
        # El destino no puede cancelar (solo el origen o admin)
        with self.assertRaises(AccessError):
            self.maquina_a.with_user(self.user_concesionario_b).action_cancelar_transferencia()

    def test_04_contacto_del_destino_acepta_transferencia(self):
        """Un usuario secundario (contacto de la empresa) del destino puede aceptar."""
        contacto_b = self.env['res.partner'].create({
            'name': 'Operador B', 'parent_id': self.partner_conc_b.id,
        })
        user_contacto_b = self.env['res.users'].create({
            'name': 'Operador B', 'login': 'operador_b', 'partner_id': contacto_b.id,
            'group_ids': [(6, 0, [self.group_internal.id, self.group_concesionario.id])],
        })
        self.maquina_a.with_user(self.user_concesionario_a).action_iniciar_transferencia_portal(
            self.concesionario_b.id, self.state.id, 'Córdoba')
        self.assertTrue(self.maquina_a.with_user(user_contacto_b).es_concesionario_destino)
        self.maquina_a.with_user(user_contacto_b).action_aceptar_transferencia()
        self.assertEqual(self.maquina_a.concesionario_id, self.concesionario_b)

    def test_05_usuario_sin_concesionario_no_ve_nada(self):
        """Un usuario concesionario sin empresa asociada no ve datos de nadie."""
        huerfano = self.env['res.users'].create({
            'name': 'Sin Concesionario', 'login': 'huerfano',
            'group_ids': [(6, 0, [self.group_internal.id, self.group_concesionario.id])],
        })
        self._ticket_a()
        self.assertFalse(self.env['pv.maquina'].with_user(huerfano).search([]))
        self.assertFalse(self.env['pv.ticket'].with_user(huerfano).search([]))
        self.assertFalse(self.env['pv.certificado'].with_user(huerfano).search([]))

    # --- Tickets ---
    def test_06_concesionario_no_salta_estados(self):
        with self.assertRaises(UserError):
            self._ticket_a(estado='aceptado')
        with self.assertRaises(UserError):
            self._ticket_a(responsable_id=self.user_staff.id)
        with self.assertRaises(UserError):
            self._ticket_a(solucion_aplicada='Me la autoapruebo')

        ticket = self._ticket_a()
        with self.assertRaises(UserError):
            ticket.with_user(self.user_concesionario_a).write({'estado': 'abierto'})
        with self.assertRaises(UserError):
            ticket.with_user(self.user_concesionario_a).write({'garantia_aceptada': True})

        ticket.with_user(self.user_concesionario_a).action_enviar_ticket()
        with self.assertRaises(AccessError):
            ticket.with_user(self.user_concesionario_a).action_tomar_ticket()
        with self.assertRaises(AccessError):
            ticket.with_user(self.user_concesionario_a).action_back_to_borrador()
        self.assertEqual(ticket.estado, 'abierto')

    def test_07_otro_concesionario_no_envia_ticket_ajeno(self):
        ticket = self._ticket_a()
        with self.assertRaises(AccessError):
            ticket.with_user(self.user_concesionario_b).action_enviar_ticket()

    def test_08_staff_no_modifica_datos_del_concesionario(self):
        ticket = self._ticket_a()
        ticket.with_user(self.user_concesionario_a).action_enviar_ticket()
        ticket.with_user(self.user_staff).action_tomar_ticket()
        with self.assertRaises(UserError):
            ticket.with_user(self.user_staff).write({'descripcion': 'Reescrito por staff'})
        # SAP sí
        ticket.with_user(self.user_staff).write({'sap_numero_aviso': 'AV-1'})
        # Retrocesos de admin
        with self.assertRaises(AccessError):
            ticket.with_user(self.user_staff).action_back_to_aceptado()
        ticket.with_user(self.user_staff).action_back_to_abierto()
        self.assertEqual(ticket.estado, 'abierto')
        self.assertFalse(ticket.responsable_id)

    def test_09_ticket_en_curso_sigue_operable_tras_transferencia(self):
        ticket = self._ticket_a()
        ticket.with_user(self.user_concesionario_a).action_enviar_ticket()
        ticket.with_user(self.user_staff).action_tomar_ticket()

        self.maquina_a.with_user(self.user_concesionario_a).action_iniciar_transferencia_portal(
            self.concesionario_b.id, self.state.id, 'Córdoba')
        ticket.with_user(self.user_staff).action_aceptar_ticket()
        self.maquina_a.with_user(self.user_concesionario_b).action_aceptar_transferencia()
        self.assertEqual(self.maquina_a.estado, 'liberada')

        wizard = self.env['pv.cerrar.ticket.wizard'].with_user(self.user_staff).create({
            'ticket_id': ticket.id,
            'garantia_aceptada': True,
            'solucion_aplicada': 'Se envió el manual.',
        })
        wizard.action_confirmar()
        self.assertEqual(ticket.estado, 'cerrado')
        # Los tickets se mudan con la máquina (por diseño)
        self.assertEqual(ticket.concesionario_id, self.concesionario_b)

    def test_10_aislamiento_multimedia_y_medidas(self):
        ticket = self._ticket_a()
        multimedia = self.env['pv.ticket.multimedia'].create({
            'ticket_id': ticket.id, 'name': 'video.mp4', 'estado_sync': 'disponible',
            'drive_url': 'https://drive.google.com/privado',
        })
        medida = self.env['pv.ticket.medida'].create({'ticket_id': ticket.id, 'name': 'Enviar repuesto'})

        self.assertFalse(self.env['pv.ticket.multimedia'].with_user(self.user_concesionario_b).search([('id', '=', multimedia.id)]))
        self.assertFalse(self.env['pv.ticket.medida'].with_user(self.user_concesionario_b).search([('id', '=', medida.id)]))
        self.assertTrue(self.env['pv.ticket.multimedia'].with_user(self.user_concesionario_a).search([('id', '=', multimedia.id)]))
        with self.assertRaises(AccessError):
            multimedia.with_user(self.user_concesionario_b).drive_url
