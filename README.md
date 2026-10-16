# Posventa Crucianelli

Módulo de Odoo 19 para gestionar el servicio de posventa de Crucianelli: las máquinas que salen de fábrica,
los certificados que el concesionario carga (FRU, FEU, CPM) y los reclamos de garantía.

- **Concesionarios** (usuarios portal) trabajan desde la web en `/my/posventa`: ven sus máquinas, cargan
  certificados, piden traslados y crean reclamos con fotos y videos.
- **Staff de Crucianelli** (usuarios internos) atiende los reclamos desde el backend de Odoo: los toma,
  carga medidas, los acepta o rechaza y los cierra con los datos de garantía y SAP.
- **Administrador de Posventa** configura todo: concesionarios y su acceso, catálogos, importación de
  máquinas, liberaciones y ajustes.

## Documentación

Leer en este orden. Los diagramas son [Mermaid](https://mermaid.js.org/): GitHub, GitLab y VS Code
(con la extensión *Markdown Preview Mermaid Support*) los dibujan solos.

| Documento | Para qué |
|---|---|
| [Conceptos](docs/conceptos.md) | El negocio en palabras simples y el glosario (OF, FRU, FEU, CPM, T1…). Empezar acá. |
| [Conceptos de Odoo](docs/odoo.md) | Las piezas de Odoo que usa el módulo (permisos, reglas, campos related, crons…), explicadas con ejemplos y con enlaces a la documentación oficial. |
| [Arquitectura](docs/arquitectura.md) | Cómo está armado el módulo, qué hace cada archivo y cómo viaja un pedido. |
| [Flujos](docs/flujos.md) | Estados de ticket, máquina y certificado, y qué acción los cambia. |
| [Seguridad](docs/seguridad.md) | Quién ve y hace qué, y cómo diagnosticar un error de acceso. |
| [Operación](docs/operacion.md) | Ajustes, tareas programadas, Google Drive, comandos y problemas comunes. |
| [Recetas](docs/recetas.md) | Paso a paso para los cambios más habituales. |
| [Referencia](docs/referencia.md) | **Generada** desde Odoo: todos los modelos y campos, permisos y quién llama a cada método. |

## Inicio rápido

```bash
# Instalar o actualizar (y reiniciar el servidor)
./odoo-bin -d <base> -u posventa --stop-after-init

# Correr los tests del módulo
./odoo-bin -d <base> -u posventa --test-tags=/posventa --stop-after-init --http-port=8071
```

Requisitos: `openpyxl` (importación de máquinas desde Excel) y, si se guardan los videos en Google Drive,
`rclone` configurado (ver [Operación](docs/operacion.md)).
