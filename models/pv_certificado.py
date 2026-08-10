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
    fecha_vencimiento = fields.Date(
        string='Fecha Vencimiento',
        tracking=True,
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

    # --- Related fields ---
    concesionario_id = fields.Many2one(
        related='maquina_id.concesionario_id',
        store=True,
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
            of = rec.maquina_id.of or ''
            rec.name = f"{tipo_label} - {of}"

    @api.constrains('tipo', 'maquina_id', 'active')
    def _check_certificado_order(self):
        for rec in self:
            if not rec.active:
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
                        'y tener activo el Formulario de Recepción de Unidad (FRU) para la máquina %s.', rec.maquina_id.name
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
                        'y tener activo el Formulario de Entrega de Unidad (FEU) para la máquina %s.', rec.maquina_id.name
                    ))

    def _get_calculated_vencimiento(self, tipo, fecha, maquina):
        from datetime import timedelta
        if not maquina:
            return fecha or fields.Date.today()
        # La fecha de ingreso de la máquina es su fecha de creación
        base_date = fields.Date.to_date(maquina.create_date) if maquina.create_date else fields.Date.today()
        ref_date = fields.Date.to_date(fecha) if fecha else fields.Date.today()
        
        # Recuperar parámetros del sistema con valores por defecto
        param_obj = self.env['ir.config_parameter'].sudo()
        try:
            fru_days = int(param_obj.get_param('posventa.fru_expiration_days', 10))
        except ValueError:
            fru_days = 10
        try:
            feu_days = int(param_obj.get_param('posventa.feu_expiration_days', 20))
        except ValueError:
            feu_days = 20
        try:
            cpm_days = int(param_obj.get_param('posventa.cpm_expiration_days', 60))
        except ValueError:
            cpm_days = 60
        
        if tipo == 'fru':
            return base_date + timedelta(days=fru_days)
        elif tipo == 'feu':
            return base_date + timedelta(days=feu_days)
        elif tipo == 'cpm':
            return ref_date + timedelta(days=cpm_days)
        return ref_date

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            maquina = self.env['pv.maquina'].browse(vals.get('maquina_id'))
            if maquina.exists():
                vals['fecha_vencimiento'] = self._get_calculated_vencimiento(
                    vals.get('tipo'),
                    vals.get('fecha'),
                    maquina
                )
        records = super().create(vals_list)
        # Cambios de estado en la máquina según el tipo de certificado cargado
        for rec in records:
            rec.maquina_id.modified(['certificado_ids'])
            if rec.active:
                if rec.tipo == 'fru':
                    rec.maquina_id.sudo().write({'estado': 'stock'})
                    rec.maquina_id.message_post(
                        body=_('Formulario de Recepción de Unidad (FRU) cargado. La máquina pasa a estado STOCK.'),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
                elif rec.tipo == 'cpm':
                    rec.maquina_id.sudo().write({'estado': 'vendida'})
                    rec.maquina_id.message_post(
                        body=_('Certificado de Puesta en Marcha (CPM) cargado. La máquina pasa a estado VENDIDA.'),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
        return records

    def write(self, vals):
        # Impedir modificaciones una vez creado el certificado (excepto campo active)
        user_fields = {'tipo', 'maquina_id', 'fecha', 'fecha_vencimiento', 'archivo', 'archivo_nombre', 'notas'}
        if user_fields.intersection(vals.keys()):
            for rec in self:
                if rec.id:
                    raise UserError(_('No se puede modificar un certificado una vez guardado. Si necesita realizar cambios, archívelo y cree uno nuevo.'))

        # Recalcular vencimiento si cambia tipo o fecha
        if 'tipo' in vals or 'fecha' in vals or 'maquina_id' in vals:
            for rec in self:
                maquina = self.env['pv.maquina'].browse(vals.get('maquina_id', rec.maquina_id.id))
                tipo = vals.get('tipo', rec.tipo)
                fecha = vals.get('fecha', rec.fecha)
                vals['fecha_vencimiento'] = self._get_calculated_vencimiento(tipo, fecha, maquina)
        
        res = super().write(vals)

        # Si cambia active o maquina_id, avisamos a la máquina
        if 'active' in vals or 'maquina_id' in vals:
            for rec in self:
                rec.maquina_id.modified(['certificado_ids'])

        # Si se vuelven a activar certificados o cambian, recalcular estado de máquina
        if 'active' in vals and vals['active']:
            for rec in self:
                if rec.tipo == 'fru':
                    rec.maquina_id.sudo().write({'estado': 'stock'})
                elif rec.tipo == 'cpm':
                    rec.maquina_id.sudo().write({'estado': 'vendida'})
        return res

    @api.constrains('maquina_id', 'tipo', 'active')
    def _check_unique_tipo_maquina(self):
        for rec in self:
            domain = [('maquina_id', '=', rec.maquina_id.id), ('tipo', '=', rec.tipo), ('active', '=', True), ('id', '!=', rec.id)]
            if self.search_count(domain) > 0:
                tipo_label = dict(TIPO_CERTIFICADO).get(rec.tipo, rec.tipo)
                raise ValidationError(_('Ya existe un certificado activo de tipo "%s" para esta máquina.', tipo_label))

    @api.constrains('maquina_id', 'active')
    def _check_maquina_cpm_completa(self):
        for rec in self:
            if not rec.active or not rec.maquina_id:
                continue
            cpm_exists = self.search_count([
                ('maquina_id', '=', rec.maquina_id.id),
                ('tipo', '=', 'cpm'),
                ('active', '=', True),
                ('id', '!=', rec.id),
            ])
            if cpm_exists:
                raise ValidationError(_(
                    'La máquina %s ya posee un Certificado de Puesta en Marcha (CPM) activo. '
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
        """Cron diario: archivar CPMs vencidos, notificar FRU/FEU vencidos."""
        hoy = fields.Date.today()
        # Buscamos certificados activos cuya fecha de vencimiento sea anterior a hoy
        certificados_vencidos = self.search([
            ('active', '=', True),
            ('fecha_vencimiento', '<', hoy)
        ])
        
        for cert in certificados_vencidos:
            if cert.tipo == 'cpm':
                cert.maquina_id.sudo().write({'estado': 'cpm_vencido'})
                cert.maquina_id.message_post(
                    body=_('El Certificado de Puesta en Marcha (CPM) ha vencido. La máquina pasa a estado CPM VENCIDO.'),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
            elif cert.tipo in ('fru', 'feu'):
                tipo_label = dict(TIPO_CERTIFICADO).get(cert.tipo, cert.tipo)
                cert.maquina_id.message_post(
                    body=_('El certificado %s ha vencido el %s. Recuerde regularizar su carga.') % (tipo_label, cert.fecha_vencimiento),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
        
        # Desactivamos únicamente los CPM vencidos
        cpm_vencidos = certificados_vencidos.filtered(lambda c: c.tipo == 'cpm')
        if cpm_vencidos:
            cpm_vencidos.write({'active': False})

    @api.model
    def _notify_upcoming_certificate_expiration(self):
        """Cron diario: Notificar a los concesionarios 3 días antes de que venza cualquier certificado."""
        from datetime import timedelta
        hoy = fields.Date.today()
        tres_dias_despues = hoy + timedelta(days=3)
        
        certificados_por_vencer = self.search([
            ('active', '=', True),
            ('fecha_vencimiento', '=', tres_dias_despues)
        ])
        
        for cert in certificados_por_vencer:
            tipo_label = dict(TIPO_CERTIFICADO).get(cert.tipo, cert.tipo)
            body_msg = _(
                "⚠️ El certificado %s de la máquina %s vencerá en 3 días (el %s)."
            ) % (tipo_label, cert.maquina_id.name, cert.fecha_vencimiento)
            
            cert.maquina_id.message_post(
                body=body_msg,
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            # Enviar correo al concesionario
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
