# Part of Crucianelli Posventa Module
"""Portal web del concesionario (/my/posventa).

Lectura: con el usuario logueado, de modo que aplican ACL y record rules.
Escritura: siempre a través de los métodos del modelo, que validan pertenencia,
grupo y estado. El controller no reimplementa reglas de negocio: solo traduce
los errores a mensajes para el usuario.
"""
import json

from odoo import _, http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

from ..models.pv_maquina import ESTADO_MAQUINA
from ..models.pv_ticket import ESTADO_TICKET

TICKETS_POR_PAGINA = 20
MAQUINAS_POR_PAGINA = 20
CERTIFICADOS_POR_PAGINA = 30

ERRORES_DE_NEGOCIO = (AccessError, MissingError, UserError, ValidationError)


class PosventaPortal(CustomerPortal):

    # --- Helpers ---
    def _pv_concesionario(self):
        return request.env['pv.concesionario']._get_concesionario_for_user()

    def _pv_flash(self, mensaje, tipo='success'):
        request.session['pv_flash'] = {'mensaje': mensaje, 'tipo': tipo}

    def _pv_render(self, template, values):
        concesionario = self._pv_concesionario()
        if not concesionario:
            return request.render('posventa.portal_sin_concesionario', {'page_name': 'pv_home'})
        values.update({
            'pv_concesionario': concesionario,
            'pv_flash': request.session.pop('pv_flash', None),
            'json': json,
        })
        return request.render(template, values)

    def _pv_get(self, model, record_id):
        """Registro legible por el usuario (ACL + record rules) o MissingError/AccessError."""
        record = request.env[model].browse(record_id).exists()
        if not record:
            raise MissingError(_('El registro no existe.'))
        record.check_access('read')
        return record

    def _pv_accion(self, redirect_url, accion, mensaje_ok):
        """Ejecuta una acción de modelo y vuelve a redirect_url con un mensaje de éxito o el error de negocio."""
        try:
            accion()
            self._pv_flash(mensaje_ok)
        except ERRORES_DE_NEGOCIO as e:
            request.env.cr.rollback()
            self._pv_flash(e.args[0] if e.args else str(e), 'danger')
        return request.redirect(redirect_url)

    # --- /my ---
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'pv_ticket_count' in counters:
            Ticket = request.env['pv.ticket']
            concesionario = self._pv_concesionario()
            values['pv_ticket_count'] = Ticket.search_count(
                [('concesionario_id', '=', concesionario.id), ('estado', 'not in', ('rechazado', 'cerrado'))]
            ) if concesionario and Ticket.has_access('read') else 0
        return values

    # --- Inicio ---
    @http.route('/my/posventa', type='http', auth='user', website=True)
    def portal_posventa_home(self, **kw):
        concesionario = self._pv_concesionario()
        if not concesionario:
            return self._pv_render('posventa.portal_sin_concesionario', {})
        data = request.env['pv.dashboard'].get_concesionario_portal_data()
        Maquina = request.env['pv.maquina']
        alertas = []
        for maquina in Maquina.search([('concesionario_id', '=', concesionario.id),
                                       ('estado', 'in', ('liberada', 'stock'))]):
            info = maquina._get_proximo_certificado_info()
            if info['estado'] in ('vence_hoy', 'vencido'):
                alertas.append({'maquina': maquina, 'info': info})
        return self._pv_render('posventa.portal_posventa_home', {
            'page_name': 'pv_home',
            'data': data,
            'alertas': alertas,
            'transferencias': Maquina.search([('concesionario_destino_id', '=', concesionario.id),
                                              ('estado', '=', 'pendiente')]),
            'estados_ticket': ESTADO_TICKET,
        })

    # --- Máquinas ---
    @http.route(['/my/posventa/maquinas', '/my/posventa/maquinas/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_posventa_maquinas(self, page=1, search='', estado='', **kw):
        concesionario = self._pv_concesionario()
        if not concesionario:
            return self._pv_render('posventa.portal_sin_concesionario', {})
        domain = [('concesionario_id', '=', concesionario.id)]
        if estado == 'pendiente':
            domain = ['|', ('concesionario_id', '=', concesionario.id),
                      ('concesionario_destino_id', '=', concesionario.id), ('estado', '=', 'pendiente')]
        elif estado in dict(ESTADO_MAQUINA):
            domain.append(('estado', '=', estado))
        if search:
            domain += ['|', '|', ('of', 'ilike', search), ('name', 'ilike', search), ('cliente_id.name', 'ilike', search)]
        Maquina = request.env['pv.maquina']
        total = Maquina.search_count(domain)
        pager = portal_pager(url='/my/posventa/maquinas', url_args={'search': search, 'estado': estado},
                             total=total, page=page, step=MAQUINAS_POR_PAGINA)
        maquinas = Maquina.search(domain, limit=MAQUINAS_POR_PAGINA, offset=pager['offset'])
        return self._pv_render('posventa.portal_posventa_maquinas', {
            'page_name': 'pv_maquinas',
            'maquinas': maquinas,
            'pager': pager,
            'search': search,
            'estado': estado,
            'estados_maquina': ESTADO_MAQUINA,
        })

    @http.route('/my/posventa/maquina/<int:maquina_id>', type='http', auth='user', website=True)
    def portal_posventa_maquina(self, maquina_id, **kw):
        try:
            maquina = self._pv_get('pv.maquina', maquina_id)
        except (AccessError, MissingError):
            return request.redirect('/my/posventa/maquinas')
        catalogo = maquina.get_transfer_catalog_data()
        return self._pv_render('posventa.portal_posventa_maquina', {
            'page_name': 'pv_maquina',
            'maquina': maquina,
            'detalle': maquina.get_portal_detail_data(),
            'concesionarios_destino': [c for c in catalogo['concesionarios'] if c['id'] != maquina.concesionario_id.id],
            'provincias': catalogo['provincias'],
            'estados_ticket': ESTADO_TICKET,
        })

    @http.route('/my/posventa/maquina/<int:maquina_id>/solicitar_liberacion', type='http', auth='user',
                methods=['POST'], website=True)
    def portal_posventa_solicitar_liberacion(self, maquina_id, motivo='', **kw):
        maquina = request.env['pv.maquina'].browse(maquina_id)
        return self._pv_accion(f'/my/posventa/maquina/{maquina_id}',
                               lambda: maquina.action_solicitar_liberacion(motivo),
                               _('Solicitud de liberación enviada. El Administrador de Posventa debe aprobarla.'))

    @http.route('/my/posventa/maquina/<int:maquina_id>/trasladar', type='http', auth='user',
                methods=['POST'], website=True)
    def portal_posventa_trasladar(self, maquina_id, concesionario_destino_id=0, provincia_destino_id=0,
                                  ciudad_destino='', **kw):
        maquina = request.env['pv.maquina'].browse(maquina_id)

        def iniciar():
            try:
                destino, provincia = int(concesionario_destino_id), int(provincia_destino_id)
            except (TypeError, ValueError):
                raise UserError(_('Debe seleccionar el concesionario y la provincia de destino.'))
            maquina.action_iniciar_transferencia_portal(destino, provincia, ciudad_destino)
        return self._pv_accion(f'/my/posventa/maquina/{maquina_id}', iniciar,
                               _('Solicitud de traslado enviada. Queda pendiente de aceptación del concesionario destino.'))

    @http.route('/my/posventa/maquina/<int:maquina_id>/transferencia/<string:accion>', type='http',
                auth='user', methods=['POST'], website=True)
    def portal_posventa_transferencia(self, maquina_id, accion, **kw):
        maquina = request.env['pv.maquina'].browse(maquina_id)
        acciones = {
            'aceptar': (maquina.action_aceptar_transferencia, _('Transferencia aceptada. Ya puede cargar los certificados de la máquina.')),
            'rechazar': (maquina.action_rechazar_transferencia, _('Transferencia rechazada.')),
            'cancelar': (maquina.action_cancelar_transferencia, _('Solicitud de traslado cancelada.')),
        }
        if accion not in acciones:
            return request.redirect(f'/my/posventa/maquina/{maquina_id}')
        metodo, mensaje = acciones[accion]
        # Al aceptar o rechazar, el concesionario destino puede dejar de ver la máquina
        destino = f'/my/posventa/maquina/{maquina_id}' if accion != 'rechazar' else '/my/posventa'
        return self._pv_accion(destino, metodo, mensaje)

    @http.route('/my/posventa/maquina/<int:maquina_id>/ticket/nuevo', type='http', auth='user', website=True)
    def portal_posventa_ticket_nuevo(self, maquina_id, **kw):
        try:
            maquina = self._pv_get('pv.maquina', maquina_id)
        except (AccessError, MissingError):
            return request.redirect('/my/posventa/maquinas')
        return self._pv_render('posventa.portal_posventa_ticket_nuevo', {
            'page_name': 'pv_ticket_nuevo',
            'maquina': maquina,
        })

    @http.route('/my/posventa/maquina/<int:maquina_id>/certificado/nuevo', type='http', auth='user', website=True)
    def portal_posventa_certificado_nuevo(self, maquina_id, **kw):
        try:
            maquina = self._pv_get('pv.maquina', maquina_id)
        except (AccessError, MissingError):
            return request.redirect('/my/posventa/maquinas')
        return self._pv_render('posventa.portal_posventa_certificado_nuevo', {
            'page_name': 'pv_certificado_nuevo',
            'maquina': maquina,
        })

    # --- Certificados ---
    @http.route(['/my/posventa/certificados', '/my/posventa/certificados/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_posventa_certificados(self, page=1, search='', tipo='', estado='', **kw):
        if not self._pv_concesionario():
            return self._pv_render('posventa.portal_sin_concesionario', {})
        Certificado = request.env['pv.certificado']
        certificados = Certificado.get_portal_list_data(search_term=search, tipo_filter=tipo, estado_filter=estado)
        pager = portal_pager(url='/my/posventa/certificados', url_args={'search': search, 'tipo': tipo, 'estado': estado},
                             total=len(certificados), page=page, step=CERTIFICADOS_POR_PAGINA)
        return self._pv_render('posventa.portal_posventa_certificados', {
            'page_name': 'pv_certificados',
            'certificados': certificados[pager['offset']:pager['offset'] + CERTIFICADOS_POR_PAGINA],
            'pager': pager,
            'search': search,
            'tipo': tipo,
            'estado': estado,
            'tipos_certificado': Certificado._fields['tipo'].selection,
            'estados_certificado': Certificado._fields['estado_certificado'].selection,
        })

    # --- Tickets ---
    @http.route(['/my/posventa/tickets', '/my/posventa/tickets/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_posventa_tickets(self, page=1, search='', estado='', **kw):
        concesionario = self._pv_concesionario()
        if not concesionario:
            return self._pv_render('posventa.portal_sin_concesionario', {})
        domain = [('concesionario_id', '=', concesionario.id)]
        if estado in dict(ESTADO_TICKET):
            domain.append(('estado', '=', estado))
        if search:
            domain += ['|', '|', ('name', 'ilike', search), ('of', 'ilike', search), ('descripcion', 'ilike', search)]
        Ticket = request.env['pv.ticket']
        total = Ticket.search_count(domain)
        pager = portal_pager(url='/my/posventa/tickets', url_args={'search': search, 'estado': estado},
                             total=total, page=page, step=TICKETS_POR_PAGINA)
        return self._pv_render('posventa.portal_posventa_tickets', {
            'page_name': 'pv_tickets',
            'tickets': Ticket.search(domain, limit=TICKETS_POR_PAGINA, offset=pager['offset']),
            'pager': pager,
            'search': search,
            'estado': estado,
            'estados_ticket': ESTADO_TICKET,
        })

    @http.route('/my/posventa/ticket/<int:ticket_id>', type='http', auth='user', website=True)
    def portal_posventa_ticket(self, ticket_id, **kw):
        try:
            ticket = self._pv_get('pv.ticket', ticket_id)
        except (AccessError, MissingError):
            return request.redirect('/my/posventa/tickets')
        adjuntos = request.env['ir.attachment'].search([
            ('res_model', '=', 'pv.ticket'), ('res_id', '=', ticket.id), ('type', '=', 'binary'),
        ])
        return self._pv_render('posventa.portal_posventa_ticket', {
            'page_name': 'pv_ticket',
            'ticket': ticket,
            'object': ticket,
            'adjuntos': adjuntos,
            'estados_ticket': ESTADO_TICKET,
            'puede_adjuntar': ticket.estado not in ('rechazado', 'cerrado'),
        })

    @http.route('/my/posventa/ticket/<int:ticket_id>/enviar', type='http', auth='user', methods=['POST'], website=True)
    def portal_posventa_ticket_enviar(self, ticket_id, **kw):
        ticket = request.env['pv.ticket'].browse(ticket_id)
        return self._pv_accion(f'/my/posventa/ticket/{ticket_id}', ticket.action_enviar_ticket,
                               _('Ticket enviado a revisión técnica.'))
