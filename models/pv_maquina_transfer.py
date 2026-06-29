from odoo import api, fields, models, _
from odoo.exceptions import UserError

class PvMaquina(models.Model):
    _inherit = 'pv.maquina'

    # 2. Campos temporales para la propuesta de transferencia
    concesionario_destino_id = fields.Many2one('pv.concesionario', string='Concesionario Destino Oculto', readonly=True)
    provincia_destino_id = fields.Many2one('res.country.state', string='Provincia Destino Oculta', readonly=True)
    ciudad_destino = fields.Char(string='Ciudad Destino Oculta', readonly=True)

    def action_aceptar_transferencia(self):
        self.ensure_one()
        # Validación de seguridad: Solo el concesionario destino (o un admin) puede aceptar
        if self.concesionario_destino_id.user_id != self.env.user and not self.env.is_admin():
            raise UserError("Solo el concesionario destino puede aceptar esta transferencia.")

        maquina_sudo = self.sudo()

        self.certificado_ids.sudo().write({'active': False})

        # Hacemos efectiva la transferencia
        maquina_sudo.write({
            'concesionario_id': self.concesionario_destino_id.id,
            'provincia_id': self.provincia_destino_id.id,
            'ciudad': self.ciudad_destino,
            'estado': 'liberada',
            # Limpiamos los campos temporales
            'concesionario_destino_id': False,
            'provincia_destino_id': False,
            'ciudad_destino': False,
        })
        maquina_sudo.message_post(body=_("Transferencia ACEPTADA. Nuevo dueño: %s") % self.concesionario_id.name)

    def action_rechazar_transferencia(self):
        self.ensure_one()
        if self.concesionario_destino_id.user_id != self.env.user and not self.env.is_admin():
            raise UserError("Solo el concesionario destino puede rechazar esta transferencia.")

        concesionario_que_rechazo = self.concesionario_destino_id.name

        maquina_sudo = self.sudo()

        # Cancelamos todo y vuelve a su estado normal con su dueño original
        maquina_sudo.write({
            'estado': 'stock', # O el estado previo que consideres
            'concesionario_destino_id': False,
            'provincia_destino_id': False,
            'ciudad_destino': False,
        })
        maquina_sudo.message_post(body=_("Transferencia RECHAZADA por el concesionario %s. La máquina permanece con el dueño original.") % concesionario_que_rechazo)