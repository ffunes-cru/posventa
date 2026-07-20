# Part of Crucianelli Posventa Module
{
    'name': 'Posventa Crucianelli',
    'version': '19.0.1.0.0',
    'category': 'Services/Aftersales',
    'summary': 'Gestión integral de reclamos de posventa centrada en la máquina',
    'description': """
Plataforma de Posventa Crucianelli
===================================
Módulo para la gestión integral de reclamos de posventa:
- Gestión de máquinas con trazabilidad completa
- Certificados (CPM, FRU, FEU, Informe de Servicio, Recall)
- Tickets de reclamo con flujo de estados
- Catálogos de sistemas, subsistemas y problemas
- Dashboard operativo con KPIs (T1, T2, T3)
- Importación masiva de máquinas desde Excel
- Comunicación centralizada dentro del ticket
- Seguimiento de medidas y vencimientos
    """,
    'author': 'Crucianelli',
    'website': 'https://www.crucianelli.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'board',
    ],
    'data': [
        # Security
        'security/pv_security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence_data.xml',
        'data/pv_sistema_data.xml',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
        'data/ir_config_parameter_data.xml',
        # Wizard
        'wizard/pv_import_maquinas_views.xml',
        'wizard/pv_transferir_maquina_wizard_views.xml',
        'wizard/pv_ticket_chat_wizard_views.xml',
        'wizard/pv_aceptar_ticket_wizard_views.xml',
        # Views
        'views/res_config_settings_views.xml',
        'views/pv_concesionario_views.xml',
        'views/pv_maquina_views.xml',
        'views/pv_certificado_views.xml',
        'views/pv_ticket_views.xml',
        'views/pv_ticket_medida_views.xml',
        'views/pv_catalogo_views.xml',
        'views/pv_dashboard_views.xml',
        'views/pv_menu.xml',
        # Report
        'report/pv_ticket_report.xml',
    ],
    'external_dependencies': {
        'python': ['openpyxl'],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
