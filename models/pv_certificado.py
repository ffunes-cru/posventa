# Part of Crucianelli Posventa Module
from datetime import timedelta

from markupsafe import Markup, escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


TIPO_CERTIFICADO = [
    ('cpm', 'CPM — Certificado de Puesta en Marcha'),
    ('fru', 'FRU — Formulario de Recepción de Unidad'),
    ('feu', 'FEU — Formulario de Entrega de Unidad'),
    ('informe_servicio', 'Informe de Servicio'),
    ('recall', 'Recall'),
]

ESTADO_CERTIFICADO = [
    ('vigente', 'Vigente'),
    ('vencido', 'Vencido por Fecha'),
    ('archivado_traslado', 'Archivado por Traslado'),
    ('archivado_manual', 'Archivado Manualmente'),
    ('legacy', 'Legacy / Canje'),
]

# Estados que cuentan como "cargado" para la secuencia FRU -> FEU -> CPM
ESTADOS_CARGADO = ('vigente', 'vencido')

# (parámetro, default) en días, por tipo de certificado
PLAZO_CARGA = {
    'fru': ('posventa.fru_expiration_days', 10),
    'feu': ('posventa.feu_expiration_days', 20),
}
VIGENCIA_RECLAMOS = {
    'fru': ('posventa.fru_grace_days', 3),
    'feu': ('posventa.feu_claims_validity_days', 90),
}

EXTENSIONES_ARCHIVO = ('.pdf', '.jpg', '.jpeg', '.png')

# El documento cargado es inmutable salvo para el Administrador
CAMPOS_DOCUMENTO = {'tipo', 'maquina_id', 'archivo', 'archivo_nombre', 'fecha'}


