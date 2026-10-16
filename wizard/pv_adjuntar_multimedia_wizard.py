# Part of Crucianelli Posventa Module
import os

from markupsafe import Markup, escape
from odoo import fields, models, _
from odoo.exceptions import UserError


class PvTicketMultimediaWizard(models.TransientModel):
    """Staff: vincula un enlace de Drive o confirma un archivo ya subido por fragmentos (widget)."""
    _name = 'pv.ticket.multimedia.wizard'
    _description = 'Asistente para Adjuntar Archivo Multimedia / Video Drive'

    ticket_id = fields.Many2one(
        'pv.ticket',
        string='Ticket',
        required=True,
        default=lambda self: self.env.context.get('default_ticket_id') or self.env.context.get('active_id'),
    )
    tipo_carga = fields.Selection([
        ('archivo', 'Subir Archivo Local / Video'),
        ('enlace_drive', 'Vincular Enlace Directo (Google Drive / URL Externa)'),
    ], string='Tipo de Carga', default='archivo', required=True)
    name = fields.Char(
        string='Título o Nombre Descriptivo',
        help='Nombre visible para identificar este archivo multimedia en el ticket.',
    )
    drive_url = fields.Char(string='Enlace Google Drive / URL')
    chunk_file_uploader = fields.Char(string='Carga de Archivo Pesado')
    uploaded_multimedia_id = fields.Many2one('pv.ticket.multimedia', string='Archivo Multimedia Cargado')

    def action_adjuntar(self):
        self.ensure_one()
        if self.tipo_carga == 'enlace_drive':
            self._vincular_enlace()
        else:
            self._confirmar_archivo_subido()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _vincular_enlace(self):
        url = (self.drive_url or '').strip()
        if not url:
            raise UserError(_("Debe ingresar un enlace válido de Google Drive o URL externa."))
        ticket = self.ticket_id
        nombre = (self.name or '').strip() or _("Enlace Google Drive - %s", fields.Date.today())
        attachment = self.env['ir.attachment'].sudo().create({
            'name': nombre, 'type': 'url', 'url': url, 'res_model': 'pv.ticket', 'res_id': ticket.id,
        })
        self.env['pv.ticket.multimedia'].create({
            'ticket_id': ticket.id,
            'name': nombre,
            'drive_url': url,
            'estado_sync': 'disponible',
            'mimetype': 'text/html',
            'ir_attachment_id': attachment.id,
        })
        if not ticket.multimedia_url:
            ticket.multimedia_url = url
        ticket.message_post(
            body=Markup(_(
                "🔗 <b>Se vinculó un enlace de Google Drive:</b> %s<br/>"
                "<a href='%s' target='_blank' class='btn btn-sm btn-outline-primary mt-1'>▶ Abrir en Google Drive</a>"
            )) % (escape(nombre), escape(url)),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

    def _confirmar_archivo_subido(self):
        multimedia = self.uploaded_multimedia_id
        if not multimedia:
            raise UserError(_("Por favor seleccione un archivo y aguarde a que finalice la subida antes de confirmar."))
        nombre = (self.name or '').strip()
        if nombre:
            # El título reemplaza al nombre de archivo, conservando la extensión
            if not os.path.splitext(nombre)[1]:
                nombre += os.path.splitext(multimedia.name or '')[1]
            multimedia.name = nombre
