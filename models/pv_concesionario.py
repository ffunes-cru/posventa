# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _


class PvConcesionario(models.Model):
    _name = 'pv.concesionario'
    _description = 'Concesionario'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Nombre', required=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner',
        string='Empresa Concesionario',
        required=True,
        tracking=True,
        help='Empresa vinculada. Sus contactos con acceso al portal operan en nombre del concesionario.',
    )
    contacto_partner_ids = fields.One2many(
        'res.partner',
        related='partner_id.child_ids',
        string='Contactos / Personal de la Empresa',
        readonly=False,
    )
    email = fields.Char(related='partner_id.email', store=True, readonly=False)
    phone = fields.Char(string='Teléfono', related='partner_id.phone', store=True, readonly=False)
    city = fields.Char(string='Ciudad', related='partner_id.city', store=True, readonly=False)
    state_id = fields.Many2one(string='Provincia', related='partner_id.state_id', store=True, readonly=False)
    maquina_ids = fields.One2many('pv.maquina', 'concesionario_id', string='Máquinas')
    maquina_count = fields.Integer(string='Cant. Máquinas', compute='_compute_counts')
    ticket_count = fields.Integer(string='Cant. Tickets', compute='_compute_counts')
    active = fields.Boolean(default=True)

    @api.model
    def _get_by_contact(self, partner):
        """Concesionario cuya empresa es el partner dado o la empresa del partner.

        Es la definición de pertenencia: debe coincidir con las ir.rule (security/pv_security.xml).
        """
        if not partner:
            return self.browse()
        return self.sudo().search(
            [('partner_id', 'in', [partner.id, partner.commercial_partner_id.id])], limit=1,
        ).with_env(self.env)

    @api.model
    def _get_concesionario_for_user(self, user=None):
        return self._get_by_contact((user or self.env.user).partner_id)

    def _is_member(self, user=None):
        """True si el usuario (o env.user) pertenece a este concesionario."""
        self.ensure_one()
        return self._get_concesionario_for_user(user) == self

    @api.depends('maquina_ids')
    def _compute_counts(self):
        tickets = dict(self.env['pv.ticket']._read_group(
            [('concesionario_id', 'in', self.ids)], ['concesionario_id'], ['__count']))
        for rec in self:
            rec.maquina_count = len(rec.maquina_ids)
            rec.ticket_count = tickets.get(rec, 0)

    def _get_portal_resumen(self):
        """Contadores y tiempos promedio del concesionario para la portada del portal."""
        self.ensure_one()
        Ticket = self.env['pv.ticket']
        counts = dict(Ticket._read_group([('concesionario_id', '=', self.id)], ['estado'], ['__count']))
        Maquina = self.env['pv.maquina']
        return {
            'maquina_count': Maquina.search_count([('concesionario_id', '=', self.id)]),
            'certificado_count': self.env['pv.certificado'].search_count([('active', '=', True)]),
            'transferencias_pendientes': Maquina.search_count([
                ('concesionario_destino_id', '=', self.id), ('estado', '=', 'pendiente')]),
            'counts': counts,
            'kpis': Ticket._get_kpis_promedio([('concesionario_id', '=', self.id)]),
        }

    def action_gestionar_acceso_portal(self):
        """Asistente estándar de acceso al portal para los contactos de la empresa."""
        self.ensure_one()
        wizard = self.env['portal.wizard'].with_context(active_ids=self.partner_id.ids).create({})
        return wizard._action_open_modal()

    def action_view_maquinas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Máquinas de %s', self.name),
            'res_model': 'pv.maquina',
            'view_mode': 'list,form',
            'domain': [('concesionario_id', '=', self.id)],
            'context': {'default_concesionario_id': self.id},
        }

    def action_view_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tickets de %s', self.name),
            'res_model': 'pv.ticket',
            'view_mode': 'list,form',
            'domain': [('concesionario_id', '=', self.id)],
        }
