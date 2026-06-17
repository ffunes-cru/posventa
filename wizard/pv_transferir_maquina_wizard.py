from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PvTransferirMaquinaWizard(models.TransientModel):
    _name = 'pv.transferir.maquina.wizard'
    _description = 'Asistente de Transferencia de Máquina'

    maquina_id = fields.Many2one('pv.maquina', string='Máquina', required=True, default=lambda self: self.env.context.get('active_id'))
    concesionario_destino_id = fields.Many2one('pv.concesionario', string='Concesionario Destino', required=True)
    provincia_destino_id = fields.Many2one('res.country.state', string='Provincia Destino', required=True)
    ciudad_destino_id = fields.Char(string='Ciudad Destino', required=True)

    def action_transferir(self):
        self.ensure_one()
        if self.maquina_id.concesionario_id == self.concesionario_destino_id:
            raise UserError("La máquina ya pertenece a este concesionario.")
        
        # .sudo() es la clave: el sistema hace el cambio de dueño saltándose las restricciones de guardado
        self.maquina_id.sudo().write({
            'concesionario_id': self.concesionario_destino_id.id,
            'provincia_id': self.provincia_destino_id.id,
            'ciudad': self.ciudad_destino_id,
            'estado': 'liberada',
        })

        self.maquina_id.message_post(
            body=_('Máquina transferida a %s por %s', self.concesionario_destino_id.name, self.env.user.name),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )   

        # Como la máquina ya no es del concesionario actual, lo redirigimos a la vista listado
        return {
            'type': 'ir.actions.act_window',
            'name': 'Máquinas',
            'res_model': 'pv.maquina',
            'view_mode': 'list,form',
            'target': 'current',
        }