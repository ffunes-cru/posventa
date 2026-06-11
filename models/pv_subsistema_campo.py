# Part of Crucianelli Posventa Module
from odoo import fields, models


TIPO_CAMPO = [
    ('texto', 'Texto'),
    ('numero', 'Número'),
    ('seleccion', 'Selección'),
    ('booleano', 'Sí / No'),
]


class PvSubsistemaCampo(models.Model):
    _name = 'pv.subsistema.campo'
    _description = 'Campo Adicional de Subsistema'
    _order = 'sequence, id'

    name = fields.Char(
        string='Etiqueta',
        required=True,
    )
    subsistema_id = fields.Many2one(
        'pv.subsistema',
        string='Subsistema',
        required=True,
        ondelete='cascade',
    )
    tipo_campo = fields.Selection(
        TIPO_CAMPO,
        string='Tipo de campo',
        required=True,
        default='texto',
    )
    obligatorio = fields.Boolean(
        string='Obligatorio',
        default=False,
    )
    opciones = fields.Text(
        string='Opciones',
        help='Opciones separadas por | (solo para tipo Selección). Ej: Opción A|Opción B|Opción C',
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )
