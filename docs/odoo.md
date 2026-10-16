# Conceptos de Odoo usados en el módulo

Resumen de las piezas de Odoo que aparecen en esta documentación, explicadas con ejemplos del módulo. Cada
sección termina con el enlace a la documentación oficial de Odoo 19, para profundizar.

## Modelos, registros y campos

Un **modelo** es una tabla con su comportamiento en Python (`pv.ticket`, `res.partner`). Un **registro** es una
fila. Los **campos** se declaran en la clase (`fields.Char`, `fields.Many2one`…). Toda lectura y escritura pasa
por el **ORM**, que es quien aplica los permisos.

- `Many2one`: apunta a un registro de otro modelo (la máquina de un ticket). `One2many` es la lista inversa
  (los tickets de una máquina). `Many2many`: varios con varios (los motivos de rechazo de un ticket).
- `create`, `write`, `unlink` son las operaciones de crear, modificar y **borrar** registros. *Unlink* es el
  nombre que usa Odoo para borrar.

Oficial: [ORM API](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html) ·
[campos relacionales](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#relational-fields)

## Usuarios internos y usuarios portal

- **Interno**: usa el backend de Odoo (Staff y Admin de Crucianelli).
- **Portal**: persona externa que solo accede a las páginas web de `/my` (los concesionarios). Odoo le da muy
  pocos permisos de base; los demás los agrega este módulo con el grupo Concesionario.

Oficial: [User portals](https://www.odoo.com/documentation/19.0/applications/general/users/user_portals.html) ·
[Access rights (usuario final)](https://www.odoo.com/documentation/19.0/applications/general/users/access_rights.html)

## Grupos

Un usuario tiene uno o más **grupos** (`res.groups`). Los permisos se asignan a grupos, nunca a usuarios. Un
grupo puede incluir a otro (`implied_ids`): el Admin de Posventa incluye al Staff.

Oficial: [Security in Odoo](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html)

## Permisos de acceso

Archivo `security/ir.model.access.csv` (modelo `ir.model.access`). Por cada modelo y grupo dice qué operaciones
se permiten **sobre el modelo entero**:

| Columna | Operación | En la referencia |
|---|---|---|
| `perm_read` | leer | L |
| `perm_write` | modificar | E |
| `perm_create` | crear | C |
| `perm_unlink` | borrar | B |

Son **sumables**: si un usuario está en dos grupos, tiene la unión de lo que le dan ambos. Si ningún grupo le da
una operación, no la puede hacer en ningún registro del modelo.

Oficial: [Access Rights](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html#access-rights)

## Reglas de registro

Archivo `security/pv_security.xml` (modelo `ir.rule`). Se evalúan **después** de los permisos de acceso y
deciden **qué registros** del modelo puede tocar el usuario, con un dominio (una condición) como
`[('concesionario_id.partner_id', 'in', [...])]`.

- Si ninguna regla aplica, se permite (lo decidieron los permisos de acceso).
- Las reglas **de grupo** se suman entre sí (alcanza con cumplir una); las reglas **globales** (sin grupo) se
  exigen todas.
- Cada regla puede aplicar solo a algunas operaciones (`perm_read`, `perm_write`, `perm_create`,
  `perm_unlink`, con el mismo significado que arriba).

**Ejemplo que importa en este módulo.** Odoo, en el módulo `base`, da a los usuarios portal permiso de **lectura
sobre el modelo** `res.partner` (permiso de acceso), pero agrega la regla de grupo
*"res_partner: portal/public: read access on my commercial partner"*:

```python
[('id', 'child_of', user.commercial_partner_id.id)]
```

O sea: un usuario portal lee contactos, **pero solo los de su propia empresa**. No es una limitación del portal
como entorno de ejecución: es una regla común y corriente, y le pasaría lo mismo a un usuario interno con una
regla así. Por eso el nombre del cliente final o del responsable de Crucianelli no se puede leer a través del
contacto.

Oficial: [Record Rules](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html#record-rules) ·
[Global rules versus group rules](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html#global-rules-versus-group-rules) ·
[tutorial: restringir acceso a datos](https://www.odoo.com/documentation/19.0/developer/tutorials/restrict_data_access.html)

## Superusuario y sudo

`registro.sudo()` devuelve el mismo registro pero operando **sin** permisos de acceso ni reglas. Es poderoso y
peligroso: en este módulo se usa solo dentro de métodos que ya validaron quién llama (por ejemplo, para que un
concesionario deje una nota en el chatter de una máquina que no puede modificar).

Oficial: [sudo](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#odoo.models.Model.sudo) ·
[Environment](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#environment)

## Campos related

Un campo **related** copia el valor de un campo de otro registro siguiendo una relación:

```python
cliente_nombre = fields.Char(related='cliente_id.name', string='Nombre del Cliente')
```

Por defecto Odoo los **calcula como superusuario**, no los guarda en la base y son **de solo lectura**. En la
práctica:

- El concesionario lee `maquina.cliente_nombre` y obtiene el texto "Productor Juan Perez", **aunque no puede leer
  el contacto** `cliente_id`. Lo único que se expone es ese texto: no ve el contacto, ni su email, teléfono o
  dirección, ni puede abrirlo, y mucho menos modificarlo (el campo es de solo lectura).
- Se puede buscar por él (el buscador de máquinas del portal filtra por `cliente_nombre`), también con permisos
  de superusuario.

Es la herramienta indicada para **mostrar un dato puntual** de un modelo que el usuario no tiene permiso de leer.
La alternativa sería agregar una regla de grupo sobre `res.partner` para el grupo Concesionario: se sumaría a la
de Odoo y funcionaría, pero le daría acceso al contacto **completo**, que es más de lo necesario.

Oficial: [Related fields](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#related-fields) ·
[Computed fields](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#computed-fields)

## Decoradores de métodos

- `@api.depends(...)`: método que calcula un campo a partir de otros (ej. T1/T2/T3).
- `@api.constrains(...)`: validación que se ejecuta al guardar; si falla, se cancela todo (ej. que el
  subsistema pertenezca al sistema elegido).
- `@api.onchange(...)`: ayuda del formulario del backend mientras el usuario edita; **no** se ejecuta desde el
  portal ni desde RPC, por eso nunca se usa para reglas.
- `@api.model_create_multi`: `create` que recibe varios registros a la vez.

Oficial: [constrains](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#odoo.api.constrains) ·
[onchange](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#odoo.api.onchange) ·
[Computed fields](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#computed-fields)

## Archivos de datos y noupdate

Los XML y CSV de `data/`, `security/` y `views/` se cargan al instalar y **se vuelven a cargar en cada
actualización** (`-u`), pisando lo que se haya cambiado desde la interfaz. Lo que está dentro de
`<data noupdate="1">` se carga **solo al instalar**: en este módulo, los crons. Por eso cambiar un cron en el XML
no alcanza para bases ya instaladas (ver [Recetas](recetas.md#cambiar-el-método-que-llama-un-cron)).

Oficial: [Data Files](https://www.odoo.com/documentation/19.0/developer/reference/backend/data.html)

## Acciones planificadas y acciones de servidor

Una **acción planificada** (`ir.cron`) ejecuta código cada cierto tiempo, como el usuario OdooBot (superusuario).
Una **acción de servidor** (`ir.actions.server`) ejecuta código al elegirla en un menú (el Tablero de Control).
`_trigger()` adelanta la próxima ejecución de un cron (se usa al terminar de subir un video).

Oficial: [Scheduled Actions](https://www.odoo.com/documentation/19.0/developer/reference/backend/actions.html#scheduled-actions-ir-cron) ·
[Server Actions](https://www.odoo.com/documentation/19.0/developer/reference/backend/actions.html#server-actions-ir-actions-server)

## Chatter

El historial de mensajes al pie de un registro viene de heredar `mail.thread`.

- `tracking=True` en un campo registra cada cambio de valor (quién, cuándo, de qué a qué).
- `message_post()` publica un mensaje y notifica a los seguidores.
- `_message_log()` deja una **nota interna** sin notificar a nadie: la usan las transiciones de estado.

Oficial: [Messaging integration](https://www.odoo.com/documentation/19.0/developer/reference/backend/mixins.html#messaging-integration) ·
[Logging changes](https://www.odoo.com/documentation/19.0/developer/reference/backend/mixins.html#logging-changes)

## Controllers y rutas

Un **controller** es una clase Python cuyos métodos responden a URLs (`@http.route('/my/posventa', ...)`).
`auth='user'` exige sesión iniciada. El portal de este módulo extiende `CustomerPortal`, el controller de Odoo
que arma `/my`.

Oficial: [Web Controllers](https://www.odoo.com/documentation/19.0/developer/reference/backend/http.html)

## Vistas, QWeb y OWL

- **Vistas del backend** (`views/*_views.xml`): formularios, listas y kanban. Un `<button type="object"
  name="action_x">` llama al método `action_x` del modelo.
- **QWeb**: el lenguaje de plantillas con el que se arman en el servidor las páginas del portal
  (`views/portal_templates.xml`).
- **OWL**: el framework JavaScript de Odoo. Los asistentes del portal son componentes OWL que se insertan en una
  página QWeb con `<owl-component>` y llaman a métodos del modelo por RPC (`orm.call`, `orm.create`).

Oficial: [View architectures](https://www.odoo.com/documentation/19.0/developer/reference/user_interface/view_architectures.html) ·
[QWeb](https://www.odoo.com/documentation/19.0/developer/reference/frontend/qweb.html) ·
[Owl components](https://www.odoo.com/documentation/19.0/developer/reference/frontend/owl_components.html) ·
[servicio RPC](https://www.odoo.com/documentation/19.0/developer/reference/frontend/services.html#rpc-service)

## Scripts de migración

Código en `migrations/<versión>/` que Odoo corre una vez al actualizar una base a esa versión del módulo
(`pre-migrate.py` antes de cargar el código nuevo, `post-migrate.py` después). Sirve para adaptar datos
existentes. Solo corre si sube la `version` del `__manifest__.py`.

Oficial: [Upgrade scripts](https://www.odoo.com/documentation/19.0/developer/reference/upgrades/upgrade_scripts.html)

## Tests

- `TransactionCase`: test de Python; cada test se deshace al terminar.
- `HttpCase`: además levanta el servidor web; permite pedir páginas (`url_open`) y correr **tours**
  (`start_tour`): un navegador sin ventana que sigue pasos como un usuario.
- `@tagged('post_install', '-at_install')`: corre después de instalar todos los módulos.

Oficial: [Testing Odoo](https://www.odoo.com/documentation/19.0/developer/reference/backend/testing.html) ·
[Writing a test tour](https://www.odoo.com/documentation/19.0/developer/reference/backend/testing.html#writing-a-test-tour)

## Línea de comandos

- `-u posventa`: actualiza el módulo (recarga código y datos).
- `--test-tags=/posventa`: corre los tests del módulo.
- `shell`: consola de Python con `env` listo, para consultas o para regenerar la referencia.

Oficial: [Command-line interface](https://www.odoo.com/documentation/19.0/developer/reference/cli.html) ·
[--test-tags](https://www.odoo.com/documentation/19.0/developer/reference/cli.html#cmdoption-odoo-bin-test-tags) ·
[shell](https://www.odoo.com/documentation/19.0/developer/reference/cli.html#shell-open-a-shell)
