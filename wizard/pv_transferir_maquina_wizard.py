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


        # En lugar de transferir, "proponemos" la transferencia
        self.maquina_id.sudo().write({
            'concesionario_destino_id': self.concesionario_destino_id.id,
            'provincia_destino_id': self.provincia_destino_id.id,
            'ciudad_destino': self.ciudad_destino_id,
            'estado': 'pendiente',
        })

        self.maquina_id.message_post(
            body=_('Solicitud de transferencia enviada a %s por %s (Pendiente de aceptación)', self.concesionario_destino_id.name, self.env.user.name),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )   

        # Redirigimos al listado
        return {
            'type': 'ir.actions.act_window',
            'name': 'Máquinas',
            'res_model': 'pv.maquina',
            'view_mode': 'list,form',
            'target': 'current',
        }