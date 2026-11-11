# Despliegue

Checklist para instalar o actualizar el módulo en un servidor de Odoo 19. Los ejemplos suponen un servicio
systemd `odoo`, un usuario de sistema `odoo` y la configuración en `/etc/odoo/odoo.conf`: ajustar a lo que use
el servidor.

## 1. Requisitos del servidor (una vez)

| Qué | Cómo verificarlo | Para qué |
|---|---|---|
| Odoo 19 con los módulos `mail`, `portal` y `board` | Vienen con Odoo. | Dependencias del módulo. |
| `openpyxl` en el Python de Odoo | `sudo -u odoo <python de odoo> -c "import openpyxl"` | Importar máquinas desde Excel. |
| `rclone` | `sudo -u odoo rclone version` | Subir videos a Google Drive. Se instala con `sudo apt install rclone`. No hace falta configurarlo. |
| Disco libre en el home del usuario `odoo` | `df -h ~odoo` | Los videos esperan en `~odoo/posventa_staging/` hasta subir a Drive (hasta 1 GB cada uno). |
| Proxy con `client_max_body_size` de 1 MB o más | `grep client_max_body_size /etc/nginx -r` | Cada fragmento de subida mide 768 KB. |
| Tareas programadas activas | En `odoo.conf`, `max_cron_threads` mayor a 0. | El cron sube los videos y revisa vencimientos. |
| Servidor de correo saliente | Ajustes → Técnico → Servidores de correo saliente | Avisos a concesionarios. |

Si Odoo corre con varios servidores detrás de un balanceador, todos los fragmentos de una subida tienen que llegar
al mismo servidor (staging en disco local). Con un solo servidor no hay nada que hacer.

## 2. Copiar el código

Copiar la carpeta `posventa` a una carpeta que esté en el `addons_path` del servidor, con git o con `rsync`:

```bash
rsync -a --delete --exclude '__pycache__' --exclude 'docs/_doxygen' addons/posventa/ servidor:/ruta/addons/posventa/
```

## 3. Instalar o actualizar

```bash
sudo systemctl stop odoo
# Primera vez: -i posventa. Después: -u posventa.
sudo -u odoo <python de odoo> <odoo-bin> -c /etc/odoo/odoo.conf -d <base> -u posventa --stop-after-init
sudo systemctl start odoo
```

Revisar que el comando termine sin `ERROR` en el log. Si falla, la base queda como estaba, porque la
actualización corre en una sola transacción.

## 4. Configurar (primera vez)

1. Ajustes → Usuarios: dar a los usuarios de Crucianelli los grupos de Posventa (*Staff* o *Administrador*).
2. Posventa → Configuración → Ajustes:
   - Plazos de FRU y FEU (por defecto 10/3 y 20/90 días).
   - Google Drive: seguir [Operación → Google Drive](operacion.md#google-drive) y terminar con *Probar
     conexión*. Mientras no esté configurado, los videos se aceptan igual y esperan en el servidor.
3. Cargar catálogos (sistemas, subsistemas, problemas, tipos de desvío) e importar máquinas desde Excel.
4. Crear los concesionarios y darles acceso al portal (ver [Seguridad](seguridad.md)).

## 5. Probar

- [ ] Un concesionario entra a `/my/posventa` y ve solo sus máquinas.
- [ ] Crea un reclamo con una foto y un video de más de 20 MB.
- [ ] En el backend, el video pasa de *Sincronizando* a *Disponible* en menos de 5 minutos y el enlace abre el
      archivo en Drive, también desde el portal del concesionario.
- [ ] Con *Probar conexión* fallando (por ejemplo, con un ID de unidad equivocado), un video nuevo se acepta,
      queda *Sincronizando* con el motivo visible, y se sube solo al corregir el ID.
- [ ] El staff toma el reclamo, carga una medida y lo cierra.
