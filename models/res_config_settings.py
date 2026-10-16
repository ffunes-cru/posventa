# Part of Crucianelli Posventa Module
from odoo import fields, models


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
    pv_rclone_remote = fields.Char(
        string='Remoto de rclone (Google Drive)',
        config_parameter='posventa.rclone_remote',
        default='crucianelli_drive',
        help='Nombre del remoto configurado en rclone para Google Drive.'
    )
    pv_rclone_drive_folder = fields.Char(
        string='Carpeta en Google Drive',
        config_parameter='posventa.rclone_drive_folder',
        default='Crucianelli_Posventa/Reclamos',
        help='Ruta base dentro de Google Drive donde se almacenarán los archivos de los reclamos.'
    )
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
        ('drive', 'Google Drive (rclone - Streaming Pesado)'),
        ('odoo', 'Almacenamiento Estándar de Odoo (Archivos Locales / Adjuntos)'),
    ], string='Modo de Carga de Archivos', config_parameter='posventa.storage_mode', default='drive',
       help='Permite alternar entre Google Drive y la subida estándar de Odoo en caso de contingencia.')


