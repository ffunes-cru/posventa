# Part of Crucianelli Posventa Module
from .common import TestPosventaCommon, DUMMY_PDF_BASE64
from odoo.exceptions import UserError, ValidationError
from odoo import fields


class TestTicketWorkflow(TestPosventaCommon):

    def setUp(self):
        super().setUp()
        # Machine in Stock with FRU (Pre-PM)
        self.maquina_stock = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TCK-001',
            'concesionario_id': self.concesionario_a.id,
        })
        self.fru = self.env['pv.certificado'].create({
            'maquina_id': self.maquina_stock.id,
            'tipo': 'fru',
            'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru.pdf',
        })

        # Machine Sold with CPM (Post-PM)
        self.maquina_sold = self.env['pv.maquina'].create({
            'tipo': 'drilor',
            'of': 'OF-TCK-002',
            'concesionario_id': self.concesionario_a.id,
        })
        self.env['pv.certificado'].create({
            'maquina_id': self.maquina_sold.id, 'tipo': 'fru', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'fru.pdf',
        })
        self.env['pv.certificado'].create({
            'maquina_id': self.maquina_sold.id, 'tipo': 'feu', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'feu.pdf',
        })
        self.cpm = self.env['pv.certificado'].create({
            'maquina_id': self.maquina_sold.id, 'tipo': 'cpm', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'cpm.pdf',
        })

    def test_01_pre_pm_ticket_creation_and_lifecycle(self):
        """Concessionaire creates Pre-PM ticket from portal and Staff processes it."""
        # 1. Create ticket in Borrador and Send directly (Portal behavior)
        ticket = self.env['pv.ticket'].with_user(self.user_concesionario_a).create({
            'maquina_id': self.maquina_stock.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'rotura',
            'descripcion': 'Manguera hidráulica cortada en transporte',
            'acciones_realizadas': 'Se verificó en descarga y se fotografió',
        })
        self.assertEqual(ticket.estado, 'borrador')
        self.assertEqual(ticket.certificado_id, self.fru)

        # Concessionaire sends ticket
        ticket.with_user(self.user_concesionario_a)._action_enviar_ticket_direct()
        self.assertEqual(ticket.estado, 'abierto')

        # 2. Concessionaire cannot modify acciones_realizadas once out of borrador
        with self.assertRaises(UserError):
            ticket.with_user(self.user_concesionario_a).write({
                'acciones_realizadas': 'Intento de cambio fuera de borrador',
            })

        # 3. Staff takes ticket
        ticket.with_user(self.user_staff).action_tomar_ticket()
        self.assertEqual(ticket.estado, 'en_proceso')
        self.assertEqual(ticket.responsable_id, self.user_staff)

        # 4. Staff adds measures
        medida = self.env['pv.ticket.medida'].with_user(self.user_staff).create({
            'name': 'Revisión y reemplazo de manguera',
            'ticket_id': ticket.id,
            'tipo': 'medida',
            'comentario': 'Manguera 3/8 R2 1.5m enviada a concesionario',
        })
        self.assertTrue(medida.id)

        # 5. Staff accepts ticket
        ticket.with_user(self.user_staff).action_aceptar_ticket_direct()
        self.assertEqual(ticket.estado, 'aceptado')
        self.assertTrue(ticket.fecha_solucion)

        # 6. Staff closes ticket
        ticket.with_user(self.user_staff).action_cerrar_ticket()
        self.assertEqual(ticket.estado, 'cerrado')
        self.assertTrue(ticket.fecha_cierre)

    def test_02_post_pm_ticket_reject(self):
        """Concessionaire creates Post-PM ticket, associates CPM, and Staff rejects it with reason."""
        ticket = self.env['pv.ticket'].with_user(self.user_concesionario_a).create({
            'maquina_id': self.maquina_sold.id,
            'tipo_ticket': 'post_pm',
            'sistema_id': self.sistema.id,
            'subsistema_id': self.subsistema.id,
            'problema_id': self.problema.id,
            'descripcion': 'Pérdida en acople rápido',
            'ubicacion_actual': 'Lote 14',
            'hectareas': 150.0,
        })
        self.assertEqual(ticket.certificado_id, self.cpm)

        ticket.with_user(self.user_concesionario_a)._action_enviar_ticket_direct()
        ticket.with_user(self.user_staff).action_tomar_ticket()

        # Staff rejects ticket
        ticket.with_user(self.user_staff).action_rechazar_ticket_direct('Falla por mal uso del operador.')
        self.assertEqual(ticket.estado, 'rechazado')
        self.assertIn('mal uso', ticket.motivo_rechazo)
