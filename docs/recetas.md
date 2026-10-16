# Recetas

Cambios habituales, paso a paso. Al terminar cualquiera: correr los tests, regenerar
[la referencia](referencia.md) (comando en [Operación](operacion.md#comandos-frecuentes)) y commitear todo junto.

## Cambios que no requieren programar

Todo esto se hace desde el backend con el usuario Administrador de Posventa:

- **Nuevo sistema, subsistema o problema del catálogo Post-PM:** Posventa → Configuración → Sistemas,
  Subsistemas o Problemas Catalogados.
- **Pregunta extra para los reclamos de un subsistema:** en el subsistema, pestaña *Campos Adicionales*.
  Tipos: texto, número, selección (opciones separadas por `|`) y sí/no. Aparece sola en el asistente del portal.
- **Tipo de desvío (Pre-PM) o motivo de rechazo / sin cobertura:** Posventa → Configuración → Tipos de Desvío o
  Motivos de Rechazo.
- **Plazos de certificados, Google Drive y límites de subida:** Posventa → Configuración → Ajustes.

## Cambiar el texto de los correos

Las plantillas están en `data/mail_template_data.xml` y **se vuelven a cargar en cada actualización del
módulo**: un cambio hecho desde la interfaz (Ajustes → Técnico → Plantillas de correo) se pierde al actualizar.
Hacer el cambio en el XML y actualizar el módulo.

## Agregar un campo al reclamo

1. **Modelo** (`models/pv_ticket.py`): declarar el campo junto a los de su grupo.
2. **Permisos por campo:** agregarlo a una de las listas del principio del archivo:
   - lo carga el concesionario al crear → `CAMPOS_CARGA_CONCESIONARIO`;
   - lo carga solo el Staff → `CAMPOS_SOLO_STAFF`;
   - lo puede tocar el concesionario después de enviar → `CAMPOS_POST_ENVIO_CONCESIONARIO` (casi nunca).
3. **Backend:** agregarlo al formulario en `views/pv_ticket_views.xml`.
4. **Portal, si lo carga el concesionario:** campo en el paso que corresponda de
   `static/src/frontend/wizards/ticket_wizard.xml`, valor inicial en `state` y envío en `ticketVals()` de
   `ticket_wizard.js`. Si es obligatorio, validarlo en `stepError()` **y** en una `@api.constrains` del modelo
   (el JS solo ayuda al usuario; la regla real es la del modelo).
5. **Portal, si solo se muestra:** agregarlo a `portal_posventa_ticket` en `views/portal_templates.xml`. Si es
   un dato de otro modelo (un contacto, un usuario), usar un campo *related* (ver
   [Seguridad](seguridad.md#mostrar-datos-que-el-usuario-no-puede-leer)).
6. **Test:** en `tests/test_ticket_workflow.py` o `tests/test_security_hardening.py`, quién puede y quién no
   puede cargarlo.
7. Si el campo es obligatorio y ya hay tickets, un script en `migrations/<nueva versión>/` que complete los
   existentes, y subir `version` en `__manifest__.py`.

## Agregar una página o acción al portal

1. **Lógica en el modelo:** un método público (`action_...`) que valide grupo, pertenencia
   (`concesionario_id._is_member()`) y estado, y lance `UserError` con un mensaje claro si no corresponde.
2. **Ruta** en `controllers/portal.py`: lectura con `self._pv_get()` (respeta las reglas); escritura con
   `self._pv_accion(url, método, mensaje_ok)`, que muestra el error de negocio como aviso.
3. **Plantilla** en `views/portal_templates.xml`, dentro de `posventa.portal_layout_posventa`.
4. **Test** en `tests/test_portal.py` con `url_open`, incluyendo que otro concesionario no pueda.

## Cambiar quién puede hacer algo

- Ver un modelo: `security/ir.model.access.csv`.
- Ver ciertos registros: reglas en `security/pv_security.xml`.
- Ejecutar una acción: la validación al principio del método (`_check_staff()`, `_check_admin()`,
  `_check_es_del_concesionario()`).

Cambiar las tres capas de forma coherente y probarlo en `tests/test_security_access.py` /
`test_security_hardening.py`.

## Cambiar el método que llama un cron

Los crons están en `data/ir_cron_data.xml` con `noupdate="1"`: en bases ya instaladas el cambio del XML **no se
aplica**. Además de cambiar el XML, agregar un script de migración que actualice el registro (ejemplo en
`migrations/19.0.1.1.0/post-migrate.py`) y subir la versión del módulo.

## Reproducir un error en un test

Antes de corregir un error, conviene reproducirlo en un test: queda probado que se corrigió y que no vuelve.

```python
# tests/test_portal.py
def test_xx_cliente_de_otra_empresa(self):
    self.maquina_a.cliente_id = self.cliente_final        # contacto que no es de la empresa del concesionario
    self.authenticate('concesionario_a', 'concesionario_a')
    self.assertIn('Productor Juan Perez', self.url_open('/my/posventa/maquinas').text)
```

`tests/common.py` ya crea dos concesionarios con sus usuarios portal (`concesionario_a`, `concesionario_b`),
un Staff (`staff_pv`), un Admin (`admin_pv`), un cliente final y un catálogo mínimo. Correrlo con
`--test-tags=/posventa:NombreDeLaClase.nombre_del_test`.
