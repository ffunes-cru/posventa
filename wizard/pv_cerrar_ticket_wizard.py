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
        string='Nro. Orden SAP',
    )
    tipo_garantia = fields.Selection([
        ('tecnica', 'Técnica'),
        ('comercial', 'Comercial'),
    ], string='Clasificación de Garantía', default='tecnica', required=True)
    garantia_aceptada = fields.Boolean(
        string='¿Se acepta la garantía?',
        default=True,
        required=True,
    )
    rechazo_tag_ids = fields.Many2many(
        'pv.tipo.rechazo',
        string='Motivos de Rechazo',
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

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ticket_id = res.get('ticket_id') or self.env.context.get('active_id')
        if ticket_id:
            ticket = self.env['pv.ticket'].browse(ticket_id)
            if ticket.exists():
                if 'sap_numero_orden' in fields_list and not res.get('sap_numero_orden'):
                    res['sap_numero_orden'] = ticket.sap_numero_orden or ''
                if 'tipo_garantia' in fields_list and ticket.tipo_garantia:
                    res['tipo_garantia'] = ticket.tipo_garantia
                if 'rechazo_tag_ids' in fields_list and ticket.rechazo_tag_ids:
                    res['rechazo_tag_ids'] = [(6, 0, ticket.rechazo_tag_ids.ids)]
        return res

    def action_confirmar(self):
        self.ensure_one()
        ticket = self.ticket_id
        if ticket.estado != 'aceptado':
            raise UserError(_("Solo se pueden cerrar tickets en estado 'Aceptado'."))

        ticket_vals = {
            'estado': 'cerrado',
            'fecha_cierre': fields.Datetime.now(),
            'garantia_aceptada': self.garantia_aceptada,
            'garantia_observaciones': self.garantia_observaciones,
            'garantia_adjunto': self.garantia_adjunto,
            'garantia_adjunto_name': self.garantia_adjunto_name,
            'tipo_garantia': self.tipo_garantia,
        }
        if self.sap_numero_orden:
            ticket_vals['sap_numero_orden'] = self.sap_numero_orden
        if self.rechazo_tag_ids:
            ticket_vals['rechazo_tag_ids'] = [(6, 0, self.rechazo_tag_ids.ids)]
            reasons_str = ", ".join(self.rechazo_tag_ids.mapped('name'))
            if not ticket.motivo_rechazo:
                ticket_vals['motivo_rechazo'] = reasons_str

        ticket.write(ticket_vals)

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
        tipo_garantia_label = dict(self._fields['tipo_garantia'].selection).get(self.tipo_garantia, self.tipo_garantia)
        rechazo_str = ", ".join(self.rechazo_tag_ids.mapped('name')) if self.rechazo_tag_ids else '-'
        body = Markup(_(
            "<h4><b>Cierre de Ticket / Expediente Completo</b></h4>"
            "<b>Clasificación de Garantía:</b> %s<br/>"
            "<b>Resolución de Garantía:</b> %s<br/>"
            "<b>Motivos de Rechazo:</b> %s<br/>"
            "<b>Orden SAP:</b> %s<br/>"
            "<b>Observaciones:</b> %s"
            "%s"
        )) % (
            escape(tipo_garantia_label),
            escape(estado_garantia),
            escape(rechazo_str),
            escape(ticket.sap_numero_orden or '-'),
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
