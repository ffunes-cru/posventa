# Part of Crucianelli Posventa Module
from odoo.tests.common import TransactionCase
import base64

DUMMY_PDF_BASE64 = base64.b64encode(b"%PDF-1.4 dummy pdf content").decode('utf-8')


class TestPosventaCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Groups
        cls.group_concesionario = cls.env.ref('posventa.group_pv_concesionario')
        cls.group_staff = cls.env.ref('posventa.group_pv_staff')
        cls.group_admin = cls.env.ref('posventa.group_pv_admin')
        cls.group_internal = cls.env.ref('base.group_user')

        # Users
        cls.user_concesionario_a = cls.env['res.users'].create({
            'name': 'Concesionario A User',
            'login': 'concesionario_a',
            'email': 'concesionario_a@crucianelli.com',
            'group_ids': [(6, 0, [cls.group_internal.id, cls.group_concesionario.id])],
        })

        cls.user_concesionario_b = cls.env['res.users'].create({
            'name': 'Concesionario B User',
            'login': 'concesionario_b',
            'email': 'concesionario_b@crucianelli.com',
            'group_ids': [(6, 0, [cls.group_internal.id, cls.group_concesionario.id])],
        })

        cls.user_staff = cls.env['res.users'].create({
            'name': 'Staff Posventa',
            'login': 'staff_pv',
            'email': 'staff@crucianelli.com',
            'group_ids': [(6, 0, [cls.group_internal.id, cls.group_staff.id])],
        })

        cls.user_admin = cls.env['res.users'].create({
            'name': 'Admin Posventa',
            'login': 'admin_pv',
            'email': 'admin_pv@crucianelli.com',
            'group_ids': [(6, 0, [cls.group_internal.id, cls.group_admin.id])],
        })

        # Concesionarios
        cls.partner_conc_a = cls.env['res.partner'].create({'name': 'Agro A S.A.'})
        cls.concesionario_a = cls.env['pv.concesionario'].create({
            'name': 'Concesionario A (Rosario)',
            'partner_id': cls.partner_conc_a.id,
            'user_id': cls.user_concesionario_a.id,
            'email': 'contacto@concesionario_a.com',
        })

        cls.partner_conc_b = cls.env['res.partner'].create({'name': 'Agro B S.A.'})
        cls.concesionario_b = cls.env['pv.concesionario'].create({
            'name': 'Concesionario B (Córdoba)',
            'partner_id': cls.partner_conc_b.id,
            'user_id': cls.user_concesionario_b.id,
            'email': 'contacto@concesionario_b.com',
        })

        # Client
        cls.cliente_final = cls.env['res.partner'].create({
            'name': 'Productor Juan Perez',
            'email': 'juanperez@campo.com',
        })

        # Catalog: Sistema, Subsistema, Problema
        cls.sistema = cls.env['pv.sistema'].create({
            'name': 'Sistema Hidráulico',
            'codigo': 'HID',
        })

        cls.subsistema = cls.env['pv.subsistema'].create({
            'name': 'Válvula de Presión',
            'codigo': 'VALV',
            'sistema_id': cls.sistema.id,
            'placeholder_descripcion': 'Detalle la fuga o pérdida de presión observada',
        })

        cls.problema = cls.env['pv.problema'].create({
            'name': 'Pérdida de Aceite',
            'codigo': 'PERD_ACEITE',
            'subsistema_id': cls.subsistema.id,
        })
