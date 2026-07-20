from odoo import api, fields, models, _
from odoo.exceptions import UserError

class PvMaquina(models.Model):
    _inherit = 'pv.maquina'

    # 2. Campos temporales para la propuesta de transferencia
    concesionario_destino_id = fields.Many2one('pv.concesionario', string='Concesionario Destino Oculto', readonly=True)
    provincia_destino_id = fields.Many2one('res.country.state', string='Provincia Destino Oculta', readonly=True)
    ciudad_destino = fields.Char(string='Ciudad Destino Oculta', readonly=True)

    es_concesionario_destino = fields.Boolean(
        compute='_compute_es_concesionario_destino', 
        store=False
    )

    def _compute_es_concesionario_destino(self):
        # Evaluamos si el usuario actual es el dueño del concesionario destino
        actual_user = self.env.user
        for record in self:
            record.es_concesionario_destino = record.concesionario_destino_id.user_id == actual_user

    def action_aceptar_transferencia(self):
        self.ensure_one()
        # Validación de seguridad: Solo el concesionario destino (o un admin) puede aceptar
        if self.concesionario_destino_id.user_id != self.env.user and not self.env.is_admin():
            raise UserError("Solo el concesionario destino puede aceptar esta transferencia.")

        maquina_sudo = self.sudo()

        self.env['pv.certificado'].sudo().search([('maquina_id', '=', self.id)]).write({'active': False})

        # Hacemos efectiva la transferencia y reseteamos los booleanos de certificados
        maquina_sudo.write({
            'concesionario_id': self.concesionario_destino_id.id,
            'provincia_id': self.provincia_destino_id.id,
            'ciudad': self.ciudad_destino,
            'estado': 'liberada',
            'tiene_fru': False,
            'tiene_feu': False,
            'tiene_cpm': False,
            # Limpiamos los campos temporales
            'concesionario_destino_id': False,
            'provincia_destino_id': False,
            'ciudad_destino': False,
        })
        maquina_sudo.modified(['certificado_ids'])
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