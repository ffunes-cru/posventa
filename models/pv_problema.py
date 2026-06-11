# Part of Crucianelli Posventa Module
from odoo import fields, models


class PvProblema(models.Model):
    _name = 'pv.problema'
    _description = 'Problema / Código de Falla'
    _order = 'subsistema_id, name'

    name = fields.Char(
        string='Descripción',
        required=True,
    )
    codigo = fields.Char(
        string='Código de falla',
    )
    subsistema_id = fields.Many2one(
        'pv.subsistema',
        string='Subsistema',
        required=True,
        ondelete='cascade',
    )
    sistema_id = fields.Many2one(
        related='subsistema_id.sistema_id',
        store=True,
        string='Sistema',
    )
    active = fields.Boolean(default=True)
