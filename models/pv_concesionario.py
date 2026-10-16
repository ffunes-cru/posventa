# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PvConcesionario(models.Model):
    _name = 'pv.concesionario'
    _description = 'Concesionario'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Empresa Concesionario',
        help='Empresa (partner) vinculada en Odoo',
        tracking=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Usuario de acceso principal',
        help='Usuario con rol concesionario para acceder al sistema',
        tracking=True,
    )
    contacto_partner_ids = fields.One2many(
        'res.partner',
        related='partner_id.child_ids',
        string='Contactos / Personal de la Empresa',
        readonly=False,
    )
    email = fields.Char(
        string='Email',
        related='partner_id.email',
        store=True,
        readonly=False,
    )
    phone = fields.Char(
        string='Teléfono',
        related='partner_id.phone',
        store=True,
        readonly=False,
    )
    city = fields.Char(
        string='Ciudad',
        related='partner_id.city',
        store=True,
        readonly=False,
    )
    state_id = fields.Many2one(
        'res.country.state',
        string='Provincia',
        related='partner_id.state_id',
        store=True,
        readonly=False,
    )
    contacto_ids = fields.One2many(
        'pv.concesionario.contacto',
        'concesionario_id',
        string='Personal Histórico',
    )

    @api.model
    def _get_concesionario_for_user(self, user=None):
        """Devuelve el registro pv.concesionario correspondiente al usuario (o env.user)."""
        if user is None:
            user = self.env.user
        partner = user.partner_id
        if not partner:
            return self.browse()

        company_partner = partner.parent_id or partner

        concesionario = self.search([
            '|',
            ('partner_id', '=', company_partner.id),
            ('partner_id', '=', partner.id),
        ], limit=1)

        if not concesionario and user.id:
            concesionario = self.search([('user_id', '=', user.id)], limit=1)

        return concesionario

    maquina_ids = fields.One2many(
        'pv.maquina',
        'concesionario_id',
        string='Máquinas',
    )
    maquina_count = fields.Integer(
        string='Cant. Máquinas',
        compute='_compute_maquina_count',
    )
    ticket_count = fields.Integer(
        string='Cant. Tickets',
        compute='_compute_ticket_count',
    )
    active = fields.Boolean(default=True)

    @api.depends('maquina_ids')
    def _compute_maquina_count(self):
        for rec in self:
            rec.maquina_count = len(rec.maquina_ids)

    @api.depends('maquina_ids.ticket_ids')
    def _compute_ticket_count(self):
        for rec in self:
            rec.ticket_count = self.env['pv.ticket'].search_count([
                ('concesionario_id', '=', rec.id)
            ])

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
