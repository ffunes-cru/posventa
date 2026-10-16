# Part of Crucianelli Posventa Module
from odoo import fields, models


class PvLiberarMaquinaWizard(models.TransientModel):
    _name = 'pv.liberar.maquina.wizard'
    _description = 'Asistente de Liberación de Máquina'

    maquina_id = fields.Many2one('pv.maquina', string='Máquina', required=True, readonly=True)
    liberacion_solicitada = fields.Boolean(related='maquina_id.liberacion_solicitada')
    liberacion_solicitante_id = fields.Many2one(related='maquina_id.liberacion_solicitante_id')
    motivo = fields.Text(string='Motivo', required=True)

    def action_liberar(self):
        self.ensure_one()
        self.maquina_id.action_liberar_maquina(self.motivo)
        return {'type': 'ir.actions.act_window_close'}
