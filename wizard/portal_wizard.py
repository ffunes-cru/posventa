# Part of Crucianelli Posventa Module
from odoo import models


class PortalWizardUser(models.TransientModel):
    _inherit = 'portal.wizard.user'

    def action_grant_access(self):
        """Los contactos de un concesionario reciben también el rol Concesionario de Posventa."""
        res = super().action_grant_access()
        if self.env['pv.concesionario']._get_by_contact(self.partner_id):
            self.user_id.sudo().write({'group_ids': [(4, self.env.ref('posventa.group_pv_concesionario').id)]})
        return res
