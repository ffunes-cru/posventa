# Part of Crucianelli Posventa Module
from .common import TestPosventaCommon, DUMMY_PDF_BASE64
from odoo.exceptions import ValidationError, UserError
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

        # Concesionario performs action_liberar_maquina
        maquina.with_user(self.user_concesionario_a).action_liberar_maquina()

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
