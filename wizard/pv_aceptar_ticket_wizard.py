# Part of Crucianelli Posventa Module
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PvAceptarTicketWizard(models.TransientModel):
    _name = 'pv.aceptar.ticket.wizard'
    _description = 'Asistente para Aceptar Ticket / Reclamo'

    ticket_id = fields.Many2one(
        'pv.ticket',
        string='Ticket',
        required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    garantia_aceptada = fields.Boolean(
        string='¿Se acepta la garantía?',
        default=True,
        required=True,
    )
    garantia_observaciones = fields.Text(
        string='Observaciones de Garantía',
    )
    garantia_adjunto = fields.Binary(
        string='Archivo Adjunto',
    )
    garantia_adjunto_name = fields.Char(
        string='Nombre del Archivo',
    )

    def action_confirmar(self):
        self.ensure_one()
        ticket = self.ticket_id
        if ticket.estado != 'en_proceso':
            raise UserError(_("Solo se pueden aceptar tickets en estado 'En Proceso'."))

        # Guardamos la info de la garantía en el ticket
        ticket.write({
            'estado': 'aceptado',
            'fecha_solucion': fields.Datetime.now(),
            'garantia_aceptada': self.garantia_aceptada,
            'garantia_observaciones': self.garantia_observaciones,
            'garantia_adjunto': self.garantia_adjunto,
            'garantia_adjunto_name': self.garantia_adjunto_name,
        })

        # Registrar mensaje en chatter con la info de la garantía
        adjunto_html = ""
        if self.garantia_adjunto and self.garantia_adjunto_name:
            # Creamos el attachment real de Odoo
            attachment = self.env['ir.attachment'].create({
                'name': self.garantia_adjunto_name,
                'type': 'binary',
                'datas': self.garantia_adjunto,
                'res_model': 'pv.ticket',
                'res_id': ticket.id,
            })
            # Adjuntamos el attachment al mensaje
            adjunto_html = f"<br/><b>Archivo Adjunto:</b> {self.garantia_adjunto_name}"

        estado_garantia = "ACEPTADA" if self.garantia_aceptada else "RECHAZADA"
        body = _(
            "<h4><b>Reclamo Aceptado y Validado</b></h4>"
            "<b>Garantía:</b> %s<br/>"
            "<b>Observaciones:</b> %s"
            "%s"
        ) % (estado_garantia, self.garantia_observaciones or 'Sin observaciones', adjunto_html)

        ticket.message_post(
            body=body,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
            attachment_ids=[attachment.id] if self.garantia_adjunto and self.garantia_adjunto_name else []
        )

        # Enviar correo predeterminado
        template = self.env.ref('posventa.mail_template_ticket_aceptado', raise_if_not_found=False)
        if template:
            template.send_mail(ticket.id, force_send=True)

        return {'type': 'ir.actions.act_window_close'}
