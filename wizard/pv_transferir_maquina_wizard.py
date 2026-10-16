from odoo import models, fields

class PvTransferirMaquinaWizard(models.TransientModel):
    _name = 'pv.transferir.maquina.wizard'
    _description = 'Asistente de Transferencia de Máquina'

    maquina_id = fields.Many2one('pv.maquina', string='Máquina', required=True, default=lambda self: self.env.context.get('default_maquina_id') or self.env.context.get('active_id'))
    concesionario_destino_id = fields.Many2one('pv.concesionario', string='Concesionario Destino', required=True)
    provincia_destino_id = fields.Many2one('res.country.state', string='Provincia Destino', required=True)
    ciudad_destino_id = fields.Char(string='Ciudad Destino', required=True)

    def action_transferir(self):
        self.ensure_one()
        # En lugar de transferir, "proponemos" la transferencia (queda pendiente de aceptación del destino)
        self.maquina_id._iniciar_transferencia(
            self.concesionario_destino_id, self.provincia_destino_id, self.ciudad_destino_id)
        return {'type': 'ir.actions.act_window_close'}
