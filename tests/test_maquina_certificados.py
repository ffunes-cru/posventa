# Part of Crucianelli Posventa Module
from .common import TestPosventaCommon, DUMMY_PDF_BASE64
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo import fields
from datetime import timedelta


class TestMaquinaCertificados(TestPosventaCommon):

    def test_01_maquina_lifecycle_and_certificates(self):
        """Test sequence FRU -> FEU -> CPM and machine status changes."""
        # 1. Create Machine in LIBERADA (Machines are created by Admin or imported)
        maquina = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TEST-001',
            'concesionario_id': self.concesionario_a.id,
            'cliente_id': self.cliente_final.id,
            'ciudad': 'Rosario',
        })
        self.assertEqual(maquina.estado, 'liberada')
        self.assertFalse(maquina.tiene_fru)
        self.assertFalse(maquina.tiene_feu)
        self.assertFalse(maquina.tiene_cpm)
        self.assertIn('OF-TEST-001', maquina.name)

        # 2. Upload FRU
        today = fields.Date.today()
        fru = self.env['pv.certificado'].with_user(self.user_concesionario_a).create({
            'maquina_id': maquina.id,
            'tipo': 'fru',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru_test.pdf',
        })
        self.assertEqual(fru.estado_certificado, 'vigente')
        self.assertEqual(maquina.estado, 'stock')
        self.assertTrue(maquina.tiene_fru)
        self.assertFalse(maquina.tiene_feu)
        self.assertFalse(maquina.tiene_cpm)
        self.assertGreater(fru.dias_para_vencer, 0)

        # 3. Upload FEU
        feu = self.env['pv.certificado'].with_user(self.user_concesionario_a).create({
            'maquina_id': maquina.id,
            'tipo': 'feu',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'feu_test.pdf',
        })
        self.assertEqual(feu.estado_certificado, 'vigente')
        self.assertTrue(maquina.tiene_feu)
        self.assertEqual(maquina.estado, 'stock')

        # 4. Upload CPM -> machine moves to VENDIDA
        cpm = self.env['pv.certificado'].with_user(self.user_concesionario_a).create({
            'maquina_id': maquina.id,
            'tipo': 'cpm',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'cpm_test.pdf',
        })
        self.assertEqual(cpm.estado_certificado, 'vigente')
        self.assertEqual(maquina.estado, 'vendida')
        self.assertTrue(maquina.tiene_cpm)

    def test_02_certificate_sequence_constraints(self):
        """Test that invalid certificate uploads are rejected."""
        maquina = self.env['pv.maquina'].create({
            'tipo': 'drilor',
            'of': 'OF-TEST-002',
            'concesionario_id': self.concesionario_a.id,
        })

        # Cannot upload FEU or CPM without FRU
        with self.assertRaises(ValidationError):
            self.env['pv.certificado'].create({
                'maquina_id': maquina.id,
                'tipo': 'feu',
                'fecha': fields.Date.today(),
                'archivo': DUMMY_PDF_BASE64,
                'archivo_nombre': 'feu_invalid.pdf',
            })

        # Upload FRU
        self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'fru',
            'fecha': fields.Date.today(),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru.pdf',
        })

        # Cannot upload duplicate vigente FRU
        with self.assertRaises(ValidationError):
            self.env['pv.certificado'].create({
                'maquina_id': maquina.id,
                'tipo': 'fru',
                'fecha': fields.Date.today(),
                'archivo': DUMMY_PDF_BASE64,
                'archivo_nombre': 'fru_dup.pdf',
            })

    def test_03_action_liberar_maquina_and_reupload(self):
        """Test returning machine to LIBERADA, archiving active certs, and re-uploading FRU."""
        maquina = self.env['pv.maquina'].create({
            'tipo': 'pionera',
            'of': 'OF-TEST-003',
            'concesionario_id': self.concesionario_a.id,
        })
        # Upload full sequence
        today = fields.Date.today()
        fru = self.env['pv.certificado'].create({
            'maquina_id': maquina.id, 'tipo': 'fru', 'fecha': today,
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'fru.pdf',
        })
        feu = self.env['pv.certificado'].create({
            'maquina_id': maquina.id, 'tipo': 'feu', 'fecha': today,
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'feu.pdf',
        })
        cpm = self.env['pv.certificado'].create({
            'maquina_id': maquina.id, 'tipo': 'cpm', 'fecha': today,
            'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': 'cpm.pdf',
        })
        self.assertEqual(maquina.estado, 'vendida')

        # Concesionario requests liberation; only the admin can approve it
        maquina.with_user(self.user_concesionario_a).action_solicitar_liberacion('Canje de unidad')
        self.assertTrue(maquina.liberacion_solicitada)
        self.assertEqual(maquina.estado, 'vendida')
        with self.assertRaises(AccessError):
            maquina.with_user(self.user_concesionario_a).action_aprobar_liberacion()
        maquina.with_user(self.user_admin).action_aprobar_liberacion()
        self.assertFalse(maquina.liberacion_solicitada)

        self.assertEqual(maquina.estado, 'liberada')
        self.assertFalse(maquina.tiene_fru)
        self.assertFalse(maquina.tiene_feu)
        self.assertFalse(maquina.tiene_cpm)
        self.assertEqual(fru.estado_certificado, 'archivado_manual')
        self.assertEqual(feu.estado_certificado, 'archivado_manual')
        self.assertEqual(cpm.estado_certificado, 'archivado_manual')

        # Should now allow uploading a new FRU from scratch
        new_fru = self.env['pv.certificado'].with_user(self.user_concesionario_a).create({
            'maquina_id': maquina.id,
            'tipo': 'fru',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'new_fru.pdf',
        })
        self.assertEqual(new_fru.estado_certificado, 'vigente')
        self.assertEqual(maquina.estado, 'stock')
        self.assertTrue(maquina.tiene_fru)
        self.assertEqual(maquina.fecha_liberacion, today)

    def test_04_cpm_never_expires_and_protects_other_certificates_from_expiration(self):
        """Test that CPM has no expiration and once CPM is loaded, prior certificates do not expire."""
        today = fields.Date.today()
        # Machine 1: Without CPM, released 30 days ago -> FRU should expire
        maquina_sin_cpm = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TEST-CRON-NO-CPM',
            'concesionario_id': self.concesionario_a.id,
            'fecha_liberacion': today - timedelta(days=30),
        })
        fru_expirable = self.env['pv.certificado'].create({
            'maquina_id': maquina_sin_cpm.id,
            'tipo': 'fru',
            'fecha': today - timedelta(days=30),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru_exp.pdf',
        })
        self.assertTrue(fru_expirable.fecha_limite_vigencia < today)

        # Machine 2: With CPM, released 30 days ago -> FRU should NOT expire because CPM is active
        maquina_con_cpm = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TEST-CRON-WITH-CPM',
            'concesionario_id': self.concesionario_a.id,
            'fecha_liberacion': today - timedelta(days=30),
        })
        fru_protected = self.env['pv.certificado'].create({
            'maquina_id': maquina_con_cpm.id,
            'tipo': 'fru',
            'fecha': today - timedelta(days=30),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru_prot.pdf',
        })
        feu_protected = self.env['pv.certificado'].create({
            'maquina_id': maquina_con_cpm.id,
            'tipo': 'feu',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'feu_prot.pdf',
        })
        cpm = self.env['pv.certificado'].create({
            'maquina_id': maquina_con_cpm.id,
            'tipo': 'cpm',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'cpm.pdf',
        })
        self.assertFalse(cpm.fecha_vencimiento)
        self.assertFalse(cpm.fecha_limite_vigencia)
        self.assertEqual(maquina_con_cpm.estado, 'vendida')

        # Run cron
        self.env['pv.certificado']._archive_expired_certificates()

        # Machine without CPM has its FRU expired
        self.assertEqual(fru_expirable.estado_certificado, 'vencido')

        # Machine with CPM maintains its certificates as vigente
        self.assertEqual(fru_protected.estado_certificado, 'vigente')
        self.assertEqual(feu_protected.estado_certificado, 'vigente')
        self.assertEqual(cpm.estado_certificado, 'vigente')

    def test_05_cannot_create_ticket_on_expired_certificate_and_fru_not_renewable(self):
        """Test that tickets cannot be created against expired certificates and FRU cannot be renewed."""
        maquina = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TEST-EXP-001',
            'concesionario_id': self.concesionario_a.id,
        })
        today = fields.Date.today()
        fru = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'fru',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru.pdf',
        })

        # Mark FRU as expired
        fru.sudo().write({'estado_certificado': 'vencido'})

        # Creating ticket with expired certificate raises ValidationError
        with self.assertRaises(ValidationError):
            self.env['pv.ticket'].create({
                'maquina_id': maquina.id,
                'certificado_id': fru.id,
                'tipo_ticket': 'pre_pm',
                'desvio_tipo': 'rotura',
                'descripcion': 'Test error con certificado vencido',
            })

        # FRU cannot be re-uploaded/renewed on this machine
        with self.assertRaises(ValidationError):
            self.env['pv.certificado'].create({
                'maquina_id': maquina.id,
                'tipo': 'fru',
                'fecha': today,
                'archivo': DUMMY_PDF_BASE64,
                'archivo_nombre': 'fru_renovar.pdf',
            })

    def test_06_feu_expiration_and_renewal_workflow(self):
        """Test FEU 90-day validity, expiration, and renewal workflow."""
        maquina = self.env['pv.maquina'].create({
            'tipo': 'drilor',
            'of': 'OF-TEST-FEU-001',
            'concesionario_id': self.concesionario_a.id,
        })
        today = fields.Date.today()
        fru = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'fru',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru.pdf',
        })

        validity_days = int(self.env['ir.config_parameter'].sudo().get_param('posventa.feu_claims_validity_days', 90))

        # Upload initial FEU
        feu_1 = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'feu',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'feu_1.pdf',
        })
        self.assertEqual(feu_1.estado_certificado, 'vigente')
        self.assertEqual(feu_1.fecha_limite_vigencia, today + timedelta(days=validity_days))

        # Can create ticket with FEU 1
        ticket = self.env['pv.ticket'].create({
            'maquina_id': maquina.id,
            'certificado_id': feu_1.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'rotura',
            'descripcion': 'Reclamo sobre FEU 1',
        })
        self.assertEqual(ticket.estado, 'borrador')

        # Expire FEU 1 (past 90 days)
        feu_1.sudo().write({'estado_certificado': 'vencido'})

        # Cannot create new tickets on expired FEU 1
        with self.assertRaises(ValidationError):
            self.env['pv.ticket'].create({
                'maquina_id': maquina.id,
                'certificado_id': feu_1.id,
                'tipo_ticket': 'pre_pm',
                'desvio_tipo': 'rotura',
                'descripcion': 'Reclamo sobre FEU vencido',
            })

        # FEU SÍ se puede renovar: concessionaire uploads FEU 2
        feu_2 = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'feu',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'feu_2_renovado.pdf',
        })
        self.assertEqual(feu_2.estado_certificado, 'vigente')
        self.assertEqual(feu_2.fecha_limite_vigencia, today + timedelta(days=validity_days))

        # Now can create tickets again with renewed FEU 2
        ticket_2 = self.env['pv.ticket'].create({
            'maquina_id': maquina.id,
            'certificado_id': feu_2.id,
            'tipo_ticket': 'pre_pm',
            'desvio_tipo': 'rotura',
            'descripcion': 'Reclamo sobre FEU 2 renovado',
        })
        self.assertEqual(ticket_2.estado, 'borrador')

    def test_07_portal_proximo_certificado_countdown_and_retraso_carga(self):
        """Test the upcoming certificate countdown and delayed upload tracking."""
        today = fields.Date.today()
        param_obj = self.env['ir.config_parameter'].sudo()
        fru_days = int(param_obj.get_param('posventa.fru_expiration_days', 10))
        feu_days = int(param_obj.get_param('posventa.feu_expiration_days', 20))
        fru_grace_days = int(param_obj.get_param('posventa.fru_grace_days', 3))

        # 1. New machine: waiting for FRU
        maquina = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TEST-PROX-001',
            'concesionario_id': self.concesionario_a.id,
            'fecha_liberacion': today,
        })
        info = maquina._get_proximo_certificado_info()
        self.assertEqual(info['tipo'], 'fru')
        self.assertEqual(info['dias_restantes'], fru_days)
        self.assertEqual(info['estado'], 'en_termino')

        # 2. Upload FRU on time (today)
        fru_ontime = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'fru',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru_ontime.pdf',
        })
        self.assertEqual(fru_ontime.dias_retraso_carga, 0)
        # FRU expiration is its grace date (today + fru_grace_days), NOT the upload deadline
        self.assertEqual(fru_ontime.fecha_vencimiento, today + timedelta(days=fru_grace_days))
        self.assertEqual(fru_ontime.dias_para_vencer, fru_grace_days)

        # Next pending certificate is now FEU
        info_feu = maquina._get_proximo_certificado_info()
        self.assertEqual(info_feu['tipo'], 'feu')
        self.assertEqual(info_feu['dias_restantes'], feu_days)
        self.assertEqual(info_feu['estado'], 'en_termino')

        # 3. Test machine where nominal upload expired (created fru_days + 5 days ago)
        maquina_tardia = self.env['pv.maquina'].create({
            'tipo': 'drilor',
            'of': 'OF-TEST-TARDIA-001',
            'concesionario_id': self.concesionario_a.id,
            'fecha_liberacion': today - timedelta(days=fru_days + 5),
        })
        info_tardia = maquina_tardia._get_proximo_certificado_info()
        self.assertEqual(info_tardia['tipo'], 'fru')
        self.assertEqual(info_tardia['dias_restantes'], -5) # 5 days overdue
        self.assertEqual(info_tardia['estado'], 'vencido')

        # Concessionaire uploads FRU 5 days late
        fru_tardio = self.env['pv.certificado'].create({
            'maquina_id': maquina_tardia.id,
            'tipo': 'fru',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru_tardio.pdf',
        })
        self.assertEqual(fru_tardio.dias_retraso_carga, 5)
        # Still gets fru_grace_days grace days to create claims!
        self.assertEqual(fru_tardio.fecha_vencimiento, today + timedelta(days=fru_grace_days))
        self.assertEqual(fru_tardio.dias_para_vencer, fru_grace_days)

        portal_data = maquina_tardia.get_portal_detail_data()
        cert_data = next(c for c in portal_data['certificados'] if c['id'] == fru_tardio.id)
        self.assertIn('Vencido luego de 5 días', cert_data['estado_certificado_label'])
        self.assertEqual(cert_data['tag_badge'], 'danger')

    def test_08_upload_certificate_with_string_dates(self):
        """Test creating certificates where fecha is passed as string, exactly as sent from JS frontend."""
        today_str = str(fields.Date.today())
        maquina = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TEST-STR-DATE-001',
            'concesionario_id': self.concesionario_a.id,
            'fecha_liberacion': today_str,
        })
        # Pass fecha as string (from frontend wizard)
        fru = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'fru',
            'fecha': today_str,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru_str_date.pdf',
        })
        self.assertEqual(fru.estado_certificado, 'vigente')
        self.assertTrue(fru.fecha_vencimiento)
        self.assertTrue(fru.fecha_limite_carga)

    def test_09_certificate_order_hardening(self):
        """Test backend hardening for certificate order, archived certificates, and dealer access."""
        from odoo.exceptions import ValidationError
        maquina = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TEST-HARDEN-001',
            'concesionario_id': self.concesionario_a.id,
        })

        # Cannot create CPM directly without FRU or FEU
        with self.assertRaises(ValidationError):
            self.env['pv.certificado'].create({
                'maquina_id': maquina.id,
                'tipo': 'cpm',
                'archivo': DUMMY_PDF_BASE64,
                'archivo_nombre': 'cpm_illegal.pdf',
            })

        # Cannot create FEU without FRU
        with self.assertRaises(ValidationError):
            self.env['pv.certificado'].create({
                'maquina_id': maquina.id,
                'tipo': 'feu',
                'archivo': DUMMY_PDF_BASE64,
                'archivo_nombre': 'feu_illegal.pdf',
            })

        # Create valid FRU
        fru = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'fru',
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru.pdf',
        })
        # Still cannot create CPM with only FRU
        with self.assertRaises(ValidationError):
            self.env['pv.certificado'].create({
                'maquina_id': maquina.id,
                'tipo': 'cpm',
                'archivo': DUMMY_PDF_BASE64,
                'archivo_nombre': 'cpm_no_feu.pdf',
            })

        # Create valid FEU
        feu = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'feu',
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'feu.pdf',
        })

        # Archive them manually
        fru.sudo().write({'estado_certificado': 'archivado_manual'})
        feu.sudo().write({'estado_certificado': 'archivado_manual'})

        # Now creating CPM should fail because FRU and FEU are archived (not vigente or vencido)
        with self.assertRaises(ValidationError):
            self.env['pv.certificado'].create({
                'maquina_id': maquina.id,
                'tipo': 'cpm',
                'archivo': DUMMY_PDF_BASE64,
                'archivo_nombre': 'cpm_after_archived.pdf',
            })

        # Test dealer isolation check: Concesionario B cannot upload cert for A's machine
        with self.assertRaises(ValidationError):
            self.env['pv.certificado'].with_user(self.user_concesionario_b).create({
                'maquina_id': maquina.id,
                'tipo': 'fru',
                'archivo': DUMMY_PDF_BASE64,
                'archivo_nombre': 'fru_cross_dealer.pdf',
            })

    def test_10_cpm_rejected_when_feu_vencido(self):
        """If FEU is expired (vencido), dealer cannot upload CPM until FEU is renewed."""
        today = fields.Date.today()
        maquina = self.env['pv.maquina'].create({
            'tipo': 'plantor',
            'of': 'OF-TEST-FEU-VENCIDO',
            'concesionario_id': self.concesionario_a.id,
            'fecha_liberacion': today - timedelta(days=90),
        })

        # Create FRU
        self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'fru',
            'fecha': today - timedelta(days=90),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'fru.pdf',
        })

        # Create FEU that expired
        feu = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'feu',
            'fecha': today - timedelta(days=90),
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'feu_vencido.pdf',
        })
        # Simulate cron expiration
        feu.write({'estado_certificado': 'vencido'})
        maquina._compute_tiene_certificados()

        self.assertTrue(maquina.tiene_feu)
        self.assertFalse(maquina.tiene_feu_vigente)

        # Proximo certificado should recommend FEU renewal, not CPM
        prox = maquina._get_proximo_certificado_info()
        self.assertEqual(prox['tipo'], 'feu')
        self.assertEqual(prox['estado'], 'vencido')

        # Uploading CPM must raise ValidationError
        with self.assertRaises(ValidationError) as cm:
            self.env['pv.certificado'].create({
                'maquina_id': maquina.id,
                'tipo': 'cpm',
                'fecha': today,
                'archivo': DUMMY_PDF_BASE64,
                'archivo_nombre': 'cpm_blocked.pdf',
            })
        self.assertIn("vencido", str(cm.exception))

        # Renew FEU
        feu_renovado = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'feu',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'feu_renovado.pdf',
        })
        self.assertEqual(feu_renovado.estado_certificado, 'vigente')
        maquina._compute_tiene_certificados()
        self.assertTrue(maquina.tiene_feu_vigente)

        # Now CPM upload should succeed
        cpm = self.env['pv.certificado'].create({
            'maquina_id': maquina.id,
            'tipo': 'cpm',
            'fecha': today,
            'archivo': DUMMY_PDF_BASE64,
            'archivo_nombre': 'cpm_success.pdf',
        })
        self.assertEqual(cpm.estado_certificado, 'vigente')
        self.assertEqual(maquina.estado, 'vendida')

