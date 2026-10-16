# Part of Crucianelli Posventa Module
from .common import TestPosventaCommon, DUMMY_PDF_BASE64
from odoo.exceptions import UserError, ValidationError
from odoo import fields


class TestTicketWorkflow(TestPosventaCommon):

    def setUp(self):
        super().setUp()
        # Machine in Stock with FRU (Pre-PM)
        self.maquina_stock = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TCK-001',
            'concesionario_id': self.concesionario_a.id,
        })
        self.fru = self.env['pv.certificado'].create({
            'maquina_id': self.maquina_stock.id,
            'tipo': 'fru',
            'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru.pdf',
        })

        # Machine Sold with CPM (Post-PM)
        self.maquina_sold = self.env['pv.maquina'].create({
            'tipo': 'drilor',
            'of': 'OF-TCK-002',
            'concesionario_id': self.concesionario_a.id,
        })
        self.env['pv.certificado'].create({
            'maquina_id': self.maquina_sold.id, 'tipo': 'fru', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'fru.pdf',
        })
        self.env['pv.certificado'].create({
            'maquina_id': self.maquina_sold.id, 'tipo': 'feu', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'feu.pdf',
        })
        self.cpm = self.env['pv.certificado'].create({
            'maquina_id': self.maquina_sold.id, 'tipo': 'cpm', 'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'cpm.pdf',
        })

    def test_01_pre_pm_ticket_creation_and_lifecycle(self):
        """Concessionaire creates Pre-PM ticket from portal and Staff processes it."""
        # 1. Create ticket in Borrador and Send directly (Portal behavior)
        ticket = self.env['pv.ticket'].with_user(self.user_concesionario_a).create({
            'maquina_id': self.maquina_stock.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'rotura',
            'descripcion': 'Manguera hidráulica cortada en transporte',
            'acciones_realizadas': 'Se verificó en descarga y se fotografió',
        })
        self.assertEqual(ticket.estado, 'borrador')
        self.assertEqual(ticket.certificado_id, self.fru)

        # Attach standard ir.attachment
        attachment = self.env['ir.attachment'].with_user(self.user_concesionario_a).create({
            'name': 'foto_rotura.png',
            'datas': DUMMY_PDF_BASE64,
            'res_model': 'pv.ticket',
            'res_id': ticket.id,
            'mimetype': 'image/png',
        })
        self.assertTrue(attachment.id)

        # Concessionaire sends ticket via action_enviar_ticket
        ticket.with_user(self.user_concesionario_a).action_enviar_ticket()
        self.assertEqual(ticket.estado, 'abierto')

        # 2. Concessionaire cannot modify acciones_realizadas once out of borrador
        with self.assertRaises(UserError):
            ticket.with_user(self.user_concesionario_a).write({
                'acciones_realizadas': 'Intento de cambio fuera de borrador',
            })

        # 3. Staff takes ticket
        ticket.with_user(self.user_staff).action_tomar_ticket()
        self.assertEqual(ticket.estado, 'en_proceso')
        self.assertEqual(ticket.responsable_id, self.user_staff)

        # 4. Staff adds measures
        medida = self.env['pv.ticket.medida'].with_user(self.user_staff).create({
            'name': 'Revisión y reemplazo de manguera',
            'ticket_id': ticket.id,
            'tipo': 'medida',
            'comentario': 'Manguera 3/8 R2 1.5m enviada a concesionario',
        })
        self.assertTrue(medida.id)

        # 5. Staff accepts ticket
        ticket.with_user(self.user_staff).action_aceptar_ticket()
        self.assertEqual(ticket.estado, 'aceptado')
        self.assertTrue(ticket.fecha_solucion)

        # 6. Staff closes ticket via wizard
        res_wizard = ticket.with_user(self.user_staff).action_cerrar_ticket()
        self.assertEqual(res_wizard.get('res_model'), 'pv.cerrar.ticket.wizard')
        wizard = self.env['pv.cerrar.ticket.wizard'].with_user(self.user_staff).create({
            'ticket_id': ticket.id,
            'tipo_garantia': 'tecnica',
            'garantia_aceptada': True,
            'solucion_aplicada': 'Se envió manguera nueva.',
        })
        wizard.action_confirmar()
        self.assertEqual(ticket.estado, 'cerrado')
        self.assertEqual(ticket.tipo_garantia, 'tecnica')
        self.assertTrue(ticket.fecha_cierre)

    def test_02_post_pm_ticket_reject(self):
        """Concessionaire creates Post-PM ticket, associates CPM, and Staff rejects it with reason."""
        ticket = self.env['pv.ticket'].with_user(self.user_concesionario_a).create({
            'maquina_id': self.maquina_sold.id,
            'tipo_ticket': 'post_pm',
            'sistema_id': self.sistema.id,
            'subsistema_id': self.subsistema.id,
            'problema_id': self.problema.id,
            'descripcion': 'Pérdida en acople rápido',
            'ubicacion_actual': 'Lote 14',
            'hectareas': 150.0,
            'multimedia_url': 'https://drive.google.com/test-mandatory-file',
        })
        self.assertEqual(ticket.certificado_id, self.cpm)

        ticket.with_user(self.user_concesionario_a).action_enviar_ticket()
        ticket.with_user(self.user_staff).action_tomar_ticket()

        # Staff rejects ticket
        tag = self.env['pv.tipo.rechazo'].create({'name': 'Falla por mal uso del operador'})
        ticket.with_user(self.user_staff).write({'rechazo_tag_ids': [(6, 0, tag.ids)]})
        ticket.with_user(self.user_staff).action_rechazar_ticket()
        self.assertEqual(ticket.estado, 'rechazado')
        self.assertEqual(ticket.rechazo_tag_ids, tag)

    def test_03_accept_and_close_with_sap_order_wizard(self):
        """Test accepting directly without popup, and closing with wizard (always opens popup, SAP optional)."""
        from .common import DUMMY_PDF_BASE64
        ticket = self.env['pv.ticket'].with_user(self.user_concesionario_a).create({
            'maquina_id': self.maquina_stock.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'faltante',
            'descripcion': 'Falta manual y bulón',
            'multimedia_url': 'https://drive.google.com/test-mandatory-file-1',
        })
        ticket.with_user(self.user_concesionario_a).action_enviar_ticket()
        ticket.with_user(self.user_staff).action_tomar_ticket()

        # 1. Staff accepts directly (no popup)
        ticket.with_user(self.user_staff).action_aceptar_ticket()
        self.assertEqual(ticket.estado, 'aceptado')
        self.assertTrue(ticket.fecha_solucion)

        # 2. Case A: Close without SAP order -> opens wizard and classifies as 'comercial'
        ticket_no_sap = self.env['pv.ticket'].with_user(self.user_concesionario_a).create({
            'maquina_id': self.maquina_stock.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'faltante',
            'descripcion': 'Falta calco lateral',
            'multimedia_url': 'https://drive.google.com/test-mandatory-file-2',
        })
        ticket_no_sap.with_user(self.user_concesionario_a).action_enviar_ticket()
        ticket_no_sap.with_user(self.user_staff).action_tomar_ticket()
        ticket_no_sap.with_user(self.user_staff).action_aceptar_ticket()
        res_no_sap = ticket_no_sap.with_user(self.user_staff).action_cerrar_ticket()
        self.assertIsInstance(res_no_sap, dict)
        self.assertEqual(res_no_sap.get('res_model'), 'pv.cerrar.ticket.wizard')

        wizard_no_sap = self.env['pv.cerrar.ticket.wizard'].with_user(self.user_staff).create({
            'ticket_id': ticket_no_sap.id,
            'tipo_garantia': 'comercial',
            'garantia_aceptada': True,
            'solucion_aplicada': 'Se envió calco lateral.',
        })
        wizard_no_sap.action_confirmar()
        self.assertEqual(ticket_no_sap.estado, 'cerrado')
        self.assertEqual(ticket_no_sap.tipo_garantia, 'comercial')
        self.assertTrue(ticket_no_sap.fecha_cierre)

        # 3. Case B: Close with SAP order and Pedido SAP -> triggers pv.cerrar.ticket.wizard
        ticket.with_user(self.user_staff).write({
            'sap_numero_orden': 'ORD-SAP-8877',
            'sap_numero_pedido': 'PED-SAP-5544',
        })
        self.assertEqual(ticket.sap_numero_pedido, 'PED-SAP-5544')

        res_with_sap = ticket.with_user(self.user_staff).action_cerrar_ticket()
        self.assertIsInstance(res_with_sap, dict)
        self.assertEqual(res_with_sap.get('res_model'), 'pv.cerrar.ticket.wizard')

        wizard = self.env['pv.cerrar.ticket.wizard'].with_user(self.user_staff).create({
            'ticket_id': ticket.id,
            'tipo_garantia': 'tecnica',
            'garantia_aceptada': True,
            'garantia_observaciones': 'Pieza defectuosa devuelta a planta y validada.',
            'solucion_aplicada': 'Reemplazo de pieza defectuosa.',
            'garantia_adjunto': DUMMY_PDF_BASE64,
            'garantia_adjunto_name': 'devolucion_comprobante.pdf',
        })
        wizard.action_confirmar()

        self.assertEqual(ticket.estado, 'cerrado')
        self.assertEqual(ticket.tipo_garantia, 'tecnica')
        self.assertTrue(ticket.fecha_cierre)
        self.assertTrue(ticket.garantia_aceptada)
        self.assertEqual(ticket.garantia_observaciones, 'Pieza defectuosa devuelta a planta y validada.')
        # Attachment created
        att = self.env['ir.attachment'].search([('res_model', '=', 'pv.ticket'), ('res_id', '=', ticket.id)])
        self.assertTrue(att.exists())

    def test_04_tipo_desvio_and_rechazo_tags(self):
        """Test pv.tipo.desvio and pv.tipo.rechazo integration with ticket."""
        desvio = self.env['pv.tipo.desvio'].create({
            'name': 'Faltante de Manual Técnico',
            'codigo': 'faltante_manual',
        })
        rechazo = self.env['pv.tipo.rechazo'].create({
            'name': 'Desgaste por uso normal',
        })

        ticket = self.env['pv.ticket'].create({
            'maquina_id': self.maquina_stock.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo_id': desvio.id,
            'descripcion': 'Falta documentación de cabina',
            'multimedia_url': 'https://drive.google.com/test-doc',
        })
        self.assertEqual(ticket.desvio_tipo, 'faltante')
        self.assertEqual(ticket.desvio_tipo_id, desvio)

        # Rejection tag integration
        ticket.with_user(self.user_concesionario_a).action_enviar_ticket()
        ticket.with_user(self.user_staff).action_tomar_ticket()
        ticket.with_user(self.user_staff).write({
            'rechazo_tag_ids': [(6, 0, [rechazo.id])],
        })
        ticket.with_user(self.user_staff).action_rechazar_ticket()
        self.assertEqual(ticket.estado, 'rechazado')
        self.assertEqual(ticket.rechazo_tag_ids, rechazo)

    def _ticket_en_proceso(self, descripcion='Falta bulón'):
        ticket = self.env['pv.ticket'].with_user(self.user_concesionario_a).create({
            'maquina_id': self.maquina_stock.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'faltante',
            'descripcion': descripcion,
            'multimedia_url': 'https://drive.google.com/test-file',
        })
        ticket.with_user(self.user_concesionario_a).action_enviar_ticket()
        ticket.with_user(self.user_staff).action_tomar_ticket()
        return ticket

    def test_05_rechazo_requiere_tags_de_reclamo(self):
        """Rejecting a claim requires claim-type tags; coverage tags are not accepted."""
        ticket = self._ticket_en_proceso()
        with self.assertRaises(UserError):
            ticket.with_user(self.user_staff).action_rechazar_ticket()

        tag_garantia = self.env['pv.tipo.rechazo'].create({'name': 'Mal uso', 'aplica_a': 'garantia'})
        with self.assertRaises(ValidationError):
            ticket.with_user(self.user_staff).write({'rechazo_tag_ids': [(6, 0, tag_garantia.ids)]})
        self.assertEqual(ticket.estado, 'en_proceso')

    def test_06_cierre_sin_garantia_requiere_motivos_y_solucion(self):
        """Closing without coverage requires coverage tags; closing always requires the applied solution."""
        ticket = self._ticket_en_proceso()
        ticket.with_user(self.user_staff).action_aceptar_ticket()
        tag_garantia = self.env['pv.tipo.rechazo'].create({'name': 'Mantenimiento nulo', 'aplica_a': 'garantia'})

        wizard = self.env['pv.cerrar.ticket.wizard'].with_user(self.user_staff).create({
            'ticket_id': ticket.id,
            'garantia_aceptada': False,
            'solucion_aplicada': 'Se envió repuesto con cargo.',
        })
        with self.assertRaises(UserError):
            wizard.action_confirmar()

        wizard.solucion_aplicada = '   '
        wizard.garantia_rechazo_tag_ids = tag_garantia
        with self.assertRaises(UserError):
            wizard.action_confirmar()

        wizard.solucion_aplicada = 'Se envió repuesto con cargo.'
        wizard.action_confirmar()
        self.assertEqual(ticket.estado, 'cerrado')
        self.assertFalse(ticket.garantia_aceptada)
        self.assertEqual(ticket.garantia_rechazo_tag_ids, tag_garantia)
        self.assertEqual(ticket.solucion_aplicada, 'Se envió repuesto con cargo.')



    def test_07_clasificacion_post_pm_obligatoria(self):
        """Post-PM requires sistema/subsistema, catalogued problem (or 'no listado') and hectares > 0."""
        base = {
            'maquina_id': self.maquina_sold.id,
            'sistema_id': self.sistema.id,
            'subsistema_id': self.subsistema.id,
            'descripcion': 'Pérdida de presión',
            'multimedia_url': 'https://drive.google.com/test-file',
        }
        Ticket = self.env['pv.ticket'].with_user(self.user_concesionario_a)
        with self.assertRaises(ValidationError):
            Ticket.create(dict(base, problema_id=self.problema.id))  # sin hectáreas
        with self.assertRaises(ValidationError):
            Ticket.create(dict(base, hectareas=100))  # sin problema
        with self.assertRaises(ValidationError):
            Ticket.create(dict(base, hectareas=100, problema_id=self.problema.id, problema_no_listado=True))

        otro_subsistema = self.env['pv.subsistema'].create({'name': 'Otro', 'sistema_id': self.sistema.id})
        with self.assertRaises(ValidationError):
            Ticket.create(dict(base, hectareas=100, subsistema_id=otro_subsistema.id, problema_id=self.problema.id))

        otro_sistema = self.env['pv.sistema'].create({'name': 'Eléctrico'})
        with self.assertRaises(ValidationError):
            Ticket.create(dict(base, hectareas=100, sistema_id=otro_sistema.id, problema_id=self.problema.id))

        ticket = Ticket.create(dict(base, hectareas=100, problema_no_listado=True))
        self.assertEqual(ticket.tipo_ticket, 'post_pm')
        ticket.action_enviar_ticket()
        self.assertEqual(ticket.estado, 'abierto')
