#!/bin/sh
# Filtro de entrada de Doxygen (ver FILTER_PATTERNS en Doxyfile). Solo cambia lo que Doxygen analiza: el
# código que muestra el sitio es el original. Conserva la cantidad de líneas para que los números coincidan.
#
# .py: Doxygen solo reconoce `self.metodo()` como llamada a un método de la clase. En Odoo lo habitual es
#      `for rec in self: rec.metodo()`, así que se cambia `rec.` por `self.` para que esas llamadas aparezcan
#      en los grafos.
# .js: se borra el comentario `/** @odoo-module **/`, que Doxygen toma como un comando desconocido.
case "$1" in
    *.py) exec sed -E 's/\brec\./self./g' "$1" ;;
    *.js) exec sed -E 's#^/\*\*? *@odoo-module.*\*/$##' "$1" ;;
    *) exec cat "$1" ;;
esac
