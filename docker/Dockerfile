# Odoo 19 para posventa: la imagen oficial más rclone, que sube los videos de los reclamos a Google Drive.
FROM odoo:19.0
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends rclone \
    && rm -rf /var/lib/apt/lists/*
USER odoo
