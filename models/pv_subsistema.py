# Part of Crucianelli Posventa Module
from odoo import fields, models


class PvSubsistema(models.Model):
    _name = 'pv.subsistema'
    _description = 'Subsistema'
    _order = 'sistema_id, sequence, name'

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
    sistema_id = fields.Many2one(
        'pv.sistema',
        string='Sistema',
        required=True,
        ondelete='cascade',
    )
    problema_ids = fields.One2many(
        'pv.problema',
        'subsistema_id',
        string='Problemas',
    )
    campo_extra_ids = fields.One2many(
        'pv.subsistema.campo',
        'subsistema_id',
        string='Campos adicionales',
        help='Campos de información adicional que se solicitan al concesionario al seleccionar este subsistema',
    )
    placeholder_descripcion = fields.Text(
        string='Guía para descripción',
        help='Texto de ayuda que se muestra al concesionario para guiar la descripción del problema',
    )
    active = fields.Boolean(default=True)
