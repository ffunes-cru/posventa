# Part of Crucianelli Posventa Module
from odoo import models
from odoo.exceptions import UserError
from odoo.tools import email_normalize


class PortalWizardUser(models.TransientModel):
    _inherit = 'portal.wizard.user'

    def action_grant_access(self):
        """Los contactos de un concesionario reciben también el rol Concesionario de Posventa."""
        res = super().action_grant_access()
        if self.env['pv.concesionario']._get_by_contact(self.partner_id):
            self.user_id.sudo().write({'group_ids': [(4, self.env.ref('posventa.group_pv_concesionario').id)]})
        return res

    def _assert_user_email_uniqueness(self):
        """El error de Odoo por correo repetido solo dice que hay "un usuario existente". Acá se dice cuál: su
        nombre, si es interno, portal o está archivado, de qué contacto es y de qué concesionario."""
        self.ensure_one()
        if self.email_state != 'exist':
            return super()._assert_user_email_uniqueness()
        # Los mismos usuarios que encontró _compute_email_state (portal y website), incluidos los archivados
        similares = self.env['res.users'].with_context(active_test=False).sudo().search_read(
            self._get_similar_users_domain(self), self._get_similar_users_fields())
        usuarios = self.env['res.users'].with_context(active_test=False).sudo().browse(
            [u['id'] for u in similares if self._is_portal_similar_than_user(u, self)])
        raise UserError(self.env._(
            'No se puede dar acceso al portal a "%(contacto)s": su correo %(email)s ya es el usuario (login) de:\n'
            '%(usuarios)s\n\n'
            'Si es la misma persona, darle acceso desde ese contacto o reactivar ese usuario (Ajustes → Usuarios, '
            'filtro Archivados). Si es otra persona, cargarle a "%(contacto)s" otro correo.',
            contacto=self.partner_id.display_name, email=email_normalize(self.email),
            usuarios='\n'.join(self._describir_usuario(usuario) for usuario in usuarios)))

    def _describir_usuario(self, usuario):
        """Una línea por usuario: nombre, tipo, estado, contacto y concesionario."""
        tipo = (self.env._('interno') if usuario._is_internal() else
                self.env._('portal') if usuario._is_portal() else self.env._('público'))
        detalles = [tipo, self.env._('activo') if usuario.active else self.env._('archivado')]
        concesionario = self.env['pv.concesionario']._get_by_contact(usuario.partner_id)
        if concesionario:
            detalles.append(self.env._('concesionario %s', concesionario.sudo().name))
        return self.env._('- %(usuario)s (%(detalles)s), contacto "%(contacto)s"',
                          usuario=usuario.name, detalles=', '.join(detalles),
                          contacto=usuario.partner_id.display_name)
