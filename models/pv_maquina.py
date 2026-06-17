# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _
from odoo.exceptions import UserError


TIPO_MAQUINA = [
    ('pionera', 'PIONERA'),
    ('gringa', 'GRINGA'),
    ('drilor', 'DRILOR'),
    ('plantor', 'PLANTOR'),
    ('mixia', 'MIXIA'),
]

ESTADO_MAQUINA = [
    ('liberada', 'LIBERADA'),
    ('stock', 'STOCK'),
    ('vendida', 'VENDIDA'),
]


class PvMaquina(models.Model):
    _name = 'pv.maquina'
    _description = 'Máquina Posventa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Referencia',
        compute='_compute_name',
        store=True,
    )
    of = fields.Char(
        string='Orden de Fabricación',
        required=True,
        tracking=True,
        index=True,
    )
    tipo = fields.Selection(
        TIPO_MAQUINA,
        string='Tipo de Máquina',
        required=True,
        tracking=True,
    )
    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        tracking=True,
    )
    concesionario_id = fields.Many2one(
        'pv.concesionario',
        string='Concesionario',
        required=True,
        tracking=True,
    )
    ciudad = fields.Char(
        string='Ciudad',
        tracking=True,
    )
    provincia_id = fields.Many2one(
        'res.country.state',
        string='Provincia',
        tracking=True,
    )
    estado = fields.Selection(
        ESTADO_MAQUINA,
        string='Estado',
        default='liberada',
        required=True,
        tracking=True,
    )
    fecha_venta = fields.Datetime(
        string='Fecha de Venta',
        readonly=True,
        help='Fecha en la que la máquina pasó a estado VENDIDA',
    )

    # --- Certificados ---
    certificado_ids = fields.One2many(
        'pv.certificado',
        'maquina_id',
        string='Certificados',
    )
    certificado_count = fields.Integer(
        compute='_compute_certificado_count',
    )

    # --- Tickets ---
    ticket_ids = fields.One2many(
        'pv.ticket',
        'maquina_id',
        string='Tickets',
    )
    ticket_count = fields.Integer(
        compute='_compute_ticket_count',
    )

    # --- Computed flags ---
    tiene_cpm = fields.Boolean(
        string='Tiene CPM',
        compute='_compute_tiene_certificados',
        store=True,
    )
    tiene_fru = fields.Boolean(
        string='Tiene FRU',
        compute='_compute_tiene_certificados',
        store=True,
    )
    tiene_feu = fields.Boolean(
        string='Tiene FEU',
        compute='_compute_tiene_certificados',
        store=True,
    )

    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('of_unique', 'UNIQUE(of)',
         'Ya existe una máquina con esta Orden de Fabricación.'),
    ]

    @api.depends('tipo', 'of')
    def _compute_name(self):
        for rec in self:
            tipo_label = dict(TIPO_MAQUINA).get(rec.tipo, '')
            rec.name = f"{tipo_label} - {rec.of}" if rec.of else ''

    @api.depends('certificado_ids', 'certificado_ids.tipo')
    def _compute_tiene_certificados(self):
        for rec in self:
            tipos = rec.certificado_ids.mapped('tipo')
            rec.tiene_cpm = 'cpm' in tipos
            rec.tiene_fru = 'fru' in tipos
            rec.tiene_feu = 'feu' in tipos

    @api.depends('certificado_ids')
    def _compute_certificado_count(self):
        for rec in self:
            rec.certificado_count = len(rec.certificado_ids)

    @api.depends('ticket_ids')
    def _compute_ticket_count(self):
        for rec in self:
            rec.ticket_count = len(rec.ticket_ids)

    def write(self, vals):
        """Track state changes for audit trail."""
        if 'estado' in vals and vals['estado'] == 'vendida':
            vals['fecha_venta'] = fields.Datetime.now()
        return super().write(vals)

    def action_marcar_stock(self):
        for rec in self:
            if rec.estado == 'stock':
                raise UserError(_('La máquina ya se encuentra en estado STOCK.'))
            rec.estado = 'stock'

    def action_marcar_vendida(self):
        for rec in self:
            if rec.estado == 'vendida':
                raise UserError(_('La máquina ya se encuentra en estado VENDIDA.'))
            rec.estado = 'vendida'

    def action_view_certificados(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Certificados de %s', self.name),
            'res_model': 'pv.certificado',
            'view_mode': 'list,form',
            'domain': [('maquina_id', '=', self.id)],
            'context': {'default_maquina_id': self.id},
        }

    def action_view_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tickets de %s', self.name),
            'res_model': 'pv.ticket',
            'view_mode': 'list,form',
            'domain': [('maquina_id', '=', self.id)],
            'context': {'default_maquina_id': self.id},
        }

    def action_transferir_concesionario(self):
        """Transfer machine to another dealer. Only current dealer or admin."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Transferir Máquina'),
            'res_model': 'pv.maquina',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'form_view_ref': 'posventa.pv_maquina_transfer_form'},
        }
        
    def action_abrir_wizard_transferencia(self):
        return {
            'name': 'Trasladar Máquina a otro Concesionario',
            'type': 'ir.actions.act_window',
            'res_model': 'pv.transferir.maquina.wizard',
            'view_mode': 'form',
            'target': 'new', # Abre el formato Pop-up
            'context': {'default_maquina_id': self.id}
        }