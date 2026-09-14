# Part of Crucianelli Posventa Module
from markupsafe import Markup, escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PvCerrarTicketWizard(models.TransientModel):
    _name = 'pv.cerrar.ticket.wizard'
    _description = 'Asistente para Cerrar Ticket / Garantía y Devolución de Pieza'

    ticket_id = fields.Many2one(
        'pv.ticket',
        string='Ticket',
        required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    sap_numero_orden = fields.Char(
        related='ticket_id.sap_numero_orden',
        string='Nro. Orden SAP',
        readonly=True,
    )
    garantia_aceptada = fields.Boolean(
        string='¿Se acepta la garantía?',
        default=True,
        required=True,
    )
    garantia_observaciones = fields.Text(
        string='Observaciones de Garantía / Devolución',
    )
    garantia_adjunto = fields.Binary(
        string='Archivo Adjunto (Comprobante / Devolución)',
    )
    garantia_adjunto_name = fields.Char(
        string='Nombre del Archivo',
    )

    def action_confirmar(self):
        self.ensure_one()
        ticket = self.ticket_id
        if ticket.estado != 'aceptado':
            raise UserError(_("Solo se pueden cerrar tickets en estado 'Aceptado'."))

        # Guardamos la info de la garantía y cerramos el ticket
        ticket.write({
            'estado': 'cerrado',
            'fecha_cierre': fields.Datetime.now(),
            'garantia_aceptada': self.garantia_aceptada,
            'garantia_observaciones': self.garantia_observaciones,
            'garantia_adjunto': self.garantia_adjunto,
            'garantia_adjunto_name': self.garantia_adjunto_name,
        })

        attachment_id = False
        adjunto_html = ""
        if self.garantia_adjunto and self.garantia_adjunto_name:
            attachment = self.env['ir.attachment'].create({
                'name': self.garantia_adjunto_name,
                'type': 'binary',
                'datas': self.garantia_adjunto,
                'res_model': 'pv.ticket',
                'res_id': ticket.id,
            })
            attachment_id = attachment.id
            adjunto_html = Markup("<br/><b>Archivo Adjunto:</b> %s") % escape(self.garantia_adjunto_name)

        estado_garantia = "ACEPTADA" if self.garantia_aceptada else "RECHAZADA"
        body = Markup(_(
            "<h4><b>Cierre de Ticket / Expediente Completo</b></h4>"
            "<b>Orden SAP:</b> %s<br/>"
            "<b>Garantía:</b> %s<br/>"
            "<b>Observaciones:</b> %s"
            "%s"
        )) % (
            escape(ticket.sap_numero_orden or '-'),
            escape(estado_garantia),
            escape(self.garantia_observaciones or 'Sin observaciones'),
            adjunto_html
        )

        ticket.message_post(
            body=body,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
            attachment_ids=[attachment_id] if attachment_id else []
        )

        return {'type': 'ir.actions.act_window_close'}
