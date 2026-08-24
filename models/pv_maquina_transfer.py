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

        # Determinamos el estado según los certificados vigentes que posee la máquina
        certificados_vigentes = self.env['pv.certificado'].sudo().search([
            ('maquina_id', '=', self.id),
            ('active', '=', True),
            ('estado_certificado', '=', 'vigente'),
        ])
        tipos_vigentes = certificados_vigentes.mapped('tipo')
        if 'cpm' in tipos_vigentes:
            new_estado = 'vendida'
        elif 'fru' in tipos_vigentes:
            new_estado = 'stock'
        else:
            new_estado = 'liberada'

        # Hacemos efectiva la transferencia manteniendo los certificados vigentes y su historial
        maquina_sudo.write({
            'concesionario_id': self.concesionario_destino_id.id,
            'provincia_id': self.provincia_destino_id.id,
            'ciudad': self.ciudad_destino,
            'estado': new_estado,
            # Limpiamos los campos temporales
            'concesionario_destino_id': False,
            'provincia_destino_id': False,
            'ciudad_destino': False,
        })
        maquina_sudo._compute_tiene_certificados()
        maquina_sudo.message_post(body=_("Transferencia ACEPTADA. Nuevo dueño: %s. Los certificados existentes se conservan intactos.") % self.concesionario_destino_id.name)

    def action_rechazar_transferencia(self):
        self.ensure_one()
        if self.concesionario_destino_id.user_id != self.env.user and not self.env.is_admin():
            raise UserError("Solo el concesionario destino puede rechazar esta transferencia.")

        concesionario_que_rechazo = self.concesionario_destino_id.name

        maquina_sudo = self.sudo()

        # Restablecemos estado previo (stock si tenía FRU, vendida si CPM, o liberada)
        prev_estado = 'liberada'
        if maquina_sudo.tiene_cpm:
            prev_estado = 'vendida'
        elif maquina_sudo.tiene_fru:
            prev_estado = 'stock'

        # Cancelamos todo y vuelve a su estado normal con su dueño original
        maquina_sudo.write({
            'estado': prev_estado,
            'concesionario_destino_id': False,
            'provincia_destino_id': False,
            'ciudad_destino': False,
        })
        maquina_sudo.message_post(body=_("Transferencia RECHAZADA por el concesionario %s. La máquina vuelve a estado %s con su dueño original.") % (concesionario_que_rechazo, prev_estado))