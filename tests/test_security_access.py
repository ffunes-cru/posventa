# Part of Crucianelli Posventa Module
from .common import TestPosventaCommon, DUMMY_PDF_BASE64
from odoo import fields


class TestSecurityAccess(TestPosventaCommon):

    def setUp(self):
        super().setUp()
        # Machine for A
        self.maquina_a = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-SEC-A',
            'concesionario_id': self.concesionario_a.id,
        })
        self.fru_a = self.env['pv.certificado'].create({
            'maquina_id': self.maquina_a.id, 'tipo': 'fru', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'fru.pdf',
        })
        self.ticket_a = self.env['pv.ticket'].create({
            'maquina_id': self.maquina_a.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'faltante',
            'descripcion': 'Falta manual',
        })

        # Machine for B
        self.maquina_b = self.env['pv.maquina'].create({
            'tipo': 'drilor',
            'of': 'OF-SEC-B',
            'concesionario_id': self.concesionario_b.id,
        })
        self.fru_b = self.env['pv.certificado'].create({
            'maquina_id': self.maquina_b.id, 'tipo': 'fru', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'fru.pdf',
        })
        self.ticket_b = self.env['pv.ticket'].create({
            'maquina_id': self.maquina_b.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'faltante',
            'descripcion': 'Falta calco',
        })

    def test_01_concesionario_isolation(self):
        """Concessionaire A can only read their own machines and tickets."""
        maquinas_a = self.env['pv.maquina'].with_user(self.user_concesionario_a).search([])
        self.assertIn(self.maquina_a, maquinas_a)
        self.assertNotIn(self.maquina_b, maquinas_a)

        tickets_a = self.env['pv.ticket'].with_user(self.user_concesionario_a).search([])
        self.assertIn(self.ticket_a, tickets_a)
        self.assertNotIn(self.ticket_b, tickets_a)

    def test_02_staff_access(self):
        """Staff sees all machines and non-draft tickets."""
        # When ticket is draft, staff does not see it
        tickets_staff = self.env['pv.ticket'].with_user(self.user_staff).search([])
        self.assertNotIn(self.ticket_a, tickets_staff)

        # When ticket is submitted (abierto), staff sees it
        self.ticket_a._action_enviar_ticket_direct()
        tickets_staff_after = self.env['pv.ticket'].with_user(self.user_staff).search([])
        self.assertIn(self.ticket_a, tickets_staff_after)

    def test_03_admin_unrestricted_access(self):
        """Admin sees everything including draft tickets and all machines."""
        maquinas_admin = self.env['pv.maquina'].with_user(self.user_admin).search([])
        self.assertIn(self.maquina_a, maquinas_admin)
        self.assertIn(self.maquina_b, maquinas_admin)

        tickets_admin = self.env['pv.ticket'].with_user(self.user_admin).search([])
        self.assertIn(self.ticket_a, tickets_admin)
        self.assertIn(self.ticket_b, tickets_admin)
