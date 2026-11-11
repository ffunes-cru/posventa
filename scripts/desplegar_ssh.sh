#!/usr/bin/env bash
# Comando forzado de la clave SSH con la que GitHub Actions despliega en staging (ver docs/despliegue.md).
# Con esa clave lo único que se puede pedir es "desplegar este commit": el SHA llega en
# SSH_ORIGINAL_COMMAND, se valida que esté en una branch del repo y se corre scripts/desplegar.sh
# con la configuración de ~/staging.env.
set -euo pipefail

sha="${SSH_ORIGINAL_COMMAND:-}"
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Se esperaba el SHA completo de un commit." >&2
    exit 2
fi

repo="$HOME/posventa"
git -C "$repo" fetch --quiet --prune origin
# Solo commits que estén en branches del repo: los de pull requests de forks no se despliegan
if [ -z "$(git -C "$repo" branch -r --contains "$sha" 2>/dev/null)" ]; then
    echo "El commit $sha no está en ninguna branch de origin." >&2
    exit 2
fi
git -C "$repo" checkout --quiet --force --detach "$sha"

set -a
# shellcheck source=/dev/null
source "$HOME/staging.env"
set +a
exec "$repo/scripts/desplegar.sh"
