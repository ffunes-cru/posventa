# Part of Crucianelli Posventa Module
from datetime import timedelta

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

# Datos de fábrica que solo modifica el Administrador de Posventa
CAMPOS_SOLO_ADMIN = {'of', 'tipo', 'concesionario_id', 'cliente_id', 'ciudad', 'provincia_id'}


class PvMaquina(models.Model):
    _name = 'pv.maquina'
    _description = 'Máquina Posventa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    of = fields.Char(string='Orden de Fabricación', required=True, tracking=True, index=True)
    tipo = fields.Selection(TIPO_MAQUINA, string='Tipo de Máquina', required=True, tracking=True)
    cliente_id = fields.Many2one('res.partner', string='Cliente', tracking=True)
    concesionario_id = fields.Many2one('pv.concesionario', string='Concesionario', required=True, tracking=True)
    ciudad = fields.Char(string='Ciudad', tracking=True)
    provincia_id = fields.Many2one('res.country.state', string='Provincia', tracking=True)
    estado = fields.Selection(ESTADO_MAQUINA, string='Estado', default='liberada', required=True, tracking=True)
    fecha_liberacion = fields.Date(
        string='Fecha de Liberación / Inicio Plazo',
        default=fields.Date.context_today,
        help='Fecha en la que la máquina fue liberada o transferida, base para cálculo de vencimientos de certificados.',
    )
    fecha_venta = fields.Datetime(string='Fecha de Venta', readonly=True,
                                  help='Fecha en la que la máquina pasó a estado VENDIDA')
    active = fields.Boolean(default=True)

    certificado_ids = fields.One2many('pv.certificado', 'maquina_id', string='Certificados')
    certificado_count = fields.Integer(compute='_compute_certificado_count')
    ticket_ids = fields.One2many('pv.ticket', 'maquina_id', string='Tickets')
    ticket_count = fields.Integer(compute='_compute_ticket_count')

    tiene_cpm = fields.Boolean(string='Tiene CPM', compute='_compute_tiene_certificados', store=True)
    tiene_fru = fields.Boolean(string='Tiene FRU', compute='_compute_tiene_certificados', store=True)
    tiene_feu = fields.Boolean(string='Tiene FEU', compute='_compute_tiene_certificados', store=True)
    tiene_feu_vigente = fields.Boolean(string='Tiene FEU Vigente', compute='_compute_tiene_certificados', store=True)

    # --- Traslado propuesto (pendiente de aceptación del destino) ---
    concesionario_destino_id = fields.Many2one('pv.concesionario', string='Concesionario Destino', readonly=True)
    provincia_destino_id = fields.Many2one('res.country.state', string='Provincia Destino', readonly=True)
    ciudad_destino = fields.Char(string='Ciudad Destino', readonly=True)
    es_concesionario_destino = fields.Boolean(compute='_compute_es_concesionario_destino')

    # --- Solicitud de liberación (la pide el concesionario, la aprueba el admin) ---
    liberacion_solicitada = fields.Boolean(string='Liberación Solicitada', readonly=True, copy=False, tracking=True)
    liberacion_motivo = fields.Text(string='Motivo de Liberación', readonly=True, copy=False)
    liberacion_solicitante_id = fields.Many2one('res.users', string='Liberación Solicitada por', readonly=True, copy=False)
    liberacion_fecha_solicitud = fields.Datetime(string='Fecha de Solicitud de Liberación', readonly=True, copy=False)

    is_pv_admin = fields.Boolean(compute='_compute_is_pv_admin')

    _of_unique = models.Constraint('UNIQUE(of)', 'Ya existe una máquina con esta Orden de Fabricación.')

    # --- Computes ---
    @api.depends('tipo', 'of')
    def _compute_name(self):
        for rec in self:
            rec.name = f"{dict(TIPO_MAQUINA).get(rec.tipo, '')} - {rec.of}" if rec.of else ''

    @api.depends('certificado_ids.tipo', 'certificado_ids.estado_certificado', 'certificado_ids.active')
    def _compute_tiene_certificados(self):
        for rec in self:
            activos = rec.certificado_ids.filtered('active')
            cargados = activos.filtered(lambda c: c.estado_certificado in ('vigente', 'vencido')).mapped('tipo')
            vigentes = activos.filtered(lambda c: c.estado_certificado == 'vigente').mapped('tipo')
            rec.tiene_cpm = 'cpm' in vigentes
            rec.tiene_fru = 'fru' in cargados
            rec.tiene_feu = 'feu' in cargados
            rec.tiene_feu_vigente = 'feu' in vigentes

    @api.depends('certificado_ids.estado_certificado', 'certificado_ids.active')
    def _compute_certificado_count(self):
        for rec in self:
            rec.certificado_count = len(rec._get_certificados_vigentes())

    @api.depends('ticket_ids')
    def _compute_ticket_count(self):
        for rec in self:
            rec.ticket_count = len(rec.ticket_ids)

    def _compute_es_concesionario_destino(self):
        mi_concesionario = self.env['pv.concesionario']._get_concesionario_for_user()
        for rec in self:
            rec.es_concesionario_destino = bool(mi_concesionario) and rec.concesionario_destino_id == mi_concesionario

    def _compute_is_pv_admin(self):
        self.is_pv_admin = self._is_pv_admin_user()

    def write(self, vals):
        if vals.get('estado') == 'vendida':
            vals['fecha_venta'] = fields.Datetime.now()
        if CAMPOS_SOLO_ADMIN.intersection(vals) and not self._is_pv_admin_user():
            raise UserError(_('Únicamente el Administrador de Posventa puede crear o modificar los datos de una máquina.'))
        return super().write(vals)

    # --- Permisos ---
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

    # --- Certificados ---
    def _get_certificados_vigentes(self):
        return self.certificado_ids.filtered(lambda c: c.active and c.estado_certificado == 'vigente')

    def _get_proximo_certificado_info(self):
        """Próximo certificado a cargar y su plazo nominal (alertas del portal)."""
        self.ensure_one()
        Certificado = self.env['pv.certificado']
        tipo_label = dict(Certificado._fields['tipo'].selection)
        if not self.tiene_fru or not self.tiene_feu:
            tipo = 'fru' if not self.tiene_fru else 'feu'
            fecha_limite = Certificado._get_plazo_nominal_carga(tipo, self)
            dias_restantes = (fecha_limite - fields.Date.today()).days
            return {
                'tipo': tipo,
                'tipo_label': tipo_label[tipo],
                'fecha_limite': str(fecha_limite),
                'dias_restantes': dias_restantes,
                'estado': 'en_termino' if dias_restantes > 0 else 'vence_hoy' if dias_restantes == 0 else 'vencido',
            }
        if not self.tiene_feu_vigente:
            return {'tipo': 'feu', 'tipo_label': _('%s (renovación requerida)', tipo_label['feu']),
                    'fecha_limite': False, 'dias_restantes': 0, 'estado': 'vencido'}
        if not self.tiene_cpm:
            return {'tipo': 'cpm', 'tipo_label': tipo_label['cpm'],
                    'fecha_limite': False, 'dias_restantes': 0, 'estado': 'cpm'}
        return {'tipo': False, 'tipo_label': _('Máquina completa (CPM activo)'),
                'fecha_limite': False, 'dias_restantes': 0, 'estado': 'completa'}

    def get_portal_detail_data(self):
        """Datos de la máquina para el portal web y sus asistentes OWL."""
        self.ensure_one()
        mi_concesionario = self.env['pv.concesionario']._get_concesionario_for_user()
        es_origen = bool(mi_concesionario) and self.concesionario_id == mi_concesionario
        puede_operar = es_origen or self._is_pv_admin_user()
        sin_tramite = not self.liberacion_solicitada and puede_operar
        return {
            'id': self.id,
            'name': self.name or '',
            'of': self.of or '',
            'tipo_label': dict(TIPO_MAQUINA).get(self.tipo, ''),
            'cliente': self.cliente_id.name or '',
            'ciudad': self.ciudad or '',
            'provincia': self.provincia_id.name or '',
            'fecha_liberacion': str(self.fecha_liberacion or ''),
            'tiene_fru': self.tiene_fru,
            'tiene_feu': self.tiene_feu,
            'tiene_cpm': self.tiene_cpm,
            'proximo_certificado': self._get_proximo_certificado_info(),
            'certificados': [
                c._get_portal_values() for c in self.certificado_ids.filtered('active').sorted('fecha', reverse=True)
            ],
            'tickets': [{
                'id': t.id,
                'name': t.name or '',
                'estado': t.estado,
                'descripcion': (t.descripcion or '')[:100],
            } for t in self.ticket_ids.sorted('create_date', reverse=True)[:20]],
            'puede_crear_ticket': self.estado not in ESTADOS_MAQUINA_SIN_TICKETS and bool(self._get_certificados_vigentes()),
            'puede_crear_certificado': not self.tiene_cpm and self.estado != 'pendiente' and puede_operar,
            'puede_transferir': self.estado == 'stock' and sin_tramite,
            'puede_solicitar_liberacion': self.estado in ESTADOS_LIBERABLES and sin_tramite,
            'liberacion_solicitada': self.liberacion_solicitada,
            'liberacion_motivo': self.liberacion_motivo or '',
            'es_pendiente_transferencia': self.estado == 'pendiente',
            'es_concesionario_destino': self.es_concesionario_destino,
            'es_concesionario_origen': es_origen,
            'concesionario_destino_name': self.concesionario_destino_id.name or '',
        }

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
            'context': {'default_maquina_id': self.id, 'create': self.estado not in ESTADOS_MAQUINA_SIN_TICKETS},
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

        self.sudo().write({
            'liberacion_solicitada': True,
            'liberacion_motivo': motivo,
            'liberacion_solicitante_id': self.env.user.id,
            'liberacion_fecha_solicitud': fields.Datetime.now(),
        })
        admins = self.env.ref('posventa.group_pv_admin').sudo().all_user_ids.filtered(lambda u: not u.share)
        self.sudo().message_post(
            body=_('%(user)s solicitó la LIBERACIÓN de la máquina. Motivo: %(motivo)s',
                   user=self.env.user.name, motivo=motivo),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            partner_ids=admins.partner_id.ids,
        )
        return True

    def action_aprobar_liberacion(self):
        self._check_pv_admin()
        for rec in self:
            rec._check_liberacion_solicitada()
            rec._liberar(rec.liberacion_motivo)
        return True

    def action_rechazar_liberacion(self):
        self._check_pv_admin()
        for rec in self:
            rec._check_liberacion_solicitada()
            rec.sudo()._limpiar_solicitud_liberacion()
            rec._post_nota(_('Solicitud de liberación RECHAZADA por %s.', self.env.user.name))
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
            'context': {'default_maquina_id': self.id, 'default_motivo': self.liberacion_motivo or ''},
        }

    def _check_liberacion_solicitada(self):
        if not self.liberacion_solicitada:
            raise UserError(_('La máquina %s no tiene una solicitud de liberación pendiente.', self.name))

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
        if self.estado not in ESTADOS_LIBERABLES:
            raise UserError(_('La máquina no se puede liberar en su estado actual.'))
        maquina = self.sudo()
        maquina.certificado_ids.filtered(lambda c: c.estado_certificado in ('vigente', 'vencido')).write(
            {'estado_certificado': 'archivado_manual'})
        maquina.write({'estado': 'liberada', 'fecha_liberacion': fields.Date.today()})
        maquina._limpiar_solicitud_liberacion()
        self._post_nota(_(
            "La máquina fue LIBERADA por %(user)s. Motivo: %(motivo)s. Sus certificados anteriores fueron "
            "marcados como 'Archivado Manualmente' y se puede iniciar una nueva carga de certificados.",
            user=self.env.user.name, motivo=motivo))

    def _post_nota(self, body):
        self.sudo().message_post(body=body, message_type='notification', subtype_xmlid='mail.mt_note')

    # --- Traslados ---
    @api.model
    def get_transfer_catalog_data(self):
        """Concesionarios y provincias para el formulario de traslado."""
        return {
            'concesionarios': self.env['pv.concesionario'].search_read([('active', '=', True)], ['id', 'name']),
            'provincias': self.env['res.country.state'].search_read([('country_id.code', '=', 'AR')], ['id', 'name']),
        }

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

    def action_iniciar_transferencia_portal(self, concesionario_destino_id, provincia_destino_id, ciudad_destino):
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
        self._post_nota(_('Solicitud de traslado enviada a %s por %s (Pendiente de aceptación).',
                          concesionario_destino.name, self.env.user.name))
        return True

    def action_aceptar_transferencia(self):
        """El destino acepta: la máquina pasa a él como LIBERADA y se archivan los certificados anteriores."""
        self.ensure_one()
        self._check_transferencia_pendiente(_("Solo el concesionario destino puede aceptar esta transferencia."))
        maquina = self.sudo()
        destino = maquina.concesionario_destino_id
        maquina.certificado_ids.filtered(lambda c: c.estado_certificado in ('vigente', 'vencido')).write(
            {'estado_certificado': 'archivado_traslado'})
        maquina.write({
            'concesionario_id': destino.id,
            'provincia_id': maquina.provincia_destino_id.id,
            'ciudad': maquina.ciudad_destino,
            'estado': 'liberada',
            'fecha_liberacion': fields.Date.today(),
        })
        maquina._limpiar_transferencia()
        self._post_nota(_(
            "Transferencia ACEPTADA por %s. Nuevo dueño: %s. Los certificados anteriores fueron marcados como "
            "'Archivado por Traslado'. El nuevo concesionario debe iniciar la carga de certificados.",
            self.env.user.name, destino.name))
        return True

    def action_rechazar_transferencia(self):
        self.ensure_one()
        self._check_transferencia_pendiente(_("Solo el concesionario destino puede rechazar esta transferencia."))
        destino = self.sudo().concesionario_destino_id.name
        estado = self._revertir_transferencia()
        self._post_nota(_("Transferencia RECHAZADA por el concesionario %s. La máquina vuelve a estado %s con su dueño original.",
                          destino, dict(ESTADO_MAQUINA)[estado]))
        return True

    def action_cancelar_transferencia(self):
        """El concesionario de origen (o admin) cancela una propuesta de traslado pendiente."""
        self.ensure_one()
        self._check_es_del_concesionario(
            self.concesionario_id, _('Solo el concesionario de origen puede cancelar el traslado.'))
        if self.estado != 'pendiente':
            raise UserError(_("Solo se pueden cancelar traslados en estado Pendiente."))
        estado = self._revertir_transferencia()
        self._post_nota(_("Solicitud de traslado CANCELADA por el concesionario de origen (%s). La máquina vuelve a estado %s.",
                          self.env.user.name, dict(ESTADO_MAQUINA)[estado]))
        return True

    def _check_transferencia_pendiente(self, mensaje):
        self._check_es_del_concesionario(self.concesionario_destino_id, mensaje)
        if self.estado != 'pendiente':
            raise UserError(_("La máquina no tiene una transferencia pendiente."))

    def _revertir_transferencia(self):
        """Vuelve la máquina al estado que le corresponde por sus certificados, con su dueño original."""
        maquina = self.sudo()
        estado = 'vendida' if maquina.tiene_cpm else 'stock' if maquina.tiene_fru else 'liberada'
        maquina.write({'estado': estado})
        maquina._limpiar_transferencia()
        return estado

    def _limpiar_transferencia(self):
        self.write({'concesionario_destino_id': False, 'provincia_destino_id': False, 'ciudad_destino': False})
