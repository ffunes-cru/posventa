# Part of Crucianelli Posventa Module
from odoo import fields, models


APLICA_A = [
    ('reclamo', 'Rechazo de Reclamo'),
    ('garantia', 'Sin Cobertura de Garantía'),
]


class PvTipoRechazo(models.Model):
    _name = 'pv.tipo.rechazo'
    _description = 'Tipo / Motivo de Rechazo de Reclamo o Garantía'
    _order = 'sequence, name'

    name = fields.Char(
        string='Motivo / Tag',
        required=True,
        translate=True,
    )
    aplica_a = fields.Selection(
        APLICA_A,
        string='Aplica a',
        required=True,
        default='reclamo',
        help='Rechazo de Reclamo: el concesionario cargó el reclamo de forma incorrecta (debe crear uno nuevo).\n'
             'Sin Cobertura de Garantía: el reclamo era válido pero la pieza no está cubierta y la abona el concesionario/cliente.',
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
