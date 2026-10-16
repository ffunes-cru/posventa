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
    garantia_rechazo_tag_ids = fields.Many2many(
        'pv.tipo.rechazo',
        string='Motivos sin Cobertura',
        domain=[('aplica_a', '=', 'garantia')],
    )
    solucion_aplicada = fields.Text(
        string='Solución Aplicada',
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
                if 'garantia_rechazo_tag_ids' in fields_list and ticket.garantia_rechazo_tag_ids:
                    res['garantia_rechazo_tag_ids'] = [(6, 0, ticket.garantia_rechazo_tag_ids.ids)]
                if 'solucion_aplicada' in fields_list and ticket.solucion_aplicada:
                    res['solucion_aplicada'] = ticket.solucion_aplicada
        return res

    def action_confirmar(self):
        self.ensure_one()
        ticket = self.ticket_id
        if ticket.estado != 'aceptado':
            raise UserError(_("Solo se pueden cerrar tickets en estado 'Aceptado'."))
        if not (self.solucion_aplicada or '').strip():
            raise UserError(_("Debe indicar la solución aplicada para cerrar el ticket."))
        if not self.garantia_aceptada and not self.garantia_rechazo_tag_ids:
            raise UserError(_("Si la garantía no cubre la pieza, debe indicar al menos un motivo sin cobertura."))
        sin_cobertura_tags = self.garantia_rechazo_tag_ids if not self.garantia_aceptada else self.env['pv.tipo.rechazo']

        ticket_vals = {
            'garantia_aceptada': self.garantia_aceptada,
            'garantia_observaciones': self.garantia_observaciones,
            'garantia_adjunto': self.garantia_adjunto,
            'garantia_adjunto_name': self.garantia_adjunto_name,
            'tipo_garantia': self.tipo_garantia,
            'garantia_rechazo_tag_ids': [(6, 0, sin_cobertura_tags.ids)],
            'solucion_aplicada': self.solucion_aplicada.strip(),
        }
        if self.sap_numero_orden:
            ticket_vals['sap_numero_orden'] = self.sap_numero_orden

        ticket._cerrar(ticket_vals)

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

        estado_garantia = _("CON GARANTÍA") if self.garantia_aceptada else _("SIN GARANTÍA (la pieza la abona el concesionario/cliente)")
        tipo_garantia_label = dict(self._fields['tipo_garantia'].selection).get(self.tipo_garantia, self.tipo_garantia)
        rechazo_str = ", ".join(sin_cobertura_tags.mapped('name')) or '-'
        body = Markup(_(
            "<h4><b>Cierre de Ticket / Expediente Completo</b></h4>"
            "<b>Clasificación de Garantía:</b> %s<br/>"
            "<b>Resolución de Garantía:</b> %s<br/>"
            "<b>Motivos sin Cobertura:</b> %s<br/>"
            "<b>Solución Aplicada:</b> %s<br/>"
            "<b>Orden SAP:</b> %s<br/>"
            "<b>Observaciones:</b> %s"
            "%s"
        )) % (
            escape(tipo_garantia_label),
            escape(estado_garantia),
            escape(rechazo_str),
            escape(ticket.solucion_aplicada),
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
