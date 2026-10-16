# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .pv_maquina import ESTADO_MAQUINA, ESTADOS_MAQUINA_SIN_TICKETS


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

# Fotos/archivos chicos van como adjunto; los mayores, por fragmentos (Drive o almacenamiento Odoo)
MAX_ADJUNTO_MB = 20

# Datos que carga el concesionario: no se modifican una vez enviado el ticket (salvo admin)
CAMPOS_CARGA_CONCESIONARIO = {
    'maquina_id', 'certificado_id', 'operador_id', 'desvio_tipo_id',
    'sistema_id', 'subsistema_id', 'problema_id', 'problema_no_listado', 'campo_extra_ids',
    'descripcion', 'acciones_realizadas', 'ubicacion_actual', 'hectareas',
}

# Lo único que el concesionario puede modificar una vez enviado: adjuntos y chatter
CAMPOS_POST_ENVIO_CONCESIONARIO = {
    'message_main_attachment_id', 'activity_ids', 'message_ids', 'message_follower_ids',
    'multimedia_ids', 'multimedia_url', 'drive_folder_url',
}

# Datos que solo carga el Staff (resolución, garantía, SAP, KPIs)
CAMPOS_SOLO_STAFF = {
    'responsable_id', 'rechazo_tag_ids', 'tipo_garantia', 'prioridad',
    'garantia_aceptada', 'garantia_rechazo_tag_ids', 'garantia_observaciones',
    'garantia_adjunto', 'garantia_adjunto_name', 'solucion_aplicada',
    'sap_numero_aviso', 'sap_numero_orden', 'sap_numero_pedido', 'sap_centro', 'sap_material', 'sap_notas',
    'fecha_creacion', 'fecha_primera_atencion', 'fecha_solucion', 'fecha_cierre',
}



def _campos_cargados(vals, campos):
    """Campos de `campos` presentes en vals con un valor no vacío (ignora False, '' y comandos x2many vacíos)."""
    def cargado(value):
        if isinstance(value, (list, tuple)):
            return any(
                not (isinstance(cmd, (list, tuple)) and cmd and (cmd[0] == 5 or (cmd[0] == 6 and not cmd[2])))
                for cmd in value
            )
        return bool(value)
    return {k for k in campos.intersection(vals) if cargado(vals[k])}


PRIORIDAD = [
    ('baja', 'Baja'),
    ('media', 'Media'),
    ('alta', 'Alta'),
    ('critica', 'Crítica'),
]


