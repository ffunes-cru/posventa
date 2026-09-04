# Part of Crucianelli Posventa Module
from .common import TestPosventaCommon, DUMMY_PDF_BASE64
from odoo.exceptions import UserError
from odoo import fields


class TestTransferenciaMaquina(TestPosventaCommon):

    def setUp(self):
        super().setUp()
        self.state_cba = self.env['res.country.state'].search([('country_id.code', '=', 'AR'), ('code', '=', 'X')], limit=1)
        if not self.state_cba:
            self.state_cba = self.env['res.country.state'].search([], limit=1)
        self.maquina = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TRANSF-001',
            'concesionario_id': self.concesionario_a.id,
            'ciudad': 'Rosario',
        })
        # Load FRU so it is in STOCK
        self.fru = self.env['pv.certificado'].create({
            'maquina_id': self.maquina.id,
            'tipo': 'fru',
            'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru.pdf',
        })
        self.assertEqual(self.maquina.estado, 'stock')

    def test_01_propose_and_cancel_transfer(self):
        """Concesionario A proposes transfer and cancels it."""
        self.maquina.with_user(self.user_concesionario_a).action_iniciar_transferencia_portal(
            concesionario_destino_id=self.concesionario_b.id,
            provincia_destino_id=self.state_cba.id,
            ciudad_destino='Marcos Juárez'
        )
        self.assertEqual(self.maquina.estado, 'pendiente')
        self.assertEqual(self.maquina.concesionario_destino_id, self.concesionario_b)

        # Cancel transfer
        self.maquina.with_user(self.user_concesionario_a).action_cancelar_transferencia()
        self.assertEqual(self.maquina.estado, 'stock')
        self.assertFalse(self.maquina.concesionario_destino_id)

    def test_02_accept_transfer_workflow(self):
        """Concesionario A proposes transfer and Concesionario B accepts."""
        self.maquina.with_user(self.user_concesionario_a).action_iniciar_transferencia_portal(
            concesionario_destino_id=self.concesionario_b.id,
            provincia_destino_id=self.state_cba.id,
            ciudad_destino='Marcos Juárez'
        )

        # Unauthorized user (Concesionario A or random user) cannot accept
        with self.assertRaises(UserError):
            self.maquina.with_user(self.user_concesionario_a).action_aceptar_transferencia()

        # Destination Concesionario B accepts
        self.maquina.with_user(self.user_concesionario_b).action_aceptar_transferencia()

        self.assertEqual(self.maquina.concesionario_id, self.concesionario_b)
        self.assertEqual(self.maquina.estado, 'liberada')
        self.assertEqual(self.fru.estado_certificado, 'archivado_traslado')
        self.assertEqual(self.fru.concesionario_id, self.concesionario_a)
        self.assertFalse(self.maquina.tiene_fru)

        # Concesionario B can see the archived certificate issued by A on their machine
        certs_b = self.env['pv.certificado'].with_user(self.user_concesionario_b).search([('maquina_id', '=', self.maquina.id)])
        self.assertIn(self.fru, certs_b)

        # Concesionario B can now upload a new FRU from scratch
        new_fru_b = self.env['pv.certificado'].with_user(self.user_concesionario_b).create({
            'maquina_id': self.maquina.id,
            'tipo': 'fru',
            'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru_b.pdf',
        })
        self.assertEqual(new_fru_b.estado_certificado, 'vigente')
        self.assertEqual(new_fru_b.concesionario_id, self.concesionario_b)
        self.assertEqual(self.maquina.estado, 'stock')
        self.assertTrue(self.maquina.tiene_fru)

    def test_03_reject_transfer_workflow(self):
        """Concesionario B rejects transfer; machine returns to A in stock."""
        self.maquina.with_user(self.user_concesionario_a).action_iniciar_transferencia_portal(
            concesionario_destino_id=self.concesionario_b.id,
            provincia_destino_id=self.state_cba.id,
            ciudad_destino='Marcos Juárez'
        )

        self.maquina.with_user(self.user_concesionario_b).action_rechazar_transferencia()
        self.assertEqual(self.maquina.concesionario_id, self.concesionario_a)
        self.assertEqual(self.maquina.estado, 'stock')
        self.assertFalse(self.maquina.concesionario_destino_id)

    def test_04_transfer_archives_previous_certificates(self):
        """Previous certificates are marked as 'archivado_traslado', machine returns to liberada, fecha_liberacion resets."""
        self.fru.sudo().write({'estado_certificado': 'vencido'})

        self.maquina.with_user(self.user_concesionario_a).action_iniciar_transferencia_portal(
            concesionario_destino_id=self.concesionario_b.id,
            provincia_destino_id=self.state_cba.id,
            ciudad_destino='Marcos Juárez'
        )

        self.maquina.with_user(self.user_concesionario_b).action_aceptar_transferencia()

        self.assertEqual(self.maquina.concesionario_id, self.concesionario_b)
        self.assertEqual(self.fru.estado_certificado, 'archivado_traslado')
        self.assertEqual(self.maquina.estado, 'liberada')
        self.assertEqual(self.maquina.fecha_liberacion, fields.Date.today())
