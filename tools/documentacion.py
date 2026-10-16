# Part of Crucianelli Posventa Module
"""Genera docs/referencia.md a partir del propio Odoo, para que no se desactualice.

Se arma con los metadatos del ORM (modelos, campos, relaciones), los registros de seguridad y
los archivos del módulo, no con análisis estático de llamadas: así incluye los vínculos que en
Odoo no son llamadas de Python (botones de vistas, crons, JS que llama al ORM).

Regenerar (y luego commitear docs/referencia.md):

    ./odoo-bin shell -d <base> --no-http <<< "from odoo.addons.posventa.tools.documentacion import escribir; escribir(env)"

El test tests/test_documentacion.py falla si el archivo quedó desactualizado.
"""
import inspect
import re
from pathlib import Path

from lxml import etree

from odoo import models

MODULO = 'posventa'
RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / 'docs' / 'referencia.md'
RELACIONALES = ('many2one', 'one2many', 'many2many')
JS_ORM_CALL = re.compile(r'orm\.call\(\s*"([\w.]+)",\s*"(\w+)"')
CODIGO_CALL = re.compile(r'model\.(\w+)\(')


def generar(env):
    todos = sorted((env[nombre] for nombre in env.registry if nombre.startswith('pv.')), key=lambda m: m._name)
    modelos = [m for m in todos if not m._transient]
    secciones = [
        '# Referencia generada del módulo Posventa',
        '> Archivo generado por `tools/documentacion.py`: no editar a mano. '
        'Cómo regenerarlo: ver el encabezado de ese archivo.',
        '## Diagrama de datos',
        _diagrama(modelos),
        '## Modelos y campos',
        *(_tabla_campos(m) for m in modelos),
        '## Puntos de entrada',
        'Métodos públicos (invocables por RPC) de modelos y asistentes, y quién los llama. Las llamadas desde Python '
        'se buscan por nombre en `controllers/` y `wizard/`, así que un nombre repetido en otro modelo puede aparecer de más.',
        _puntos_de_entrada(env, todos),
        '## Permisos por modelo',
        'L = leer, E = escribir, C = crear, B = borrar. Sin fila: el grupo no accede al modelo.',
        _matriz_acceso(env),
        '## Reglas de registro',
        'Filtran qué registros ve cada grupo. Las reglas de distintos grupos de un mismo usuario se suman (O lógico).',
        _reglas(env),
    ]
    return '\n\n'.join(secciones) + '\n'


def escribir(env):
    ARCHIVO.write_text(generar(env), encoding='utf-8')
    return ARCHIVO


# --- Modelos ---
def _id_mermaid(nombre):
    return nombre.replace('.', '_')


def _campos_propios(modelo):
    # Sin las columnas automáticas de Odoo (id, create_uid, write_date...): están en todos los modelos
    return [f for nombre, f in sorted(modelo._fields.items())
            if MODULO in f._modules and nombre not in models.MAGIC_COLUMNS]


def _diagrama(modelos):
    lineas = ['```mermaid', 'erDiagram']
    for modelo in modelos:
        for campo in _campos_propios(modelo):
            if campo.type == 'many2one' and not campo.related:
                destino = '||' if campo.required else 'o|'
                lineas.append(f'    {_id_mermaid(modelo._name)} }}o--{destino} {_id_mermaid(campo.comodel_name)} : {campo.name}')
            elif campo.type == 'many2many' and not campo.related:
                lineas.append(f'    {_id_mermaid(modelo._name)} }}o--o{{ {_id_mermaid(campo.comodel_name)} : {campo.name}')
    lineas.append('```')
    return '\n'.join(lineas)


def _celda(texto):
    return ' '.join(str(texto or '').split()).replace('|', '\\|')


def _detalle(campo):
    detalle = []
    if campo.type in RELACIONALES:
        detalle.append(f'→ `{campo.comodel_name}`')
    if campo.type == 'selection' and isinstance(campo.selection, list):
        detalle.append('valores: ' + ', '.join(f'`{clave}`' for clave, _etiqueta in campo.selection))
    if campo.required:
        detalle.append('obligatorio')
    if campo.related:
        detalle.append(f'related `{".".join(campo.related)}`')
    elif campo.compute:
        detalle.append('calculado' + (' (guardado)' if campo.store else ''))
    if campo.help:
        detalle.append(campo.help)
    return _celda('; '.join(detalle))


def _tabla_campos(modelo):
    filas = [f'| `{c.name}` | {c.type} | {_celda(c.string)} | {_detalle(c)} |' for c in _campos_propios(modelo)]
    return '\n'.join([
        f'### `{modelo._name}` — {_celda(modelo._description)}',
        '| Campo | Tipo | Etiqueta | Detalle |',
        '|---|---|---|---|',
        *filas,
    ])


