from odoo import api, fields, models, _
from odoo.exceptions import UserError
from .pv_maquina import ESTADO_MAQUINA

class PvMaquina(models.Model):
    _inherit = 'pv.maquina'

    # 2. Campos temporales para la propuesta de transferencia
    concesionario_destino_id = fields.Many2one('pv.concesionario', string='Concesionario Destino Oculto', readonly=True)
    provincia_destino_id = fields.Many2one('res.country.state', string='Provincia Destino Oculta', readonly=True)
    ciudad_destino = fields.Char(string='Ciudad Destino Oculta', readonly=True)

    es_concesionario_destino = fields.Boolean(
        compute='_compute_es_concesionario_destino', 
        store=False
    )

    def _compute_es_concesionario_destino(self):
        mi_concesionario = self.env['pv.concesionario']._get_concesionario_for_user()
        for record in self:
            record.es_concesionario_destino = bool(mi_concesionario) and record.concesionario_destino_id == mi_concesionario

    def action_aceptar_transferencia(self):
        self.ensure_one()
        self._check_es_del_concesionario(
            self.concesionario_destino_id, _("Solo el concesionario destino puede aceptar esta transferencia."))
        if self.estado != 'pendiente':
            raise UserError(_("La máquina no tiene una transferencia pendiente."))

        maquina_sudo = self.sudo()
        destino = maquina_sudo.concesionario_destino_id

        # Los certificados anteriores (vigentes o vencidos) pasan a 'archivado_traslado'
        certificados_anteriores = maquina_sudo.certificado_ids.filtered(
            lambda c: c.estado_certificado in ('vigente', 'vencido')
        )
        if certificados_anteriores:
            certificados_anteriores.write({'estado_certificado': 'archivado_traslado'})

        # Hacemos efectiva la transferencia pasando la máquina a LIBERADA para que el nuevo dueño cargue sus certificados
        maquina_sudo.write({
            'concesionario_id': destino.id,
            'provincia_id': maquina_sudo.provincia_destino_id.id,
            'ciudad': maquina_sudo.ciudad_destino,
            'estado': 'liberada',
            'fecha_liberacion': fields.Date.today(),
            # Limpiamos los campos temporales
            'concesionario_destino_id': False,
            'provincia_destino_id': False,
            'ciudad_destino': False,
        })
        maquina_sudo.message_post(
            body=_("Transferencia ACEPTADA por %s. Nuevo dueño: %s. Los certificados anteriores fueron marcados como "
                   "'Archivado por Traslado'. El nuevo concesionario debe iniciar la carga de certificados.",
                   self.env.user.name, destino.name),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        return True

    def action_rechazar_transferencia(self):
        self.ensure_one()
        self._check_es_del_concesionario(
            self.concesionario_destino_id, _("Solo el concesionario destino puede rechazar esta transferencia."))
        if self.estado != 'pendiente':
            raise UserError(_("La máquina no tiene una transferencia pendiente."))

        maquina_sudo = self.sudo()
        concesionario_que_rechazo = maquina_sudo.concesionario_destino_id.name
        prev_estado = maquina_sudo._get_estado_sin_transferencia()

        # Cancelamos todo y vuelve a su estado normal con su dueño original
        maquina_sudo.write({
            'estado': prev_estado,
            'concesionario_destino_id': False,
            'provincia_destino_id': False,
            'ciudad_destino': False,
        })
        maquina_sudo.message_post(
            body=_("Transferencia RECHAZADA por el concesionario %s. La máquina vuelve a estado %s con su dueño original.",
                   concesionario_que_rechazo, dict(ESTADO_MAQUINA).get(prev_estado, prev_estado)),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        return True
