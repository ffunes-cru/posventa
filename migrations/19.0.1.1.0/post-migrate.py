# Part of Crucianelli Posventa Module
"""Fase 2: los concesionarios pasan de usuarios internos a usuarios portal (/my/posventa).

1. La pertenencia ya no usa pv.concesionario.user_id: el usuario principal de cada
   concesionario pasa a ser contacto de la empresa (si no lo era).
2. Los usuarios del grupo Concesionario que no son Staff pasan a usuarios portal.
"""
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    if column_exists(cr, 'pv_concesionario', 'user_id'):
        cr.execute("SELECT partner_id, user_id FROM pv_concesionario WHERE user_id IS NOT NULL")
        for empresa_id, user_id in cr.fetchall():
            partner = env['res.users'].browse(user_id).partner_id
            if partner.commercial_partner_id.id != empresa_id and partner.id != empresa_id:
                partner.parent_id = empresa_id

    grupo_concesionario = env.ref('posventa.group_pv_concesionario')
    grupo_staff = env.ref('posventa.group_pv_staff')
    grupo_portal = env.ref('base.group_portal')
    usuarios = env['res.users'].with_context(active_test=False).search([
        ('group_ids', 'in', grupo_concesionario.id),
        ('share', '=', False),
    ]).filtered(lambda u: grupo_staff not in u.all_group_ids)
    usuarios.write({'group_ids': [(6, 0, [grupo_portal.id, grupo_concesionario.id])]})
    _logger.info("Posventa: %s usuarios concesionario convertidos a usuarios portal: %s",
                 len(usuarios), usuarios.mapped('login'))

    # La sincronización con Drive pasó de pv.ticket a pv.ticket.multimedia (el cron es noupdate)
    env.ref('posventa.cron_pv_sync_multimedia_drive').ir_actions_server_id.write({
        'model_id': env.ref('posventa.model_pv_ticket_multimedia').id,
        'code': 'model._cron_sync_pending()',
    })
