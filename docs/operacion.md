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
| `posventa.storage_mode` | `drive` | Dónde van los archivos pesados: `drive` (Google Drive con rclone) u `odoo` (adjuntos de Odoo, tope 200 MB). Cambiarlo no pierde lo ya guardado. |
| `posventa.rclone_remote` | `crucianelli_drive` | Nombre del remoto de rclone. |
| `posventa.rclone_drive_folder` | `Crucianelli_Posventa/Reclamos` | Carpeta base en Drive. Cada reclamo crea `<OF>_<número de ticket>/` adentro. |
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

## Google Drive con rclone

```bash
bash addons/posventa/scripts/setup_rclone.sh   # instala rclone en ~/.local/bin si falta
~/.local/bin/rclone config                     # crear el remoto (tipo "drive"), nombre: crucianelli_drive
~/.local/bin/rclone lsd crucianelli_drive:     # verificar que conecta
```

rclone debe estar configurado **para el usuario del sistema que corre Odoo**. Si no está, el asistente de
reclamo lo avisa y no deja subir archivos pesados; mientras tanto se puede pasar a modo `odoo`.

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

## Problemas comunes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El concesionario ve "no está asociado a un concesionario" | Su contacto no tiene como *Empresa* la del concesionario. | Corregir la empresa del contacto. |
| "Estos registros están restringidos … Contacto (res.partner)" en el portal | Una página muestra un dato de otra empresa. | Ver [Seguridad](seguridad.md#mostrar-datos-que-el-usuario-no-puede-leer). |
| No se puede crear un reclamo | Máquina LIBERADA o PENDIENTE, o sin certificado vigente. | Ver el detalle de la máquina en el portal: indica el próximo certificado y su plazo. |
| Un video queda "Sincronizando" mucho tiempo | rclone no conecta o el cron no corre. | Ver el error en la pestaña Multimedia del reclamo; probar `rclone lsd`; revisar que el cron esté activo. Botón *Reintentar* para reencolar. |
| Error HTTP 413 al subir | El fragmento supera el límite del proxy. | Bajar `posventa.chunk_size_kb` o subir `client_max_body_size`. |
| Los concesionarios no reciben correos | Servidor de correo saliente no configurado. | Ajustes → Técnico → Servidores de correo saliente. |

## Ver también

- [Conceptos de Odoo](odoo.md): crons, línea de comandos y tests.
- [Configurar el servidor de correo saliente (Odoo)](https://www.odoo.com/documentation/19.0/applications/general/email_communication.html)