class PvCertificado(models.Model):
    _name = 'pv.certificado'
    _description = 'Certificado de Máquina'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    tipo = fields.Selection(TIPO_CERTIFICADO, string='Tipo', required=True, tracking=True)
    maquina_id = fields.Many2one(
        'pv.maquina', string='Máquina', required=True, ondelete='cascade', tracking=True,
        domain="[('tiene_cpm', '=', False)]",
    )
    concesionario_id = fields.Many2one('pv.concesionario', string='Concesionario Emisor', tracking=True)
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today, required=True, tracking=True)
    estado_certificado = fields.Selection(
        ESTADO_CERTIFICADO, string='Estado / Tag', default='vigente', required=True, tracking=True)
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    archivo = fields.Binary(string='Archivo PDF', attachment=True, required=True)
    archivo_nombre = fields.Char(string='Nombre de archivo', required=True)
    notas = fields.Text(string='Observaciones')

    fecha_limite_carga = fields.Date(
        string='Plazo Nominal de Carga', compute='_compute_fechas', store=True, readonly=False,
        help='Fecha límite nominal que tenía la máquina para la carga de este certificado.',
    )
    dias_retraso_carga = fields.Integer(
        string='Días de Retraso en Carga', compute='_compute_fechas', store=True, readonly=False,
        help='Días que la carga real superó el plazo nominal.',
    )
    fecha_vencimiento = fields.Date(
        string='Vigente para Reclamos hasta', compute='_compute_fechas', store=True, readonly=False, tracking=True,
        help='Hasta esta fecha el certificado permite crear reclamos; después pasa a Vencido. El CPM no vence.',
    )
    dias_para_vencer = fields.Integer(string='Días para Vencer', compute='_compute_dias_para_vencer')

    ticket_ids = fields.One2many('pv.ticket', 'certificado_id', string='Tickets / Reclamos')
    ticket_count = fields.Integer(string='Cantidad de Tickets', compute='_compute_ticket_count')

    # --- Plazos ---
    def _get_param_dias(self, param):
        key, default = param
        try:
            return int(self.env['ir.config_parameter'].sudo().get_param(key, default))
        except ValueError:
            return default

    @api.model
    def _get_plazo_nominal_carga(self, tipo, maquina):
        """Fecha límite nominal para cargar este tipo de certificado, contada desde la liberación de la máquina."""
        if tipo not in PLAZO_CARGA or not maquina:
            return False
        base = maquina.fecha_liberacion or fields.Date.to_date(maquina.create_date) or fields.Date.today()
        return base + timedelta(days=self._get_param_dias(PLAZO_CARGA[tipo]))

    def _get_vencimiento_reclamos(self):
        if self.tipo not in VIGENCIA_RECLAMOS:
            return False
        return (self.fecha or fields.Date.today()) + timedelta(days=self._get_param_dias(VIGENCIA_RECLAMOS[self.tipo]))

    def _get_fecha_carga(self):
        """Fecha real en que se subió el certificado (no la fecha que declara el usuario)."""
        return fields.Date.to_date(self.create_date) if self.create_date else fields.Date.today()

    @api.depends('tipo', 'fecha', 'maquina_id.fecha_liberacion')
    def _compute_fechas(self):
        for rec in self:
            plazo = self._get_plazo_nominal_carga(rec.tipo, rec.maquina_id)
            rec.fecha_limite_carga = plazo
            rec.dias_retraso_carga = max((rec._get_fecha_carga() - plazo).days, 0) if plazo else 0
            rec.fecha_vencimiento = rec._get_vencimiento_reclamos()

    @api.depends('fecha_vencimiento')
    def _compute_dias_para_vencer(self):
        hoy = fields.Date.today()
        for rec in self:
            rec.dias_para_vencer = (rec.fecha_vencimiento - hoy).days if rec.fecha_vencimiento else 0

    @api.depends('ticket_ids')
    def _compute_ticket_count(self):
        for rec in self:
            rec.ticket_count = len(rec.ticket_ids)

    @api.depends('tipo', 'maquina_id.of')
    def _compute_name(self):
        for rec in self:
            rec.name = f"{dict(TIPO_CERTIFICADO).get(rec.tipo, '')} - {rec.maquina_id.sudo().of or ''}"

    def _es_vigente_para_reclamos(self):
        self.ensure_one()
        return (self.active and self.estado_certificado == 'vigente'
                and not (self.fecha_vencimiento and self.fecha_vencimiento < fields.Date.today()))

    # --- Validaciones ---
    def _otros_de_la_maquina(self, tipo, estados):
        return self.search_count([
            ('maquina_id', '=', self.maquina_id.id),
            ('tipo', '=', tipo),
            ('estado_certificado', 'in', estados),
            ('active', '=', True),
            ('id', '!=', self.id),
        ])

    @api.constrains('tipo', 'maquina_id', 'estado_certificado', 'active')
    def _check_secuencia(self):
        """Secuencia FRU -> FEU -> CPM, un solo vigente por tipo y nada después del CPM."""
        for rec in self:
            if not rec.active or rec.estado_certificado != 'vigente':
                continue
            maquina = rec.maquina_id.name
            if rec.maquina_id.estado == 'pendiente':
                raise ValidationError(_('No se pueden cargar certificados en la máquina %s porque se encuentra en proceso de transferencia pendiente.', maquina))
            if rec._otros_de_la_maquina('cpm', ['vigente']):
                raise ValidationError(_('La máquina %s ya posee un Certificado de Puesta en Marcha (CPM) vigente. No se pueden agregar más certificados a una máquina completa.', maquina))
            if rec.tipo == 'fru' and rec._otros_de_la_maquina('fru', ESTADOS_CARGADO):
                raise ValidationError(_('El Formulario de Recepción de Unidad (FRU) ya ha sido cargado para esta máquina y no puede renovarse. Debe cargar el Formulario de Entrega (FEU).'))
            if rec.tipo != 'fru' and rec._otros_de_la_maquina(rec.tipo, ['vigente']):
                raise ValidationError(_('Ya existe un certificado vigente de tipo "%s" para esta máquina.', dict(TIPO_CERTIFICADO)[rec.tipo]))
            if rec.tipo in ('feu', 'cpm') and not rec._otros_de_la_maquina('fru', ESTADOS_CARGADO):
                raise ValidationError(_('No se puede cargar el %s sin antes haber cargado el Formulario de Recepción de Unidad (FRU) para la máquina %s.', dict(TIPO_CERTIFICADO)[rec.tipo], maquina))
            if rec.tipo == 'cpm' and not rec._otros_de_la_maquina('feu', ['vigente']):
                if rec._otros_de_la_maquina('feu', ['vencido']):
                    raise ValidationError(_('El Formulario de Entrega de Unidad (FEU) de la máquina %s se encuentra vencido. Debe renovarlo antes de poder cargar el Certificado de Puesta en Marcha (CPM).', maquina))
                raise ValidationError(_('No se puede cargar un Certificado de Puesta en Marcha (CPM) sin antes haber cargado un Formulario de Entrega de Unidad (FEU) vigente para la máquina %s.', maquina))

    @api.constrains('fecha')
    def _check_fecha_no_futura(self):
        if any(rec.fecha > fields.Date.today() for rec in self):
            raise ValidationError(_('La fecha del certificado no puede ser posterior a hoy.'))

    @api.constrains('archivo', 'archivo_nombre')
    def _check_archivo(self):
        for rec in self:
            if not rec.archivo:
                raise ValidationError(_('El archivo adjunto es obligatorio.'))
            if not (rec.archivo_nombre or '').lower().endswith(EXTENSIONES_ARCHIVO):
                raise ValidationError(_('El archivo debe tener una de las siguientes extensiones: %s y este es: %s', EXTENSIONES_ARCHIVO, rec.archivo_nombre))

    # --- ORM ---
    @api.model_create_multi
    def create(self, vals_list):
        es_staff = self.env.su or self.env.user.has_group('posventa.group_pv_staff')
        concesionario_usuario = self.env['pv.concesionario']._get_concesionario_for_user()
        for vals in vals_list:
            maquina = self.env['pv.maquina'].sudo().browse(vals.get('maquina_id')).exists()
            if es_staff:
                vals['concesionario_id'] = vals.get('concesionario_id') or (concesionario_usuario or maquina.concesionario_id).id
                continue
            # El concesionario carga certificados vigentes a su nombre: estado y emisor no son suyos de elegir
            if not concesionario_usuario:
                raise UserError(_('Su usuario no está asociado a ningún concesionario.'))
            if maquina.concesionario_id != concesionario_usuario:
                raise ValidationError(_('No puede cargar certificados para una máquina que no pertenece a su concesionario actual.'))
            fecha = fields.Date.to_date(vals.get('fecha')) or fields.Date.today()
            if maquina.fecha_liberacion and fecha < maquina.fecha_liberacion:
                raise ValidationError(_(
                    'La fecha del certificado no puede ser anterior a la fecha de liberación de la máquina (%s).',
                    maquina.fecha_liberacion))
            vals.update(concesionario_id=concesionario_usuario.id, estado_certificado='vigente', active=True)
        records = super().create(vals_list)
        records._actualizar_estado_maquina()
        return records

    def write(self, vals):
        if CAMPOS_DOCUMENTO.intersection(vals) and not (self.env.su or self.env.user.has_group('posventa.group_pv_admin')):
            raise UserError(_('No se puede modificar un certificado una vez guardado. Si necesita cambios, '
                              'solicite al Administrador de Posventa que lo archive.'))
        res = super().write(vals)
        if vals.get('active') or vals.get('estado_certificado') == 'vigente':
            self._actualizar_estado_maquina()
        return res

    def _actualizar_estado_maquina(self):
        """Un FRU vigente pone la máquina en STOCK y un CPM vigente en VENDIDA."""
        mensajes = {
            'fru': ('stock', _('Formulario de Recepción de Unidad (FRU) cargado. La máquina pasa a estado STOCK.')),
            'cpm': ('vendida', _('Certificado de Puesta en Marcha (CPM) cargado. La máquina pasa a estado VENDIDA.')),
        }
        for rec in self.filtered(lambda c: c.active and c.estado_certificado == 'vigente' and c.tipo in mensajes):
            estado, mensaje = mensajes[rec.tipo]
            maquina = rec.maquina_id.sudo()
            if maquina.estado != estado:
                maquina.write({'estado': estado})
                maquina._message_log(body=mensaje)

    # --- Crons ---
    @api.model
    def _archive_expired_certificates(self):
        """Cron diario: pasa a Vencido los certificados cuya vigencia para reclamos expiró (no aplica al CPM)."""
        vencidos = self.search([
            ('active', '=', True),
            ('estado_certificado', '=', 'vigente'),
            ('maquina_id.tiene_cpm', '=', False),
            ('fecha_vencimiento', '<', fields.Date.today()),
        ])
        for cert in vencidos:
            cert.maquina_id._message_log(body=_(
                'El certificado %s ha superado su vigencia para reclamos (límite: %s). Su estado pasa a Vencido.',
                dict(TIPO_CERTIFICADO)[cert.tipo], cert.fecha_vencimiento))
        vencidos.write({'estado_certificado': 'vencido'})

    @api.model
    def _notify_upcoming_certificate_expiration(self):
        """Cron diario: avisa al concesionario 3 días antes de que venza un certificado."""
        por_vencer = self.search([
            ('active', '=', True),
            ('estado_certificado', '=', 'vigente'),
            ('fecha_vencimiento', '=', fields.Date.today() + timedelta(days=3)),
        ])
        for cert in por_vencer:
            tipo = dict(TIPO_CERTIFICADO)[cert.tipo]
            maquina = cert.maquina_id
            maquina._message_log(body=_("⚠️ El certificado %s de la máquina %s vencerá en 3 días (el %s).",
                                 tipo, maquina.name, cert.fecha_vencimiento))
            email = cert.concesionario_id.partner_id.email
            if email:
                url = f"{maquina.get_base_url()}/my/posventa/maquina/{maquina.id}"
                self.env['mail.mail'].sudo().create({
                    'subject': _('Vencimiento Próximo de Certificado: %s', maquina.name),
                    'body_html': Markup(_(
                        "<p>Estimado/a Concesionario %(concesionario)s,</p>"
                        "<p>El certificado <b>%(tipo)s</b> de la máquina <b>%(maquina)s</b> vence el %(fecha)s.</p>"
                        "<p>Por favor, cargue el próximo certificado a la brevedad desde el "
                        "<a href='%(url)s'>portal de Posventa</a> para evitar bloqueos.</p>"
                    )) % {
                        'concesionario': escape(cert.concesionario_id.name), 'tipo': escape(tipo),
                        'maquina': escape(maquina.name), 'fecha': cert.fecha_vencimiento, 'url': escape(url),
                    },
                    'email_to': email,
                }).send()

    # --- Portal ---
    def _get_portal_values(self):
        """Datos del certificado para el portal (detalle de máquina, listado y asistentes)."""
        self.ensure_one()
        etiqueta, color = {
            'vigente': (_('Vigente'), 'success'),
            'vencido': (_('Vencido'), 'danger'),
            'archivado_traslado': (_('Archivado por Traslado'), 'warning'),
        }.get(self.estado_certificado, (_('Archivado Manualmente'), 'secondary'))
        if self.estado_certificado == 'vigente' and self.dias_retraso_carga:
            etiqueta = (_('Vencido luego de 1 día') if self.dias_retraso_carga == 1
                        else _('Vencido luego de %s días', self.dias_retraso_carga))
            color = 'danger'
        maquina = self.maquina_id.sudo()
        return {
            'id': self.id,
            'tipo': self.tipo,
            'tipo_label': dict(TIPO_CERTIFICADO).get(self.tipo, ''),
            'fecha': str(self.fecha or ''),
            'fecha_vencimiento': str(self.fecha_vencimiento or ''),
            'estado_certificado': self.estado_certificado,
            'estado_certificado_label': etiqueta,
            'tag_badge': color,
            'concesionario_name': self.concesionario_id.name or '',
            'archivo_nombre': self.archivo_nombre or '',
            'active': self.active,
            'maquina_id': maquina.id,
            'maquina_name': maquina.name or '',
        }

    @api.model
    def get_portal_list_data(self, search_term='', tipo_filter='', estado_filter=''):
        """Certificados visibles por el usuario para el listado del portal."""
        domain = [('active', '=', True)]
        if search_term:
            domain += ['|', '|', ('maquina_id.of', 'ilike', search_term), ('archivo_nombre', 'ilike', search_term),
                       ('concesionario_id.name', 'ilike', search_term)]
        if tipo_filter:
            domain.append(('tipo', '=', tipo_filter))
        if estado_filter:
            domain.append(('estado_certificado', '=', estado_filter))
        mi_concesionario = self.env['pv.concesionario']._get_concesionario_for_user()
        res = []
        for cert in self.search(domain):
            maquina = cert.maquina_id.sudo()
            valores = cert._get_portal_values()
            valores['puede_ver_maquina'] = bool(mi_concesionario) and mi_concesionario in (
                maquina.concesionario_id, maquina.concesionario_destino_id if maquina.estado == 'pendiente' else False)
            res.append(valores)
        return res

    def action_view_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tickets de %s', self.name),
            'res_model': 'pv.ticket',
            'view_mode': 'list,form',
            'domain': [('certificado_id', '=', self.id)],
            'context': {'default_maquina_id': self.maquina_id.id, 'default_certificado_id': self.id},
        }
