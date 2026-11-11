#!/usr/bin/env bash
# Actualiza el módulo posventa en un servidor con Odoo en Docker Compose: copia el código a la carpeta de
# addons montada, actualiza la base y reinicia el contenedor. Si la actualización falla, vuelve a poner el
# código anterior y levanta Odoo igual.
#
# Lo usa el job "desplegar" de GitHub Actions (.github/workflows/ci.yml), y también se puede correr a mano
# desde una copia del repositorio: ODOO_COMPOSE_DIR=/opt/odoo ODOO_DB=pruebas scripts/desplegar.sh
#
# Variables:
#   ODOO_COMPOSE_DIR  (obligatoria) carpeta con el docker-compose.yml de Odoo
#   ODOO_DB           (obligatoria) base a actualizar
#   ODOO_ADDONS_DIR   carpeta de addons montada en el contenedor (por defecto: $ODOO_COMPOSE_DIR/addons)
#   ODOO_SERVICE      servicio de Odoo en el compose (por defecto: web)
#   ODOO_URL          URL para comprobar que Odoo levantó (por defecto: http://localhost:8069)
set -euo pipefail

origen="$(cd "$(dirname "$0")/.." && pwd)"
compose_dir="${ODOO_COMPOSE_DIR:?Falta ODOO_COMPOSE_DIR}"
base="${ODOO_DB:?Falta ODOO_DB}"
destino="${ODOO_ADDONS_DIR:-$compose_dir/addons}/posventa"
servicio="${ODOO_SERVICE:-web}"
url="${ODOO_URL:-http://localhost:8069}"
anterior="$(mktemp -d)"
trap 'rm -rf "$anterior"' EXIT

compose() { docker compose --project-directory "$compose_dir" "$@"; }

copiar() {
    rsync -a --delete --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
        --exclude .git --exclude .github --exclude __pycache__ --exclude docs/_doxygen "$1/" "$2/"
}

if [ -d "$destino" ]; then
    copiar "$destino" "$anterior"
fi
copiar "$origen" "$destino"

echo "Actualizando posventa en la base $base"
compose stop "$servicio"
if ! compose run --rm --no-deps "$servicio" odoo -d "$base" -u posventa --stop-after-init --no-http; then
    echo "::error::Falló la actualización de posventa: se restaura el código anterior"
    if [ -n "$(ls -A "$anterior")" ]; then
        copiar "$anterior" "$destino"
    fi
    compose up -d "$servicio"
    exit 1
fi
compose up -d "$servicio"

for _ in $(seq 30); do
    if curl -fs -o /dev/null "$url/web/login"; then
        echo "Odoo responde en $url"
        exit 0
    fi
    sleep 2
done
echo "::error::Odoo no respondió en $url después de 60 segundos"
exit 1
