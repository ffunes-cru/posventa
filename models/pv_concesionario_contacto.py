# Part of Crucianelli Posventa Module
from odoo import fields, models


class PvConcesionarioContacto(models.Model):
    _name = 'pv.concesionario.contacto'
    _description = 'Contacto de Concesionario'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
    )
    cargo = fields.Char(
        string='Cargo',
    )
    telefono = fields.Char(
        string='Teléfono',
    )
    email = fields.Char(
        string='Email',
    )
    concesionario_id = fields.Many2one(
        'pv.concesionario',
        string='Concesionario',
        required=True,
        ondelete='cascade',
    )
    active = fields.Boolean(default=True)
