# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _


class PvDashboard(models.TransientModel):
    _name = 'pv.dashboard'
    _description = 'Tablero de Control Posventa'

    name = fields.Char(string='Nombre', default='Tablero de Control')

    # Counts
    count_borrador = fields.Integer(string='Borrador', compute='_compute_counts')
    count_abierto = fields.Integer(string='Abiertos (Pendientes)', compute='_compute_counts')
    count_en_proceso = fields.Integer(string='En Proceso', compute='_compute_counts')
    count_aceptado = fields.Integer(string='Aceptados', compute='_compute_counts')
    count_rechazado = fields.Integer(string='Rechazados', compute='_compute_counts')
    count_cerrado = fields.Integer(string='Cerrados', compute='_compute_counts')

    # Avg hours
    avg_t1 = fields.Float(string='T1 Promedio (h)', compute='_compute_averages')
    avg_t2 = fields.Float(string='T2 Promedio (h)', compute='_compute_averages')
    avg_t3 = fields.Float(string='T3 Promedio (h)', compute='_compute_averages')

    @api.model
    def search(self, args, offset=0, limit=None, order=None):
        if not self.search_count([]):
            self.create({})
        return super().search(args, offset=offset, limit=limit, order=order)

    def _compute_counts(self):
        ticket_model = self.env['pv.ticket']
        # Usar _read_group moderno de Odoo 19
        groups = ticket_model._read_group([], ['estado'], ['__count'])
        counts = {estado: count for estado, count in groups if estado}
        for rec in self:
            rec.count_borrador = counts.get('borrador', 0)
            rec.count_abierto = counts.get('abierto', 0)
            rec.count_en_proceso = counts.get('en_proceso', 0)
            rec.count_aceptado = counts.get('aceptado', 0)
            rec.count_rechazado = counts.get('rechazado', 0)
            rec.count_cerrado = counts.get('cerrado', 0)

    def _compute_averages(self):
        self.env.cr.execute("""
            SELECT AVG(t1_horas), AVG(t2_horas), AVG(t3_horas)
            FROM pv_ticket
        """)
        res = self.env.cr.fetchone()
        avg_t1 = res[0] or 0.0 if res else 0.0
        avg_t2 = res[1] or 0.0 if res else 0.0
        avg_t3 = res[2] or 0.0 if res else 0.0
        for rec in self:
            rec.avg_t1 = round(avg_t1, 1)
            rec.avg_t2 = round(avg_t2, 1)
            rec.avg_t3 = round(avg_t3, 1)

    def _action_view_tickets_by_state(self, state):
        return {
            'name': _('Tickets: %s') % state.upper(),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.ticket',
            'view_mode': 'list,kanban,form',
            'domain': [('estado', '=', state)],
            'target': 'current',
        }

    def action_view_borrador(self):
        return self._action_view_tickets_by_state('borrador')

    def action_view_abierto(self):
        return self._action_view_tickets_by_state('abierto')

    def action_view_en_proceso(self):
        return self._action_view_tickets_by_state('en_proceso')

    def action_view_aceptado(self):
        return self._action_view_tickets_by_state('aceptado')

    def action_view_rechazado(self):
        return self._action_view_tickets_by_state('rechazado')

    def action_view_cerrado(self):
        return self._action_view_tickets_by_state('cerrado')

    def action_view_metrics(self):
        # Open pivot/graph metric views of tickets
        return {
            'name': _('Métricas Avanzadas de Tickets'),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.ticket',
            'view_mode': 'graph,pivot',
            'target': 'current',
        }

    @api.model
    def action_open_dashboard(self):
        # Create a new transient dashboard record dynamically
        record = self.sudo().create({})
        return {
            'name': _('Tablero de Control'),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.dashboard',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
            'context': self.env.context,
        }

    @api.model
    def get_concesionario_portal_data(self):
        """Return all data needed by the concesionario OWL portal in a single RPC call."""
        concesionario = self.env['pv.concesionario'].search([('user_id', '=', self.env.uid)], limit=1)
        if not concesionario:
            return {'error': 'No se encontró un concesionario vinculado a este usuario.'}

        # Ticket counts by state (only concesionario's tickets)
        Ticket = self.env['pv.ticket']
        domain_base = [('concesionario_id', '=', concesionario.id)]
        groups = Ticket._read_group(domain_base, ['estado'], ['__count'])
        counts = {estado: count for estado, count in groups if estado}

        # KPIs (averages for this concesionario)
        self.env.cr.execute("""
            SELECT AVG(t1_horas), AVG(t2_horas), AVG(t3_horas)
            FROM pv_ticket
            WHERE concesionario_id = %s
        """, (concesionario.id,))
        res = self.env.cr.fetchone()
        avg_t1 = round(res[0] or 0.0, 1) if res else 0.0
        avg_t2 = round(res[1] or 0.0, 1) if res else 0.0
        avg_t3 = round(res[2] or 0.0, 1) if res else 0.0

        # Machine count
        maquina_count = self.env['pv.maquina'].search_count([('concesionario_id', '=', concesionario.id)])

        # Pending transfers (machines where this concesionario is destination)
        transferencias_pendientes = self.env['pv.maquina'].search_count([
            ('concesionario_destino_id', '=', concesionario.id),
            ('estado', '=', 'pendiente'),
        ])

        return {
            'concesionario_id': concesionario.id,
            'concesionario_name': concesionario.name,
            'maquina_count': maquina_count,
            'transferencias_pendientes': transferencias_pendientes,
            'counts': {
                'borrador': counts.get('borrador', 0),
                'abierto': counts.get('abierto', 0),
                'en_proceso': counts.get('en_proceso', 0),
                'aceptado': counts.get('aceptado', 0),
                'rechazado': counts.get('rechazado', 0),
                'cerrado': counts.get('cerrado', 0),
            },
            'kpis': {
                'avg_t1': avg_t1,
                'avg_t2': avg_t2,
                'avg_t3': avg_t3,
            },
        }
