# Mantenibilidad

Estado del código medido con **complejidad ciclomática** función por función, cruzada con la cobertura de
los tests, con los puntos críticos analizados y una lista priorizada de mejoras. La primera parte se
escribe a mano; desde *Resumen por área* el documento lo genera `tools/complejidad.py`.

## Qué se mide

### Complejidad ciclomática (CCN)

Es la cantidad de **caminos independientes** que tiene una función: 1 más uno por cada punto en que el
código se bifurca. Se usa porque se relaciona directamente con dos costos:

- **Entender**: cada bifurcación es un caso más que hay que tener en la cabeza al leer o cambiar la
  función.
- **Probar**: es la cantidad mínima de tests para recorrer todos los caminos. Una función con CCN 40
  necesita 40 casos para cubrirse entera; en la práctica, nadie los escribe.

La mide [lizard](https://github.com/terryyin/lizard) 1.25, igual para Python y JavaScript. Suma 1 por:

| Python | JavaScript |
|---|---|
| `if`, `elif`, `for`, `while`, `except`, `finally` | `if`, `for`, `while`, `catch`, `case` |
| `and`, `or` (también dentro de f-strings) | `&&`, `\|\|`, `??` (también dentro de `` `${…}` ``) |
| `if` y `for` de una comprensión; `x if c else y` | el ternario `c ? x : y` |

No suman: `else`, `with`, `return`, ni el encadenamiento opcional `?.` de JavaScript.

### Escala

| Rango | CCN | Lectura |
|:-:|--:|---|
| **A** | 1–5 | Simple. Se entiende de una lectura. |
| **B** | 6–10 | Bien estructurada. Es el techo para código nuevo. |
| **C** | 11–20 | Compleja. Aceptable si la complejidad es del problema (muchas validaciones), no de la forma. |
| **D** | 21–30 | Muy compleja. Cuesta cambiarla sin romper un caso; conviene dividirla. |
| **E** | 31–40 | Alarmante. |
| **F** | 41+ | Inmantenible en la práctica: nadie puede tener todos los caminos en la cabeza ni probarlos. |

Es la escala de McCabe que usan radon y SonarQube. Además se mide:

- **Líneas de código** (NLOC): líneas con código, sin comentarios ni líneas en blanco. Más de ~60 en una
  función suele indicar que hace varias cosas.
- **Parámetros**: más de 5 suele indicar que falta agrupar datos (un dict o un registro).

### Lo que la cifra no dice

- **Inflación por valores por defecto.** `x or ''` suma 1 aunque no sea una decisión de negocio. Por
  ejemplo, `pv.maquina.get_portal_detail_data` da 21, pero casi todo son `or ''` y condiciones de una
  línea al armar un diccionario (ver *Puntos críticos*).
- **Funciones largas pero lineales.** Una función que arma HTML puede tener CCN bajo y 150 líneas: hay
  que mirar también las líneas de código.
- **Funciones anónimas.** En JavaScript cada callback (`forEach(x => …)`) se mide aparte de la función
  que lo contiene. La función que lo contiene "parece" más simple de lo que es.
- **No mide anidamiento ni nombres.** Dos funciones con el mismo CCN pueden leerse muy distinto.

## Estado general

**Sano.** De 335 funciones (servidor y navegador, sin tests), el 95 % está en A o B y la mediana es 2. No
hay ninguna en E ni F; hay 2 en D y 13 en C, casi todas validaciones con muchas reglas de negocio.

El **núcleo** (estados del reclamo, quién puede escribir qué, pertenencia al concesionario, vigencia y
secuencia de certificados) está en A–C y los tests lo recorren casi entero:

| Función | Qué hace | CCN | Cobertura |
|---|---|--:|--:|
| `pv.ticket._write_estado` y `action_tomar/aceptar/rechazar/cerrar_ticket` | Cambios de estado del reclamo | 1–3 | 100 % |
| `pv.ticket.action_enviar_ticket` | El concesionario envía el reclamo | 7 | 85 % |
| `pv.ticket._check_write_permitido` | Qué campo puede cambiar quién y en qué estado | 12 | 93 % |
| `pv.ticket.create` | Alta del reclamo (concesionario, certificado, tipo) | 9 | 100 % |
| `pv.concesionario._is_member`, `_get_concesionario_for_user` | Pertenencia del usuario al concesionario | 1–2 | 100 % |
| `pv.certificado._es_vigente_para_reclamos` | Si un certificado habilita reclamos | 4 | 100 % |
| `pv.certificado._check_secuencia` | FRU → FEU → CPM | 15 | 84 % |
| `pv.ticket._check_clasificacion` | Sistema, subsistema, problema y hectáreas | 15 | 89 % |

*Cobertura*: porcentaje de las líneas de la función que ejecutan los tests del módulo (`coverage.py`,
noviembre de 2026). En total, los tests recorren el **88 %** de las líneas de Python. Los archivos por
debajo del 80 % son el tablero (66 %), el controlador de subida (71 %), las medidas de seguimiento (74 %),
los asistentes de liberar y trasladar (75 %), el de cierre (79 %) y `tools/drive.py` (79 %). El
JavaScript no se mide; lo prueban los tours del portal.

### El riesgo real: complejo y sin tests

| Función | CCN | Cobertura | Qué falta probar |
|---|--:|--:|---|
| `upload_chunk` (`controllers/multimedia.py`) | 29 | 72 % | **Todos los caminos de error**, incluidos los dos de permisos: ticket inexistente o sin acceso (404) y ticket de otro concesionario (403). También parámetros inválidos, cantidad de fragmentos que no coincide, fragmento más grande que lo configurado, fragmentos faltantes, archivo final de otro tamaño y modo *Odoo* (adjunto). |
| `pv.cerrar.ticket.wizard.default_get` | 13 | 33 % | Que el asistente de cierre traiga los datos que ya tenía el reclamo. |
| `upload_status` (`controllers/multimedia.py`) | 4 | 20 % | La consulta de estado de una subida. |

El primero es el único que importa: es la puerta de entrada de archivos desde el portal. El código tiene
los controles (`has_access('write')` sobre el ticket y pertenencia al concesionario), pero **ningún test
avisaría si un cambio los rompe**.

## Puntos críticos

Las 2 funciones en rango D y las C que conviene mirar.

### D · `upload_chunk` — CCN 29, 91 líneas

Recibe un fragmento de un archivo pesado y, con el último, arma el archivo y lo deja para Drive (o lo
guarda como adjunto en modo *Odoo*). Hace cuatro cosas en secuencia: **validar** (parámetros, acceso al
ticket, pertenencia, límites de tamaño), **guardar el fragmento**, **ensamblar** cuando llega el último y
**entregar** el archivo según el modo de almacenamiento. Cada validación es un `if … return _error(…)`:
de ahí sale casi toda la complejidad.

- **Riesgo**: medio. Es código de seguridad (lo llama cualquier usuario logueado, con `csrf=False`) y sus
  caminos de error no tienen tests.
- **Cómo bajarla**: una función por etapa (`_validar_subida`, `_guardar_fragmento`, `_ensamblar`) y el
  controlador solo las encadena. Cada una queda en A–B y se puede probar por separado. Antes, escribir los
  tests de los errores (mejora 1) para dividirla con red.

### D · `pv.maquina.get_portal_detail_data` — CCN 21, 39 líneas

Arma el diccionario con los datos de la máquina para el portal y los asistentes. **No es compleja**: la
cifra sale de nueve `x or ''` y de condiciones de una línea en los permisos (`puede_crear_ticket`,
`puede_transferir`…). No tiene caminos que se crucen y los tests la recorren entera (100 %). No hace falta
tocarla.

### C · `pv.cerrar.ticket.wizard.action_confirmar` — CCN 15, 57 líneas

Valida el cierre, cierra el reclamo, adjunta el comprobante y escribe el resumen en el chatter. Las tres
primeras partes son cortas; el largo sale del resumen, armado como HTML en un string con siete
`escape(…)`. Separar el resumen en `_mensaje_cierre()` (o una plantilla QWeb) la deja en ~8.

### C · `pv.cerrar.ticket.wizard.default_get` — CCN 13, 15 líneas

Copia cuatro campos del reclamo al asistente, cada uno con su `if`. Un bucle sobre una lista de campos la
deja en ~4. Es la de menor cobertura (33 %).

### C · Validaciones (`_check_secuencia`, `_check_clasificacion`, `_check_write_permitido`, `stepError`, `validateStep`)

Una regla por `if`, cada una con su mensaje. La complejidad es la del problema, no la de la forma: se
leen de arriba abajo y están cubiertas (84–93 %). Partirlas no las haría más claras.

### C · Lectura del Excel de máquinas (`_leer_excel`, `_validar_filas`)

Leer y validar una planilla: un caso por columna y por error posible. Cubiertas al 82 y 100 %.

### C · `uploadFileInChunks` (`static/src/shared/chunk_upload.js`) — CCN 16

Envía los fragmentos con reintentos. Mezcla el bucle de fragmentos con el de reintentos y el armado del
mensaje de error; sacar el envío de un fragmento con reintentos a su propia función la deja en ~6.

## Mejoras priorizadas

| # | Qué | Por qué | Esfuerzo | CCN hoy → esperado |
|---|---|---|---|---|
| 1 | Tests de los errores de `upload_chunk` (permisos, parámetros, tamaños, fragmentos, modo *Odoo*) | Es la entrada de archivos desde el portal y sus controles de acceso no tienen tests | Bajo | — |
| 2 | Dividir `upload_chunk` en validar, guardar, ensamblar | Con la 1 hecha, cada parte queda probada por separado | Medio | 29 → ninguna parte > 10 |
| 3 | `default_get` del cierre con una lista de campos, y su test | Simple y casi sin cobertura | Bajo | 13 → ~4 |
| 4 | Resumen del cierre en `_mensaje_cierre()` | HTML en un string largo | Bajo | 15 → ~8 |
| 5 | Envío de un fragmento con reintentos aparte en `chunk_upload.js` | Dos bucles mezclados | Bajo | 16 → ~6 |

## Reglas para el código nuevo

1. **CCN ≤ 10** (rango B) en toda función nueva. Si el problema pide más (una validación larga), dejar
   escrito por qué en el docstring.
2. **No hacer crecer una función C o peor**: lo nuevo, en una función aparte que se llame desde ahí.
3. **Una función, una tarea**: si el docstring necesita "y después…", son dos funciones.
4. **Todo control de acceso con su test**, también el camino que deniega.
5. **HTML en plantillas** (QWeb), no armado en strings: escapan solas y no suman caminos.
6. Al cambiar código, **regenerar este documento** y commitearlo junto.

Estilos: ver [Arquitectura › Decisiones de diseño](arquitectura.md#decisiones-de-diseño-que-conviene-conocer).

## Regenerar

Desde la carpeta del módulo (no necesita Odoo ni una base):

```bash
uv run --no-project --with lizard==1.25.0 python tools/complejidad.py
```

Reescribe solo lo que está entre los marcadores `complejidad:inicio` y `complejidad:fin`; el análisis de
arriba se actualiza a mano. Si una función de *Puntos críticos* cambia de rango, corregir su texto. Las
cifras de *Estado general* son de noviembre de 2026.

La cobertura de tests se mide aparte, en una base de prueba (`coverage` no es dependencia del módulo):

```bash
python -m coverage run --source=addons/posventa --omit='*/tests/*,*/migrations/*' \
    odoo-bin -d <base_de_prueba> -i posventa --test-tags /posventa --stop-after-init --http-port 8299
python -m coverage report --show-missing
```

<!-- complejidad:inicio (generado por tools/complejidad.py, no editar a mano) -->

## Resumen por área

| Área | Funciones | Líneas de código | CCN promedio | CCN máxima | CCN > 10 | A | B | C | D | E | F |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Servidor | 232 | 2120 | 3.6 | 29 | 11 | 190 | 31 | 9 | 2 | 0 | 0 |
| Navegador | 103 | 813 | 2.5 | 17 | 4 | 94 | 5 | 4 | 0 | 0 | 0 |
| Tests | 102 | 1844 | 1.2 | 3 | 0 | 102 | 0 | 0 | 0 | 0 | 0 |
| **Total** | 437 | 4777 | 2.8 | 29 | 15 | 386 | 36 | 13 | 2 | 0 | 0 |

## Funciones que requieren atención (CCN > 10)

Ordenadas de mayor a menor complejidad.

| CCN | Rango | Función | Ubicación | Líneas de código | Parámetros |
|--:|:-:|---|---|--:|--:|
| 29 | D | `upload_chunk` | [controllers/multimedia.py:29](../controllers/multimedia.py#L29) | 91 | 2 |
| 21 | D | `get_portal_detail_data` | [models/pv_maquina.py:169](../models/pv_maquina.py#L169) | 39 | 1 |
| 17 | C | `stepError` | [static/src/frontend/wizards/ticket_wizard.js:231](../static/src/frontend/wizards/ticket_wizard.js#L231) | 33 | 1 |
| 16 | C | `uploadFileInChunks` | [static/src/shared/chunk_upload.js:40](../static/src/shared/chunk_upload.js#L40) | 46 | 1 |
| 15 | C | `_check_secuencia` | [models/pv_certificado.py:147](../models/pv_certificado.py#L147) | 19 | 1 |
| 15 | C | `_check_clasificacion` | [models/pv_ticket.py:281](../models/pv_ticket.py#L281) | 18 | 1 |
| 15 | C | `action_confirmar` | [wizard/pv_cerrar_ticket_wizard.py:65](../wizard/pv_cerrar_ticket_wizard.py#L65) | 57 | 1 |
| 14 | C | `_llamadores` | [tools/documentacion.py:140](../tools/documentacion.py#L140) | 19 | 1 |
| 14 | C | `_leer_excel` | [wizard/pv_import_maquinas.py:68](../wizard/pv_import_maquinas.py#L68) | 20 | 1 |
| 13 | C | `default_get` | [wizard/pv_cerrar_ticket_wizard.py:49](../wizard/pv_cerrar_ticket_wizard.py#L49) | 15 | 2 |
| 12 | C | `_check_write_permitido` | [models/pv_ticket.py:348](../models/pv_ticket.py#L348) | 15 | 2 |
| 12 | C | `validateStep` | [static/src/frontend/wizards/certificado_wizard.js:152](../static/src/frontend/wizards/certificado_wizard.js#L152) | 34 | 1 |
| 12 | C | `_validar_filas` | [wizard/pv_import_maquinas.py:113](../wizard/pv_import_maquinas.py#L113) | 44 | 1 |
| 11 | C | `create` | [models/pv_certificado.py:183](../models/pv_certificado.py#L183) | 21 | 2 |
| 11 | C | `get certificateTypes` | [static/src/frontend/wizards/certificado_wizard.js:72](../static/src/frontend/wizards/certificado_wizard.js#L72) | 43 | 0 |

## Por archivo

| Archivo | Funciones | Líneas de código | CCN promedio | CCN máxima | Peor rango | CCN > 10 |
|---|--:|--:|--:|--:|:-:|--:|
| [controllers/multimedia.py](../controllers/multimedia.py) | 5 | 136 | 7.4 | 29 | D | 1 |
| [controllers/portal.py](../controllers/portal.py) | 19 | 202 | 2.4 | 5 | A | 0 |
| [models/pv_certificado.py](../models/pv_certificado.py) | 21 | 207 | 4.5 | 15 | C | 2 |
| [models/pv_concesionario.py](../models/pv_concesionario.py) | 8 | 53 | 1.4 | 2 | A | 0 |
| [models/pv_dashboard.py](../models/pv_dashboard.py) | 5 | 36 | 1.6 | 3 | A | 0 |
| [models/pv_maquina.py](../models/pv_maquina.py) | 33 | 304 | 3.1 | 21 | D | 1 |
| [models/pv_ticket.py](../models/pv_ticket.py) | 51 | 340 | 3.4 | 15 | C | 2 |
| [models/pv_ticket_medida.py](../models/pv_ticket_medida.py) | 3 | 19 | 2.3 | 3 | A | 0 |
| [models/pv_ticket_multimedia.py](../models/pv_ticket_multimedia.py) | 21 | 187 | 3.6 | 8 | B | 0 |
| [models/res_config_settings.py](../models/res_config_settings.py) | 4 | 27 | 2.2 | 4 | A | 0 |
| [static/src/backend/multimedia_chunk_uploader.js](../static/src/backend/multimedia_chunk_uploader.js) | 8 | 67 | 1.4 | 3 | A | 0 |
| [static/src/frontend/portal_posventa.js](../static/src/frontend/portal_posventa.js) | 19 | 104 | 1.7 | 8 | B | 0 |
| [static/src/frontend/wizards/certificado_wizard.js](../static/src/frontend/wizards/certificado_wizard.js) | 21 | 195 | 3.5 | 12 | C | 2 |
| [static/src/frontend/wizards/ticket_wizard.js](../static/src/frontend/wizards/ticket_wizard.js) | 46 | 370 | 2.5 | 17 | C | 1 |
| [static/src/shared/chunk_upload.js](../static/src/shared/chunk_upload.js) | 9 | 77 | 3.2 | 16 | C | 1 |
| [static/tests/tours/portal_posventa_tour.js](../static/tests/tours/portal_posventa_tour.js) | 11 | 176 | 1.0 | 1 | A | 0 |
| [tests/common.py](../tests/common.py) | 3 | 52 | 1.3 | 2 | A | 0 |
| [tests/test_documentacion.py](../tests/test_documentacion.py) | 1 | 4 | 1.0 | 1 | A | 0 |
| [tests/test_drive.py](../tests/test_drive.py) | 6 | 42 | 1.0 | 1 | A | 0 |
| [tests/test_import_maquinas.py](../tests/test_import_maquinas.py) | 5 | 72 | 1.8 | 2 | A | 0 |
| [tests/test_maquina_certificados.py](../tests/test_maquina_certificados.py) | 10 | 442 | 1.2 | 3 | A | 0 |
| [tests/test_multimedia_upload.py](../tests/test_multimedia_upload.py) | 13 | 264 | 1.2 | 3 | A | 0 |
| [tests/test_portal.py](../tests/test_portal.py) | 11 | 126 | 1.1 | 2 | A | 0 |
| [tests/test_security_access.py](../tests/test_security_access.py) | 9 | 132 | 1.3 | 2 | A | 0 |
| [tests/test_security_hardening.py](../tests/test_security_hardening.py) | 18 | 200 | 1.1 | 2 | A | 0 |
| [tests/test_ticket_workflow.py](../tests/test_ticket_workflow.py) | 10 | 255 | 1.0 | 1 | A | 0 |
| [tests/test_transferencia.py](../tests/test_transferencia.py) | 5 | 79 | 1.2 | 2 | A | 0 |
| [tools/complejidad.py](../tools/complejidad.py) | 11 | 100 | 4.0 | 8 | B | 0 |
| [tools/documentacion.py](../tools/documentacion.py) | 18 | 137 | 4.6 | 14 | C | 1 |
| [tools/drive.py](../tools/drive.py) | 12 | 72 | 2.8 | 5 | A | 0 |
| [wizard/portal_wizard.py](../wizard/portal_wizard.py) | 4 | 34 | 3.2 | 5 | A | 0 |
| [wizard/pv_adjuntar_multimedia_wizard.py](../wizard/pv_adjuntar_multimedia_wizard.py) | 3 | 43 | 4.7 | 6 | B | 0 |
| [wizard/pv_cerrar_ticket_wizard.py](../wizard/pv_cerrar_ticket_wizard.py) | 2 | 72 | 14.0 | 15 | C | 2 |
| [wizard/pv_import_maquinas.py](../wizard/pv_import_maquinas.py) | 10 | 142 | 5.3 | 14 | C | 2 |
| [wizard/pv_liberar_maquina_wizard.py](../wizard/pv_liberar_maquina_wizard.py) | 1 | 4 | 1.0 | 1 | A | 0 |
| [wizard/pv_transferir_maquina_wizard.py](../wizard/pv_transferir_maquina_wizard.py) | 1 | 5 | 1.0 | 1 | A | 0 |

## Todas las funciones

Por archivo y en orden de aparición. Las funciones anónimas de JavaScript (callbacks) se miden aparte de la función que las contiene.

<details><summary><code>controllers/multimedia.py</code> — 5 funciones, CCN máxima 29</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [15](../controllers/multimedia.py#L15) | `_sanitize_filename` | 2 | A | 4 | 1 |
| [22](../controllers/multimedia.py#L22) | `_error` | 1 | A | 2 | 2 |
| [29](../controllers/multimedia.py#L29) | `upload_chunk` | 29 | D | 91 | 2 |
| [148](../controllers/multimedia.py#L148) | `_store_as_attachment` | 1 | A | 26 | 6 |
| [177](../controllers/multimedia.py#L177) | `upload_status` | 4 | A | 13 | 2 |

</details>

<details><summary><code>controllers/portal.py</code> — 19 funciones, CCN máxima 5</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [29](../controllers/portal.py#L29) | `_pv_concesionario` | 1 | A | 2 | 1 |
| [32](../controllers/portal.py#L32) | `_pv_flash` | 1 | A | 2 | 3 |
| [35](../controllers/portal.py#L35) | `_pv_render` | 2 | A | 10 | 3 |
| [46](../controllers/portal.py#L46) | `_pv_get` | 2 | A | 6 | 3 |
| [54](../controllers/portal.py#L54) | `_pv_accion` | 3 | A | 8 | 4 |
| [65](../controllers/portal.py#L65) | `_prepare_home_portal_values` | 4 | A | 9 | 2 |
| [77](../controllers/portal.py#L77) | `portal_posventa_home` | 4 | A | 20 | 2 |
| [101](../controllers/portal.py#L101) | `portal_posventa_maquinas` | 5 | A | 25 | 5 |
| [128](../controllers/portal.py#L128) | `portal_posventa_maquina` | 4 | A | 14 | 3 |
| [145](../controllers/portal.py#L145) | `portal_posventa_solicitar_liberacion` | 1 | A | 5 | 4 |
| [153](../controllers/portal.py#L153) | `portal_posventa_trasladar` | 1 | A | 6 | 6 |
| [157](../controllers/portal.py#L157) | `portal_posventa_trasladar.iniciar` | 2 | A | 6 | 0 |
| [168](../controllers/portal.py#L168) | `portal_posventa_transferencia` | 3 | A | 12 | 4 |
| [183](../controllers/portal.py#L183) | `portal_posventa_ticket_nuevo` | 2 | A | 9 | 3 |
| [194](../controllers/portal.py#L194) | `portal_posventa_certificado_nuevo` | 2 | A | 9 | 3 |
| [207](../controllers/portal.py#L207) | `portal_posventa_certificados` | 2 | A | 17 | 6 |
| [228](../controllers/portal.py#L228) | `portal_posventa_tickets` | 4 | A | 21 | 5 |
| [251](../controllers/portal.py#L251) | `portal_posventa_ticket` | 2 | A | 17 | 3 |
| [271](../controllers/portal.py#L271) | `portal_posventa_ticket_enviar` | 1 | A | 4 | 3 |

</details>

<details><summary><code>models/pv_certificado.py</code> — 21 funciones, CCN máxima 15</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [83](../models/pv_certificado.py#L83) | `_get_param_dias` | 2 | A | 6 | 2 |
| [91](../models/pv_certificado.py#L91) | `_get_plazo_nominal_carga` | 5 | A | 5 | 3 |
| [98](../models/pv_certificado.py#L98) | `_get_vencimiento_reclamos` | 3 | A | 4 | 1 |
| [103](../models/pv_certificado.py#L103) | `_get_fecha_carga` | 2 | A | 2 | 1 |
| [108](../models/pv_certificado.py#L108) | `_compute_fechas` | 3 | A | 6 | 1 |
| [116](../models/pv_certificado.py#L116) | `_compute_dias_para_vencer` | 3 | A | 4 | 1 |
| [122](../models/pv_certificado.py#L122) | `_compute_ticket_count` | 2 | A | 3 | 1 |
| [127](../models/pv_certificado.py#L127) | `_compute_name` | 3 | A | 3 | 1 |
| [131](../models/pv_certificado.py#L131) | `_es_vigente_para_reclamos` | 4 | A | 4 | 1 |
| [137](../models/pv_certificado.py#L137) | `_otros_de_la_maquina` | 1 | A | 8 | 3 |
| [147](../models/pv_certificado.py#L147) | `_check_secuencia` | 15 | C | 19 | 1 |
| [169](../models/pv_certificado.py#L169) | `_check_fecha_no_futura` | 3 | A | 3 | 1 |
| [174](../models/pv_certificado.py#L174) | `_check_archivo` | 5 | A | 6 | 1 |
| [183](../models/pv_certificado.py#L183) | `create` | 11 | C | 21 | 2 |
| [206](../models/pv_certificado.py#L206) | `write` | 6 | B | 8 | 2 |
| [215](../models/pv_certificado.py#L215) | `_actualizar_estado_maquina` | 5 | A | 11 | 1 |
| [230](../models/pv_certificado.py#L230) | `_archive_expired_certificates` | 2 | A | 12 | 1 |
| [245](../models/pv_certificado.py#L245) | `_notify_upcoming_certificate_expiration` | 3 | A | 27 | 1 |
| [275](../models/pv_certificado.py#L275) | `_get_portal_values` | 9 | B | 27 | 1 |
| [305](../models/pv_certificado.py#L305) | `get_portal_list_data` | 7 | B | 18 | 4 |
| [325](../models/pv_certificado.py#L325) | `action_view_tickets` | 1 | A | 10 | 1 |

</details>

<details><summary><code>models/pv_concesionario.py</code> — 8 funciones, CCN máxima 2</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [35](../models/pv_concesionario.py#L35) | `_get_by_contact` | 2 | A | 6 | 2 |
| [47](../models/pv_concesionario.py#L47) | `_get_concesionario_for_user` | 2 | A | 2 | 2 |
| [50](../models/pv_concesionario.py#L50) | `_is_member` | 1 | A | 3 | 2 |
| [56](../models/pv_concesionario.py#L56) | `_compute_counts` | 2 | A | 6 | 1 |
| [63](../models/pv_concesionario.py#L63) | `_get_portal_resumen` | 1 | A | 13 | 1 |
| [78](../models/pv_concesionario.py#L78) | `action_gestionar_acceso_portal` | 1 | A | 4 | 1 |
| [84](../models/pv_concesionario.py#L84) | `action_view_maquinas` | 1 | A | 10 | 1 |
| [95](../models/pv_concesionario.py#L95) | `action_view_tickets` | 1 | A | 9 | 1 |

</details>

<details><summary><code>models/pv_dashboard.py</code> — 5 funciones, CCN máxima 3</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [24](../models/pv_dashboard.py#L24) | `_compute_counts` | 3 | A | 5 | 1 |
| [30](../models/pv_dashboard.py#L30) | `_compute_averages` | 2 | A | 4 | 1 |
| [35](../models/pv_dashboard.py#L35) | `action_view_tickets` | 1 | A | 10 | 1 |
| [47](../models/pv_dashboard.py#L47) | `action_view_metrics` | 1 | A | 8 | 1 |
| [57](../models/pv_dashboard.py#L57) | `action_open_dashboard` | 1 | A | 9 | 1 |

</details>

<details><summary><code>models/pv_maquina.py</code> — 33 funciones, CCN máxima 21</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [85](../models/pv_maquina.py#L85) | `_compute_name` | 3 | A | 3 | 1 |
| [90](../models/pv_maquina.py#L90) | `_compute_tiene_certificados` | 2 | A | 9 | 1 |
| [101](../models/pv_maquina.py#L101) | `_compute_certificado_count` | 2 | A | 3 | 1 |
| [106](../models/pv_maquina.py#L106) | `_compute_ticket_count` | 2 | A | 3 | 1 |
| [110](../models/pv_maquina.py#L110) | `_compute_es_concesionario_destino` | 3 | A | 4 | 1 |
| [115](../models/pv_maquina.py#L115) | `_compute_is_pv_admin` | 1 | A | 2 | 1 |
| [118](../models/pv_maquina.py#L118) | `write` | 4 | A | 6 | 2 |
| [126](../models/pv_maquina.py#L126) | `_is_pv_admin_user` | 2 | A | 2 | 1 |
| [129](../models/pv_maquina.py#L129) | `_check_pv_admin` | 2 | A | 3 | 1 |
| [133](../models/pv_maquina.py#L133) | `_check_es_del_concesionario` | 4 | A | 5 | 3 |
| [141](../models/pv_maquina.py#L141) | `_get_certificados_vigentes` | 2 | A | 2 | 1 |
| [144](../models/pv_maquina.py#L144) | `_get_proximo_certificado_info` | 8 | B | 23 | 1 |
| [169](../models/pv_maquina.py#L169) | `get_portal_detail_data` | 21 | D | 39 | 1 |
| [210](../models/pv_maquina.py#L210) | `action_view_certificados` | 1 | A | 10 | 1 |
| [221](../models/pv_maquina.py#L221) | `action_view_tickets` | 1 | A | 10 | 1 |
| [233](../models/pv_maquina.py#L233) | `action_solicitar_liberacion` | 5 | A | 26 | 2 |
| [262](../models/pv_maquina.py#L262) | `action_aprobar_liberacion` | 2 | A | 6 | 1 |
| [269](../models/pv_maquina.py#L269) | `action_rechazar_liberacion` | 2 | A | 7 | 1 |
| [277](../models/pv_maquina.py#L277) | `action_liberar_maquina` | 4 | A | 8 | 2 |
| [287](../models/pv_maquina.py#L287) | `action_abrir_wizard_liberacion` | 2 | A | 11 | 1 |
| [299](../models/pv_maquina.py#L299) | `_check_liberacion_solicitada` | 2 | A | 3 | 1 |
| [303](../models/pv_maquina.py#L303) | `_limpiar_solicitud_liberacion` | 1 | A | 7 | 1 |
| [311](../models/pv_maquina.py#L311) | `_liberar` | 2 | A | 13 | 2 |
| [328](../models/pv_maquina.py#L328) | `get_transfer_catalog_data` | 1 | A | 5 | 1 |
| [335](../models/pv_maquina.py#L335) | `action_abrir_wizard_transferencia` | 1 | A | 12 | 1 |
| [348](../models/pv_maquina.py#L348) | `action_iniciar_transferencia_portal` | 3 | A | 7 | 4 |
| [356](../models/pv_maquina.py#L356) | `_iniciar_transferencia` | 9 | B | 25 | 4 |
| [384](../models/pv_maquina.py#L384) | `action_aceptar_transferencia` | 1 | A | 20 | 1 |
| [406](../models/pv_maquina.py#L406) | `action_rechazar_transferencia` | 1 | A | 8 | 1 |
| [415](../models/pv_maquina.py#L415) | `action_cancelar_transferencia` | 2 | A | 10 | 1 |
| [427](../models/pv_maquina.py#L427) | `_check_transferencia_pendiente` | 2 | A | 4 | 2 |
| [432](../models/pv_maquina.py#L432) | `_revertir_transferencia` | 3 | A | 6 | 1 |
| [440](../models/pv_maquina.py#L440) | `_limpiar_transferencia` | 1 | A | 2 | 1 |

</details>

<details><summary><code>models/pv_ticket.py</code> — 51 funciones, CCN máxima 15</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [56](../models/pv_ticket.py#L56) | `_campos_cargados` | 3 | A | 3 | 2 |
| [58](../models/pv_ticket.py#L58) | `_campos_cargados.cargado` | 7 | B | 7 | 1 |
| [68](../models/pv_ticket.py#L68) | `_horas_entre` | 3 | A | 2 | 2 |
| [203](../models/pv_ticket.py#L203) | `_compute_access_url` | 2 | A | 4 | 1 |
| [208](../models/pv_ticket.py#L208) | `_compute_storage_mode` | 1 | A | 2 | 1 |
| [212](../models/pv_ticket.py#L212) | `_group_expand_estados` | 2 | A | 2 | 3 |
| [217](../models/pv_ticket.py#L217) | `_compute_multimedia_count` | 2 | A | 3 | 1 |
| [222](../models/pv_ticket.py#L222) | `_compute_medida_count` | 2 | A | 4 | 1 |
| [228](../models/pv_ticket.py#L228) | `_compute_kpis` | 2 | A | 5 | 1 |
| [235](../models/pv_ticket.py#L235) | `_get_kpis_promedio` | 1 | A | 7 | 2 |
| [237](../models/pv_ticket.py#L237) | `_get_kpis_promedio.promedio` | 2 | A | 3 | 2 |
| [247](../models/pv_ticket.py#L247) | `_compute_tipo_ticket` | 3 | A | 3 | 1 |
| [253](../models/pv_ticket.py#L253) | `_compute_certificado_id` | 7 | B | 7 | 1 |
| [264](../models/pv_ticket.py#L264) | `_check_certificado_de_la_maquina` | 4 | A | 7 | 1 |
| [273](../models/pv_ticket.py#L273) | `_check_rechazo_tags_aplica_a` | 6 | B | 6 | 1 |
| [281](../models/pv_ticket.py#L281) | `_check_clasificacion` | 15 | C | 18 | 1 |
| [301](../models/pv_ticket.py#L301) | `_check_campos_extra_obligatorios` | 4 | A | 4 | 1 |
| [307](../models/pv_ticket.py#L307) | `_check_maquina_admite_tickets` | 4 | A | 6 | 1 |
| [316](../models/pv_ticket.py#L316) | `_check_responsable_coherence` | 4 | A | 4 | 1 |
| [321](../models/pv_ticket.py#L321) | `_check_certificado_vigente` | 3 | A | 4 | 1 |
| [329](../models/pv_ticket.py#L329) | `create` | 9 | B | 13 | 2 |
| [343](../models/pv_ticket.py#L343) | `write` | 2 | A | 4 | 2 |
| [348](../models/pv_ticket.py#L348) | `_check_write_permitido` | 12 | C | 15 | 2 |
| [366](../models/pv_ticket.py#L366) | `_onchange_sistema_id` | 1 | A | 3 | 1 |
| [371](../models/pv_ticket.py#L371) | `_onchange_problema_id` | 2 | A | 3 | 1 |
| [376](../models/pv_ticket.py#L376) | `_onchange_problema_no_listado` | 2 | A | 3 | 1 |
| [381](../models/pv_ticket.py#L381) | `_onchange_subsistema_id` | 2 | A | 5 | 1 |
| [389](../models/pv_ticket.py#L389) | `_check_pv_group` | 3 | A | 3 | 3 |
| [393](../models/pv_ticket.py#L393) | `_check_staff` | 1 | A | 2 | 1 |
| [396](../models/pv_ticket.py#L396) | `_check_admin` | 1 | A | 2 | 1 |
| [399](../models/pv_ticket.py#L399) | `_check_estado` | 3 | A | 3 | 3 |
| [404](../models/pv_ticket.py#L404) | `_write_estado` | 1 | A | 2 | 2 |
| [408](../models/pv_ticket.py#L408) | `_tiene_multimedia` | 3 | A | 4 | 1 |
| [413](../models/pv_ticket.py#L413) | `action_enviar_ticket` | 7 | B | 14 | 1 |
| [429](../models/pv_ticket.py#L429) | `action_tomar_ticket` | 3 | A | 10 | 1 |
| [441](../models/pv_ticket.py#L441) | `action_aceptar_ticket` | 3 | A | 9 | 1 |
| [452](../models/pv_ticket.py#L452) | `action_rechazar_ticket` | 3 | A | 25 | 1 |
| [480](../models/pv_ticket.py#L480) | `action_cerrar_ticket` | 3 | A | 16 | 1 |
| [498](../models/pv_ticket.py#L498) | `_cerrar` | 1 | A | 4 | 2 |
| [505](../models/pv_ticket.py#L505) | `_retroceder` | 3 | A | 6 | 4 |
| [512](../models/pv_ticket.py#L512) | `action_back_to_borrador` | 1 | A | 3 | 1 |
| [516](../models/pv_ticket.py#L516) | `action_back_to_abierto` | 1 | A | 4 | 1 |
| [521](../models/pv_ticket.py#L521) | `action_back_to_en_proceso` | 1 | A | 4 | 1 |
| [526](../models/pv_ticket.py#L526) | `action_back_to_aceptado` | 1 | A | 4 | 1 |
| [532](../models/pv_ticket.py#L532) | `_send_notification_to_staff` | 2 | A | 6 | 1 |
| [539](../models/pv_ticket.py#L539) | `_message_get_default_recipients` | 3 | A | 6 | 3 |
| [547](../models/pv_ticket.py#L547) | `portal_adjuntar_archivo` | 5 | A | 14 | 4 |
| [564](../models/pv_ticket.py#L564) | `get_wizard_catalog_data` | 8 | B | 20 | 3 |
| [587](../models/pv_ticket.py#L587) | `action_view_medidas` | 1 | A | 10 | 1 |
| [598](../models/pv_ticket.py#L598) | `action_abrir_carpeta_drive` | 9 | B | 12 | 1 |
| [612](../models/pv_ticket.py#L612) | `action_adjuntar_multimedia` | 1 | A | 10 | 1 |

</details>

<details><summary><code>models/pv_ticket_medida.py</code> — 3 funciones, CCN máxima 3</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [93](../models/pv_ticket_medida.py#L93) | `action_completar` | 2 | A | 6 | 1 |
| [100](../models/pv_ticket_medida.py#L100) | `action_en_curso` | 2 | A | 3 | 1 |
| [105](../models/pv_ticket_medida.py#L105) | `_cron_check_vencimientos` | 3 | A | 10 | 1 |

</details>

<details><summary><code>models/pv_ticket_multimedia.py</code> — 21 funciones, CCN máxima 8</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [48](../models/pv_ticket_multimedia.py#L48) | `get_staging_root` | 1 | A | 4 | 0 |
| [76](../models/pv_ticket_multimedia.py#L76) | `_compute_file_size_display` | 4 | A | 6 | 1 |
| [84](../models/pv_ticket_multimedia.py#L84) | `_compute_is_video` | 5 | A | 3 | 1 |
| [90](../models/pv_ticket_multimedia.py#L90) | `_get_param` | 1 | A | 2 | 3 |
| [94](../models/pv_ticket_multimedia.py#L94) | `_get_storage_mode` | 2 | A | 3 | 1 |
| [99](../models/pv_ticket_multimedia.py#L99) | `get_upload_config` | 1 | A | 7 | 1 |
| [109](../models/pv_ticket_multimedia.py#L109) | `_get_chunk_size_bytes` | 1 | A | 2 | 1 |
| [113](../models/pv_ticket_multimedia.py#L113) | `_get_max_upload_bytes` | 2 | A | 5 | 1 |
| [120](../models/pv_ticket_multimedia.py#L120) | `action_abrir_drive` | 3 | A | 6 | 1 |
| [127](../models/pv_ticket_multimedia.py#L127) | `action_reintentar_sync` | 5 | A | 11 | 1 |
| [141](../models/pv_ticket_multimedia.py#L141) | `_encolar_sync` | 1 | A | 8 | 1 |
| [152](../models/pv_ticket_multimedia.py#L152) | `_cron_sync_pending` | 6 | B | 29 | 1 |
| [185](../models/pv_ticket_multimedia.py#L185) | `_carpeta_drive` | 3 | A | 4 | 1 |
| [191](../models/pv_ticket_multimedia.py#L191) | `_staging_existe` | 2 | A | 2 | 1 |
| [194](../models/pv_ticket_multimedia.py#L194) | `_esta_en_drive` | 1 | A | 2 | 2 |
| [198](../models/pv_ticket_multimedia.py#L198) | `_get_mimetype` | 7 | B | 5 | 1 |
| [204](../models/pv_ticket_multimedia.py#L204) | `_sync_to_drive` | 6 | B | 29 | 2 |
| [240](../models/pv_ticket_multimedia.py#L240) | `_publicar_en_ticket` | 8 | B | 23 | 3 |
| [266](../models/pv_ticket_multimedia.py#L266) | `_borrar_staging` | 5 | A | 10 | 1 |
| [277](../models/pv_ticket_multimedia.py#L277) | `_registrar_error_sync` | 6 | B | 18 | 2 |
| [298](../models/pv_ticket_multimedia.py#L298) | `_cleanup_staging` | 6 | B | 8 | 1 |

</details>

<details><summary><code>models/res_config_settings.py</code> — 4 funciones, CCN máxima 4</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [73](../models/res_config_settings.py#L73) | `_compute_pv_drive_cuenta` | 2 | A | 3 | 1 |
| [77](../models/res_config_settings.py#L77) | `_compute_pv_drive_en_espera` | 1 | A | 3 | 1 |
| [81](../models/res_config_settings.py#L81) | `set_values` | 4 | A | 7 | 1 |
| [89](../models/res_config_settings.py#L89) | `action_pv_probar_drive` | 2 | A | 14 | 1 |

</details>

<details><summary><code>static/src/backend/multimedia_chunk_uploader.js</code> — 8 funciones, CCN máxima 3</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [14](../static/src/backend/multimedia_chunk_uploader.js#L14) | `setup` | 1 | A | 15 | 0 |
| [27](../static/src/backend/multimedia_chunk_uploader.js#L27) | `(anónima)` | 1 | A | 3 | 0 |
| [32](../static/src/backend/multimedia_chunk_uploader.js#L32) | `get ticketId` | 1 | A | 3 | 0 |
| [36](../static/src/backend/multimedia_chunk_uploader.js#L36) | `triggerFileSelect` | 1 | A | 3 | 0 |
| [40](../static/src/backend/multimedia_chunk_uploader.js#L40) | `onFileSelected` | 3 | A | 17 | 1 |
| [58](../static/src/backend/multimedia_chunk_uploader.js#L58) | `startUpload` | 2 | A | 21 | 0 |
| [68](../static/src/backend/multimedia_chunk_uploader.js#L68) | `onProgress` | 1 | A | 1 | 2 |
| [80](../static/src/backend/multimedia_chunk_uploader.js#L80) | `onFinish` | 1 | A | 4 | 0 |

</details>

<details><summary><code>static/src/frontend/portal_posventa.js</code> — 19 funciones, CCN máxima 8</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [14](../static/src/frontend/portal_posventa.js#L14) | `useMaquinaDetail` | 1 | A | 6 | 1 |
| [17](../static/src/frontend/portal_posventa.js#L17) | `(anónima)` | 4 | A | 7 | 0 |
| [32](../static/src/frontend/portal_posventa.js#L32) | `setup` | 1 | A | 3 | 0 |
| [36](../static/src/frontend/portal_posventa.js#L36) | `get maquinaUrl` | 1 | A | 3 | 0 |
| [40](../static/src/frontend/portal_posventa.js#L40) | `onClose` | 1 | A | 3 | 0 |
| [44](../static/src/frontend/portal_posventa.js#L44) | `onSuccess` | 1 | A | 3 | 1 |
| [54](../static/src/frontend/portal_posventa.js#L54) | `setup` | 1 | A | 3 | 0 |
| [58](../static/src/frontend/portal_posventa.js#L58) | `get maquinaUrl` | 1 | A | 3 | 0 |
| [62](../static/src/frontend/portal_posventa.js#L62) | `onClose` | 1 | A | 3 | 0 |
| [66](../static/src/frontend/portal_posventa.js#L66) | `onSuccess` | 1 | A | 3 | 0 |
| [76](../static/src/frontend/portal_posventa.js#L76) | `setup` | 1 | A | 6 | 0 |
| [80](../static/src/frontend/portal_posventa.js#L80) | `(anónima)` | 1 | A | 3 | 0 |
| [85](../static/src/frontend/portal_posventa.js#L85) | `onFilesChange` | 4 | A | 12 | 1 |
| [98](../static/src/frontend/portal_posventa.js#L98) | `removeFile` | 1 | A | 3 | 1 |
| [102](../static/src/frontend/portal_posventa.js#L102) | `upload` | 8 | B | 30 | 0 |
| [118](../static/src/frontend/portal_posventa.js#L118) | `onProgress` | 1 | A | 3 | 2 |
| [147](../static/src/frontend/portal_posventa.js#L147) | `onClick` | 1 | A | 8 | 0 |
| [151](../static/src/frontend/portal_posventa.js#L151) | `confirm` | 1 | A | 1 | 0 |
| [152](../static/src/frontend/portal_posventa.js#L152) | `cancel` | 1 | A | 1 | 0 |

</details>

<details><summary><code>static/src/frontend/wizards/certificado_wizard.js</code> — 21 funciones, CCN máxima 12</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [16](../static/src/frontend/wizards/certificado_wizard.js#L16) | `setup` | 9 | B | 24 | 0 |
| [24](../static/src/frontend/wizards/certificado_wizard.js#L24) | `(anónima)` | 3 | A | 1 | 1 |
| [45](../static/src/frontend/wizards/certificado_wizard.js#L45) | `get fechaMax` | 1 | A | 3 | 0 |
| [49](../static/src/frontend/wizards/certificado_wizard.js#L49) | `get fechaMin` | 2 | A | 3 | 0 |
| [53](../static/src/frontend/wizards/certificado_wizard.js#L53) | `get showFeuWarning` | 4 | A | 8 | 0 |
| [58](../static/src/frontend/wizards/certificado_wizard.js#L58) | `(anónima)` | 3 | A | 1 | 1 |
| [63](../static/src/frontend/wizards/certificado_wizard.js#L63) | `get stepLabels` | 1 | A | 7 | 0 |
| [72](../static/src/frontend/wizards/certificado_wizard.js#L72) | `get certificateTypes` | 11 | C | 43 | 0 |
| [75](../static/src/frontend/wizards/certificado_wizard.js#L75) | `(anónima)` | 2 | A | 1 | 1 |
| [76](../static/src/frontend/wizards/certificado_wizard.js#L76) | `(anónima)` | 1 | A | 1 | 1 |
| [78](../static/src/frontend/wizards/certificado_wizard.js#L78) | `(anónima)` | 3 | A | 1 | 1 |
| [93](../static/src/frontend/wizards/certificado_wizard.js#L93) | `_t` | 2 | A | 5 | 0 |
| [105](../static/src/frontend/wizards/certificado_wizard.js#L105) | `_t` | 3 | A | 5 | 0 |
| [125](../static/src/frontend/wizards/certificado_wizard.js#L125) | `onFileChange` | 3 | A | 17 | 1 |
| [131](../static/src/frontend/wizards/certificado_wizard.js#L131) | `(anónima)` | 1 | A | 1 | 1 |
| [142](../static/src/frontend/wizards/certificado_wizard.js#L142) | `reader.onload` | 2 | A | 6 | 0 |
| [152](../static/src/frontend/wizards/certificado_wizard.js#L152) | `validateStep` | 12 | C | 34 | 1 |
| [158](../static/src/frontend/wizards/certificado_wizard.js#L158) | `(anónima)` | 1 | A | 1 | 1 |
| [187](../static/src/frontend/wizards/certificado_wizard.js#L187) | `nextStep` | 2 | A | 5 | 0 |
| [193](../static/src/frontend/wizards/certificado_wizard.js#L193) | `prevStep` | 2 | A | 5 | 0 |
| [199](../static/src/frontend/wizards/certificado_wizard.js#L199) | `submitCertificado` | 6 | B | 23 | 0 |

</details>

<details><summary><code>static/src/frontend/wizards/ticket_wizard.js</code> — 46 funciones, CCN máxima 17</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [14](../static/src/frontend/wizards/ticket_wizard.js#L14) | `certificadosParaReclamo` | 3 | A | 6 | 2 |
| [17](../static/src/frontend/wizards/ticket_wizard.js#L17) | `(anónima)` | 3 | A | 1 | 1 |
| [21](../static/src/frontend/wizards/ticket_wizard.js#L21) | `nombreDe` | 2 | A | 3 | 2 |
| [22](../static/src/frontend/wizards/ticket_wizard.js#L22) | `(anónima)` | 1 | A | 1 | 1 |
| [25](../static/src/frontend/wizards/ticket_wizard.js#L25) | `mensajeDeError` | 3 | A | 3 | 2 |
| [47](../static/src/frontend/wizards/ticket_wizard.js#L47) | `setup` | 3 | A | 40 | 0 |
| [91](../static/src/frontend/wizards/ticket_wizard.js#L91) | `(anónima)` | 1 | A | 1 | 0 |
| [95](../static/src/frontend/wizards/ticket_wizard.js#L95) | `loadCatalogs` | 6 | B | 26 | 0 |
| [122](../static/src/frontend/wizards/ticket_wizard.js#L122) | `onDesvioTipoChange` | 2 | A | 3 | 1 |
| [126](../static/src/frontend/wizards/ticket_wizard.js#L126) | `onSistemaChange` | 2 | A | 10 | 1 |
| [137](../static/src/frontend/wizards/ticket_wizard.js#L137) | `onSubsistemaChange` | 3 | A | 13 | 1 |
| [139](../static/src/frontend/wizards/ticket_wizard.js#L139) | `(anónima)` | 1 | A | 1 | 1 |
| [147](../static/src/frontend/wizards/ticket_wizard.js#L147) | `(anónima)` | 2 | A | 1 | 1 |
| [151](../static/src/frontend/wizards/ticket_wizard.js#L151) | `setCampoValue` | 1 | A | 3 | 2 |
| [156](../static/src/frontend/wizards/ticket_wizard.js#L156) | `onFilesChange` | 5 | A | 20 | 1 |
| [178](../static/src/frontend/wizards/ticket_wizard.js#L178) | `onHeavyFilesChange` | 3 | A | 6 | 1 |
| [185](../static/src/frontend/wizards/ticket_wizard.js#L185) | `agregarArchivoPesado` | 3 | A | 19 | 1 |
| [205](../static/src/frontend/wizards/ticket_wizard.js#L205) | `removeAttachment` | 1 | A | 3 | 1 |
| [209](../static/src/frontend/wizards/ticket_wizard.js#L209) | `removeHeavyFile` | 1 | A | 3 | 1 |
| [214](../static/src/frontend/wizards/ticket_wizard.js#L214) | `get steps` | 3 | A | 11 | 0 |
| [223](../static/src/frontend/wizards/ticket_wizard.js#L223) | `(anónima)` | 1 | A | 1 | 2 |
| [226](../static/src/frontend/wizards/ticket_wizard.js#L226) | `get currentStepKey` | 2 | A | 3 | 0 |
| [231](../static/src/frontend/wizards/ticket_wizard.js#L231) | `stepError` | 17 | C | 33 | 1 |
| [251](../static/src/frontend/wizards/ticket_wizard.js#L251) | `(anónima)` | 2 | A | 1 | 1 |
| [252](../static/src/frontend/wizards/ticket_wizard.js#L252) | `_t` | 1 | A | 1 | 1 |
| [265](../static/src/frontend/wizards/ticket_wizard.js#L265) | `nextStep` | 3 | A | 8 | 0 |
| [274](../static/src/frontend/wizards/ticket_wizard.js#L274) | `prevStep` | 2 | A | 5 | 0 |
| [281](../static/src/frontend/wizards/ticket_wizard.js#L281) | `get borradoresExistentes` | 2 | A | 3 | 0 |
| [282](../static/src/frontend/wizards/ticket_wizard.js#L282) | `(anónima)` | 1 | A | 1 | 1 |
| [285](../static/src/frontend/wizards/ticket_wizard.js#L285) | `get availableCertificates` | 1 | A | 3 | 0 |
| [289](../static/src/frontend/wizards/ticket_wizard.js#L289) | `get selectedCertificado` | 2 | A | 3 | 0 |
| [290](../static/src/frontend/wizards/ticket_wizard.js#L290) | `(anónima)` | 1 | A | 1 | 1 |
| [293](../static/src/frontend/wizards/ticket_wizard.js#L293) | `get selectedSistemaName` | 1 | A | 3 | 0 |
| [297](../static/src/frontend/wizards/ticket_wizard.js#L297) | `get selectedSubsistemaName` | 1 | A | 3 | 0 |
| [301](../static/src/frontend/wizards/ticket_wizard.js#L301) | `get selectedProblemaName` | 2 | A | 6 | 0 |
| [308](../static/src/frontend/wizards/ticket_wizard.js#L308) | `get desvioTipoLabel` | 1 | A | 3 | 0 |
| [313](../static/src/frontend/wizards/ticket_wizard.js#L313) | `ticketVals` | 4 | A | 25 | 0 |
| [335](../static/src/frontend/wizards/ticket_wizard.js#L335) | `(anónima)` | 2 | A | 5 | 1 |
| [343](../static/src/frontend/wizards/ticket_wizard.js#L343) | `subirArchivo` | 2 | A | 15 | 2 |
| [355](../static/src/frontend/wizards/ticket_wizard.js#L355) | `onProgress` | 1 | A | 6 | 2 |
| [365](../static/src/frontend/wizards/ticket_wizard.js#L365) | `subirArchivosPendientes` | 3 | A | 26 | 1 |
| [367](../static/src/frontend/wizards/ticket_wizard.js#L367) | `(anónima)` | 2 | A | 1 | 1 |
| [392](../static/src/frontend/wizards/ticket_wizard.js#L392) | `submitTicket` | 7 | B | 26 | 1 |
| [421](../static/src/frontend/wizards/ticket_wizard.js#L421) | `retryUpload` | 1 | A | 3 | 0 |
| [425](../static/src/frontend/wizards/ticket_wizard.js#L425) | `proceedWithoutFailedFile` | 1 | A | 4 | 0 |
| [430](../static/src/frontend/wizards/ticket_wizard.js#L430) | `keepInDraft` | 1 | A | 7 | 0 |

</details>

<details><summary><code>static/src/shared/chunk_upload.js</code> — 9 funciones, CCN máxima 16</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [4](../static/src/shared/chunk_upload.js#L4) | `formatFileSize` | 2 | A | 8 | 1 |
| [13](../static/src/shared/chunk_upload.js#L13) | `newUploadUuid` | 1 | A | 3 | 0 |
| [17](../static/src/shared/chunk_upload.js#L17) | `fileToBase64` | 1 | A | 3 | 1 |
| [18](../static/src/shared/chunk_upload.js#L18) | `(anónima)` | 1 | A | 6 | 2 |
| [20](../static/src/shared/chunk_upload.js#L20) | `reader.onload` | 2 | A | 1 | 0 |
| [21](../static/src/shared/chunk_upload.js#L21) | `reader.onerror` | 1 | A | 1 | 1 |
| [27](../static/src/shared/chunk_upload.js#L27) | `adjuntarArchivo` | 4 | A | 8 | 4 |
| [40](../static/src/shared/chunk_upload.js#L40) | `uploadFileInChunks` | 16 | C | 46 | 1 |
| [80](../static/src/shared/chunk_upload.js#L80) | `(anónima)` | 1 | A | 1 | 1 |

</details>

<details><summary><code>static/tests/tours/portal_posventa_tour.js</code> — 11 funciones, CCN máxima 1</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [12](../static/tests/tours/portal_posventa_tour.js#L12) | `steps` | 1 | A | 41 | 0 |
| [56](../static/tests/tours/portal_posventa_tour.js#L56) | `elegirArchivo` | 1 | A | 6 | 4 |
| [65](../static/tests/tours/portal_posventa_tour.js#L65) | `steps` | 1 | A | 35 | 0 |
| [78](../static/tests/tours/portal_posventa_tour.js#L78) | `run` | 1 | A | 3 | 0 |
| [106](../static/tests/tours/portal_posventa_tour.js#L106) | `elegirOpcion` | 1 | A | 7 | 2 |
| [110](../static/tests/tours/portal_posventa_tour.js#L110) | `run` | 1 | A | 4 | 0 |
| [111](../static/tests/tours/portal_posventa_tour.js#L111) | `(anónima)` | 1 | A | 1 | 1 |
| [119](../static/tests/tours/portal_posventa_tour.js#L119) | `steps` | 1 | A | 56 | 0 |
| [153](../static/tests/tours/portal_posventa_tour.js#L153) | `run` | 1 | A | 3 | 0 |
| [180](../static/tests/tours/portal_posventa_tour.js#L180) | `steps` | 1 | A | 17 | 0 |
| [184](../static/tests/tours/portal_posventa_tour.js#L184) | `run` | 1 | A | 3 | 0 |

</details>

<details><summary><code>tests/common.py</code> — 3 funciones, CCN máxima 2</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [11](../tests/common.py#L11) | `setUpClass` | 1 | A | 41 | 1 |
| [68](../tests/common.py#L68) | `_crear_usuario` | 2 | A | 8 | 4 |
| [78](../tests/common.py#L78) | `_crear_usuario_concesionario` | 1 | A | 3 | 3 |

</details>

<details><summary><code>tests/test_documentacion.py</code> — 1 funciones, CCN máxima 1</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [10](../tests/test_documentacion.py#L10) | `test_referencia_actualizada` | 1 | A | 4 | 1 |

</details>

<details><summary><code>tests/test_drive.py</code> — 6 funciones, CCN máxima 1</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [13](../tests/test_drive.py#L13) | `_resultado` | 1 | A | 2 | 3 |
| [19](../tests/test_drive.py#L19) | `setUp` | 1 | A | 6 | 1 |
| [26](../tests/test_drive.py#L26) | `test_01_config_en_memoria_por_entorno` | 1 | A | 7 | 1 |
| [35](../tests/test_drive.py#L35) | `test_02_errores_legibles` | 1 | A | 12 | 1 |
| [49](../tests/test_drive.py#L49) | `test_03_enlace_interno_si_la_unidad_no_permite_publicos` | 1 | A | 4 | 1 |
| [54](../tests/test_drive.py#L54) | `test_04_ajustes` | 1 | A | 11 | 1 |

</details>

<details><summary><code>tests/test_import_maquinas.py</code> — 5 funciones, CCN máxima 2</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [19](../tests/test_import_maquinas.py#L19) | `_wizard` | 2 | A | 10 | 3 |
| [30](../tests/test_import_maquinas.py#L30) | `test_01_vista_previa_e_importacion` | 2 | A | 21 | 1 |
| [53](../tests/test_import_maquinas.py#L53) | `test_02_archivo_invalido` | 1 | A | 8 | 1 |
| [63](../tests/test_import_maquinas.py#L63) | `test_03_cliente_provincias_y_filas_vacias` | 2 | A | 26 | 1 |
| [92](../tests/test_import_maquinas.py#L92) | `test_04_solo_excel` | 2 | A | 7 | 1 |

</details>

<details><summary><code>tests/test_maquina_certificados.py</code> — 10 funciones, CCN máxima 3</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [10](../tests/test_maquina_certificados.py#L10) | `test_01_maquina_lifecycle_and_certificates` | 1 | A | 47 | 1 |
| [66](../tests/test_maquina_certificados.py#L66) | `test_02_certificate_sequence_constraints` | 1 | A | 29 | 1 |
| [103](../tests/test_maquina_certificados.py#L103) | `test_03_action_liberar_maquina_and_reupload` | 1 | A | 45 | 1 |
| [156](../tests/test_maquina_certificados.py#L156) | `test_04_cpm_never_expires_and_protects_other_certificates_from_expiration` | 1 | A | 51 | 1 |
| [218](../tests/test_maquina_certificados.py#L218) | `test_05_cannot_create_ticket_on_expired_certificate_and_fru_not_renewable` | 1 | A | 30 | 1 |
| [256](../tests/test_maquina_certificados.py#L256) | `test_06_feu_expiration_and_renewal_workflow` | 1 | A | 55 | 1 |
| [326](../tests/test_maquina_certificados.py#L326) | `test_07_portal_proximo_certificado_countdown_and_retraso_carga` | 3 | A | 54 | 1 |
| [395](../tests/test_maquina_certificados.py#L395) | `test_08_upload_certificate_with_string_dates` | 1 | A | 18 | 1 |
| [416](../tests/test_maquina_certificados.py#L416) | `test_09_certificate_order_hardening` | 1 | A | 56 | 1 |
| [489](../tests/test_maquina_certificados.py#L489) | `test_10_cpm_rejected_when_feu_vencido` | 1 | A | 57 | 1 |

</details>

<details><summary><code>tests/test_multimedia_upload.py</code> — 13 funciones, CCN máxima 3</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [19](../tests/test_multimedia_upload.py#L19) | `setUp` | 1 | A | 19 | 1 |
| [39](../tests/test_multimedia_upload.py#L39) | `test_01_multimedia_model_and_computes` | 1 | A | 28 | 1 |
| [76](../tests/test_multimedia_upload.py#L76) | `test_02_actions_and_links` | 1 | A | 20 | 1 |
| [103](../tests/test_multimedia_upload.py#L103) | `_request_falso` | 1 | A | 6 | 1 |
| [105](../tests/test_multimedia_upload.py#L105) | `_request_falso.make_json_response` | 1 | A | 4 | 2 |
| [114](../tests/test_multimedia_upload.py#L114) | `_drive_falso` | 2 | A | 6 | 1 |
| [122](../tests/test_multimedia_upload.py#L122) | `test_03_sync_a_drive` | 1 | A | 25 | 1 |
| [152](../tests/test_multimedia_upload.py#L152) | `test_04_chunked_streaming_controller_assembly` | 1 | A | 50 | 1 |
| [216](../tests/test_multimedia_upload.py#L216) | `test_05_backend_multimedia_wizard_and_retry` | 1 | A | 45 | 1 |
| [275](../tests/test_multimedia_upload.py#L275) | `test_06_error_sync_con_backoff_y_aviso_unico` | 3 | A | 20 | 1 |
| [297](../tests/test_multimedia_upload.py#L297) | `test_07_controller_rechaza_archivo_excedido` | 1 | A | 9 | 1 |
| [308](../tests/test_multimedia_upload.py#L308) | `test_08_cron_espera_drive_sin_consumir_reintentos` | 1 | A | 17 | 1 |
| [329](../tests/test_multimedia_upload.py#L329) | `test_09_subida_no_depende_de_drive` | 1 | A | 15 | 1 |

</details>

<details><summary><code>tests/test_portal.py</code> — 11 funciones, CCN máxima 2</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [12](../tests/test_portal.py#L12) | `setUpClass` | 1 | A | 24 | 1 |
| [37](../tests/test_portal.py#L37) | `_post` | 1 | A | 2 | 3 |
| [40](../tests/test_portal.py#L40) | `test_01_paginas_y_aislamiento` | 1 | A | 25 | 1 |
| [70](../tests/test_portal.py#L70) | `test_02_acciones_via_formularios` | 1 | A | 10 | 1 |
| [84](../tests/test_portal.py#L84) | `test_03_no_opera_registros_ajenos` | 1 | A | 11 | 1 |
| [96](../tests/test_portal.py#L96) | `test_04_usuario_sin_concesionario` | 1 | A | 3 | 1 |
| [100](../tests/test_portal.py#L100) | `test_05_tour_nuevo_ticket` | 1 | A | 7 | 1 |
| [109](../tests/test_portal.py#L109) | `test_05b_tour_ticket_post_pm` | 2 | A | 22 | 1 |
| [134](../tests/test_portal.py#L134) | `test_06_tour_cargar_certificado` | 1 | A | 9 | 1 |
| [144](../tests/test_portal.py#L144) | `test_07_tour_adjuntar_foto` | 1 | A | 6 | 1 |
| [151](../tests/test_portal.py#L151) | `test_08_mails_al_concesionario_linkean_al_portal` | 1 | A | 7 | 1 |

</details>

<details><summary><code>tests/test_security_access.py</code> — 9 funciones, CCN máxima 2</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [9](../tests/test_security_access.py#L9) | `setUp` | 1 | A | 30 | 1 |
| [43](../tests/test_security_access.py#L43) | `test_01_concesionario_isolation` | 1 | A | 7 | 1 |
| [53](../tests/test_security_access.py#L53) | `test_02_staff_access` | 1 | A | 13 | 1 |
| [77](../tests/test_security_access.py#L77) | `test_03_admin_unrestricted_access` | 1 | A | 7 | 1 |
| [87](../tests/test_security_access.py#L87) | `test_04_menu_visibility_restrictions` | 2 | A | 10 | 1 |
| [100](../tests/test_security_access.py#L100) | `test_05_portal_certificados_view_and_isolation` | 2 | A | 6 | 1 |
| [110](../tests/test_security_access.py#L110) | `test_06_concesionario_contact_user_access` | 1 | A | 22 | 1 |
| [144](../tests/test_security_access.py#L144) | `test_07_alta_por_asistente_de_portal` | 1 | A | 16 | 1 |
| [165](../tests/test_security_access.py#L165) | `test_08_correo_ya_usado_dice_por_quien` | 2 | A | 21 | 1 |

</details>

<details><summary><code>tests/test_security_hardening.py</code> — 18 funciones, CCN máxima 2</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [13](../tests/test_security_hardening.py#L13) | `setUp` | 1 | A | 13 | 1 |
| [27](../tests/test_security_hardening.py#L27) | `_ticket_a` | 1 | A | 9 | 2 |
| [38](../tests/test_security_hardening.py#L38) | `test_01_otro_concesionario_no_opera_maquina_ajena` | 1 | A | 16 | 1 |
| [55](../tests/test_security_hardening.py#L55) | `test_02_solo_admin_libera` | 1 | A | 18 | 1 |
| [78](../tests/test_security_hardening.py#L78) | `test_03_transferencia_solo_desde_stock` | 1 | A | 8 | 1 |
| [89](../tests/test_security_hardening.py#L89) | `test_04_contacto_del_destino_acepta_transferencia` | 1 | A | 13 | 1 |
| [104](../tests/test_security_hardening.py#L104) | `test_05_usuario_sin_concesionario_no_ve_nada` | 1 | A | 9 | 1 |
| [116](../tests/test_security_hardening.py#L116) | `test_06_concesionario_no_salta_estados` | 1 | A | 18 | 1 |
| [137](../tests/test_security_hardening.py#L137) | `test_07_otro_concesionario_no_envia_ticket_ajeno` | 1 | A | 4 | 1 |
| [142](../tests/test_security_hardening.py#L142) | `test_08_staff_no_modifica_datos_del_concesionario` | 1 | A | 12 | 1 |
| [157](../tests/test_security_hardening.py#L157) | `test_09_ticket_en_curso_sigue_operable_tras_transferencia` | 1 | A | 17 | 1 |
| [178](../tests/test_security_hardening.py#L178) | `test_10_aislamiento_multimedia_y_medidas` | 1 | A | 12 | 1 |
| [193](../tests/test_security_hardening.py#L193) | `_cert_vals` | 1 | A | 7 | 3 |
| [201](../tests/test_security_hardening.py#L201) | `test_11_concesionario_no_modifica_certificados` | 2 | A | 10 | 1 |
| [213](../tests/test_security_hardening.py#L213) | `test_12_fecha_de_certificado_acotada` | 1 | A | 11 | 1 |
| [225](../tests/test_security_hardening.py#L225) | `test_13_retraso_se_mide_contra_la_carga_real` | 1 | A | 10 | 1 |
| [237](../tests/test_security_hardening.py#L237) | `test_14_concesionario_no_elige_emisor_ni_estado` | 1 | A | 8 | 1 |
| [247](../tests/test_security_hardening.py#L247) | `test_15_of_unica` | 1 | A | 5 | 1 |

</details>

<details><summary><code>tests/test_ticket_workflow.py</code> — 10 funciones, CCN máxima 1</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [9](../tests/test_ticket_workflow.py#L9) | `setUp` | 1 | A | 31 | 1 |
| [44](../tests/test_ticket_workflow.py#L44) | `test_01_pre_pm_ticket_creation_and_lifecycle` | 1 | A | 43 | 1 |
| [105](../tests/test_ticket_workflow.py#L105) | `test_02_post_pm_ticket_reject` | 1 | A | 19 | 1 |
| [129](../tests/test_ticket_workflow.py#L129) | `test_03_accept_and_close_with_sap_order_wizard` | 1 | A | 60 | 1 |
| [202](../tests/test_ticket_workflow.py#L202) | `test_04_tipo_desvio_and_rechazo_tags` | 1 | A | 23 | 1 |
| [230](../tests/test_ticket_workflow.py#L230) | `_ticket_en_proceso` | 1 | A | 10 | 2 |
| [241](../tests/test_ticket_workflow.py#L241) | `test_05_rechazo_requiere_tags_de_reclamo` | 1 | A | 8 | 1 |
| [252](../tests/test_ticket_workflow.py#L252) | `test_06_cierre_sin_garantia_requiere_motivos_y_solucion` | 1 | A | 21 | 1 |
| [280](../tests/test_ticket_workflow.py#L280) | `test_07_clasificacion_post_pm_obligatoria` | 1 | A | 25 | 1 |
| [310](../tests/test_ticket_workflow.py#L310) | `test_08_kpis_promedian_solo_etapas_alcanzadas` | 1 | A | 15 | 1 |

</details>

<details><summary><code>tests/test_transferencia.py</code> — 5 funciones, CCN máxima 2</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [9](../tests/test_transferencia.py#L9) | `setUp` | 2 | A | 19 | 1 |
| [30](../tests/test_transferencia.py#L30) | `test_01_propose_and_cancel_transfer` | 1 | A | 11 | 1 |
| [45](../tests/test_transferencia.py#L45) | `test_02_accept_transfer_workflow` | 1 | A | 27 | 1 |
| [83](../tests/test_transferencia.py#L83) | `test_03_reject_transfer_workflow` | 1 | A | 10 | 1 |
| [96](../tests/test_transferencia.py#L96) | `test_04_transfer_archives_previous_certificates` | 1 | A | 12 | 1 |

</details>

<details><summary><code>tools/complejidad.py</code> — 11 funciones, CCN máxima 8</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [45](../tools/complejidad.py#L45) | `rango` | 4 | A | 5 | 1 |
| [57](../tools/complejidad.py#L57) | `analizar` | 8 | B | 25 | 0 |
| [90](../tools/complejidad.py#L90) | `_enlace` | 1 | A | 2 | 1 |
| [99](../tools/complejidad.py#L99) | `_resumen` | 7 | B | 10 | 1 |
| [117](../tools/complejidad.py#L117) | `_tabla_areas` | 8 | B | 12 | 1 |
| [136](../tools/complejidad.py#L136) | `_tabla_atencion` | 4 | A | 9 | 1 |
| [152](../tools/complejidad.py#L152) | `_por_archivo` | 2 | A | 5 | 1 |
| [164](../tools/complejidad.py#L164) | `_tabla_archivos` | 2 | A | 9 | 1 |
| [180](../tools/complejidad.py#L180) | `_tabla_funciones` | 3 | A | 13 | 1 |
| [200](../tools/complejidad.py#L200) | `generar` | 2 | A | 3 | 1 |
| [210](../tools/complejidad.py#L210) | `escribir` | 3 | A | 7 | 0 |

</details>

<details><summary><code>tools/documentacion.py</code> — 18 funciones, CCN máxima 14</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [30](../tools/documentacion.py#L30) | `generar` | 6 | B | 25 | 1 |
| [57](../tools/documentacion.py#L57) | `escribir` | 1 | A | 3 | 1 |
| [63](../tools/documentacion.py#L63) | `_id_mermaid` | 1 | A | 2 | 1 |
| [67](../tools/documentacion.py#L67) | `_campos_propios` | 4 | A | 3 | 1 |
| [73](../tools/documentacion.py#L73) | `_diagrama` | 8 | B | 11 | 1 |
| [86](../tools/documentacion.py#L86) | `_celda` | 2 | A | 2 | 1 |
| [90](../tools/documentacion.py#L90) | `_detalle` | 10 | B | 15 | 1 |
| [107](../tools/documentacion.py#L107) | `_tabla_campos` | 2 | A | 8 | 1 |
| [118](../tools/documentacion.py#L118) | `_metodos_publicos` | 7 | B | 9 | 1 |
| [131](../tools/documentacion.py#L131) | `_resumen` | 3 | A | 2 | 1 |
| [135](../tools/documentacion.py#L135) | `_registros_del_modulo` | 1 | A | 3 | 2 |
| [140](../tools/documentacion.py#L140) | `_llamadores` | 14 | C | 19 | 1 |
| [144](../tools/documentacion.py#L144) | `_llamadores.agregar` | 1 | A | 2 | 3 |
| [166](../tools/documentacion.py#L166) | `_modelo_del_boton` | 2 | A | 4 | 3 |
| [173](../tools/documentacion.py#L173) | `_llamadas_python` | 4 | A | 4 | 1 |
| [179](../tools/documentacion.py#L179) | `_puntos_de_entrada` | 7 | B | 11 | 2 |
| [194](../tools/documentacion.py#L194) | `_matriz_acceso` | 6 | B | 7 | 1 |
| [203](../tools/documentacion.py#L203) | `_reglas` | 3 | A | 7 | 1 |

</details>

<details><summary><code>tools/drive.py</code> — 12 funciones, CCN máxima 5</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [25](../tools/drive.py#L25) | `cuenta_de_servicio` | 3 | A | 5 | 1 |
| [35](../tools/drive.py#L35) | `__init__` | 4 | A | 4 | 4 |
| [41](../tools/drive.py#L41) | `desde_ajustes` | 1 | A | 3 | 2 |
| [45](../tools/drive.py#L45) | `ruta` | 1 | A | 2 | 2 |
| [50](../tools/drive.py#L50) | `verificar` | 3 | A | 6 | 1 |
| [58](../tools/drive.py#L58) | `copiar` | 1 | A | 3 | 4 |
| [62](../tools/drive.py#L62) | `existe` | 2 | A | 6 | 3 |
| [69](../tools/drive.py#L69) | `enlace` | 5 | A | 13 | 3 |
| [85](../tools/drive.py#L85) | `_rclone` | 4 | A | 9 | 3 |
| [96](../tools/drive.py#L96) | `_entorno` | 1 | A | 9 | 1 |
| [107](../tools/drive.py#L107) | `_binario` | 3 | A | 5 | 0 |
| [114](../tools/drive.py#L114) | `_ultima_linea` | 5 | A | 7 | 1 |

</details>

<details><summary><code>wizard/portal_wizard.py</code> — 4 funciones, CCN máxima 5</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [10](../wizard/portal_wizard.py#L10) | `action_grant_access` | 2 | A | 5 | 1 |
| [17](../wizard/portal_wizard.py#L17) | `action_quien_usa_el_correo` | 1 | A | 4 | 1 |
| [23](../wizard/portal_wizard.py#L23) | `_assert_user_email_uniqueness` | 5 | A | 15 | 1 |
| [42](../wizard/portal_wizard.py#L42) | `_describir_usuario` | 5 | A | 10 | 2 |

</details>

<details><summary><code>wizard/pv_adjuntar_multimedia_wizard.py</code> — 3 funciones, CCN máxima 6</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [32](../wizard/pv_adjuntar_multimedia_wizard.py#L32) | `action_adjuntar` | 2 | A | 7 | 1 |
| [40](../wizard/pv_adjuntar_multimedia_wizard.py#L40) | `_vincular_enlace` | 6 | B | 27 | 1 |
| [68](../wizard/pv_adjuntar_multimedia_wizard.py#L68) | `_confirmar_archivo_subido` | 6 | B | 9 | 1 |

</details>

<details><summary><code>wizard/pv_cerrar_ticket_wizard.py</code> — 2 funciones, CCN máxima 15</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [49](../wizard/pv_cerrar_ticket_wizard.py#L49) | `default_get` | 13 | C | 15 | 2 |
| [65](../wizard/pv_cerrar_ticket_wizard.py#L65) | `action_confirmar` | 15 | C | 57 | 1 |

</details>

<details><summary><code>wizard/pv_import_maquinas.py</code> — 10 funciones, CCN máxima 14</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [27](../wizard/pv_import_maquinas.py#L27) | `_celda` | 2 | A | 2 | 2 |
| [31](../wizard/pv_import_maquinas.py#L31) | `_clave` | 1 | A | 3 | 1 |
| [37](../wizard/pv_import_maquinas.py#L37) | `_indice` | 2 | A | 5 | 1 |
| [45](../wizard/pv_import_maquinas.py#L45) | `_tabla_html` | 4 | A | 8 | 4 |
| [68](../wizard/pv_import_maquinas.py#L68) | `_leer_excel` | 14 | C | 20 | 1 |
| [92](../wizard/pv_import_maquinas.py#L92) | `_clientes` | 6 | B | 7 | 2 |
| [101](../wizard/pv_import_maquinas.py#L101) | `_buscar` | 4 | A | 10 | 5 |
| [113](../wizard/pv_import_maquinas.py#L113) | `_validar_filas` | 12 | C | 44 | 1 |
| [162](../wizard/pv_import_maquinas.py#L162) | `action_preview` | 6 | B | 30 | 1 |
| [193](../wizard/pv_import_maquinas.py#L193) | `action_import` | 2 | A | 13 | 1 |

</details>

<details><summary><code>wizard/pv_liberar_maquina_wizard.py</code> — 1 funciones, CCN máxima 1</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [14](../wizard/pv_liberar_maquina_wizard.py#L14) | `action_liberar` | 1 | A | 4 | 1 |

</details>

<details><summary><code>wizard/pv_transferir_maquina_wizard.py</code> — 1 funciones, CCN máxima 1</summary>

| Línea | Función | CCN | Rango | Líneas de código | Parámetros |
|--:|---|--:|:-:|--:|--:|
| [12](../wizard/pv_transferir_maquina_wizard.py#L12) | `action_transferir` | 1 | A | 5 | 1 |

</details>

<!-- complejidad:fin -->
