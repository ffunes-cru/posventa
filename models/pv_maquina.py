# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


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
]

# Estados desde los que el admin puede liberar la máquina (canje / reset)
ESTADOS_LIBERABLES = ('stock', 'vendida')

# Estados en los que no se pueden crear ni enviar tickets
ESTADOS_MAQUINA_SIN_TICKETS = ('liberada', 'pendiente')


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
    tiene_feu_vigente = fields.Boolean(
        string='Tiene FEU Vigente',
        compute='_compute_tiene_certificados',
        store=True,
    )

    # --- Solicitud de liberación (la pide el concesionario, la aprueba el admin) ---
    liberacion_solicitada = fields.Boolean(
        string='Liberación Solicitada',
        readonly=True,
        copy=False,
        tracking=True,
    )
    liberacion_motivo = fields.Text(
        string='Motivo de Liberación',
        readonly=True,
        copy=False,
    )
    liberacion_solicitante_id = fields.Many2one(
        'res.users',
        string='Liberación Solicitada por',
        readonly=True,
        copy=False,
    )
    liberacion_fecha_solicitud = fields.Datetime(
        string='Fecha de Solicitud de Liberación',
        readonly=True,
        copy=False,
    )

    active = fields.Boolean(default=True)

    _of_unique = models.Constraint(
        'UNIQUE(of)',
        'Ya existe una máquina con esta Orden de Fabricación.',
    )

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
            rec.tiene_feu_vigente = 'feu' in tipos_vigentes

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
                'create': self.estado not in ESTADOS_MAQUINA_SIN_TICKETS,
            },
        }

    # --- Chequeos de permisos ---
    def _is_pv_admin_user(self):
        return self.env.su or self.env.user.has_group('posventa.group_pv_admin')

    def _check_pv_admin(self):
        if not self._is_pv_admin_user():
            raise AccessError(_('Únicamente el Administrador de Posventa puede realizar esta acción.'))

    def _check_es_del_concesionario(self, concesionario, mensaje):
        """Permite la acción al admin o a un usuario que pertenezca al concesionario indicado."""
        if self._is_pv_admin_user():
            return
        if not concesionario or not concesionario._is_member():
            raise AccessError(mensaje)

    def _get_estado_sin_transferencia(self):
        """Estado que corresponde a la máquina según sus certificados (al cancelar/rechazar un traslado)."""
        self.ensure_one()
        if self.tiene_cpm:
            return 'vendida'
        if self.tiene_fru:
            return 'stock'
        return 'liberada'

    def action_abrir_wizard_transferencia(self):
        self.ensure_one()
        self._check_es_del_concesionario(
            self.concesionario_id, _('Solo el concesionario dueño de la máquina puede trasladarla.'))
        return {
            'name': _('Trasladar Máquina a otro Concesionario'),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.transferir.maquina.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_maquina_id': self.id},
        }

    @api.model
    def get_portal_list_data(self, search_term='', estado_filter=''):
        """Return machine list data for the concesionario portal."""
        concesionario = self.env['pv.concesionario']._get_concesionario_for_user(self.env.user)
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
                'tiene_feu_vigente': m.tiene_feu_vigente,
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
        elif not self.tiene_feu_vigente:
            return {
                'tipo': 'feu',
                'tipo_label': 'FEU — Formulario de Entrega de Unidad (Renovación Requerida)',
                'fecha_limite': False,
                'dias_restantes': 0,
                'estado': 'vencido',
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
        puede_crear_ticket = self.estado not in ESTADOS_MAQUINA_SIN_TICKETS and tiene_cert_vigente
        mi_concesionario = self.env['pv.concesionario']._get_concesionario_for_user()
        es_concesionario_origen = bool(mi_concesionario) and self.concesionario_id == mi_concesionario
        es_concesionario_destino = self.es_concesionario_destino
        puede_operar = es_concesionario_origen or self._is_pv_admin_user()
        puede_crear_certificado = not self.tiene_cpm and puede_operar
        puede_transferir = self.estado == 'stock' and not self.liberacion_solicitada and puede_operar
        puede_solicitar_liberacion = (
            self.estado in ESTADOS_LIBERABLES and not self.liberacion_solicitada and puede_operar
        )

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
            'fecha_liberacion': str(self.fecha_liberacion) if self.fecha_liberacion else '',
            'tiene_fru': self.tiene_fru,
            'tiene_feu': self.tiene_feu,
            'tiene_feu_vigente': self.tiene_feu_vigente,
            'tiene_cpm': self.tiene_cpm,
            'proximo_certificado': self._get_proximo_certificado_info(),
            'certificados': certificados,
            'tickets': tickets,
            'puede_crear_ticket': puede_crear_ticket,
            'puede_crear_certificado': puede_crear_certificado,
            'puede_transferir': puede_transferir,
            'puede_solicitar_liberacion': puede_solicitar_liberacion,
            'liberacion_solicitada': self.liberacion_solicitada,
            'liberacion_motivo': self.liberacion_motivo or '',
            'es_pendiente_transferencia': self.estado == 'pendiente',
            'es_concesionario_destino': es_concesionario_destino,
            'es_concesionario_origen': es_concesionario_origen,
            'concesionario_destino_name': self.concesionario_destino_id.name if self.concesionario_destino_id else '',
        }

    # --- Liberación ---
    def action_solicitar_liberacion(self, motivo):
        """El concesionario dueño solicita liberar la máquina; la liberación la aprueba el admin."""
        self.ensure_one()
        self._check_es_del_concesionario(
            self.concesionario_id, _('Solo el concesionario dueño de la máquina puede solicitar su liberación.'))
        motivo = (motivo or '').strip()
        if not motivo:
            raise UserError(_('Debe indicar el motivo de la solicitud de liberación.'))
        if self.estado not in ESTADOS_LIBERABLES:
            raise UserError(_('La máquina no se puede liberar en su estado actual.'))
        if self.liberacion_solicitada:
            raise UserError(_('Ya existe una solicitud de liberación pendiente para esta máquina.'))

        maquina_sudo = self.sudo()
        maquina_sudo.write({
            'liberacion_solicitada': True,
            'liberacion_motivo': motivo,
            'liberacion_solicitante_id': self.env.user.id,
            'liberacion_fecha_solicitud': fields.Datetime.now(),
        })
        admin_group = self.env.ref('posventa.group_pv_admin', raise_if_not_found=False)
        admin_partners = admin_group.sudo().all_user_ids.filtered(lambda u: not u.share).partner_id if admin_group else False
        maquina_sudo.message_post(
            body=_('%(user)s solicitó la LIBERACIÓN de la máquina. Motivo: %(motivo)s',
                   user=self.env.user.name, motivo=motivo),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            partner_ids=admin_partners.ids if admin_partners else [],
        )
        return True

    def action_aprobar_liberacion(self):
        self._check_pv_admin()
        for rec in self:
            if not rec.liberacion_solicitada:
                raise UserError(_('La máquina %s no tiene una solicitud de liberación pendiente.', rec.name))
            rec._liberar(rec.liberacion_motivo)
        return True

    def action_rechazar_liberacion(self):
        self._check_pv_admin()
        for rec in self:
            if not rec.liberacion_solicitada:
                raise UserError(_('La máquina %s no tiene una solicitud de liberación pendiente.', rec.name))
            rec.sudo()._limpiar_solicitud_liberacion()
            rec.sudo().message_post(
                body=_('Solicitud de liberación RECHAZADA por %s.', self.env.user.name),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_liberar_maquina(self, motivo):
        """Liberación directa por el admin (canje / reset), con motivo obligatorio."""
        self._check_pv_admin()
        motivo = (motivo or '').strip()
        if not motivo:
            raise UserError(_('Debe indicar el motivo de la liberación.'))
        for rec in self:
            rec._liberar(motivo)
        return True

    def action_abrir_wizard_liberacion(self):
        self.ensure_one()
        self._check_pv_admin()
        return {
            'name': _('Liberar Máquina'),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.liberar.maquina.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_maquina_id': self.id,
                'default_motivo': self.liberacion_motivo or '',
            },
        }

    def _limpiar_solicitud_liberacion(self):
        self.write({
            'liberacion_solicitada': False,
            'liberacion_motivo': False,
            'liberacion_solicitante_id': False,
            'liberacion_fecha_solicitud': False,
        })

    def _liberar(self, motivo):
        """Retorna la máquina a LIBERADA y archiva sus certificados vigentes/vencidos."""
        self.ensure_one()
        maquina_sudo = self.sudo()
        if maquina_sudo.estado not in ESTADOS_LIBERABLES:
            raise UserError(_('La máquina no se puede liberar en su estado actual.'))

        certificados_a_archivar = maquina_sudo.certificado_ids.filtered(
            lambda c: c.estado_certificado in ('vigente', 'vencido')
        )
        if certificados_a_archivar:
            certificados_a_archivar.write({'estado_certificado': 'archivado_manual'})

        maquina_sudo.write({
            'estado': 'liberada',
            'fecha_liberacion': fields.Date.today(),
        })
        maquina_sudo._limpiar_solicitud_liberacion()
        maquina_sudo.message_post(
            body=_("La máquina fue LIBERADA por %(user)s. Motivo: %(motivo)s. Sus certificados anteriores fueron "
                   "marcados como 'Archivado Manualmente' y se puede iniciar una nueva carga de certificados.",
                   user=self.env.user.name, motivo=motivo),
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )

    # --- Transferencias ---
    def action_cancelar_transferencia(self):
        """El concesionario de origen (o admin) cancela una propuesta de traslado pendiente."""
        self.ensure_one()
        self._check_es_del_concesionario(
            self.concesionario_id, _('Solo el concesionario de origen puede cancelar el traslado.'))
        maquina_sudo = self.sudo()
        if maquina_sudo.estado != 'pendiente':
            raise UserError(_("Solo se pueden cancelar traslados en estado Pendiente."))

        prev_estado = maquina_sudo._get_estado_sin_transferencia()
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
        return self._iniciar_transferencia(
            self.env['pv.concesionario'].browse(int(concesionario_destino_id or 0)),
            self.env['res.country.state'].browse(int(provincia_destino_id or 0)),
            ciudad_destino,
        )

    def _iniciar_transferencia(self, concesionario_destino, provincia_destino, ciudad_destino):
        """Propone el traslado de la máquina a otro concesionario (queda Pendiente de aceptación)."""
        self.ensure_one()
        self._check_es_del_concesionario(
            self.concesionario_id, _('Solo el concesionario dueño de la máquina puede trasladarla.'))
        if self.estado != 'stock':
            raise UserError(_("Solo se pueden trasladar máquinas en estado STOCK."))
        if self.liberacion_solicitada:
            raise UserError(_("La máquina tiene una solicitud de liberación pendiente."))
        concesionario_destino = concesionario_destino.sudo().exists()
        if not concesionario_destino or not concesionario_destino.active:
            raise UserError(_("Debe seleccionar un concesionario destino válido."))
        if concesionario_destino == self.concesionario_id:
            raise UserError(_("La máquina ya pertenece a este concesionario."))
        ciudad_destino = (ciudad_destino or '').strip()
        if not provincia_destino.exists() or not ciudad_destino:
            raise UserError(_("Debe indicar la provincia y ciudad de destino."))

        self.sudo().write({
            'concesionario_destino_id': concesionario_destino.id,
            'provincia_destino_id': provincia_destino.id,
            'ciudad_destino': ciudad_destino,
            'estado': 'pendiente',
        })
        self.sudo().message_post(
            body=_('Solicitud de traslado enviada a %s por %s (Pendiente de aceptación).',
                   concesionario_destino.name, self.env.user.name),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        return True
