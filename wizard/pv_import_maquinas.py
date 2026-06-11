# Part of Crucianelli Posventa Module
import base64
import io
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

try:
    import openpyxl
except ImportError:
    openpyxl = None


class PvImportMaquinas(models.TransientModel):
    _name = 'pv.import.maquinas'
    _description = 'Importar Máquinas desde Excel'

    archivo = fields.Binary(
        string='Archivo Excel',
        required=True,
    )
    archivo_nombre = fields.Char(
        string='Nombre del archivo',
    )
    preview_html = fields.Html(
        string='Vista previa',
        readonly=True,
    )
    error_html = fields.Html(
        string='Errores encontrados',
        readonly=True,
    )
    state = fields.Selection([
        ('upload', 'Cargar archivo'),
        ('preview', 'Vista previa'),
        ('done', 'Importado'),
    ], default='upload')
    lineas_ok = fields.Integer(readonly=True)
    lineas_error = fields.Integer(readonly=True)

    TIPOS_VALIDOS = ['pionera', 'gringa', 'drilor', 'plantor', 'mixia']
    ESTADOS_VALIDOS = ['liberada', 'stock', 'vendida']
    COLUMNAS_ESPERADAS = ['of', 'tipo', 'concesionario', 'cliente', 'ciudad', 'provincia', 'estado']

    def _parse_excel(self):
        """Parse the uploaded Excel file and return rows."""
        if not openpyxl:
            raise UserError(_('La librería openpyxl no está instalada.'))
        if not self.archivo:
            raise UserError(_('Debe seleccionar un archivo.'))

        file_data = base64.b64decode(self.archivo)
        wb = openpyxl.load_workbook(io.BytesIO(file_data), read_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise UserError(_('El archivo está vacío.'))

        # Validate headers
        headers = [str(h).strip().lower() if h else '' for h in rows[0]]
        for col in self.COLUMNAS_ESPERADAS:
            if col not in headers:
                raise UserError(_(
                    'Falta la columna "%s" en el archivo. '
                    'Columnas esperadas: %s', col, ', '.join(self.COLUMNAS_ESPERADAS)
                ))

        return headers, rows[1:]

    def action_preview(self):
        """Parse and show preview with validation."""
        self.ensure_one()
        headers, data_rows = self._parse_excel()

        errors = []
        valid_rows = []
        ofs_seen = set()
        existing_ofs = set(
            self.env['pv.maquina'].search([]).mapped('of')
        )
        concesionarios = {
            c.name.strip().upper(): c.id
            for c in self.env['pv.concesionario'].search([])
        }

        for idx, row in enumerate(data_rows, start=2):
            row_dict = dict(zip(headers, row))
            row_errors = []

            of_val = str(row_dict.get('of', '') or '').strip()
            tipo_val = str(row_dict.get('tipo', '') or '').strip().lower()
            conc_val = str(row_dict.get('concesionario', '') or '').strip()
            estado_val = str(row_dict.get('estado', '') or '').strip().lower() or 'liberada'

            if not of_val:
                row_errors.append('OF vacía')
            elif of_val in existing_ofs:
                row_errors.append(f'OF duplicada en BD: {of_val}')
            elif of_val in ofs_seen:
                row_errors.append(f'OF duplicada en archivo: {of_val}')
            else:
                ofs_seen.add(of_val)

            if tipo_val not in self.TIPOS_VALIDOS:
                row_errors.append(f'Tipo inválido: {tipo_val}')

            if not conc_val:
                row_errors.append('Concesionario vacío')
            elif conc_val.upper() not in concesionarios:
                row_errors.append(f'Concesionario inexistente: {conc_val}')

            if estado_val and estado_val not in self.ESTADOS_VALIDOS:
                row_errors.append(f'Estado inválido: {estado_val}')

            if row_errors:
                errors.append((idx, row_dict, row_errors))
            else:
                valid_rows.append(row_dict)

        # Build preview HTML
        preview_lines = []
        for row_dict in valid_rows[:20]:
            preview_lines.append(
                f"<tr><td>{row_dict.get('of','')}</td>"
                f"<td>{row_dict.get('tipo','')}</td>"
                f"<td>{row_dict.get('concesionario','')}</td>"
                f"<td>{row_dict.get('estado','liberada')}</td></tr>"
            )
        remaining = len(valid_rows) - 20
        preview_html = (
            f"<h4>✅ {len(valid_rows)} filas válidas</h4>"
            "<table class='table table-sm table-bordered'>"
            "<thead><tr><th>OF</th><th>Tipo</th><th>Concesionario</th><th>Estado</th></tr></thead>"
            "<tbody>" + ''.join(preview_lines) + "</tbody></table>"
        )
        if remaining > 0:
            preview_html += f"<p><i>...y {remaining} filas más.</i></p>"

        # Build error HTML
        error_html = ''
        if errors:
            error_lines = []
            for line_num, row_dict, errs in errors:
                error_lines.append(
                    f"<tr><td>{line_num}</td>"
                    f"<td>{row_dict.get('of','')}</td>"
                    f"<td>{'<br/>'.join(errs)}</td></tr>"
                )
            error_html = (
                f"<h4>❌ {len(errors)} filas con errores</h4>"
                "<table class='table table-sm table-bordered table-danger'>"
                "<thead><tr><th>Línea</th><th>OF</th><th>Errores</th></tr></thead>"
                "<tbody>" + ''.join(error_lines) + "</tbody></table>"
            )

        self.write({
            'state': 'preview',
            'preview_html': preview_html,
            'error_html': error_html,
            'lineas_ok': len(valid_rows),
            'lineas_error': len(errors),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'pv.import.maquinas',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import(self):
        """Actually import the valid rows."""
        self.ensure_one()
        headers, data_rows = self._parse_excel()

        concesionarios = {
            c.name.strip().upper(): c.id
            for c in self.env['pv.concesionario'].search([])
        }
        existing_ofs = set(
            self.env['pv.maquina'].search([]).mapped('of')
        )
        provincias = {
            p.name.strip().upper(): p.id
            for p in self.env['res.country.state'].search([
                ('country_id.code', '=', 'AR')
            ])
        }

        vals_list = []
        for row in data_rows:
            row_dict = dict(zip(headers, row))
            of_val = str(row_dict.get('of', '') or '').strip()
            tipo_val = str(row_dict.get('tipo', '') or '').strip().lower()
            conc_val = str(row_dict.get('concesionario', '') or '').strip()
            estado_val = str(row_dict.get('estado', '') or '').strip().lower() or 'liberada'
            ciudad_val = str(row_dict.get('ciudad', '') or '').strip()
            prov_val = str(row_dict.get('provincia', '') or '').strip()

            if not of_val or of_val in existing_ofs:
                continue
            if tipo_val not in self.TIPOS_VALIDOS:
                continue
            if conc_val.upper() not in concesionarios:
                continue

            prov_id = provincias.get(prov_val.upper(), False)

            vals_list.append({
                'of': of_val,
                'tipo': tipo_val,
                'concesionario_id': concesionarios[conc_val.upper()],
                'estado': estado_val if estado_val in self.ESTADOS_VALIDOS else 'liberada',
                'ciudad': ciudad_val,
                'provincia_id': prov_id,
            })
            existing_ofs.add(of_val)

        if not vals_list:
            raise UserError(_('No hay filas válidas para importar.'))

        maquinas = self.env['pv.maquina'].create(vals_list)

        self.state = 'done'

        return {
            'type': 'ir.actions.act_window',
            'name': _('Máquinas importadas (%d)', len(maquinas)),
            'res_model': 'pv.maquina',
            'view_mode': 'list,form',
            'domain': [('id', 'in', maquinas.ids)],
        }
