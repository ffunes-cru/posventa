# Part of Crucianelli Posventa Module
from odoo import fields, models


class PvSistema(models.Model):
    _name = 'pv.sistema'
    _description = 'Sistema Involucrado'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nombre',
        required=True,
    )
    codigo = fields.Char(
        string='Código',
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )
    subsistema_ids = fields.One2many(
        'pv.subsistema',
        'sistema_id',
        string='Subsistemas',
    )
    active = fields.Boolean(default=True)
