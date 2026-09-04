# Part of Crucianelli Posventa Module
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


class PvCertificado(models.Model):
    _name = 'pv.certificado'
    _description = 'Certificado de Máquina'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'


    name = fields.Char(
        string='Referencia',
        compute='_compute_name',
        store=True,
    )
    tipo = fields.Selection(
        TIPO_CERTIFICADO,
        string='Tipo',
        required=True,
        tracking=True,
    )
    maquina_id = fields.Many2one(
        'pv.maquina',
        string='Máquina',
        required=True,
        domain="[('tiene_cpm', '=', False)]",
        ondelete='cascade',
        tracking=True,
    )
    fecha = fields.Date(
        string='Fecha',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    dias_retraso_carga = fields.Integer(
        string='Días de Retraso en Carga',
        default=0,
        help='Días que se excedió el concesionario respecto al plazo nominal de carga al subir el certificado.',
    )
    fecha_limite_carga = fields.Date(
        string='Plazo Nominal de Carga',
        help='Fecha límite nominal que tenía la máquina para la carga de este certificado.',
    )
    fecha_vencimiento = fields.Date(
        string='Fecha Vencimiento (Gracia / Reclamos)',
        tracking=True,
        help='Fecha de vencimiento efectiva de la vigencia/gracia para reclamos.',
    )
    fecha_limite_vigencia = fields.Date(
        string='Fecha Límite de Vigencia para Reclamos',
        compute='_compute_fecha_limite_vigencia',
        store=True,
        help='Fecha real hasta la cual el certificado permite crear tickets de reclamo antes de pasar a Vencido.'
    )
    estado_certificado = fields.Selection(
        ESTADO_CERTIFICADO,
        string='Estado / Tag',
        default='vigente',
        required=True,
        tracking=True,
        help='Estado o etiqueta descriptiva del certificado'
    )
    dias_para_vencer = fields.Integer(
        string='Días para Vencer',
        compute='_compute_dias_para_vencer',
        help='Días faltantes para el vencimiento de la gracia/validez de reclamos.'
    )
    archivo = fields.Binary(
        string='Archivo PDF',
        attachment=True,
        required=True,
    )
    archivo_nombre = fields.Char(
        string='Nombre de archivo',
        required=True,
    )
    notas = fields.Text(
        string='Observaciones',
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True,
    )

    @api.depends('fecha_vencimiento')
    def _compute_fecha_limite_vigencia(self):
        for rec in self:
            rec.fecha_limite_vigencia = rec.fecha_vencimiento

    @api.depends('fecha_vencimiento')
    def _compute_dias_para_vencer(self):
        hoy = fields.Date.today()
        for rec in self:
            if rec.fecha_vencimiento:
                rec.dias_para_vencer = (rec.fecha_vencimiento - hoy).days
            else:
                rec.dias_para_vencer = 0

    # --- Concesionario Emisor ---
    concesionario_id = fields.Many2one(
        'pv.concesionario',
        string='Concesionario Emisor',
        store=True,
        tracking=True,
    )

    # --- Tickets / Reclamos ---
    ticket_ids = fields.One2many(
        'pv.ticket',
        'certificado_id',
        string='Tickets / Reclamos',
    )
    ticket_count = fields.Integer(
        compute='_compute_ticket_count',
        string='Cantidad de Tickets',
    )

    @api.depends('ticket_ids')
    def _compute_ticket_count(self):
        for rec in self:
            rec.ticket_count = len(rec.ticket_ids)

    def action_view_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tickets de %s', self.name),
            'res_model': 'pv.ticket',
            'view_mode': 'list,form',
            'domain': [('certificado_id', '=', self.id)],
            'context': {
                'default_maquina_id': self.maquina_id.id,
                'default_certificado_id': self.id,
            },
        }

    @api.depends('tipo', 'maquina_id.of')
    def _compute_name(self):
        for rec in self:
            tipo_label = dict(TIPO_CERTIFICADO).get(rec.tipo, '')
            of = rec.maquina_id.sudo().of or ''
            rec.name = f"{tipo_label} - {of}"

    @api.constrains('tipo', 'maquina_id', 'estado_certificado', 'active')
    def _check_certificado_order(self):
        for rec in self:
            if not rec.active or rec.estado_certificado != 'vigente':
                continue
            if rec.tipo == 'feu':
                fru_exists = self.search_count([
                    ('maquina_id', '=', rec.maquina_id.id),
                    ('tipo', '=', 'fru'),
                    ('active', '=', True),
                ])
                if not fru_exists:
                    raise ValidationError(_(
                        'No se puede cargar un Formulario de Entrega de Unidad (FEU) sin antes haber cargado '
                        'el Formulario de Recepción de Unidad (FRU) para la máquina %s.', rec.maquina_id.name
                    ))
            elif rec.tipo == 'cpm':
                feu_exists = self.search_count([
                    ('maquina_id', '=', rec.maquina_id.id),
                    ('tipo', '=', 'feu'),
                    ('active', '=', True),
                ])
                if not feu_exists:
                    raise ValidationError(_(
                        'No se puede cargar un Certificado de Puesta en Marcha (CPM) sin antes haber cargado '
                        'el Formulario de Entrega de Unidad (FEU) para la máquina %s.', rec.maquina_id.name
                    ))

    def _get_calculated_vencimiento(self, tipo, fecha, maquina):
        """Calcula la fecha de vencimiento real de la vigencia/gracia para reclamos."""
        from datetime import timedelta
        if not maquina or tipo == 'cpm':
            return False

        param_obj = self.env['ir.config_parameter'].sudo()
        ref_date = fields.Date.to_date(fecha) if fecha else fields.Date.today()
        
        if tipo == 'fru':
            try:
                fru_grace_days = int(param_obj.get_param('posventa.fru_grace_days', 3))
            except ValueError:
                fru_grace_days = 3
            return ref_date + timedelta(days=fru_grace_days)
        elif tipo == 'feu':
            try:
                feu_validity_days = int(param_obj.get_param('posventa.feu_claims_validity_days', 90))
            except ValueError:
                feu_validity_days = 90
            return ref_date + timedelta(days=feu_validity_days)
        return False

    def _get_plazo_nominal_carga(self, tipo, maquina):
        """Devuelve la fecha límite nominal que tenía la máquina para cargar este tipo de certificado."""
        from datetime import timedelta
        if not maquina or tipo == 'cpm':
            return False

        raw_base = maquina.fecha_liberacion or (fields.Date.to_date(maquina.create_date) if maquina.create_date else fields.Date.today())
        base_date = fields.Date.to_date(raw_base) or fields.Date.today()
        param_obj = self.env['ir.config_parameter'].sudo()
        
        if tipo == 'fru':
            try:
                fru_days = int(param_obj.get_param('posventa.fru_expiration_days', 10))
            except ValueError:
                fru_days = 10
            return base_date + timedelta(days=fru_days)
        elif tipo == 'feu':
            try:
                feu_days = int(param_obj.get_param('posventa.feu_expiration_days', 20))
            except ValueError:
                feu_days = 20
            return base_date + timedelta(days=feu_days)
        return False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            maquina = self.env['pv.maquina'].browse(vals.get('maquina_id'))
            if not vals.get('concesionario_id'):
                concesionario = self.env['pv.concesionario'].search([('user_id', '=', self.env.uid)], limit=1)
                if concesionario:
                    vals['concesionario_id'] = concesionario.id
                elif maquina.exists() and maquina.concesionario_id:
                    vals['concesionario_id'] = maquina.concesionario_id.id
            if maquina.exists():
                tipo = vals.get('tipo')
                fecha_emision = fields.Date.to_date(vals.get('fecha')) if vals.get('fecha') else fields.Date.today()
                vals['fecha_vencimiento'] = self._get_calculated_vencimiento(tipo, fecha_emision, maquina)
                plazo_nominal = self._get_plazo_nominal_carga(tipo, maquina)
                vals['fecha_limite_carga'] = plazo_nominal
                if plazo_nominal and fecha_emision > plazo_nominal:
                    vals['dias_retraso_carga'] = (fecha_emision - plazo_nominal).days
                else:
                    vals['dias_retraso_carga'] = 0
        records = super().create(vals_list)
        for rec in records:
            rec.maquina_id.modified(['certificado_ids'])
            if rec.active and rec.estado_certificado == 'vigente':
                if rec.tipo == 'fru':
                    rec.maquina_id.sudo().write({'estado': 'stock'})
                    rec.maquina_id.sudo().message_post(
                        body=_('Formulario de Recepción de Unidad (FRU) cargado. La máquina pasa a estado STOCK.'),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
                elif rec.tipo == 'cpm':
                    rec.maquina_id.sudo().write({'estado': 'vendida'})
                    rec.maquina_id.sudo().message_post(
                        body=_('Certificado de Puesta en Marcha (CPM) cargado. La máquina pasa a estado VENDIDA.'),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
        return records

    def write(self, vals):
        user_fields = {'tipo', 'maquina_id', 'fecha', 'fecha_vencimiento', 'archivo', 'archivo_nombre', 'notas'}
        if user_fields.intersection(vals.keys()):
            for rec in self:
                if rec.id:
                    raise UserError(_('No se puede modificar un certificado una vez guardado. Si necesita realizar cambios, desactívelo o archívelo.'))

        if 'tipo' in vals or 'fecha' in vals or 'maquina_id' in vals:
            for rec in self:
                maquina = self.env['pv.maquina'].browse(vals.get('maquina_id', rec.maquina_id.id))
                tipo = vals.get('tipo', rec.tipo)
                fecha = vals.get('fecha', rec.fecha)
                vals['fecha_vencimiento'] = self._get_calculated_vencimiento(tipo, fecha, maquina)
        
        res = super().write(vals)

        if 'active' in vals or 'estado_certificado' in vals or 'maquina_id' in vals:
            for rec in self:
                rec.maquina_id.modified(['certificado_ids'])

        if ('active' in vals and vals['active']) or ('estado_certificado' in vals and vals['estado_certificado'] == 'vigente'):
            for rec in self:
                if rec.estado_certificado == 'vigente':
                    if rec.tipo == 'fru':
                        rec.maquina_id.sudo().write({'estado': 'stock'})
                    elif rec.tipo == 'cpm':
                        rec.maquina_id.sudo().write({'estado': 'vendida'})
        return res

    @api.constrains('maquina_id', 'tipo', 'estado_certificado', 'active')
    def _check_unique_tipo_maquina(self):
        for rec in self:
            if rec.estado_certificado != 'vigente' or not rec.active:
                continue
            if rec.tipo == 'fru':
                # El FRU no se puede renovar: no puede haber más de un FRU (vigente o vencido)
                fru_count = self.search_count([
                    ('maquina_id', '=', rec.maquina_id.id),
                    ('tipo', '=', 'fru'),
                    ('estado_certificado', 'in', ('vigente', 'vencido')),
                    ('active', '=', True),
                    ('id', '!=', rec.id)
                ])
                if fru_count > 0:
                    raise ValidationError(_('El Formulario de Recepción de Unidad (FRU) ya ha sido cargado para esta máquina y no puede renovarse. Debe cargar el Formulario de Entrega (FEU).'))
            else:
                domain = [
                    ('maquina_id', '=', rec.maquina_id.id),
                    ('tipo', '=', rec.tipo),
                    ('estado_certificado', '=', 'vigente'),
                    ('active', '=', True),
                    ('id', '!=', rec.id)
                ]
                if self.search_count(domain) > 0:
                    tipo_label = dict(TIPO_CERTIFICADO).get(rec.tipo, rec.tipo)
                    raise ValidationError(_('Ya existe un certificado vigente de tipo "%s" para esta máquina.', tipo_label))

    @api.constrains('maquina_id', 'estado_certificado', 'active')
    def _check_maquina_cpm_completa(self):
        for rec in self:
            if not rec.active or rec.estado_certificado != 'vigente' or not rec.maquina_id:
                continue
            cpm_exists = self.search_count([
                ('maquina_id', '=', rec.maquina_id.id),
                ('tipo', '=', 'cpm'),
                ('estado_certificado', '=', 'vigente'),
                ('active', '=', True),
                ('id', '!=', rec.id),
            ])
            if cpm_exists:
                raise ValidationError(_(
                    'La máquina %s ya posee un Certificado de Puesta en Marcha (CPM) vigente. '
                    'No se pueden agregar más certificados a una máquina completa.', rec.maquina_id.name
                ))

    @api.constrains('archivo', 'archivo_nombre')
    def _check_archivo_pdf(self):
        extensiones_validas = ('.pdf', '.jpg', '.jpeg', '.png')
        for rec in self:
            if not rec.archivo:
                raise ValidationError(_('El archivo adjunto es obligatorio.'))
            if rec.archivo_nombre and not rec.archivo_nombre.lower().endswith(extensiones_validas):
                raise ValidationError(_('El archivo debe tener una de las siguientes extensiones: %s y este es: %s', extensiones_validas, rec.archivo_nombre))

    @api.model
    def _archive_expired_certificates(self):
        """Cron diario: marcar certificados vencidos cuya fecha límite de vigencia de reclamos haya expirado (excluyendo máquinas con CPM / vendidas)."""
        hoy = fields.Date.today()
        certificados_vencidos = self.search([
            ('active', '=', True),
            ('estado_certificado', '=', 'vigente'),
            ('tipo', '!=', 'cpm'),
            ('maquina_id.tiene_cpm', '=', False),
            ('maquina_id.estado', '!=', 'vendida'),
            ('fecha_limite_vigencia', '!=', False),
            ('fecha_limite_vigencia', '<', hoy)
        ])
        
        for cert in certificados_vencidos:
            tipo_label = dict(TIPO_CERTIFICADO).get(cert.tipo, cert.tipo)
            cert.maquina_id.sudo().message_post(
                body=_('El certificado %s ha superado su vigencia para reclamos (límite: %s). Su estado pasa a Vencido.') % (tipo_label, cert.fecha_limite_vigencia),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
        
        if certificados_vencidos:
            certificados_vencidos.write({'estado_certificado': 'vencido'})

    @api.model
    def _notify_upcoming_certificate_expiration(self):
        """Cron diario: Notificar a los concesionarios 3 días antes de que venza cualquier certificado."""
        from datetime import timedelta
        hoy = fields.Date.today()
        tres_dias_despues = hoy + timedelta(days=3)
        
        certificados_por_vencer = self.search([
            ('active', '=', True),
            ('estado_certificado', '=', 'vigente'),
            ('fecha_vencimiento', '=', tres_dias_despues)
        ])
        
        for cert in certificados_por_vencer:
            tipo_label = dict(TIPO_CERTIFICADO).get(cert.tipo, cert.tipo)
            body_msg = _(
                "⚠️ El certificado %s de la máquina %s vencerá en 3 días (el %s)."
            ) % (tipo_label, cert.maquina_id.name, cert.fecha_vencimiento)
            
            cert.maquina_id.sudo().message_post(
                body=body_msg,
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            partner = cert.concesionario_id.partner_id
            if partner and partner.email:
                self.env['mail.mail'].sudo().create({
                    'subject': _('Vencimiento Próximo de Certificado: %s') % cert.maquina_id.name,
                    'body_html': f'<p>Estimado/a Concesionario {cert.concesionario_id.name},</p>'
                                  f'<p>Le informamos que el certificado <b>{tipo_label}</b> para la máquina '
                                  f'<b>{cert.maquina_id.name}</b> vencerá el {cert.fecha_vencimiento}.</p>'
                                  f'<p>Por favor, ingrese un nuevo certificado a la brevedad para evitar bloqueos.</p>',
                     'email_to': partner.email,
                }).send()

    @api.model
    def get_portal_list_data(self, search_term="", tipo_filter="", estado_filter=""):
        """Return list of certificates for the concesionario portal."""
        domain = [('active', '=', True)]
        if search_term:
            domain += ['|', '|',
                ('maquina_id.of', 'ilike', search_term),
                ('archivo_nombre', 'ilike', search_term),
                ('concesionario_id.name', 'ilike', search_term),
            ]
        if tipo_filter:
            domain += [('tipo', '=', tipo_filter)]
        if estado_filter:
            domain += [('estado_certificado', '=', estado_filter)]

        records = self.search(domain, order='fecha desc, id desc')
        res = []
        is_internal = self.env.user.has_group('posventa.group_pv_staff') or self.env.user.has_group('posventa.group_pv_admin')
        my_uid = self.env.uid
        for c in records:
            retraso = c.dias_retraso_carga or 0
            if c.estado_certificado == 'vigente':
                if retraso > 0:
                    tag_label = _('Vencido hace %s días') % retraso
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
                tag_label = dict(self._fields['estado_certificado'].selection).get(c.estado_certificado, c.estado_certificado)
                tag_badge = 'secondary'

            m = c.maquina_id.sudo() if c.maquina_id else None
            puede_ver_maquina = bool(
                is_internal or 
                (m and m.concesionario_id.user_id.id == my_uid) or 
                (m and m.concesionario_destino_id.user_id.id == my_uid and m.estado == 'pendiente')
            )

            res.append({
                'id': c.id,
                'name': c.name or '',
                'tipo': c.tipo,
                'tipo_label': dict(self._fields['tipo'].selection).get(c.tipo, ''),
                'maquina_id': m.id if m else False,
                'maquina_name': m.name or '' if m else '',
                'maquina_of': m.of or '' if m else '',
                'maquina_tipo_label': dict(self.env['pv.maquina']._fields['tipo'].selection).get(m.tipo, '') if m else '',
                'puede_ver_maquina': puede_ver_maquina,
                'fecha': str(c.fecha) if c.fecha else '',
                'fecha_vencimiento': str(c.fecha_vencimiento) if c.fecha_vencimiento else '',
                'fecha_limite_vigencia': str(c.fecha_limite_vigencia) if c.fecha_limite_vigencia else '',
                'dias_para_vencer': c.dias_para_vencer or 0,
                'dias_retraso_carga': retraso,
                'estado_certificado': c.estado_certificado,
                'estado_certificado_label': tag_label,
                'tag_badge': tag_badge,
                'concesionario_name': c.concesionario_id.name or '',
                'archivo_nombre': c.archivo_nombre or '',
            })
        return res

