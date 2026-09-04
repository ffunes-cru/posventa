# Part of Crucianelli Posventa Module
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pv_fru_expiration_days = fields.Integer(
        string='Plazo de Carga FRU (Días)',
        config_parameter='posventa.fru_expiration_days',
        default=10,
        help='Días desde el ingreso/liberación de la máquina para que venza el plazo nominal de carga del FRU.'
    )
    pv_fru_grace_days = fields.Integer(
        string='Días de Gracia / Vigencia FRU',
        config_parameter='posventa.fru_grace_days',
        default=3,
        help='Días de gracia tras el vencimiento nominal durante los cuales el FRU sigue vigente para crear tickets antes de pasar a Vencido.'
    )
    pv_feu_expiration_days = fields.Integer(
        string='Plazo de Carga FEU (Días)',
        config_parameter='posventa.feu_expiration_days',
        default=20,
        help='Días desde el ingreso/liberación de la máquina para que venza el plazo nominal de carga del FEU.'
    )
    pv_feu_claims_validity_days = fields.Integer(
        string='Validez de Reclamos FEU (Días)',
        config_parameter='posventa.feu_claims_validity_days',
        default=90,
        help='Días desde la emisión/carga del FEU durante los cuales está vigente para crear tickets antes de vencer y requerir renovación.'
    )
    pv_enable_ai_integration = fields.Boolean(
        string='Habilitar Integración con IA',
        config_parameter='posventa.enable_ai_integration',
        help='Habilita o deshabilita las funcionalidades y asistencia con Inteligencia Artificial (Gemini) en los tickets.'
    )
