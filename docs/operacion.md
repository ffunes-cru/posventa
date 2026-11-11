# Operación

## Ajustes (Posventa → Configuración → Ajustes)

Se guardan como parámetros del sistema (`ir.config_parameter`), así que también se ven en
*Ajustes → Técnico → Parámetros del sistema*.

| Parámetro | Por defecto | Qué controla |
|---|---|---|
| `posventa.fru_expiration_days` | 10 | Días desde la liberación para cargar el FRU sin retraso. |
| `posventa.fru_grace_days` | 3 | Días desde la fecha del FRU en que sirve para reclamos. |
| `posventa.feu_expiration_days` | 20 | Días desde la liberación para cargar el FEU sin retraso. |
| `posventa.feu_claims_validity_days` | 90 | Días desde la fecha del FEU en que sirve para reclamos. |
| `posventa.storage_mode` | `drive` | Dónde van los archivos pesados: `drive` (unidad compartida de Google Drive) u `odoo` (adjuntos de Odoo, tope 200 MB). Cambiarlo no pierde lo ya guardado. |
| `posventa.drive_credentials` | (vacío) | JSON de la clave de la cuenta de servicio de Google. |
| `posventa.drive_shared_drive_id` | (vacío) | ID de la unidad compartida. |
| `posventa.drive_folder` | `Crucianelli_Posventa/Reclamos` | Carpeta base en la unidad. Cada reclamo crea `<OF>_<número de ticket>/` adentro. |
| `posventa.chunk_size_kb` | 768 | Tamaño de cada fragmento de subida. Debe ser menor al límite de cuerpo del proxy (Nginx `client_max_body_size`). |
| `posventa.max_file_size_mb` | 1024 | Tamaño máximo de un archivo pesado. |

Las fotos y archivos de hasta 20 MB (`MAX_ADJUNTO_MB` en `models/pv_ticket_multimedia.py`) van como adjunto
normal del reclamo; los mayores, como archivo pesado.

## Tareas programadas (Ajustes → Técnico → Acciones planificadas)

