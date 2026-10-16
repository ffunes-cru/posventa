# Part of Crucianelli Posventa Module
from odoo import fields, models


class PvTipoDesvio(models.Model):
    _name = 'pv.tipo.desvio'
    _description = 'Tipo de Desvío de Reclamo'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nombre',
        required=True,
        translate=True,
    )
    codigo = fields.Char(
        string='Código',
        help='Identificador técnico o código SAP (opcional)',
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
