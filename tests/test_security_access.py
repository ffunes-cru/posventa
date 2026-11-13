# Part of Crucianelli Posventa Module
from .common import TestPosventaCommon, DUMMY_PDF_BASE64
from odoo import fields
from odoo.exceptions import AccessError


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
            'desvio_tipo_id': self.desvio_faltante.id,
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
            'desvio_tipo_id': self.desvio_faltante.id,
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
        """Staff sees all non-draft tickets and can collaborate across tickets."""
        # When ticket is draft, staff does not see it
        tickets_staff = self.env['pv.ticket'].with_user(self.user_staff).search([])
        self.assertNotIn(self.ticket_a, tickets_staff)

        # Attach image to comply with mandatory attachments before sending
        self.ticket_a.write({'multimedia_url': 'https://drive.google.com/test-mandatory-file'})

        # When ticket is submitted (abierto), staff sees it regardless of assignment
        self.ticket_a.action_enviar_ticket()
        tickets_staff_after = self.env['pv.ticket'].with_user(self.user_staff).search([])
        self.assertIn(self.ticket_a, tickets_staff_after)

        # If ticket is moved to 'en_proceso' and assigned to another user (admin), staff STILL sees it
        self.ticket_a.write({'estado': 'en_proceso', 'responsable_id': self.user_admin.id})
        tickets_staff_assigned_other = self.env['pv.ticket'].with_user(self.user_staff).search([])
        self.assertIn(self.ticket_a, tickets_staff_assigned_other)

        # If ticket is assigned to this staff user, staff sees it in 'en_proceso'
        self.ticket_a.write({'responsable_id': self.user_staff.id})
        tickets_staff_assigned_self = self.env['pv.ticket'].with_user(self.user_staff).search([])
        self.assertIn(self.ticket_a, tickets_staff_assigned_self)

    def test_03_admin_unrestricted_access(self):
        """Admin sees everything including draft tickets and all machines."""
        maquinas_admin = self.env['pv.maquina'].with_user(self.user_admin).search([])
        self.assertIn(self.maquina_a, maquinas_admin)
        self.assertIn(self.maquina_b, maquinas_admin)

        tickets_admin = self.env['pv.ticket'].with_user(self.user_admin).search([])
        self.assertIn(self.ticket_a, tickets_admin)
        self.assertIn(self.ticket_b, tickets_admin)

    def test_04_menu_visibility_restrictions(self):
        """El backend de Posventa es solo para Crucianelli: el concesionario (portal) no ve la app."""
        m_config = self.env.ref('posventa.menu_pv_config').id
        self.assertTrue(self.user_concesionario_a.share)
        with self.assertRaises(AccessError):
            self.env['ir.ui.menu'].with_user(self.user_concesionario_a).load_menus(False)

        menus_staff = self.env['ir.ui.menu'].with_user(self.user_staff).load_menus(False)
        for xmlid in ('menu_pv_dashboard', 'menu_pv_ticket', 'menu_pv_maquina', 'menu_pv_certificado', 'menu_pv_ticket_medida'):
            self.assertIn(self.env.ref(f'posventa.{xmlid}').id, menus_staff)
        self.assertNotIn(m_config, menus_staff)
        self.assertIn(m_config, self.env['ir.ui.menu'].with_user(self.user_admin).load_menus(False))

    def test_05_portal_certificados_view_and_isolation(self):
        """Concessionaire can see their certificates via portal methods and count is accurate."""
        # Check portal data has certificado_count
        portal_data = self.concesionario_a.with_user(self.user_concesionario_a)._get_portal_resumen()
        self.assertIn('certificado_count', portal_data)
        self.assertEqual(portal_data['certificado_count'], 1)

        # Check get_portal_list_data returns only A's certificates
        certs_a = self.env['pv.certificado'].with_user(self.user_concesionario_a).get_portal_list_data()
        self.assertEqual([c['id'] for c in certs_a], self.fru_a.ids)
    def test_06_concesionario_contact_user_access(self):
        """Users created as child contacts of a dealership partner can access the dealership's records."""
        # Create a contact partner under concesionario_a's company partner
        contact_partner = self.env['res.partner'].create({
            'name': 'Operador Juan Perez',
            'parent_id': self.concesionario_a.partner_id.id,
            'is_company': False,
            'email': 'juan.perez@concesionarioa.com',
        })
        user_contact = self.env['res.users'].create({
            'name': 'Juan Perez',
            'login': 'juan_perez_a',
            'email': 'juan.perez@concesionarioa.com',
            'partner_id': contact_partner.id,
            'group_ids': [(6, 0, [self.group_portal.id, self.group_concesionario.id])],
        })

        # Test resolving concesionario for user
        concesionario = self.env['pv.concesionario']._get_concesionario_for_user(user_contact)
        self.assertEqual(concesionario, self.concesionario_a)

        # Contact user sees machine A but not machine B
        maquinas = self.env['pv.maquina'].with_user(user_contact).search([])
        self.assertIn(self.maquina_a, maquinas)
        self.assertNotIn(self.maquina_b, maquinas)

        # Contact user sees ticket A but not ticket B
        tickets = self.env['pv.ticket'].with_user(user_contact).search([])
        self.assertIn(self.ticket_a, tickets)
        self.assertNotIn(self.ticket_b, tickets)




    def test_07_alta_por_asistente_de_portal(self):
        """El admin da acceso al portal a un contacto: queda como usuario portal con rol Concesionario."""
        contacto = self.env['res.partner'].create({
            'name': 'Nuevo Operador', 'email': 'nuevo.operador@example.com', 'parent_id': self.partner_conc_a.id,
        })
        action = self.concesionario_a.with_user(self.user_admin).action_gestionar_acceso_portal()
        wizard = self.env['portal.wizard'].browse(action['res_id'])
        linea = wizard.user_ids.filtered(lambda u: u.partner_id == contacto)
        linea.with_user(self.user_admin).action_grant_access()

        usuario = contacto.user_ids
        self.assertTrue(usuario.share)
        self.assertIn(self.group_concesionario, usuario.all_group_ids)
        self.assertEqual(self.env['pv.concesionario']._get_concesionario_for_user(usuario), self.concesionario_a)

        # Un contacto que no es de un concesionario no recibe el rol
        cliente = self.env['res.partner'].create({'name': 'Cliente Portal', 'email': 'cliente@example.com'})
        linea_cliente = self.env['portal.wizard'].with_context(active_ids=cliente.ids).create({}).user_ids
        linea_cliente.action_grant_access()
        self.assertNotIn(self.group_concesionario, cliente.user_ids.all_group_ids)