class PvTicket(models.Model):
    _name = 'pv.ticket'
    _description = 'Ticket de Reclamo Posventa'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
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
        compute='_compute_tipo_ticket',
        store=True,
        tracking=True,
    )
    desvio_tipo_id = fields.Many2one(
        'pv.tipo.desvio',
        string='Tipo de Desvío',
        tracking=True,
    )

    # --- Datos de máquina (heredados) ---
    maquina_id = fields.Many2one(
        'pv.maquina',
        string='Máquina',
        required=True,
        domain="[('estado', 'not in', ('liberada', 'pendiente'))]",
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
    certificado_id = fields.Many2one(
        'pv.certificado',
        string='Certificado Asociado',
        compute='_compute_certificado_id',
        store=True,
        readonly=False,
        tracking=True,
        ondelete='restrict',
        help='Certificado vigente asociado al momento de la creación del ticket.'
    )

    # --- Operador (Contacto de Concesionario) ---
    operador_id = fields.Many2one(
        'res.partner',
        string='Cargado por',
        default=lambda self: self.env.user.partner_id,
        tracking=True,
    )
    # Los related se leen como superusuario: el portal muestra el nombre sin dar acceso al contacto
    operador_nombre = fields.Char(related='operador_id.name', string='Nombre del Operador')
    storage_mode = fields.Selection(
        [('drive', 'Google Drive'), ('odoo', 'Odoo')],
        string='Modo de Almacenamiento',
        compute='_compute_storage_mode',
    )

    def _compute_storage_mode(self):
        self.storage_mode = self.env['pv.ticket.multimedia']._get_storage_mode()

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
    problema_no_listado = fields.Boolean(
        string='Problema no listado',
        tracking=True,
        help='El problema no figura en el catálogo del subsistema; se detalla en la descripción.',
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
        help='Hectáreas trabajadas por la máquina al momento de la falla (obligatorio en reclamos Post-PM).',
    )
    multimedia_url = fields.Char(
        string='Multimedia (link Google Drive)',
    )
    drive_folder_url = fields.Char(
        string='Carpeta en Google Drive',
    )
    multimedia_ids = fields.One2many(
        'pv.ticket.multimedia',
        'ticket_id',
        string='Archivos Multimedia Pesados',
    )
    multimedia_count = fields.Integer(
        string='Cantidad de Archivos Multimedia',
        compute='_compute_multimedia_count',
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
    responsable_nombre = fields.Char(related='responsable_id.name', string='Nombre del Responsable')
    rechazo_tag_ids = fields.Many2many(
        'pv.tipo.rechazo',
        string='Motivos de Rechazo del Reclamo',
        domain=[('aplica_a', '=', 'reclamo')],
        tracking=True,
        help='Errores de carga por los que se rechaza el reclamo. El concesionario debe crear un ticket nuevo.',
    )
    tipo_garantia = fields.Selection(
        [('tecnica', 'Técnica'), ('comercial', 'Comercial')],
        string='Tipo de Garantía',
        tracking=True,
    )
    prioridad = fields.Selection(
        PRIORIDAD,
        string='Prioridad',
        default='alta',
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
    sap_numero_pedido = fields.Char(
        string='Nro. Pedido SAP',
        tracking=True,
        help='Número de pedido registrado en SAP para repuestos o insumos.',
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

    # --- Garantía (Cargada al aceptar reclamo) ---
    garantia_aceptada = fields.Boolean(
        string='Garantía Aceptada',
        tracking=True,
    )
    garantia_rechazo_tag_ids = fields.Many2many(
        'pv.tipo.rechazo',
        'pv_ticket_garantia_rechazo_rel',
        'ticket_id',
        'tipo_rechazo_id',
        string='Motivos sin Cobertura',
        domain=[('aplica_a', '=', 'garantia')],
        tracking=True,
        help='Motivos por los que la garantía no cubre la pieza (la abona el concesionario/cliente).',
    )
    garantia_observaciones = fields.Text(
        string='Observaciones de Garantía',
        tracking=True,
    )
    solucion_aplicada = fields.Text(
        string='Solución Aplicada',
        tracking=True,
        help='Qué se hizo para resolver la falla. Se carga al cerrar y alimenta el historial de casos similares.',
    )
    garantia_adjunto = fields.Binary(
        string='Adjunto de Garantía',
    )
    garantia_adjunto_name = fields.Char(
        string='Nombre del adjunto de garantía',
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

    def _compute_access_url(self):
        super()._compute_access_url()
        for rec in self:
            rec.access_url = f'/my/posventa/ticket/{rec.id}'

    # --- Color for kanban ---
    color = fields.Integer(string='Color')

    @api.model
    def _group_expand_estados(self, states, domain):
        """Show all states in kanban even if empty."""
        return [key for key, _ in ESTADO_TICKET]

    @api.depends('multimedia_ids')
    def _compute_multimedia_count(self):
        for rec in self:
            rec.multimedia_count = len(rec.multimedia_ids)

    @api.depends('medida_ids', 'medida_ids.estado')
    def _compute_medida_count(self):
        for rec in self:
            rec.medida_count = len(rec.medida_ids)
            rec.medidas_vencidas_count = len(
                rec.medida_ids.filtered(lambda m: m.estado == 'vencida')
            )

    @api.model
    def _get_kpis_promedio(self, domain=()):
        """T1/T2/T3 promedio (horas) de los tickets que alcanzaron cada etapa (los pendientes tienen 0)."""
        def promedio(campo_horas, campo_fecha):
            [(valor,)] = self._read_group(list(domain) + [(campo_fecha, '!=', False)], [], [f'{campo_horas}:avg'])
            return round(valor or 0.0, 1)
        return {
            'avg_t1': promedio('t1_horas', 'fecha_primera_atencion'),
            'avg_t2': promedio('t2_horas', 'fecha_solucion'),
            'avg_t3': promedio('t3_horas', 'fecha_cierre'),
        }

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

    @api.depends('maquina_id')
    def _compute_tipo_ticket(self):
        for rec in self:
            rec.tipo_ticket = 'post_pm' if rec.maquina_id.tiene_cpm else 'pre_pm'

    @api.depends('maquina_id', 'maquina_id.certificado_ids', 'maquina_id.certificado_ids.estado_certificado', 'maquina_id.certificado_ids.active', 'tipo_ticket')
    def _compute_certificado_id(self):
        """Certificado vigente que respalda el reclamo: CPM en Post-PM; FEU (o, si no hay, FRU) en Pre-PM."""
        prioridad = {'post_pm': ['cpm'], 'pre_pm': ['feu', 'fru']}
        for rec in self:
            if rec.certificado_id:
                continue
            vigentes = rec.maquina_id._get_certificados_vigentes()
            candidatos = [c for tipo in prioridad[rec.tipo_ticket] for c in vigentes if c.tipo == tipo]
            rec.certificado_id = candidatos[0] if candidatos else False

    @api.constrains('certificado_id', 'maquina_id')
    def _check_certificado_vigente(self):
        for rec in self:
            if not rec.certificado_id:
                raise ValidationError(_('Todo ticket de reclamo debe estar asociado a un certificado vigente de la máquina.'))
            if rec.certificado_id.maquina_id != rec.maquina_id:
                raise ValidationError(_('El certificado seleccionado (%s) no pertenece a la máquina %s.',
                                        rec.certificado_id.name, rec.maquina_id.name))

    @api.constrains('rechazo_tag_ids', 'garantia_rechazo_tag_ids')
    def _check_rechazo_tags_aplica_a(self):
        for rec in self:
            if any(t.aplica_a != 'reclamo' for t in rec.rechazo_tag_ids):
                raise ValidationError(_('Los motivos de rechazo del reclamo solo pueden ser de tipo "Rechazo de Reclamo".'))
            if any(t.aplica_a != 'garantia' for t in rec.garantia_rechazo_tag_ids):
                raise ValidationError(_('Los motivos sin cobertura solo pueden ser de tipo "Sin Cobertura de Garantía".'))

    @api.constrains('tipo_ticket', 'sistema_id', 'subsistema_id', 'problema_id', 'problema_no_listado', 'hectareas')
    def _check_clasificacion(self):
        for rec in self:
            if rec.hectareas < 0:
                raise ValidationError(_('Las hectáreas no pueden ser negativas.'))
            if rec.subsistema_id and rec.subsistema_id.sistema_id != rec.sistema_id:
                raise ValidationError(_('El subsistema %s no pertenece al sistema seleccionado.', rec.subsistema_id.name))
            if rec.problema_id and rec.problema_id.subsistema_id != rec.subsistema_id:
                raise ValidationError(_('El problema %s no pertenece al subsistema seleccionado.', rec.problema_id.name))
            if rec.problema_id and rec.problema_no_listado:
                raise ValidationError(_('Seleccione un problema del catálogo o márquelo como no listado, no ambos.'))
            if rec.tipo_ticket != 'post_pm':
                continue
            if not rec.sistema_id or not rec.subsistema_id:
                raise ValidationError(_('En reclamos Post-PM debe indicar el sistema y subsistema involucrado.'))
            if not rec.problema_id and not rec.problema_no_listado:
                raise ValidationError(_('Seleccione el problema catalogado o indique que no está en la lista.'))
            if rec.hectareas <= 0:
                raise ValidationError(_('En reclamos Post-PM debe indicar las hectáreas trabajadas.'))

    @api.constrains('campo_extra_ids')
    def _check_obligatory_extra_fields(self):
        for rec in self:
            if rec.campo_extra_ids:
                for campo in rec.campo_extra_ids:
                    if campo.campo_obligatorio and not campo.valor:
                        raise ValidationError(_(
                            'El campo %s es obligatorio.', campo.campo_nombre
                    ))

    @api.constrains('maquina_id')
    def _check_maquina_estado_valido(self):
        # Solo al asignar la máquina: un traslado o liberación posterior no debe trabar tickets en curso
        for rec in self:
            if rec.maquina_id and rec.maquina_id.estado in ESTADOS_MAQUINA_SIN_TICKETS:
                estado_label = dict(ESTADO_MAQUINA).get(rec.maquina_id.estado, rec.maquina_id.estado)
                raise ValidationError(_(
                    'No se puede crear un ticket para la máquina %s '
                    'porque se encuentra en estado "%s".', rec.maquina_id.name or rec.maquina_id.of, estado_label
                ))

    @api.constrains('responsable_id', 'estado')
    def _check_responsable_coherence(self):
        for rec in self:
            if rec.responsable_id and rec.estado in ('borrador', 'abierto'):
                raise ValidationError(_("Un ticket no puede tener un responsable asignado en estado Borrador o Abierto."))

    @api.model_create_multi
    def create(self, vals_list):
        es_staff = self.env.su or self.env.user.has_group('posventa.group_pv_staff')
        for vals in vals_list:
            if not self.env.su and vals.get('estado', 'borrador') != 'borrador':
                raise UserError(_('Los tickets se crean en estado Borrador.'))
            if not es_staff and _campos_cargados(vals, CAMPOS_SOLO_STAFF):
                raise UserError(_('Acción denegada: hay datos del ticket que solo puede cargar el Staff de Posventa.'))
            vals.pop('tipo_ticket', None)  # siempre se deduce de la máquina
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('pv.ticket') or _('Nuevo')
        tickets = super().create(vals_list)
        # La vigencia se exige al crear (no como constraint: el certificado puede vencer durante el trámite)
        for ticket in tickets:
            if not ticket.certificado_id._es_vigente_para_reclamos():
                raise ValidationError(_('No se pueden crear reclamos sobre el certificado %s porque ya no está vigente para reclamos.',
                                        ticket.certificado_id.name))
        return tickets

    # El método write() se encuentra unificado al final del archivo para centralizar todas las validaciones de seguridad.



    @api.onchange('sistema_id')
    def _onchange_sistema_id(self):
        """Clear subsistema and problema when sistema changes."""
        self.subsistema_id = False
        self.problema_id = False

    @api.onchange('problema_id')
    def _onchange_problema_id(self):
        if self.problema_id:
            self.problema_no_listado = False

    @api.onchange('problema_no_listado')
    def _onchange_problema_no_listado(self):
        if self.problema_no_listado:
            self.problema_id = False

    @api.onchange('subsistema_id')
    def _onchange_subsistema_id(self):
        """Clear problema and regenerate extra fields when subsistema changes."""
        self.problema_id = False
        self.problema_no_listado = False
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

    def _check_mandatory_attachments(self):
        for rec in self:
            has_multimedia = bool(rec.multimedia_ids or rec.multimedia_url)
            if not has_multimedia:
                attachments = self.env['ir.attachment'].sudo().search([
                    ('res_model', '=', 'pv.ticket'),
                    ('res_id', '=', rec.id),
                ])
                if attachments:
                    has_multimedia = True
            if not has_multimedia:
                raise UserError(_('Es obligatorio adjuntar al menos una imagen o video donde se observe la problemática antes de enviar el ticket a revisión.'))

    # --- Permisos y transiciones de estado ---
    def _check_pv_group(self, group_xmlid, mensaje):
        if not self.env.su and not self.env.user.has_group(group_xmlid):
            raise AccessError(mensaje)

    def _check_staff(self):
        self._check_pv_group('posventa.group_pv_staff', _('Solo el Staff de Posventa puede realizar esta acción.'))

    def _check_admin(self):
        self._check_pv_group('posventa.group_pv_admin', _('Solo el Administrador de Posventa puede realizar esta acción.'))

    def _write_estado(self, vals):
        """Único camino para cambiar el estado: write() rechaza 'estado' sin este contexto."""
        return self.with_context(pv_transicion_estado=True).write(vals)

    def _check_listo_para_enviar(self):
        """Validaciones de negocio al enviar el ticket (BORRADOR -> ABIERTO)."""
        for rec in self:
            rec._check_mandatory_attachments()
            if rec.maquina_id.estado in ESTADOS_MAQUINA_SIN_TICKETS:
                estado_label = dict(ESTADO_MAQUINA).get(rec.maquina_id.estado, rec.maquina_id.estado)
                raise UserError(_(
                    'No se puede enviar el ticket porque la máquina %s se encuentra en estado "%s".',
                    rec.maquina_id.name or rec.maquina_id.of, estado_label
                ))
            if not rec.certificado_id._es_vigente_para_reclamos():
                raise UserError(_(
                    'No se puede enviar el ticket porque el certificado %s ya no está vigente para reclamos.',
                    rec.certificado_id.name))

    def action_enviar_ticket(self):
        """ El concesionario envía el ticket al Staff (BORRADOR -> ABIERTO) """
        es_admin = self.env.su or self.env.user.has_group('posventa.group_pv_admin')
        for rec in self:
            if not es_admin and not rec.concesionario_id._is_member():
                raise AccessError(_('Solo el concesionario dueño del ticket puede enviarlo.'))
            if rec.estado != 'borrador':
                raise UserError(_('Solo se pueden enviar tickets en estado Borrador.'))
            rec._check_listo_para_enviar()

            rec._write_estado({'estado': 'abierto'})
            rec.sudo().message_post(
                body=_('Ticket enviado a revisión técnica por el concesionario.'),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            rec._send_notification_to_staff()

    def action_tomar_ticket(self):
        """Staff takes the ticket (ABIERTO -> EN_PROCESO)."""
        self._check_staff()
        for rec in self:
            if rec.estado != 'abierto':
                raise UserError(_('Solo se pueden tomar tickets en estado ABIERTO.'))
            vals = {
                'estado': 'en_proceso',
                'responsable_id': self.env.user.id,
            }
            if not rec.fecha_primera_atencion:
                vals['fecha_primera_atencion'] = fields.Datetime.now()
            rec._write_estado(vals)
            rec.message_post(
                body=_('Ticket tomado por %s', self.env.user.name),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    def action_aceptar_ticket(self):
        """Acepta el reclamo (EN_PROCESO -> ACEPTADO): es válido y queda en evaluación de garantía."""
        self._check_staff()
        for rec in self:
            if rec.estado != 'en_proceso':
                raise UserError(_('Solo se pueden aceptar tickets EN PROCESO.'))
            rec._write_estado({
                'estado': 'aceptado',
                'fecha_solucion': fields.Datetime.now(),
            })
            rec.message_post(
                body=_('Reclamo aceptado y validado.'),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            template = self.env.ref('posventa.mail_template_ticket_aceptado', raise_if_not_found=False)
            if template:
                template.send_mail(rec.id, force_send=True)

    def action_rechazar_ticket(self):
        """Rechaza el reclamo por error de carga (EN_PROCESO -> RECHAZADO) y abre el correo al concesionario."""
        self.ensure_one()
        self._check_staff()
        if self.estado != 'en_proceso':
            raise UserError(_('Solo se pueden rechazar tickets EN PROCESO.'))
        if not self.rechazo_tag_ids:
            raise UserError(_('Debe indicar al menos un motivo de rechazo del reclamo.'))

        self._write_estado({
            'estado': 'rechazado',
            'fecha_cierre': fields.Datetime.now(),
        })
        self.message_post(
            body=_('Reclamo rechazado. Motivos: %s', ", ".join(self.rechazo_tag_ids.mapped('name'))),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        template = self.env.ref('posventa.mail_template_ticket_rechazado', raise_if_not_found=False)
        ctx = {
            'default_model': 'pv.ticket',
            'default_res_ids': self.ids,
            'default_composition_mode': 'comment',
            'default_template_id': template.id if template else False,
            'default_partner_ids': self.concesionario_id.partner_id.ids,
            'force_email': True,
        }
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
        """Close the ticket (ACEPTADO -> CERRADO).
        Siempre abre el asistente de cierre para registrar la solución aplicada, si la garantía
        cubre la pieza (con sus motivos si no la cubre) y el comprobante u orden SAP.
        """
        self.ensure_one()
        self._check_staff()
        if self.estado != 'aceptado':
            raise UserError(_('Solo se pueden cerrar tickets ACEPTADOS.'))

        return {
            'name': _('Cierre de Reclamo / Garantía y Devolución'),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.cerrar.ticket.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_sap_numero_orden': self.sap_numero_orden or '',
                'default_tipo_garantia': self.tipo_garantia or 'tecnica',
            }
        }

    def _cerrar(self, vals):
        """Usado por el asistente de cierre (ACEPTADO -> CERRADO)."""
        self._check_staff()
        for rec in self:
            if rec.estado != 'aceptado':
                raise UserError(_("Solo se pueden cerrar tickets en estado 'Aceptado'."))
        return self._write_estado(dict(vals, estado='cerrado', fecha_cierre=fields.Datetime.now()))

    # --- Retrocesos de estado ---
    def _retroceder(self, desde, vals, mensaje):
        for rec in self:
            if rec.estado not in desde:
                raise UserError(_('El ticket %s no se puede devolver desde su estado actual.', rec.name))
            rec._write_estado(vals)
            rec.message_post(
                body=mensaje % self.env.user.name,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    def action_back_to_borrador(self):
        self._check_admin()
        self._retroceder(('abierto',), {'estado': 'borrador'}, _('Ticket devuelto a Borrador por %s.'))

    def action_back_to_abierto(self):
        self._check_staff()
        self._retroceder(('en_proceso',), {'estado': 'abierto', 'responsable_id': False},
                         _('Ticket devuelto a Abierto por %s.'))

    def action_back_to_en_proceso(self):
        self._check_staff()
        for rec in self:
            rec._retroceder(('aceptado', 'rechazado'), {
                'estado': 'en_proceso',
                'fecha_solucion': False,
                'fecha_cierre': False,
            }, _('Ticket devuelto a En Proceso por %s.'))

    def action_back_to_aceptado(self):
        self._check_admin()
        self._retroceder(('cerrado',), {'estado': 'aceptado', 'fecha_cierre': False},
                         _('Ticket devuelto a Aceptado por %s.'))

    def _send_notification_to_staff(self):
        self.ensure_one()
        emails = self.env.ref('posventa.group_pv_staff').sudo().all_user_ids.filtered('email').mapped('email')
        if emails:
            self.env.ref('posventa.mail_template_ticket_creado').sudo().send_mail(
                self.id, force_send=True, email_values={'email_to': ','.join(emails)})

    def portal_adjuntar_archivo(self, nombre, datas, mimetype=None):
        """Adjunta una foto/archivo chico al ticket (los usuarios portal no crean ir.attachment directamente)."""
        self.ensure_one()
        self.check_access('write')
        if self.estado in ('rechazado', 'cerrado'):
            raise UserError(_('No se pueden agregar archivos a un reclamo %s.', dict(ESTADO_TICKET)[self.estado]))
        if len(datas or '') * 3 // 4 > MAX_ADJUNTO_MB * 1024 * 1024:
            raise UserError(_('El archivo supera %s MB: súbalo como archivo pesado.', MAX_ADJUNTO_MB))
        return self.env['ir.attachment'].sudo().create({
            'name': nombre,
            'datas': datas,
            'mimetype': mimetype or 'application/octet-stream',
            'res_model': self._name,
            'res_id': self.id,
        }).id

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

    def write(self, vals):
        if not self.env.su:
            if 'estado' in vals and not self.env.context.get('pv_transicion_estado'):
                raise UserError(_("El estado del ticket solo puede cambiarse mediante los botones de acción."))

            user = self.env.user
            if not user.has_group('posventa.group_pv_admin'):
                es_staff = user.has_group('posventa.group_pv_staff')
                if not es_staff and _campos_cargados(vals, CAMPOS_SOLO_STAFF):
                    raise UserError(_("Acción denegada: hay datos del ticket que solo puede cargar el Staff de Posventa."))
                for rec in self:
                    if rec.estado == 'borrador':
                        continue
                    if es_staff:
                        if CAMPOS_CARGA_CONCESIONARIO.intersection(vals):
                            raise UserError(_("Los datos cargados por el concesionario no se pueden modificar una vez enviado el ticket."))
                    elif set(vals) - CAMPOS_POST_ENVIO_CONCESIONARIO:
                        raise UserError(_("Acción denegada: No tienes permisos para modificar este documento una vez creado y enviado."))

        # Trazabilidad verbosa si se asigna o reasigna el responsable
        if 'responsable_id' in vals:
            new_resp = self.env['res.users'].browse(vals['responsable_id'])
            for rec in self:
                if rec.responsable_id != new_resp:
                    rec.message_post(
                        body=_('Responsable del ticket cambiado de "%(old)s" a "%(new)s" por %(user)s.',
                               old=rec.responsable_id.name or _('Sin asignar'),
                               new=new_resp.name or _('Sin asignar'),
                               user=self.env.user.name),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
        return super().write(vals)

    @api.model
    def get_wizard_catalog_data(self, sistema_id=None, subsistema_id=None):
        """Helper for ticket wizard dropdowns and dynamic fields."""
        sistemas = self.env['pv.sistema'].search_read([('active', '=', True)], ['id', 'name', 'codigo'])
        subsistemas = []
        if sistema_id:
            subsistemas = self.env['pv.subsistema'].search_read(
                [('active', '=', True), ('sistema_id', '=', sistema_id)],
                ['id', 'name', 'codigo', 'placeholder_descripcion']
            )

        problemas = []
        campos_extras = []
        if subsistema_id:
            problemas = self.env['pv.problema'].search_read(
                [('active', '=', True), ('subsistema_id', '=', subsistema_id)],
                ['id', 'name', 'codigo']
            )
            campos_rec = self.env['pv.subsistema.campo'].search([('subsistema_id', '=', subsistema_id)])
            for c in campos_rec:
                opciones_list = [o.strip() for o in (c.opciones or '').split('|') if o.strip()]
                campos_extras.append({
                    'id': c.id,
                    'name': c.name,
                    'tipo_campo': c.tipo_campo,
                    'obligatorio': c.obligatorio,
                    'opciones': opciones_list,
                })

        Multimedia = self.env['pv.ticket.multimedia']
        storage_mode = Multimedia._get_storage_mode()
        is_configured, rclone_msg = Multimedia._is_rclone_configured() if storage_mode == 'drive' else (True, "OK")
        tipos_desvio = self.env['pv.tipo.desvio'].search_read([('active', '=', True)], ['id', 'name', 'codigo'])

        return {
            'sistemas': sistemas,
            'subsistemas': subsistemas,
            'problemas': problemas,
            'campos_extras': campos_extras,
            'tipos_desvio': tipos_desvio,
            'storage_mode': storage_mode,
            'chunk_size_bytes': Multimedia._get_chunk_size_bytes(),
            'max_adjunto_bytes': MAX_ADJUNTO_MB * 1024 * 1024,
            'max_file_size_bytes': Multimedia._get_max_upload_bytes(),
            'rclone_configured': is_configured,
            'rclone_msg': rclone_msg,
        }

    def action_abrir_carpeta_drive(self):
        """Abre la carpeta de Google Drive del ticket o, si no hay, el primer enlace multimedia disponible."""
        self.ensure_one()
        url = (self.drive_folder_url or self.multimedia_url
               or next((m.drive_folder_url or m.drive_url for m in self.multimedia_ids if m.drive_folder_url or m.drive_url), False))
        if url:
            return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}
        if self.multimedia_ids.filtered(lambda m: m.estado_sync == 'procesando'):
            raise UserError(_(
                "Los archivos multimedia se están transfiriendo actualmente a Google Drive. "
                "Por favor aguarde unos instantes mientras finaliza la sincronización (puede consultar el estado en la pestaña Multimedia)."
            ))
        raise UserError(_("No hay una carpeta o archivo de Google Drive asociado a este ticket todavía."))

    def action_adjuntar_multimedia(self):
        """Abre el asistente para adjuntar un archivo multimedia o enlace de Google Drive."""
        self.ensure_one()
        return {
            'name': _('Adjuntar Video / Archivo Multimedia'),
            'type': 'ir.actions.act_window',
            'res_model': 'pv.ticket.multimedia.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
            },
        }