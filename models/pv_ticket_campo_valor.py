# Part of Crucianelli Posventa Module
from odoo import fields, models


class PvTicketCampoValor(models.Model):
    _name = 'pv.ticket.campo.valor'
    _description = 'Valor de Campo Adicional en Ticket'
    _order = 'campo_sequence, id'

    ticket_id = fields.Many2one(
        'pv.ticket',
        string='Ticket',
        required=True,
        ondelete='cascade',
    )
    campo_id = fields.Many2one(
        'pv.subsistema.campo',
        string='Campo',
        required=True,
        ondelete='cascade',
    )
    campo_nombre = fields.Char(
        related='campo_id.name',
        string='Etiqueta',
    )
    campo_tipo = fields.Selection(
        related='campo_id.tipo_campo',
        string='Tipo',
    )
    campo_obligatorio = fields.Boolean(
        related='campo_id.obligatorio',
    )
    campo_opciones = fields.Text(
        related='campo_id.opciones',
    )
    campo_sequence = fields.Integer(
        related='campo_id.sequence',
        store=True,
    )
    valor = fields.Char(
        string='Valor',
    )