Son [acciones planificadas](odoo.md#acciones-planificadas-y-acciones-de-servidor) de Odoo.

| Tarea | Frecuencia | Qué hace |
|---|---|---|
| Posventa: Verificar vencimientos de medidas | Diaria | Marca vencidas las medidas pasadas de fecha y lo avisa en el reclamo. |
| Posventa: Archivar vencimientos de certificados | Diaria | Pasa a *Vencido* los FRU/FEU que superaron su vigencia. |
| Posventa: Notificar vencimientos próximos de certificados | Diaria | Correo al concesionario 3 días antes del vencimiento. |
| Posventa: Sincronizar multimedia pendiente a Google Drive | Cada 5 min (y al terminar cada subida) | Sube a Drive los archivos pesados pendientes, reintenta los fallidos y limpia temporales de más de 24 h. |

## Google Drive

Los videos van a una **unidad compartida** de Google Workspace, con una **cuenta de servicio**: no depende de la
cuenta de una persona y no vence. Todo se configura desde *Posventa → Configuración → Ajustes*. En el servidor
solo hace falta el programa rclone, que ya viene en la imagen de Odoo del VPS (`imagen-odoo/` en el repo de
infra, ver [Despliegue](despliegue.md)). Sin Docker, se instala con `sudo apt install rclone`.
Odoo le pasa las credenciales en cada llamada, así que no se corre `rclone config` ni existe un `rclone.conf`.

### Configuración inicial (una vez)

1. **Crear la cuenta de servicio** en [Google Cloud Console](https://console.cloud.google.com/):
   1. Crear un proyecto (o usar uno existente) y habilitar la **Google Drive API**
      (*APIs y servicios → Biblioteca*).
   2. *IAM y administración → Cuentas de servicio → Crear cuenta de servicio*. No necesita roles.
   3. En la cuenta creada: *Claves → Agregar clave → JSON*. Se descarga un archivo `.json`.
      [Guía de Google](https://cloud.google.com/iam/docs/keys-create-delete).
2. **En Odoo, Ajustes de Posventa:** pegar el contenido completo del `.json` en *Cuenta de servicio de Google*.
   Debajo aparece el email de la cuenta (`...@...iam.gserviceaccount.com`).
3. **En Google Drive:** en la unidad compartida, *Administrar miembros* → agregar ese email como
   **Administrador de contenido**. Si Drive no deja agregarlo, la unidad solo admite miembros de la
   organización: habilitar *Permitir que personas ajenas a la organización accedan a los archivos* en la
   configuración de la unidad.
4. **De vuelta en Ajustes:** pegar el *ID de la unidad compartida* (abrir la unidad en el navegador y copiar lo
   que sigue a `/drive/folders/` en la URL), *Probar conexión* y guardar. La prueba crea la carpeta base si falta
   y confirma que se puede escribir.
5. **Para que los concesionarios abran los enlaces:** en la configuración de la unidad compartida (y en la
   consola de administración de Workspace, si está restringido) permitir compartir con personas **ajenas a la
   organización**. Si no se permite, los enlaces siguen funcionando, pero solo para los miembros de la unidad.

El JSON queda guardado como parámetro del sistema, visible solo para administradores. Para cambiar de clave,
crear una nueva en Google Cloud, pegarla en Ajustes y borrar la vieja.

### Qué pasa si Drive no funciona

- **La subida nunca se bloquea.** El archivo queda guardado en el servidor (`posventa_staging/` en el home del
  usuario que corre Odoo: `/var/lib/odoo` en Docker) y el reclamo
  se crea igual.
- **Drive sin configurar o sin conexión:** cada 5 minutos el cron prueba la conexión. Mientras falle, los
  archivos esperan sin gastar reintentos. El motivo se ve en la pestaña Multimedia del reclamo y Ajustes muestra
  cuántos archivos esperan. Cuando la conexión vuelve, se suben solos. Al guardar Ajustes también se disparan.
- **Falla la copia de un archivo puntual** (por ejemplo, la cuota está llena): se reintenta a los 5, 10, 20 y 40
  minutos, y se avisa en el chatter la primera y la última vez. Después queda el botón *Reintentar*.
- **Contingencia larga:** pasar *Dónde se guardan* a *Odoo*. Los archivos nuevos van como adjuntos (tope 200 MB)
  y los que ya estaban esperando se suben a Drive cuando vuelva.

Mientras Drive no funcione, los videos ocupan disco en el servidor: vigilar el espacio si la caída dura días.

## Comandos frecuentes

Opciones explicadas en [Línea de comandos](odoo.md#línea-de-comandos).

```bash
# Actualizar el módulo después de cambiar código (y reiniciar el servidor)
./odoo-bin -d <base> -u posventa --stop-after-init

# Tests del módulo (usar una base de prueba, nunca la de producción)
./odoo-bin -d <base_de_prueba> -u posventa --test-tags=/posventa --stop-after-init --http-port=8071

# Un solo test
./odoo-bin -d <base_de_prueba> --test-tags=/posventa:TestPortalPosventa.test_01_paginas_y_aislamiento --stop-after-init --http-port=8071

# Regenerar docs/referencia.md (el test test_documentacion falla si quedó desactualizado)
./odoo-bin shell -d <base_de_prueba> --no-http <<< "from odoo.addons.posventa.tools.documentacion import escribir; escribir(env)"
```

Los tests de navegador (`start_tour`) necesitan Chrome o Chromium instalado.

## Sitio de documentación (Doxygen)

[Doxygen](https://www.doxygen.nl/manual/index.html) arma un sitio web navegable, con buscador, que junta en un
solo lugar estos documentos y el código Python y JS. Para cada función muestra su docstring, un enlace al código
y dos grafos:

- **Gráfico de llamadas de esta función:** a qué funciones llama, y lo que llaman esas, en cadena.
- **Gráfico de llamadas a esta función:** desde qué funciones se la llama.

Los nodos de los grafos se pueden cliquear para saltar a esa función. El sitio no se guarda en git: se genera
cuando se lo quiere ver.

```bash
# Una vez: instalar doxygen y graphviz (Arch: pacman -S doxygen graphviz; Debian/Ubuntu: apt install doxygen graphviz)
# Desde la carpeta del módulo:
doxygen
# Abrir docs/_doxygen/html/index.html en el navegador
```

La configuración está en `Doxyfile`, comentada; está probada con Doxygen 1.18. Las advertencias, por ejemplo un
enlace roto en estos documentos, quedan en `docs/_doxygen/advertencias.log`. Los diagramas Mermaid se dibujan en
el navegador y necesitan internet. Con una versión de Doxygen sin soporte de Mermaid, se ven como texto.

**Qué no muestra.** Doxygen solo lee el código, así que no ve las llamadas que arma Odoo en tiempo de ejecución:

- botones de las vistas
- crons
- acciones de servidor
- `orm.call` desde el JS

Un `action_*` que solo se llama desde un botón aparece sin nadie que lo llame. Esas conexiones están en la
[referencia generada](referencia.md#puntos-de-entrada).

Otros detalles a tener en cuenta:
- `super().write()` aparece como una flecha de `write` a sí mismo.
- El tipo que Doxygen le pone a algunos campos (`bool`, `list`) es una suposición suya: el tipo real es el
  `fields.*` de la definición.
- Para que entren en los grafos las llamadas dentro de `for rec in self:`, el filtro `scripts/doxygen_filtro.sh`
  le hace leer `rec.` como `self.`. Mantener ese nombre de variable en los bucles sobre `self`.

## Problemas comunes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El concesionario ve "no está asociado a un concesionario" | Su contacto no tiene como *Empresa* la del concesionario. | Corregir la empresa del contacto. |
| "Estos registros están restringidos … Contacto (res.partner)" en el portal | Una página muestra un dato de otra empresa. | Ver [Seguridad](seguridad.md#mostrar-datos-que-el-usuario-no-puede-leer). |
| No se puede crear un reclamo | Máquina LIBERADA o PENDIENTE, o sin certificado vigente. | Ver el detalle de la máquina en el portal: indica el próximo certificado y su plazo. |
| Un video queda "Sincronizando" mucho tiempo | Drive sin configurar o sin conexión, o el cron no corre. | Ver el motivo en la pestaña Multimedia del reclamo; *Probar conexión* en Ajustes; revisar que el cron esté activo. |
| Google Cloud no deja crear la clave JSON | La política `iam.disableServiceAccountKeyCreation` de la organización (activa por defecto en organizaciones nuevas). | Un administrador de la organización la desactiva para ese proyecto. |
| *Probar conexión*: "rclone no está instalado" | Odoo corre con la imagen oficial, sin rclone. | Usar la imagen `imagen-odoo/` del repo de infra (ver [Despliegue](despliegue.md)). |
| *Probar conexión*: "notFound" o "File not found" con el ID de la unidad | ID mal copiado o la cuenta de servicio no es miembro de la unidad. | Revisar el ID y los miembros de la unidad (paso 3 de la configuración inicial). |
| *Probar conexión*: "insufficientPermissions" | La cuenta de servicio es miembro con rol de solo lectura. | Darle rol *Administrador de contenido*. |
| Error HTTP 413 al subir | El fragmento supera el límite del proxy. | Bajar `posventa.chunk_size_kb` o subir `client_max_body_size`. |
| Los concesionarios no reciben correos | Servidor de correo saliente no configurado. | Ajustes → Técnico → Servidores de correo saliente. |

## Ver también

- [Conceptos de Odoo](odoo.md): crons, línea de comandos y tests.
- [Manual de Doxygen](https://www.doxygen.nl/manual/index.html) · [opciones del `Doxyfile`](https://www.doxygen.nl/manual/config.html)
- [Configurar el servidor de correo saliente (Odoo)](https://www.odoo.com/documentation/19.0/applications/general/email_communication.html)
