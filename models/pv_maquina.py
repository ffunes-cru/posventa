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
    ('pendiente', 'PENDIENTE DE TRANSFERENCIA'),
    ('liberada', 'LIBERADA'),
    ('stock', 'STOCK'),
    ('vendida', 'VENDIDA'),
    ('cpm_vencido', 'CPM VENCIDO'),
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

    is_pv_admin = fields.Boolean(compute='_compute_is_pv_admin', store=False)

    def _compute_is_pv_admin(self):
        # Evaluamos el grupo una sola vez para el usuario actual
        has_group = self.env.user.has_group('posventa.group_pv_admin')
        for record in self:
            record.is_pv_admin = has_group

    @api.depends('tipo', 'of')
    def _compute_name(self):
        for rec in self:
            tipo_label = dict(TIPO_MAQUINA).get(rec.tipo, '')
            rec.name = f"{tipo_label} - {rec.of}" if rec.of else ''

    @api.depends('certificado_ids', 'certificado_ids.tipo', 'certificado_ids.active')
    def _compute_tiene_certificados(self):
        for rec in self:
            tipos = rec.certificado_ids.filtered(lambda l: l.active).mapped('tipo')
            rec.tiene_cpm = 'cpm' in tipos
            rec.tiene_fru = 'fru' in tipos
            rec.tiene_feu = 'feu' in tipos

    @api.depends('certificado_ids')
    def _compute_certificado_count(self):
        for rec in self:
            rec.certificado_count = len(rec.certificado_ids.filtered(lambda l: l.active))

    @api.depends('ticket_ids')
    def _compute_ticket_count(self):
        for rec in self:
            rec.ticket_count = len(rec.ticket_ids)

    def write(self, vals):
        """Track state changes and restrict modification permissions."""
        if 'estado' in vals and vals['estado'] == 'vendida':
            vals['fecha_venta'] = fields.Datetime.now()

        # Si cambia el concesionario (transferencia o edición manual)
        if 'concesionario_id' in vals:
            for rec in self:
                if rec.concesionario_id and rec.concesionario_id.id != vals['concesionario_id']:
                    # Archivar certificados activos de forma segura (bypasseando reglas de registro del usuario)
                    self.env['pv.certificado'].sudo().search([('maquina_id', '=', rec.id)]).write({'active': False})
                    rec.modified(['certificado_ids'])
            # Reseteamos los flags y devolvemos la máquina a estado liberada
            vals.update({
                'tiene_fru': False,
                'tiene_feu': False,
                'tiene_cpm': False,
                'estado': 'liberada',
            })

        # Restricción: Concesionarios o Staff no pueden cambiar datos básicos del registro
        campos_restringidos = {'of', 'tipo', 'concesionario_id', 'cliente_id', 'ciudad', 'provincia_id'}
        if campos_restringidos.intersection(vals.keys()):
            if not self.env.su and not self.env.user.has_group('posventa.group_pv_admin'):
                raise UserError(_('Únicamente el Administrador de Posventa puede crear o modificar los datos de una máquina.'))

        return super().write(vals)

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
            'context': {
                'default_maquina_id': self.id,
                'create': self.estado not in ('liberada', 'pendiente', 'cpm_vencido'),
            },
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