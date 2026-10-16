# Part of Crucianelli Posventa Module
import base64
import io

from markupsafe import Markup

from odoo import fields, models, _
from odoo.exceptions import UserError

from ..models.pv_maquina import TIPO_MAQUINA

try:
    import openpyxl
except ImportError:
    openpyxl = None

COLUMNAS_ESPERADAS = ['of', 'tipo', 'concesionario', 'cliente', 'ciudad', 'provincia', 'estado']
ESTADOS_IMPORTABLES = ('liberada', 'stock', 'vendida')
FILAS_EN_VISTA_PREVIA = 20


def _celda(fila, columna):
    return str(fila.get(columna) or '').strip()


def _tabla_html(titulo, clase, encabezados, filas):
    return Markup(
        "<h4>%s</h4><table class='table table-sm table-bordered %s'><thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
    ) % (
        titulo, clase,
        Markup().join(Markup('<th>%s</th>') % e for e in encabezados),
        Markup().join(Markup('<tr>%s</tr>') % Markup().join(Markup('<td>%s</td>') % c for c in f) for f in filas),
    )


class PvImportMaquinas(models.TransientModel):
    """Alta masiva de máquinas desde un Excel: primero valida y muestra la vista previa, luego crea las filas válidas."""
    _name = 'pv.import.maquinas'
    _description = 'Importar Máquinas desde Excel'

    archivo = fields.Binary(string='Archivo Excel', required=True)
    archivo_nombre = fields.Char(string='Nombre del archivo')
    preview_html = fields.Html(string='Vista previa', readonly=True)
    error_html = fields.Html(string='Errores encontrados', readonly=True)
    state = fields.Selection([('upload', 'Cargar archivo'), ('preview', 'Vista previa')], default='upload')
    lineas_ok = fields.Integer(readonly=True)
    lineas_error = fields.Integer(readonly=True)

    def _leer_excel(self):
        """Filas del Excel como diccionarios {columna: valor}, con el número de línea de la planilla."""
        if not openpyxl:
            raise UserError(_('La librería openpyxl no está instalada.'))
        if not self.archivo:
            raise UserError(_('Debe seleccionar un archivo.'))
        hoja = openpyxl.load_workbook(io.BytesIO(base64.b64decode(self.archivo)), read_only=True).active
        filas = list(hoja.iter_rows(values_only=True))
        if not filas:
            raise UserError(_('El archivo está vacío.'))
        encabezados = [str(h or '').strip().lower() for h in filas[0]]
        faltantes = [c for c in COLUMNAS_ESPERADAS if c not in encabezados]
        if faltantes:
            raise UserError(_('Faltan las columnas %(faltantes)s en el archivo. Columnas esperadas: %(esperadas)s',
                              faltantes=', '.join(faltantes), esperadas=', '.join(COLUMNAS_ESPERADAS)))
        return [(linea, dict(zip(encabezados, fila))) for linea, fila in enumerate(filas[1:], start=2)]

    def _validar_filas(self):
        """Valida el Excel completo. Devuelve ([vals de pv.maquina], [(línea, OF, [errores])])."""
        concesionarios = {c.name.strip().upper(): c.id for c in self.env['pv.concesionario'].search([])}
        provincias = {p.name.strip().upper(): p.id
                      for p in self.env['res.country.state'].search([('country_id.code', '=', 'AR')])}
        ofs_usadas = set(self.env['pv.maquina'].with_context(active_test=False).search([]).mapped('of'))
        tipos = dict(TIPO_MAQUINA)

        validas, errores = [], []
        for linea, fila in self._leer_excel():
            of, tipo, concesionario, provincia = (_celda(fila, c) for c in ('of', 'tipo', 'concesionario', 'provincia'))
            tipo = tipo.lower()
            estado = _celda(fila, 'estado').lower() or 'liberada'
            problemas = []
            if not of:
                problemas.append(_('OF vacía'))
            elif of in ofs_usadas:
                problemas.append(_('OF duplicada (ya existe o se repite en el archivo): %s', of))
            if tipo not in tipos:
                problemas.append(_('Tipo inválido: %s', tipo))
            if not concesionario:
                problemas.append(_('Concesionario vacío'))
            elif concesionario.upper() not in concesionarios:
                problemas.append(_('Concesionario inexistente: %s', concesionario))
            if provincia and provincia.upper() not in provincias:
                problemas.append(_('Provincia inexistente: %s', provincia))
            if estado not in ESTADOS_IMPORTABLES:
                problemas.append(_('Estado inválido: %s', estado))

            ofs_usadas.add(of)
            if problemas:
                errores.append((linea, of, problemas))
                continue
            validas.append({
                'of': of,
                'tipo': tipo,
                'concesionario_id': concesionarios[concesionario.upper()],
                'estado': estado,
                'ciudad': _celda(fila, 'ciudad'),
                'provincia_id': provincias.get(provincia.upper(), False),
            })
        return validas, errores

    def action_preview(self):
        self.ensure_one()
        validas, errores = self._validar_filas()
        tipos = dict(TIPO_MAQUINA)
        Concesionario = self.env['pv.concesionario']
        preview = _tabla_html(
            _('✅ %s filas válidas', len(validas)), '', [_('OF'), _('Tipo'), _('Concesionario'), _('Estado')],
            [(v['of'], tipos[v['tipo']], Concesionario.browse(v['concesionario_id']).name, v['estado'].upper())
             for v in validas[:FILAS_EN_VISTA_PREVIA]])
        if len(validas) > FILAS_EN_VISTA_PREVIA:
            preview += Markup('<p><i>%s</i></p>') % _('...y %s filas más.', len(validas) - FILAS_EN_VISTA_PREVIA)
        self.write({
            'state': 'preview',
            'preview_html': preview,
            'error_html': _tabla_html(
                _('❌ %s filas con errores', len(errores)), 'table-danger', [_('Línea'), _('OF'), _('Errores')],
                [(linea, of, Markup('<br/>').join(problemas)) for linea, of, problemas in errores],
            ) if errores else False,
            'lineas_ok': len(validas),
            'lineas_error': len(errores),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import(self):
        """Crea las filas válidas; las que tienen errores se omiten (ya se mostraron en la vista previa)."""
        self.ensure_one()
        validas, _errores = self._validar_filas()
        if not validas:
            raise UserError(_('No hay filas válidas para importar.'))
        maquinas = self.env['pv.maquina'].create(validas)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Máquinas importadas (%d)', len(maquinas)),
            'res_model': 'pv.maquina',
            'view_mode': 'list,form',
            'domain': [('id', 'in', maquinas.ids)],
        }
