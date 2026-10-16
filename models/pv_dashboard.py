# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _

from .pv_ticket import ESTADO_TICKET


class PvDashboard(models.TransientModel):
    _name = 'pv.dashboard'
    _description = 'Tablero de Control Posventa'

    name = fields.Char(string='Nombre', default='Tablero de Control')

    count_borrador = fields.Integer(string='Borrador', compute='_compute_counts')
    count_abierto = fields.Integer(string='Abiertos (Pendientes)', compute='_compute_counts')
    count_en_proceso = fields.Integer(string='En Proceso', compute='_compute_counts')
    count_aceptado = fields.Integer(string='Aceptados', compute='_compute_counts')
    count_rechazado = fields.Integer(string='Rechazados', compute='_compute_counts')
    count_cerrado = fields.Integer(string='Cerrados', compute='_compute_counts')

    avg_t1 = fields.Float(string='T1 Promedio (h)', compute='_compute_averages')
    avg_t2 = fields.Float(string='T2 Promedio (h)', compute='_compute_averages')
    avg_t3 = fields.Float(string='T3 Promedio (h)', compute='_compute_averages')

    def _compute_counts(self):
        counts = dict(self.env['pv.ticket']._read_group([], ['estado'], ['__count']))
        for rec in self:
            for estado, _label in ESTADO_TICKET:
                rec[f'count_{estado}'] = counts.get(estado, 0)

    def _compute_averages(self):
        kpis = self.env['pv.ticket']._get_kpis_promedio()
        for rec in self:
            rec.update(kpis)

    def action_view_tickets(self):
        """Listado de tickets del estado indicado en el contexto del botón."""
        estado = self.env.context.get('estado')
        return {
            'name': _('Tickets: %s', dict(ESTADO_TICKET).get(estado, '')),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.ticket',
            'view_mode': 'list,kanban,form',
            'domain': [('estado', '=', estado)],
            'target': 'current',
        }

    def action_view_metrics(self):
        return {
            'name': _('Métricas Avanzadas de Tickets'),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.ticket',
            'view_mode': 'graph,pivot',
            'target': 'current',
        }

    @api.model
    def action_open_dashboard(self):
        return {
            'name': _('Tablero de Control'),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.dashboard',
            'view_mode': 'form',
            'res_id': self.create({}).id,
            'target': 'current',
        }
