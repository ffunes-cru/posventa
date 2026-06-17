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
        required=True,
    )
    archivo_nombre = fields.Char(
        string='Nombre de archivo',
        required=True,
    )
    notas = fields.Text(
        string='Observaciones',
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

    @api.constrains('maquina_id', 'tipo')
    def _check_unique_tipo_maquina(self):
        for rec in self:
            domain = [('maquina_id', '=', rec.maquina_id.id), ('tipo', '=', rec.tipo), ('id', '!=', rec.id)]
            if self.search_count(domain) > 0:
                tipo_label = dict(TIPO_CERTIFICADO).get(rec.tipo, rec.tipo)
                raise ValidationError(_('Ya existe un certificado de tipo "%s" para esta máquina.', tipo_label))

    @api.constrains('archivo', 'archivo_nombre')
    def _check_archivo_pdf(self):
        for rec in self:
            if not rec.archivo:
                raise ValidationError(_('El archivo adjunto es obligatorio.'))
            if rec.archivo_nombre and not rec.archivo_nombre.lower().endswith('.pdf'):
                raise ValidationError(_('El archivo debe tener extensión .pdf y este es: %s', rec.archivo_nombre))


