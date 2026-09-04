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

    def test_04_menu_visibility_restrictions(self):
        """Concesionario only sees Portal and Tickets, not Maquinas, Certificados or Medidas."""
        menus_conc = self.env['ir.ui.menu'].with_user(self.user_concesionario_a).load_menus(False)
        m_portal = self.env.ref('posventa.menu_pv_portal_concesionario').id
        m_ticket = self.env.ref('posventa.menu_pv_ticket').id
        m_maquina = self.env.ref('posventa.menu_pv_maquina').id
        m_certificado = self.env.ref('posventa.menu_pv_certificado').id
        m_medida = self.env.ref('posventa.menu_pv_ticket_medida').id
        m_dash = self.env.ref('posventa.menu_pv_dashboard').id
        m_config = self.env.ref('posventa.menu_pv_config').id

        # Concesionario checks
        self.assertIn(m_portal, menus_conc)
        self.assertIn(m_ticket, menus_conc)
        self.assertNotIn(m_maquina, menus_conc)
        self.assertNotIn(m_certificado, menus_conc)
        self.assertNotIn(m_medida, menus_conc)
        self.assertNotIn(m_dash, menus_conc)
        self.assertNotIn(m_config, menus_conc)

        # Staff checks
        menus_staff = self.env['ir.ui.menu'].with_user(self.user_staff).load_menus(False)
        self.assertIn(m_dash, menus_staff)
        self.assertIn(m_ticket, menus_staff)
        self.assertIn(m_maquina, menus_staff)
        self.assertIn(m_certificado, menus_staff)
        self.assertIn(m_medida, menus_staff)
        self.assertNotIn(m_portal, menus_staff)
        self.assertNotIn(m_config, menus_staff)

    def test_05_portal_certificados_view_and_isolation(self):
        """Concessionaire can see their certificates via portal methods and count is accurate."""
        # Check portal data has certificado_count
        portal_data = self.env['pv.dashboard'].with_user(self.user_concesionario_a).get_concesionario_portal_data()
        self.assertIn('certificado_count', portal_data)
        self.assertEqual(portal_data['certificado_count'], 1)

        # Check get_portal_list_data returns only A's certificates
        certs_a = self.env['pv.certificado'].with_user(self.user_concesionario_a).get_portal_list_data()
        cert_ids_a = [c['id'] for c in certs_a]
        self.assertIn(self.fru_a.id, cert_ids_a)
        self.assertNotIn(self.fru_b.id, cert_ids_a)


