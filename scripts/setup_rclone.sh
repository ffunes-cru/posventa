#!/usr/bin/env bash
# ==============================================================================
# Setup Rclone para Crucianelli Posventa
# Configura el acceso a Google Drive para el almacenamiento de multimedia pesada
# ==============================================================================

RCLONE_BIN="$HOME/.local/bin/rclone"

if [ ! -f "$RCLONE_BIN" ]; then
    echo "Descargando e instalando rclone..."
    mkdir -p "$HOME/.local/bin"
    curl -sL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o /tmp/rclone.zip
    unzip -q -o /tmp/rclone.zip -d /tmp/
    mv /tmp/rclone-*-linux-amd64/rclone "$RCLONE_BIN"
    chmod +x "$RCLONE_BIN"
    rm -rf /tmp/rclone*
fi

echo "Rclone disponible en: $RCLONE_BIN"
"$RCLONE_BIN" version

echo ""
echo "=============================================================================="
echo "Configuración de Google Drive para Posventa:"
echo "Nombre recomendado del remote: 'crucianelli_drive'"
echo "Tipo de almacenamiento: 'drive' (Google Drive)"
echo "=============================================================================="
echo "Ejecute el siguiente comando para configurar o verificar el remote:"
echo "  $RCLONE_BIN config"
echo "=============================================================================="
