# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..tools import drive


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pv_fru_expiration_days = fields.Integer(
        string='Plazo de Carga FRU (Días)',
        config_parameter='posventa.fru_expiration_days',
        default=10,
        help='Días desde el ingreso/liberación de la máquina para que venza el plazo nominal de carga del FRU.'
    )
    pv_fru_grace_days = fields.Integer(
        string='Días de Gracia / Vigencia FRU',
        config_parameter='posventa.fru_grace_days',
        default=3,
        help='Días de gracia tras el vencimiento nominal durante los cuales el FRU sigue vigente para crear tickets antes de pasar a Vencido.'
    )
    pv_feu_expiration_days = fields.Integer(
        string='Plazo de Carga FEU (Días)',
        config_parameter='posventa.feu_expiration_days',
        default=20,
        help='Días desde el ingreso/liberación de la máquina para que venza el plazo nominal de carga del FEU.'
    )
    pv_feu_claims_validity_days = fields.Integer(
        string='Validez de Reclamos FEU (Días)',
        config_parameter='posventa.feu_claims_validity_days',
        default=90,
        help='Días desde la emisión/carga del FEU durante los cuales está vigente para crear tickets antes de vencer y requerir renovación.'
    )
    pv_drive_credenciales = fields.Char(
        string='Cuenta de servicio de Google (JSON)',
        config_parameter=drive.PARAM_CREDENCIALES,
        help='Contenido completo del archivo .json de la clave de la cuenta de servicio (Google Cloud → IAM → '
             'Cuentas de servicio → Claves).'
    )
    pv_drive_cuenta = fields.Char(string='Cuenta a invitar en la unidad', compute='_compute_pv_drive_cuenta')
    pv_drive_unidad_id = fields.Char(
        string='ID de la unidad compartida',
        config_parameter=drive.PARAM_UNIDAD,
        help='Lo que sigue a /drive/folders/ en la URL al abrir la unidad compartida en el navegador.'
    )
    pv_drive_carpeta = fields.Char(
        string='Carpeta en Google Drive',
        config_parameter=drive.PARAM_CARPETA,
        default=drive.CARPETA_BASE_DEFAULT,
        help='Ruta dentro de la unidad compartida donde se crea una carpeta por reclamo.'
    )
    pv_drive_en_espera = fields.Integer(string='Archivos esperando subida', compute='_compute_pv_drive_en_espera')
    pv_multimedia_chunk_size_kb = fields.Integer(
        string='Tamaño de Bloque (KB)',
        config_parameter='posventa.chunk_size_kb',
        default=768,
        help='Tamaño en KB de cada fragmento al subir archivos pesados por streaming (768 KB recomendado si Nginx tiene límite de 1MB).'
    )
    pv_multimedia_max_size_mb = fields.Integer(
        string='Tamaño Máximo de Archivo (MB)',
        config_parameter='posventa.max_file_size_mb',
        default=1024,
        help='Límite máximo permitido en MB para archivos multimedia pesados (por defecto 1024 MB = 1 GB).'
    )
    pv_storage_mode = fields.Selection([
        ('drive', 'Google Drive (unidad compartida)'),
        ('odoo', 'Almacenamiento Estándar de Odoo (Archivos Locales / Adjuntos)'),
    ], string='Modo de Carga de Archivos', config_parameter='posventa.storage_mode', default='drive',
       help='Permite alternar entre Google Drive y la subida estándar de Odoo en caso de contingencia.')

    @api.depends('pv_drive_credenciales')
    def _compute_pv_drive_cuenta(self):
        for settings in self:
            settings.pv_drive_cuenta = drive.cuenta_de_servicio(settings.pv_drive_credenciales)

    def _compute_pv_drive_en_espera(self):
        self.pv_drive_en_espera = self.env['pv.ticket.multimedia'].sudo().search_count(
            [('estado_sync', 'in', ('procesando', 'error'))])

    def set_values(self):
        if self.pv_drive_credenciales and not self.pv_drive_cuenta:
            raise UserError(_("El JSON de la cuenta de servicio no es válido: pegue el contenido completo del "
                              "archivo .json descargado de Google Cloud."))
        super().set_values()
        if self.pv_drive_en_espera:
            self.env.ref('posventa.cron_pv_sync_multimedia_drive')._trigger()

    def action_pv_probar_drive(self):
        """Prueba la conexión con los valores del formulario, antes de guardarlos."""
        self.ensure_one()
        try:
            drive.RcloneDrive(self.pv_drive_credenciales, self.pv_drive_unidad_id, self.pv_drive_carpeta).verificar()
        except drive.DriveError as e:
            tipo, mensaje = 'danger', str(e)
        else:
            tipo, mensaje = 'success', _("Conexión correcta: la carpeta '%s' existe y se puede escribir.",
                                         self.pv_drive_carpeta)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _("Google Drive"), 'message': mensaje, 'type': tipo, 'sticky': tipo == 'danger'},
        }
