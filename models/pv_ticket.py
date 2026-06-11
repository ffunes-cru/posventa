# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


ESTADO_TICKET = [
    ('borrador', 'BORRADOR'),
    ('abierto', 'ABIERTO'),
    ('en_proceso', 'EN PROCESO'),
    ('aceptado', 'ACEPTADO'),
    ('rechazado', 'RECHAZADO'),
    ('cerrado', 'CERRADO'),
]

TIPO_TICKET = [
    ('pre_pm', 'Pre Puesta en Marcha'),
    ('post_pm', 'Post Puesta en Marcha'),
]

PRIORIDAD = [
    ('baja', 'Baja'),
    ('media', 'Media'),
    ('alta', 'Alta'),
    ('critica', 'Crítica'),
]


class PvTicket(models.Model):
    _name = 'pv.ticket'
    _description = 'Ticket de Reclamo Posventa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # --- Identificación ---
    name = fields.Char(
        string='Número',
        readonly=True,
        default=lambda self: _('Nuevo'),
        copy=False,
        tracking=True,
    )
    tipo_ticket = fields.Selection(
        TIPO_TICKET,
        string='Tipo de Ticket',
        required=True,
        default='post_pm',
        tracking=True,
    )

    # --- Datos de máquina (heredados) ---
    maquina_id = fields.Many2one(
        'pv.maquina',
        string='Máquina',
        required=True,
        tracking=True,
    )
    of = fields.Char(
        string='Orden de Fabricación',
        related='maquina_id.of',
        store=True,
    )
    tipo_maquina = fields.Selection(
        related='maquina_id.tipo',
        store=True,
        string='Tipo de Máquina',
    )
    cliente_id = fields.Many2one(
        related='maquina_id.cliente_id',
        store=True,
        string='Cliente',
    )
    concesionario_id = fields.Many2one(
        related='maquina_id.concesionario_id',
        store=True,
        string='Concesionario',
    )

    # --- Operador ---
    operador_id = fields.Many2one(
        'pv.concesionario.contacto',
        string='Cargado por',
        domain="[('concesionario_id', '=', concesionario_id)]",
        tracking=True,
    )

    # --- Clasificación del desvío ---
    sistema_id = fields.Many2one(
        'pv.sistema',
        string='Sistema involucrado',
        tracking=True,
    )
    subsistema_id = fields.Many2one(
        'pv.subsistema',
        string='Subsistema',
        domain="[('sistema_id', '=', sistema_id)]",
        tracking=True,
    )
    problema_id = fields.Many2one(
        'pv.problema',
        string='Problema',
        domain="[('subsistema_id', '=', subsistema_id)]",
        tracking=True,
    )
    campo_extra_ids = fields.One2many(
        'pv.ticket.campo.valor',
        'ticket_id',
        string='Información adicional',
    )
    placeholder_descripcion = fields.Text(
        related='subsistema_id.placeholder_descripcion',
        string='Guía para descripción',
    )

    # --- Descripción del reclamo ---
    descripcion = fields.Text(
        string='Descripción del reclamo',
        tracking=True,
    )
    acciones_realizadas = fields.Text(
        string='Acciones realizadas',
        tracking=True,
    )
    ubicacion_actual = fields.Char(
        string='Ubicación actual',
    )
    hectareas = fields.Float(
        string='Hectáreas',
    )
    multimedia_url = fields.Char(
        string='Multimedia (link Google Drive)',
    )

    # --- Estado y asignación ---
    estado = fields.Selection(
        ESTADO_TICKET,
        string='Estado',
        default='borrador',
        required=True,
        tracking=True,
        group_expand='_group_expand_estados',
    )
    responsable_id = fields.Many2one(
        'res.users',
        string='Responsable',
        tracking=True,
    )
    motivo_rechazo = fields.Text(
        string='Motivo de rechazo',
        tracking=True,
    )
    prioridad = fields.Selection(
        PRIORIDAD,
        string='Prioridad',
        default='media',
        tracking=True,
    )

    # --- Campos SAP (habilitados en estado aceptado) ---
    sap_numero_aviso = fields.Char(
        string='Nro. Aviso SAP',
        tracking=True,
    )
    sap_numero_orden = fields.Char(
        string='Nro. Orden SAP',
        tracking=True,
    )
    sap_centro = fields.Char(
        string='Centro SAP',
    )
    sap_material = fields.Char(
        string='Material SAP',
    )
    sap_notas = fields.Text(
        string='Notas SAP',
    )

    # --- Medidas y seguimiento ---
    medida_ids = fields.One2many(
        'pv.ticket.medida',
        'ticket_id',
        string='Medidas / Seguimiento',
    )
    medida_count = fields.Integer(
        compute='_compute_medida_count',
        store=True,
    )
    medidas_vencidas_count = fields.Integer(
        compute='_compute_medida_count',
        store=True,
    )

    # --- KPIs ---
    fecha_creacion = fields.Datetime(
        string='Fecha de creación',
        default=fields.Datetime.now,
        readonly=True,
    )
    fecha_primera_atencion = fields.Datetime(
        string='Primera atención',
        readonly=True,
    )
    fecha_solucion = fields.Datetime(
        string='Fecha de solución',
        readonly=True,
    )
    fecha_cierre = fields.Datetime(
        string='Fecha de cierre',
        readonly=True,
    )
    t1_horas = fields.Float(
        string='T1 (horas)',
        compute='_compute_kpis',
        store=True,
        help='Tiempo de primera atención: desde creación hasta primera asignación',
    )
    t2_horas = fields.Float(
        string='T2 (horas)',
        compute='_compute_kpis',
        store=True,
        help='Tiempo de solución: desde creación hasta contención/solución',
    )
    t3_horas = fields.Float(
        string='T3 (horas)',
        compute='_compute_kpis',
        store=True,
        help='Tiempo de cierre definitivo: desde creación hasta cierre (interno)',
    )

    # --- Color for kanban ---
    color = fields.Integer(string='Color')
    kanban_state = fields.Selection([
        ('normal', 'En curso'),
        ('done', 'Listo'),
        ('blocked', 'Bloqueado'),
    ], default='normal')

    @api.model
    def _group_expand_estados(self, states, domain):
        """Show all states in kanban even if empty."""
        return [key for key, _ in ESTADO_TICKET]

    @api.depends('medida_ids', 'medida_ids.estado')
    def _compute_medida_count(self):
        for rec in self:
            rec.medida_count = len(rec.medida_ids)
            rec.medidas_vencidas_count = len(
                rec.medida_ids.filtered(lambda m: m.estado == 'vencida')
            )

    @api.depends('fecha_creacion', 'fecha_primera_atencion',
                 'fecha_solucion', 'fecha_cierre')
    def _compute_kpis(self):
        for rec in self:
            rec.t1_horas = 0
            rec.t2_horas = 0
            rec.t3_horas = 0
            if rec.fecha_creacion and rec.fecha_primera_atencion:
                delta = rec.fecha_primera_atencion - rec.fecha_creacion
                rec.t1_horas = round(delta.total_seconds() / 3600, 2)
            if rec.fecha_creacion and rec.fecha_solucion:
                delta = rec.fecha_solucion - rec.fecha_creacion
                rec.t2_horas = round(delta.total_seconds() / 3600, 2)
            if rec.fecha_creacion and rec.fecha_cierre:
                delta = rec.fecha_cierre - rec.fecha_creacion
                rec.t3_horas = round(delta.total_seconds() / 3600, 2)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('pv.ticket') or _('Nuevo')
        return super().create(vals_list)

    @api.constrains('tipo_ticket', 'maquina_id')
    def _check_ticket_requirements(self):
        for rec in self:
            if rec.estado == 'borrador':
                continue

            if rec.tipo_ticket == 'post_pm' and rec.maquina_id:
                if not rec.maquina_id.tiene_cpm:
                    raise ValidationError(_(
                        'No se puede crear un ticket Post Puesta en Marcha '
                        'sin que la máquina tenga un CPM cargado.\n'
                        'Máquina: %s\n\n'
                        'Debe cargar primero el Certificado de Puesta en Marcha (CPM).',
                        rec.maquina_id.name
                    ))

    @api.onchange('sistema_id')
    def _onchange_sistema_id(self):
        """Clear subsistema and problema when sistema changes."""
        self.subsistema_id = False
        self.problema_id = False

    @api.onchange('subsistema_id')
    def _onchange_subsistema_id(self):
        """Clear problema and regenerate extra fields when subsistema changes."""
        self.problema_id = False
        # Regenerate extra field values for new subsistema
        if self.subsistema_id and self.subsistema_id.campo_extra_ids:
            new_campos = []
            for campo in self.subsistema_id.campo_extra_ids:
                new_campos.append((0, 0, {
                    'campo_id': campo.id,
                    'valor': '',
                }))
            self.campo_extra_ids = [(5, 0, 0)] + new_campos
        else:
            self.campo_extra_ids = [(5, 0, 0)]

    def action_enviar_ticket(self):
        """ El concesionario envía el ticket al Staff (BORRADOR -> ABIERTO) """
        for rec in self:
            if rec.estado != 'borrador':
                raise UserError(_('Solo se pueden enviar tickets en estado Borrador.'))
            
            # Al intentar enviar, Odoo ejecutará el @api.constrains automáticamente
            rec.write({'estado': 'abierto'})
            rec.message_post(
                body=_('Ticket enviado a revisión técnica por el concesionario.'),
                message_type='notification',
            )

    # --- State transitions ---
    def action_tomar_ticket(self):
        """Staff takes the ticket (ABIERTO -> EN_PROCESO)."""
        for rec in self:
            if rec.estado != 'abierto':
                raise UserError(_('Solo se pueden tomar tickets en estado ABIERTO.'))
            rec.write({
                'estado': 'en_proceso',
                'responsable_id': self.env.user.id,
                'fecha_primera_atencion': fields.Datetime.now(),
            })
            rec.message_post(
                body=_('Ticket tomado por %s', self.env.user.name),
                message_type='notification',
            )

    def action_aceptar_ticket(self):
        """Accept the claim and open the email wizard like standard Sales does."""
        self.ensure_one()
        if self.estado != 'en_proceso':
            raise UserError(_('Solo se pueden aceptar tickets EN PROCESO.'))
            
        self.write({
            'estado': 'aceptado',
            'fecha_solucion': fields.Datetime.now(),
        })
        self.message_post(
            body=_('Reclamo aceptado y validado'),
            message_type='notification',
        )
        
        template = self.env.ref('posventa.mail_template_ticket_aceptado', raise_if_not_found=False)
        
        # 1. Buscamos el res.partner real del concesionario
        partner = self.concesionario_id.partner_id or (self.concesionario_id.user_id.partner_id if self.concesionario_id.user_id else False)
        partner_id = partner.id if partner else False

        # 2. Armamos el contexto idéntico al estándar de Ventas
        ctx = {
            'default_model': 'pv.ticket',
            'default_res_ids': self.ids,
            'default_composition_mode': 'comment',
            'default_template_id': template.id if template else False,
            'force_email': True,
        }
        
        # 3. Si encontramos al partner, lo obligamos a bajarse como destinatario predeterminado
        if partner_id:
            ctx['default_partner_ids'] = [partner_id]

        return {
            'name': _('Enviar correo'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    def action_rechazar_ticket(self):
        """Reject the claim and open the email wizard like standard Sales does."""
        self.ensure_one()
        if self.estado != 'en_proceso':
            raise UserError(_('Solo se pueden rechazar tickets EN PROCESO.'))
        if not self.motivo_rechazo:
            raise UserError(_('Debe indicar el motivo de rechazo.'))
            
        self.write({
            'estado': 'rechazado',
            'fecha_cierre': fields.Datetime.now(),
        })
        self.message_post(
            body=_('Reclamo rechazado. Motivo: %s', self.motivo_rechazo),
            message_type='notification',
        )

        template = self.env.ref('posventa.mail_template_ticket_rechazado', raise_if_not_found=False)
        
        # Buscamos el res.partner real del concesionario
        partner = self.concesionario_id.partner_id or (self.concesionario_id.user_id.partner_id if self.concesionario_id.user_id else False)
        partner_id = partner.id if partner else False

        ctx = {
            'default_model': 'pv.ticket',
            'default_res_ids': self.ids,
            'default_composition_mode': 'comment',
            'default_template_id': template.id if template else False,
            'force_email': True,
        }
        
        if partner_id:
            ctx['default_partner_ids'] = [partner_id]

        return {
            'name': _('Enviar correo'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }
        
    def action_cerrar_ticket(self):
        """Close the ticket (ACEPTADO -> CERRADO)."""
        for rec in self:
            if rec.estado != 'aceptado':
                raise UserError(_('Solo se pueden cerrar tickets ACEPTADOS.'))
            rec.write({
                'estado': 'cerrado',
                'fecha_cierre': fields.Datetime.now(),
            })
            rec.message_post(
                body=_('Ticket cerrado. Expediente completo.'),
                message_type='notification',
            )

    def action_view_medidas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Medidas de %s', self.name),
            'res_model': 'pv.ticket.medida',
            'view_mode': 'list,form',
            'domain': [('ticket_id', '=', self.id)],
            'context': {'default_ticket_id': self.id},
        }

    def _message_get_default_recipients(self, with_cc=False, all_tos=False):
        res = super()._message_get_default_recipients(with_cc=with_cc, all_tos=all_tos)
        for rec in self:
            if rec.concesionario_id and rec.concesionario_id.partner_id:
                res[rec.id].update({
                    'partner_ids': [rec.concesionario_id.partner_id.id],
                    'email_to': '',
                })
        return res
