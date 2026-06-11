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

TIPO_RECLAMO_PREVIO = [
    ('rotura', 'Rotura'),
    ('faltante', 'Faltante'),
    ('otro', 'Otro'),
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
        ondelete='cascade',
        tracking=True,
    )
    fecha = fields.Date(
        string='Fecha',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    archivo = fields.Binary(
        string='Archivo PDF',
        attachment=True,
    )
    archivo_nombre = fields.Char(
        string='Nombre de archivo',
    )
    notas = fields.Text(
        string='Observaciones',
    )

    # --- Reclamo previo a puesta en marcha (solo FRU) ---
    tiene_reclamo_previo = fields.Boolean(
        string='¿Tiene reclamo previo a la puesta en marcha?',
        help='Marcar si al recepcionar la unidad se detecta un desvío',
    )
    reclamo_previo_tipo = fields.Selection(
        TIPO_RECLAMO_PREVIO,
        string='Tipo de desvío',
    )
    reclamo_previo_comentario = fields.Text(
        string='Detalle del desvío',
    )
    reclamo_previo_multimedia = fields.Char(
        string='Multimedia (link Google Drive)',
    )
    ticket_previo_id = fields.Many2one(
        'pv.ticket',
        string='Ticket generado',
        readonly=True,
    )

    # --- Related fields ---
    concesionario_id = fields.Many2one(
        related='maquina_id.concesionario_id',
        store=True,
    )

    @api.depends('tipo', 'maquina_id.of')
    def _compute_name(self):
        for rec in self:
            tipo_label = dict(TIPO_CERTIFICADO).get(rec.tipo, '')
            of = rec.maquina_id.of or ''
            rec.name = f"{tipo_label} - {of}"

    @api.constrains('tipo', 'maquina_id')
    def _check_cpm_vendida(self):
        """CPM can only be uploaded when machine is VENDIDA."""
        for rec in self:
            if rec.tipo == 'cpm' and rec.maquina_id.estado != 'vendida':
                raise ValidationError(_(
                    'No se puede cargar un CPM si la máquina no está '
                    'en estado VENDIDA. Máquina: %s', rec.maquina_id.name
                ))

    @api.constrains('tiene_reclamo_previo', 'reclamo_previo_tipo', 'tipo')
    def _check_reclamo_previo_fields(self):
        for rec in self:
            if rec.tiene_reclamo_previo and rec.tipo == 'fru':
                if not rec.reclamo_previo_tipo:
                    raise ValidationError(_(
                        'Debe seleccionar el tipo de desvío del reclamo previo.'
                    ))

    def action_crear_ticket_previo(self):
        """Create a pre-PM ticket from FRU with claim."""
        self.ensure_one()
        if self.tipo != 'fru':
            raise UserError(_('Solo se puede crear un ticket previo desde un FRU.'))
        if not self.tiene_reclamo_previo:
            raise UserError(_('No se marcó reclamo previo.'))
        if self.ticket_previo_id:
            raise UserError(_('Ya existe un ticket previo para este certificado.'))

        ticket = self.env['pv.ticket'].create({
            'maquina_id': self.maquina_id.id,
            'tipo_ticket': 'pre_pm',
            'descripcion': self.reclamo_previo_comentario or '',
            'multimedia_url': self.reclamo_previo_multimedia or '',
            'prioridad': 'media',
        })
        self.ticket_previo_id = ticket.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Ticket Previo'),
            'res_model': 'pv.ticket',
            'view_mode': 'form',
            'res_id': ticket.id,
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Auto-create pre-PM ticket if FRU with reclamo previo
        for rec in records:
            if rec.tipo == 'fru' and rec.tiene_reclamo_previo:
                rec.action_crear_ticket_previo()
        return records
