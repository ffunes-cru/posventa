/** @odoo-module **/
import { _t } from "@web/core/l10n/translation";

/** Archivos de hasta este tamaño se adjuntan como ir.attachment; los mayores van por fragmentos. */
export const MAX_STANDARD_SIZE = 20 * 1024 * 1024;

export function newUploadUuid() {
    return "file_" + Math.random().toString(36).substring(2, 10) + "_" + Date.now();
}

export function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
        reader.onerror = (error) => reject(error);
        reader.readAsDataURL(file);
    });
}

/**
 * Sube un archivo pesado al endpoint /posventa/ticket/upload_chunk en fragmentos de `chunkSize`
 * bytes, con hasta 3 reintentos por fragmento. Lanza Error con el mensaje del servidor si falla.
 */
export async function uploadFileInChunks({ ticketId, file, uuid, name, chunkSize, onProgress }) {
    const totalChunks = Math.ceil(file.size / chunkSize) || 1;
    let lastResponse = null;
    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
        const start = chunkIndex * chunkSize;
        const formData = new FormData();
        formData.append("ticket_id", ticketId);
        formData.append("file_uuid", uuid);
        formData.append("filename", name || file.name);
        formData.append("chunk_index", chunkIndex);
        formData.append("total_chunks", totalChunks);
        formData.append("file_size", file.size);
        formData.append("chunk", file.slice(start, Math.min(start + chunkSize, file.size)), name || file.name);

        let retries = 3;
        while (true) {
            try {
                const response = await fetch("/posventa/ticket/upload_chunk", { method: "POST", body: formData });
                let data = {};
                try {
                    data = await response.json();
                } catch {
                    // respuesta sin JSON (p. ej. proxy)
                }
                if (!response.ok || data.error) {
                    const msg = data.error || (response.status === 413
                        ? _t("El archivo o bloque supera el límite admitido por el servidor (HTTP 413).")
                        : _t("Error del servidor (HTTP %s)", response.status));
                    const error = new Error(msg);
                    // Errores de validación del servidor: no tiene sentido reintentar
                    error.noRetry = response.status >= 400 && response.status < 500;
                    throw error;
                }
                lastResponse = data;
                break;
            } catch (err) {
                retries--;
                if (retries === 0 || err.noRetry) {
                    throw err;
                }
                await new Promise((r) => setTimeout(r, 1000));
            }
        }
        if (onProgress) {
            onProgress(chunkIndex + 1, totalChunks);
        }
    }
    return lastResponse;
}
