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
    fecha_liberacion = fields.Date(
        string='Fecha de Liberación / Inicio Plazo',
        default=fields.Date.context_today,
        help='Fecha en la que la máquina fue liberada o transferida, base para cálculo de vencimientos de certificados.',
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

    @api.depends('certificado_ids', 'certificado_ids.tipo', 'certificado_ids.estado_certificado', 'certificado_ids.active')
    def _compute_tiene_certificados(self):
        for rec in self:
            tipos_cargados = rec.certificado_ids.filtered(lambda l: l.active and l.estado_certificado in ('vigente', 'vencido')).mapped('tipo')
            tipos_vigentes = rec.certificado_ids.filtered(lambda l: l.active and l.estado_certificado == 'vigente').mapped('tipo')
            rec.tiene_cpm = 'cpm' in tipos_vigentes
            rec.tiene_fru = 'fru' in tipos_cargados
            rec.tiene_feu = 'feu' in tipos_cargados

    @api.depends('certificado_ids', 'certificado_ids.estado_certificado', 'certificado_ids.active')
    def _compute_certificado_count(self):
        for rec in self:
            rec.certificado_count = len(rec.certificado_ids.filtered(lambda l: l.active and l.estado_certificado == 'vigente'))

    @api.depends('ticket_ids')
    def _compute_ticket_count(self):
        for rec in self:
            rec.ticket_count = len(rec.ticket_ids)

    def write(self, vals):
        """Track state changes and restrict modification permissions."""
        if 'estado' in vals and vals['estado'] == 'vendida':
            vals['fecha_venta'] = fields.Datetime.now()

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

    @api.model
    def get_portal_list_data(self, search_term='', estado_filter=''):
        """Return machine list data for the concesionario portal."""
        concesionario = self.env['pv.concesionario'].search([('user_id', '=', self.env.uid)], limit=1)
        if not concesionario:
            return []

        if estado_filter == 'pendiente':
            domain = [
                '|',
                    '&', ('concesionario_id', '=', concesionario.id), ('estado', '=', 'pendiente'),
                    '&', ('concesionario_destino_id', '=', concesionario.id), ('estado', '=', 'pendiente')
            ]
        else:
            domain = [('concesionario_id', '=', concesionario.id)]
            if estado_filter:
                domain.append(('estado', '=', estado_filter))

        if search_term:
            domain.append('|')
            domain.append(('of', 'ilike', search_term))
            domain.append(('name', 'ilike', search_term))

        maquinas = self.search(domain, order='create_date desc', limit=100)
        result = []
        for m in maquinas:
            result.append({
                'id': m.id,
                'name': m.name or '',
                'of': m.of or '',
                'tipo': m.tipo or '',
                'tipo_label': dict(TIPO_MAQUINA).get(m.tipo, ''),
                'estado': m.estado or '',
                'estado_label': dict(ESTADO_MAQUINA).get(m.estado, ''),
                'cliente': m.cliente_id.name or '',
                'tiene_fru': m.tiene_fru,
                'tiene_feu': m.tiene_feu,
                'tiene_cpm': m.tiene_cpm,
                'es_pendiente_transferencia': m.estado == 'pendiente',
                'proximo_certificado': m._get_proximo_certificado_info(),
            })
        return result

    def _get_proximo_certificado_info(self):
        """Calcula el próximo certificado pendiente de cargar para la máquina y su countdown nominal."""
        self.ensure_one()
        from datetime import timedelta
        hoy = fields.Date.today()
        param_obj = self.env['ir.config_parameter'].sudo()
        raw_base = self.fecha_liberacion or (fields.Date.to_date(self.create_date) if self.create_date else hoy)
        base_date = fields.Date.to_date(raw_base) or hoy

        if not self.tiene_fru:
            try:
                fru_days = int(param_obj.get_param('posventa.fru_expiration_days', 10))
            except ValueError:
                fru_days = 10
            fecha_limite = base_date + timedelta(days=fru_days)
            dias_restantes = (fecha_limite - hoy).days
            if dias_restantes > 0:
                estado = 'en_termino'
            elif dias_restantes == 0:
                estado = 'vence_hoy'
            else:
                estado = 'vencido'
            return {
                'tipo': 'fru',
                'tipo_label': 'FRU — Formulario de Recepción de Unidad',
                'fecha_limite': str(fecha_limite),
                'dias_restantes': dias_restantes,
                'estado': estado,
            }
        elif not self.tiene_feu:
            try:
                feu_days = int(param_obj.get_param('posventa.feu_expiration_days', 20))
            except ValueError:
                feu_days = 20
            fecha_limite = base_date + timedelta(days=feu_days)
            dias_restantes = (fecha_limite - hoy).days
            if dias_restantes > 0:
                estado = 'en_termino'
            elif dias_restantes == 0:
                estado = 'vence_hoy'
            else:
                estado = 'vencido'
            return {
                'tipo': 'feu',
                'tipo_label': 'FEU — Formulario de Entrega de Unidad',
                'fecha_limite': str(fecha_limite),
                'dias_restantes': dias_restantes,
                'estado': estado,
            }
        elif not self.tiene_cpm:
            return {
                'tipo': 'cpm',
                'tipo_label': 'CPM — Certificado de Puesta en Marcha',
                'fecha_limite': False,
                'dias_restantes': 0,
                'estado': 'cpm',
            }
        else:
            return {
                'tipo': False,
                'tipo_label': 'Máquina Completa (CPM Activo)',
                'fecha_limite': False,
                'dias_restantes': 0,
                'estado': 'completa',
            }

    def get_portal_detail_data(self):
        """Return detailed machine data for the concesionario portal."""
        self.ensure_one()
        certificados = []
        for c in self.certificado_ids.filtered(lambda x: x.active).sorted('fecha', reverse=True):
            if c.estado_certificado == 'vigente':
                if (c.dias_retraso_carga or 0) > 0:
                    tag_label = _('Vencido luego de 1 día') if c.dias_retraso_carga == 1 else _('Vencido luego de %s días') % c.dias_retraso_carga
                    tag_badge = 'danger'
                else:
                    tag_label = _('Vigente')
                    tag_badge = 'success'
            elif c.estado_certificado == 'vencido':
                tag_label = _('Vencido')
                tag_badge = 'danger'
            elif c.estado_certificado == 'archivado_traslado':
                tag_label = _('Archivado por Traslado')
                tag_badge = 'warning'
            elif c.estado_certificado in ('archivado_manual', 'legacy'):
                tag_label = _('Archivado Manualmente')
                tag_badge = 'secondary'
            else:
                tag_label = dict(self.env['pv.certificado']._fields['estado_certificado'].selection).get(c.estado_certificado, c.estado_certificado)
                tag_badge = 'secondary'

            certificados.append({
                'id': c.id,
                'tipo': c.tipo,
                'tipo_label': dict(self.env['pv.certificado']._fields['tipo'].selection).get(c.tipo, ''),
                'fecha': str(c.fecha) if c.fecha else '',
                'fecha_vencimiento': str(c.fecha_vencimiento) if c.fecha_vencimiento else '',
                'fecha_limite_vigencia': str(c.fecha_limite_vigencia) if c.fecha_limite_vigencia else '',
                'dias_para_vencer': c.dias_para_vencer,
                'dias_retraso_carga': c.dias_retraso_carga,
                'estado_certificado': c.estado_certificado,
                'estado_certificado_label': tag_label,
                'tag_badge': tag_badge,
                'concesionario_name': c.concesionario_id.name or '',
                'archivo_nombre': c.archivo_nombre or '',
                'active': c.active,
            })
        tickets = []
        for t in self.ticket_ids.sorted('create_date', reverse=True)[:20]:
            tickets.append({
                'id': t.id,
                'name': t.name or '',
                'tipo_ticket': t.tipo_ticket or '',
                'estado': t.estado or '',
                'fecha_creacion': str(t.fecha_creacion) if t.fecha_creacion else '',
                'sistema': t.sistema_id.name if t.sistema_id else '',
                'descripcion': (t.descripcion or '')[:100],
            })
        tiene_cert_vigente = any(c.active and c.estado_certificado == 'vigente' for c in self.certificado_ids)
        puede_crear_ticket = self.estado not in ('liberada', 'pendiente', 'cpm_vencido') and tiene_cert_vigente
        puede_crear_certificado = not self.tiene_cpm
        puede_transferir = self.estado not in ('liberada', 'pendiente', 'vendida', 'cpm_vencido')
        puede_liberar_maquina = self.estado in ('stock', 'vendida', 'cpm_vencido')
        es_concesionario_destino = self.es_concesionario_destino
        es_concesionario_origen = self.concesionario_id.user_id == self.env.user if self.concesionario_id else False

        return {
            'id': self.id,
            'name': self.name or '',
            'of': self.of or '',
            'tipo': self.tipo or '',
            'tipo_label': dict(TIPO_MAQUINA).get(self.tipo, ''),
            'estado': self.estado or '',
            'estado_label': dict(ESTADO_MAQUINA).get(self.estado, ''),
            'cliente': self.cliente_id.name or '',
            'ciudad': self.ciudad or '',
            'provincia': self.provincia_id.name if self.provincia_id else '',
            'tiene_fru': self.tiene_fru,
            'tiene_feu': self.tiene_feu,
            'tiene_cpm': self.tiene_cpm,
            'proximo_certificado': self._get_proximo_certificado_info(),
            'certificados': certificados,
            'tickets': tickets,
            'puede_crear_ticket': puede_crear_ticket,
            'puede_crear_certificado': puede_crear_certificado,
            'puede_transferir': puede_transferir,
            'puede_liberar_maquina': puede_liberar_maquina,
            'es_pendiente_transferencia': self.estado == 'pendiente',
            'es_concesionario_destino': es_concesionario_destino,
            'es_concesionario_origen': es_concesionario_origen,
            'concesionario_destino_name': self.concesionario_destino_id.name if self.concesionario_destino_id else '',
        }

    def action_liberar_maquina(self):
        """Retorna la máquina a estado LIBERADA y marca los certificados anteriores como 'archivado_manual'."""
        self.ensure_one()
        maquina_sudo = self.sudo()
        if maquina_sudo.estado in ('liberada', 'pendiente'):
            raise UserError(_("La máquina ya se encuentra en estado Liberada o Pendiente de transferencia."))

        certificados_a_archivar = maquina_sudo.certificado_ids.filtered(
            lambda c: c.estado_certificado in ('vigente', 'vencido')
        )
        if certificados_a_archivar:
            certificados_a_archivar.write({'estado_certificado': 'archivado_manual'})

        maquina_sudo.write({
            'estado': 'liberada',
            'fecha_liberacion': fields.Date.today(),
        })
        maquina_sudo._compute_tiene_certificados()
        maquina_sudo.message_post(
            body=_("La máquina ha sido LIBERADA por %s. Sus certificados anteriores fueron marcados como 'Archivado Manualmente'. Se puede iniciar una nueva carga de certificados."),
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
        return True

    def action_volver_a_stock(self):
        return self.action_liberar_maquina()

    def action_cancelar_transferencia(self):
        """El concesionario de origen (o admin) cancela una propuesta de traslado pendiente."""
        self.ensure_one()
        maquina_sudo = self.sudo()
        if maquina_sudo.estado != 'pendiente':
            raise UserError(_("Solo se pueden cancelar traslados en estado Pendiente."))

        # Restablecemos estado previo (stock si tenía FRU, vendida si CPM, o liberada)
        prev_estado = 'liberada'
        if maquina_sudo.tiene_cpm:
            prev_estado = 'vendida'
        elif maquina_sudo.tiene_fru:
            prev_estado = 'stock'

        maquina_sudo.write({
            'estado': prev_estado,
            'concesionario_destino_id': False,
            'provincia_destino_id': False,
            'ciudad_destino': False,
        })
        maquina_sudo.message_post(
            body=_("Solicitud de traslado CANCELADA por el concesionario de origen (%s). La máquina vuelve a estado %s.",
                   self.env.user.name, dict(ESTADO_MAQUINA).get(prev_estado, prev_estado)),
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
        return True

    @api.model
    def get_transfer_catalog_data(self):
        """Returns catalog of concesionarios and provinces for transfer modal."""
        concesionarios = self.env['pv.concesionario'].search_read([('active', '=', True)], ['id', 'name'])
        provincias = self.env['res.country.state'].search_read([('country_id.code', '=', 'AR')], ['id', 'name'])
        if not provincias:
            provincias = self.env['res.country.state'].search_read([], ['id', 'name'], limit=50)
        return {
            'concesionarios': concesionarios,
            'provincias': provincias,
        }

    def action_iniciar_transferencia_portal(self, concesionario_destino_id, provincia_destino_id, ciudad_destino):
        """Initiate transfer from portal."""
        self.ensure_one()
        if self.concesionario_id.id == concesionario_destino_id:
            raise UserError(_("La máquina ya pertenece a este concesionario."))

        self.sudo().write({
            'concesionario_destino_id': concesionario_destino_id,
            'provincia_destino_id': provincia_destino_id,
            'ciudad_destino': ciudad_destino,
            'estado': 'pendiente',
        })
        self.sudo().message_post(
            body=_('Solicitud de traslado/transferencia iniciada desde el portal hacia el concesionario %s (Pendiente de aceptación)',
                   self.env['pv.concesionario'].browse(concesionario_destino_id).name),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        return True