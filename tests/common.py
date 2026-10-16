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
        cls.group_portal = cls.env.ref('base.group_portal')

        # Concesionarios: empresa + usuario portal que es contacto de la empresa
        cls.partner_conc_a = cls.env['res.partner'].create({'name': 'Agro A S.A.', 'is_company': True})
        cls.concesionario_a = cls.env['pv.concesionario'].create({
            'name': 'Concesionario A (Rosario)', 'partner_id': cls.partner_conc_a.id,
        })
        cls.user_concesionario_a = cls._crear_usuario_concesionario('concesionario_a', cls.partner_conc_a)

        cls.partner_conc_b = cls.env['res.partner'].create({'name': 'Agro B S.A.', 'is_company': True})
        cls.concesionario_b = cls.env['pv.concesionario'].create({
            'name': 'Concesionario B (Córdoba)', 'partner_id': cls.partner_conc_b.id,
        })
        cls.user_concesionario_b = cls._crear_usuario_concesionario('concesionario_b', cls.partner_conc_b)

        cls.desvio_rotura = cls.env.ref('posventa.desvio_rotura')
        cls.desvio_faltante = cls.env.ref('posventa.desvio_faltante')
        cls.desvio_otro = cls.env.ref('posventa.desvio_otro')

        # Crucianelli: usuarios internos
        cls.user_staff = cls._crear_usuario('staff_pv', [cls.group_internal, cls.group_staff])
        cls.user_admin = cls._crear_usuario('admin_pv', [cls.group_internal, cls.group_admin])

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

    @classmethod
    def _crear_usuario(cls, login, grupos, **vals):
        return cls.env['res.users'].with_context(no_reset_password=True).create(dict({
            'name': login.replace('_', ' ').title(),
            'login': login,
            'password': login,
            'email': f'{login}@example.com',
            'group_ids': [(6, 0, [g.id for g in grupos])],
        }, **vals))

    @classmethod
    def _crear_usuario_concesionario(cls, login, empresa):
        contacto = cls.env['res.partner'].create({'name': login.title(), 'parent_id': empresa.id})
        return cls._crear_usuario(login, [cls.group_portal, cls.group_concesionario], partner_id=contacto.id)