# --- Puntos de entrada ---
def _metodos_publicos(modelo):
    """{nombre: primera línea del docstring} de los métodos públicos definidos en este módulo."""
    metodos = {}
    for clase in type(modelo).__mro__:
        if not clase.__module__.startswith(f'odoo.addons.{MODULO}.'):
            continue
        for nombre, valor in vars(clase).items():
            # Los overrides del ORM (create, write...) no son puntos de entrada propios
            if inspect.isfunction(valor) and not nombre.startswith('_') and not hasattr(models.BaseModel, nombre):
                metodos[nombre] = _resumen(valor)
    return metodos


def _resumen(funcion):
    return (inspect.getdoc(funcion) or '').split('\n')[0] if funcion else ''


def _registros_del_modulo(env, modelo):
    datos = env['ir.model.data'].search([('module', '=', MODULO), ('model', '=', modelo)])
    return env[modelo].browse(datos.mapped('res_id')).exists()


def _llamadores(env):
    """{(modelo, método): {descripciones de quién lo llama}} desde vistas, crons, JS y Python."""
    llamadores = {}

    def agregar(modelo, metodo, origen):
        llamadores.setdefault((modelo, metodo), set()).add(origen)

    for vista in _registros_del_modulo(env, 'ir.ui.view'):
        for boton in etree.fromstring(vista.arch_db).iter('button'):
            if boton.get('type') == 'object':
                agregar(_modelo_del_boton(env, vista.model, boton), boton.get('name'), f'botón en vista `{vista.name}`')
    # Crons y acciones de servidor se leen del XML (en la base pueden quedar versiones viejas: son noupdate)
    for xml in sorted(RAIZ.glob('*/*.xml')):
        for registro in etree.parse(str(xml)).iter('record'):
            codigo, modelo = registro.find("field[@name='code']"), registro.find("field[@name='model_id']")
            if registro.get('model') in ('ir.cron', 'ir.actions.server') and codigo is not None and modelo is not None:
                tipo = 'cron' if registro.get('model') == 'ir.cron' else 'acción de servidor'
                nombre = registro.findtext("field[@name='name']")
                for metodo in CODIGO_CALL.findall(codigo.text or ''):
                    agregar(env.ref(f"{MODULO}.{modelo.get('ref')}").model, metodo, f'{tipo} «{nombre}»')
    for js in sorted((RAIZ / 'static' / 'src').rglob('*.js')):
        for modelo, metodo in JS_ORM_CALL.findall(js.read_text(encoding='utf-8')):
            agregar(modelo, metodo, f'JS `{js.relative_to(RAIZ)}`')
    return llamadores


def _modelo_del_boton(env, modelo, boton):
    """Un botón dentro de la sub-vista de un campo x2many actúa sobre el modelo de ese campo."""
    for ancestro in reversed(list(boton.iterancestors('field'))):
        modelo = env[modelo]._fields[ancestro.get('name')].comodel_name
    return modelo


def _llamadas_python(metodo):
    patron = re.compile(rf'\.{metodo}\(')
    return {f'`{py.relative_to(RAIZ)}`' for carpeta in ('controllers', 'wizard')
            for py in (RAIZ / carpeta).glob('*.py') if patron.search(py.read_text(encoding='utf-8'))}


def _puntos_de_entrada(env, modelos):
    llamadores = _llamadores(env)
    filas = []
    for modelo in modelos:
        metodos = _metodos_publicos(modelo)
        # Los crons llaman métodos privados: también son puntos de entrada
        metodos.update({m: _resumen(getattr(type(modelo), m, None))
                        for (nombre, m) in llamadores if nombre == modelo._name and m not in metodos})
        for metodo, doc in sorted(metodos.items()):
            origenes = sorted(llamadores.get((modelo._name, metodo), set()) | _llamadas_python(metodo))
            filas.append(f'| `{modelo._name}` | `{metodo}` | {_celda(doc)} | {_celda("; ".join(origenes)) or "—"} |')
    return '\n'.join(['| Modelo | Método | Qué hace | Llamado desde |', '|---|---|---|---|', *filas])


# --- Seguridad ---
def _matriz_acceso(env):
    filas = []
    for acceso in _registros_del_modulo(env, 'ir.model.access').sorted(lambda a: (a.model_id.model, a.group_id.name or '')):
        permisos = ''.join(letra if permitido else '-' for letra, permitido in (
            ('L', acceso.perm_read), ('E', acceso.perm_write), ('C', acceso.perm_create), ('B', acceso.perm_unlink)))
        filas.append(f'| `{acceso.model_id.model}` | {_celda(acceso.group_id.name or "Todos")} | `{permisos}` |')
    return '\n'.join(['| Modelo | Grupo | Permisos |', '|---|---|---|', *filas])


def _reglas(env):
    filas = [
        f'| `{regla.model_id.model}` | {_celda(", ".join(regla.groups.mapped("name")) or "Todos")} | '
        f'{_celda(regla.name)} | `{_celda(regla.domain_force)}` |'
        for regla in _registros_del_modulo(env, 'ir.rule').sorted(lambda r: (r.model_id.model, r.name))
    ]
    return '\n'.join(['| Modelo | Grupos | Regla | Dominio |', '|---|---|---|---|', *filas])
