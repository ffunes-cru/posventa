# Part of Crucianelli Posventa Module
import base64
import io

import openpyxl
from openpyxl.styles import Font

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

    def test_03_cliente_provincias_y_filas_vacias(self):
        cliente = self.env['res.partner'].create({'name': 'Cliente Importado'})
        self.env['res.partner'].create([{'name': 'Cliente Repetido'}, {'name': 'Cliente Repetido'}])
        libro = openpyxl.Workbook()
        hoja = libro.active
        for fila in (ENCABEZADOS,
                     ['OF-C1', 'gringa', self.concesionario_a.name, 'cliente importado', '', 'Cordoba', 'vendida'],
                     ['OF-C2', 'gringa', self.concesionario_a.name, '', '', 'CABA', ''],
                     ['OF-C3', 'gringa', self.concesionario_a.name, 'Cliente Inexistente', '', '', ''],
                     ['OF-C4', 'gringa', self.concesionario_a.name, 'Cliente Repetido', '', '', '']):
            hoja.append(fila)
        # Filas vacías al final con formato: no son errores
        hoja.cell(row=10, column=1).font = Font(bold=True)
        archivo = io.BytesIO()
        libro.save(archivo)
        wizard = self.env['pv.import.maquinas'].with_user(self.user_admin).create({
            'archivo': base64.b64encode(archivo.getvalue()),
        })
        wizard.action_preview()
        self.assertEqual((wizard.lineas_ok, wizard.lineas_error), (2, 2))
        self.assertIn('Cliente inexistente: Cliente Inexistente', wizard.error_html)
        self.assertIn('Cliente ambiguo, hay 2 con ese nombre', wizard.error_html)

        maquinas = self.env['pv.maquina'].search(wizard.action_import()['domain'], order='of')
        self.assertEqual(maquinas[0].cliente_id, cliente)
        self.assertEqual(maquinas[0].provincia_id.code, 'X')  # Córdoba
        self.assertEqual(maquinas[1].provincia_id.code, 'C')  # Ciudad Autónoma de Buenos Aires
        self.assertFalse(maquinas[1].cliente_id)

    def test_04_solo_excel(self):
        for contenido in (b'of,tipo,concesionario\nOF-1,gringa,X\n', b'\xd0\xcf\x11\xe0' + bytes(100)):
            wizard = self.env['pv.import.maquinas'].with_user(self.user_admin).create({
                'archivo': base64.b64encode(contenido),
            })
            with self.assertRaisesRegex(UserError, 'no es un Excel .xlsx'):
                wizard.action_preview()
