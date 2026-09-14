# Part of Crucianelli Posventa Module
from markupsafe import Markup, escape
from odoo import api, fields, models, _


TIPO_MEDIDA = [
    ('accion', 'Acción'),
    ('medida', 'Medida'),
    ('actualizacion', 'Actualización'),
    ('resolucion_parcial', 'Resolución Parcial'),
    ('resolucion_definitiva', 'Resolución Definitiva'),
]

ESTADO_MEDIDA = [
    ('pendiente', 'Pendiente'),
    ('en_curso', 'En Curso'),
    ('completada', 'Completada'),
    ('vencida', 'Vencida'),
]


class PvTicketMedida(models.Model):
    _name = 'pv.ticket.medida'
    _description = 'Medida / Seguimiento de Ticket'
    _inherit = ['mail.thread']
    _order = 'fecha_vencimiento asc, id desc'

    name = fields.Char(
        string='Título',
        required=True,
        tracking=True,
    )
    ticket_id = fields.Many2one(
        'pv.ticket',
        string='Ticket',
        required=True,
        ondelete='cascade',
    )
    ticket_name = fields.Char(
        related='ticket_id.name',
        string='Nro. Ticket',
    )
    tipo = fields.Selection(
        TIPO_MEDIDA,
        string='Tipo',
        required=True,
        default='accion',
        tracking=True,
    )
    responsable_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.user,
        tracking=True,
    )
    comentario = fields.Text(
        string='Comentario',
        tracking=True,
    )
    fecha_vencimiento = fields.Date(
        string='Fecha de vencimiento',
        tracking=True,
    )
    estado = fields.Selection(
        ESTADO_MEDIDA,
        string='Estado',
        default='pendiente',
        required=True,
        tracking=True,
    )
    fecha_creacion = fields.Datetime(
        string='Fecha de creación',
        default=fields.Datetime.now,
        readonly=True,
    )
    fecha_completada = fields.Datetime(
        string='Fecha completada',
        readonly=True,
    )

    # Related for dashboard filtering
    ticket_estado = fields.Selection(
        related='ticket_id.estado',
        store=True,
        string='Estado del Ticket',
    )
    concesionario_id = fields.Many2one(
        related='ticket_id.concesionario_id',
        store=True,
        string='Concesionario',
    )

    def action_completar(self):
        for rec in self:
            rec.write({
                'estado': 'completada',
                'fecha_completada': fields.Datetime.now(),
            })

    def action_en_curso(self):
        for rec in self:
            rec.estado = 'en_curso'

    @api.model
    def _cron_check_vencimientos(self):
        """Cron job: mark overdue measures and notify."""
        today = fields.Date.context_today(self)
        vencidas = self.search([
            ('fecha_vencimiento', '<', today),
            ('estado', 'in', ['pendiente', 'en_curso']),
        ])
        for medida in vencidas:
            medida.estado = 'vencida'
            medida.ticket_id.message_post(
                body=Markup(_('⚠️ Medida vencida: <b>%s</b> (Responsable: %s)')) % (
                    escape(medida.name), escape(medida.responsable_id.name or 'Sin asignar')
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
