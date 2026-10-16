# Part of Crucianelli Posventa Module
import base64
import io

import openpyxl

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TestPosventaCommon

ENCABEZADOS = ['OF', 'Tipo', 'Concesionario', 'Cliente', 'Ciudad', 'Provincia', 'Estado']


@tagged('post_install', '-at_install')
class TestImportMaquinas(TestPosventaCommon):

    def _wizard(self, *filas, encabezados=ENCABEZADOS):
        libro = openpyxl.Workbook()
        hoja = libro.active
        for fila in (encabezados, *filas):
            hoja.append(fila)
        archivo = io.BytesIO()
        libro.save(archivo)
        return self.env['pv.import.maquinas'].with_user(self.user_admin).create({
            'archivo': base64.b64encode(archivo.getvalue()),
        })

    def test_01_vista_previa_e_importacion(self):
        self.env['pv.maquina'].create({'tipo': 'gringa', 'of': 'OF-EXISTE', 'concesionario_id': self.concesionario_a.id})
        wizard = self._wizard(
            ['OF-1', 'Plantor', self.concesionario_a.name, '', 'Rosario', 'Santa Fe', 'stock'],
            ['OF-2', 'drilor', self.concesionario_b.name.upper(), '', '', '', ''],
            ['OF-1', 'drilor', self.concesionario_a.name, '', '', '', ''],
            ['OF-EXISTE', 'drilor', self.concesionario_a.name, '', '', '', ''],
            ['OF-3', 'tractor', 'Inexistente', '', '', 'Narnia', 'robada'],
        )
        wizard.action_preview()
        self.assertEqual((wizard.lineas_ok, wizard.lineas_error), (2, 3))
        for error in ('OF duplicada', 'Tipo inválido: tractor', 'Concesionario inexistente', 'Provincia inexistente',
                      'Estado inválido: robada'):
            self.assertIn(error, wizard.error_html)

        accion = wizard.action_import()
        maquinas = self.env['pv.maquina'].search(accion['domain'], order='of')
        self.assertEqual(maquinas.mapped('of'), ['OF-1', 'OF-2'])
        self.assertEqual(maquinas[0].estado, 'stock')
        self.assertEqual(maquinas[0].provincia_id.name, 'Santa Fe')
        self.assertEqual(maquinas[1].estado, 'liberada')
        self.assertEqual(maquinas[1].concesionario_id, self.concesionario_b)

    def test_02_archivo_invalido(self):
        with self.assertRaisesRegex(UserError, 'Faltan las columnas estado'):
            self._wizard(['OF-1'], encabezados=ENCABEZADOS[:-1]).action_preview()
        with self.assertRaisesRegex(UserError, 'No hay filas válidas'):
            self._wizard(['', 'plantor', self.concesionario_a.name, '', '', '', '']).action_import()
        # El contenido de las celdas se escapa en la vista previa
        wizard = self._wizard(['<b>OF</b>', 'x', '', '', '', '', ''])
        wizard.action_preview()
        self.assertNotIn('<b>OF</b>', wizard.error_html)
