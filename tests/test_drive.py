# Part of Crucianelli Posventa Module
import json
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from odoo.addons.posventa.tools.drive import DriveError, RcloneDrive

CREDENCIALES = json.dumps({'type': 'service_account', 'client_email': 'posventa@proyecto.iam.gserviceaccount.com'})


def _resultado(returncode=0, stdout='', stderr=''):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestDrive(TransactionCase):

    def setUp(self):
        super().setUp()
        self.drive = RcloneDrive(CREDENCIALES, 'UNIDAD123', '/Posventa/Reclamos/')
        patch('odoo.addons.posventa.tools.drive._binario', return_value='/usr/bin/rclone').start()
        self.run = patch('odoo.addons.posventa.tools.drive.subprocess.run', return_value=_resultado()).start()
        self.addCleanup(patch.stopall)

    def test_01_config_en_memoria_por_entorno(self):
        """rclone recibe la cuenta y la unidad por variables de entorno, sin archivo de configuración."""
        self.drive.verificar()
        args, kwargs = self.run.call_args
        self.assertEqual(args[0], ['/usr/bin/rclone', '--config', '', '--retries', '1', 'mkdir', 'posventa:Posventa/Reclamos'])
        self.assertEqual(kwargs['env']['RCLONE_CONFIG_POSVENTA_TYPE'], 'drive')
        self.assertEqual(kwargs['env']['RCLONE_CONFIG_POSVENTA_SERVICE_ACCOUNT_CREDENTIALS'], CREDENCIALES)
        self.assertEqual(kwargs['env']['RCLONE_CONFIG_POSVENTA_TEAM_DRIVE'], 'UNIDAD123')

    def test_02_errores_legibles(self):
        with self.assertRaisesRegex(DriveError, 'cuenta de servicio'):
            RcloneDrive('', 'UNIDAD123', '').verificar()
        with self.assertRaisesRegex(DriveError, 'unidad compartida'):
            RcloneDrive(CREDENCIALES, '', '').verificar()
        self.run.return_value = _resultado(1, stderr="2026/01/01 10:00:00 NOTICE: algo\n"
                                                     "2026/01/01 10:00:01 ERROR : Reclamos: permiso denegado\n")
        with self.assertRaisesRegex(DriveError, '^Reclamos: permiso denegado$'):
            self.drive.verificar()

    def test_03_enlace_interno_si_la_unidad_no_permite_publicos(self):
        self.run.side_effect = [_resultado(1, stderr="ERROR : sharing disabled"),
                                _resultado(stdout='{"ID": "abc", "IsDir": false}')]
        self.assertEqual(self.drive.enlace('OF1_T1', 'video.mp4'), 'https://drive.google.com/file/d/abc/view')

    def test_04_ajustes(self):
        settings = self.env['res.config.settings'].create({
            'pv_drive_credenciales': CREDENCIALES, 'pv_drive_unidad_id': 'UNIDAD123',
        })
        self.assertEqual(settings.pv_drive_cuenta, 'posventa@proyecto.iam.gserviceaccount.com')
        self.assertEqual(settings.action_pv_probar_drive()['params']['type'], 'success')

        self.run.return_value = _resultado(1, stderr="ERROR : not found")
        self.assertEqual(settings.action_pv_probar_drive()['params']['type'], 'danger')

        settings.pv_drive_credenciales = 'no es json'
        with self.assertRaises(UserError):
            settings.execute()
