# Part of Crucianelli Posventa Module
from odoo import fields, models


class PvTipoRechazo(models.Model):
    _name = 'pv.tipo.rechazo'
    _description = 'Tipo / Motivo de Rechazo de Reclamo o Garantía'
    _order = 'sequence, name'

    name = fields.Char(
        string='Motivo / Tag',
        required=True,
        translate=True,
    )
    color = fields.Integer(
        string='Color de Etiqueta',
        default=1,
    )
    descripcion = fields.Text(
        string='Descripción / Criterio',
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
