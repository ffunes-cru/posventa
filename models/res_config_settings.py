# Part of Crucianelli Posventa Module
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pv_fru_expiration_days = fields.Integer(
        string='Días de Vencimiento FRU',
        config_parameter='posventa.fru_expiration_days',
        default=10,
        help='Días desde la fecha de ingreso (creación) de la máquina para que venza el certificado FRU.'
    )
    pv_feu_expiration_days = fields.Integer(
        string='Días de Vencimiento FEU',
        config_parameter='posventa.feu_expiration_days',
        default=20,
        help='Días desde la fecha de ingreso (creación) de la máquina para que venza el certificado FEU.'
    )
    pv_cpm_expiration_days = fields.Integer(
        string='Días de Vencimiento CPM',
        config_parameter='posventa.cpm_expiration_days',
        default=60,
        help='Días de validez para el Certificado de Puesta en Marcha (CPM) desde su fecha de carga.'
    )
