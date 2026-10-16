/** @odoo-module **/
import { registry } from "@web/core/registry";

const siguiente = {
    content: "Siguiente paso",
    trigger: ".pv-wizard-footer button.pv-btn-primary:contains(Siguiente)",
    run: "click",
};

// Reclamo Pre-PM de punta a punta desde el portal web: wizard OWL -> envío -> detalle del ticket
registry.category("web_tour.tours").add("posventa_portal_nuevo_ticket", {
    steps: () => [
        {
            content: "El wizard OWL se monta en la página del portal",
            trigger: ".o_pv_portal .o_pv_frontend_wizard .pv-wizard-container",
        },
        siguiente,
        {
            content: "Paso de clasificación Pre-PM",
            trigger: ".pv-wizard-content h3:contains(Clasificación)",
        },
        siguiente,
        {
            content: "Descripción del reclamo",
            trigger: ".pv-wizard-content textarea[placeholder*='Describa detalladamente']",
            run: "edit Faltan los bulones de la tolva (tour portal)",
        },
        {
            content: "Enlace a fotos en Drive",
            trigger: ".pv-wizard-content input[type=url]",
            run: "edit https://drive.google.com/drive/folders/tour-portal",
        },
        siguiente,
        {
            content: "Guardar y enviar",
            trigger: ".pv-wizard-footer button.pv-btn-success:contains(Enviar)",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "Redirige al detalle del ticket, ya enviado",
            trigger: ".o_pv_portal .badge:contains(ABIERTO)",
        },
        {
            content: "El uploader de archivos está disponible",
            trigger: ".o_pv_ticket_uploader input[type=file]",
        },
        {
            content: "El chatter del portal está disponible",
            trigger: ".o_portal_chatter",
        },
    ],
});

/** Simula que el usuario elige un archivo en un <input type=file>. */
function elegirArchivo(input, nombre, tipo, contenido) {
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(new File([contenido], nombre, { type: tipo }));
    input.files = dataTransfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
}

// Carga del FRU de una máquina liberada desde el portal web
registry.category("web_tour.tours").add("posventa_portal_cargar_certificado", {
    steps: () => [
        {
            content: "El wizard de certificados se monta en el portal",
            trigger: ".o_pv_portal .o_pv_frontend_wizard",
        },
        {
            content: "Paso 1: tipo y fecha (FRU por defecto)",
            trigger: ".pv-wizard-footer button.pv-btn-primary",
            run: "click",
        },
        {
            content: "Paso 2: adjuntar el PDF",
            trigger: ".pv-wizard-content input[type=file]",
            run() {
                elegirArchivo(this.anchor, "fru_tour.pdf", "application/pdf", "%PDF-1.4 tour");
            },
        },
        {
            content: "El archivo quedó cargado",
            trigger: ".pv-wizard-content:contains(fru_tour.pdf)",
        },
        {
            content: "Siguiente",
            trigger: ".pv-wizard-footer button.pv-btn-primary",
            run: "click",
        },
        {
            content: "Confirmar carga",
            trigger: ".pv-wizard-footer button.pv-btn-success",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "Vuelve al detalle de la máquina, ahora en STOCK con el FRU",
            trigger: ".o_pv_portal .badge:contains(STOCK)",
        },
    ],
});

// Adjuntar una foto a un ticket existente desde su detalle
/** Paso que elige la opción cuyo texto contiene `texto`, una vez cargada (los ids dependen de la base). */
function elegirOpcion(content, texto) {
    return {
        content,
        trigger: `.pv-wizard-content select:has(option:contains(${texto}))`,
        run() {
            this.anchor.value = [...this.anchor.options].find((o) => o.text.includes(texto)).value;
            this.anchor.dispatchEvent(new Event("change", { bubbles: true }));
        },
    };
}

// Reclamo Post-PM: catálogo en cascada, campo adicional obligatorio, problema no listado y foto adjunta
registry.category("web_tour.tours").add("posventa_portal_ticket_post_pm", {
    steps: () => [
        {
            content: "El wizard OWL se monta con el CPM preseleccionado",
            trigger: ".o_pv_portal .pv-wizard-content:contains(CPM)",
        },
        siguiente,
        elegirOpcion("Sistema", "Sistema Hidráulico"),
        elegirOpcion("Subsistema", "Válvula de Presión"),
        elegirOpcion("Problema no listado", "no está en la lista"),
        siguiente,
        {
            content: "Sin hectáreas no avanza",
            trigger: ".o_notification:contains(hectáreas)",
        },
        {
            content: "Hectáreas trabajadas",
            trigger: ".pv-wizard-content input[type=number]",
            run: "edit 350",
        },
        siguiente,
        {
            content: "Campo adicional del subsistema",
            trigger: ".pv-wizard-content .pv-form-group:contains(Presión medida) input",
            run: "edit 12 bar",
        },
        siguiente,
        {
            content: "Descripción del reclamo",
            trigger: ".pv-wizard-content textarea[placeholder*='Describa detalladamente']",
            run: "edit Pierde aceite la válvula (tour post-pm)",
        },
        {
            content: "Foto del problema",
            trigger: ".pv-wizard-content input[type=file][accept^=image]",
            run() {
                elegirArchivo(this.anchor, "valvula.png", "image/png", "PNGDATA");
            },
        },
        {
            content: "La foto queda en la lista",
            trigger: ".pv-wizard-content:contains(valvula.png)",
        },
        siguiente,
        {
            content: "El resumen muestra el problema no listado",
            trigger: ".pv-wizard-content:contains(No está en la lista)",
        },
        {
            content: "Guardar y enviar",
            trigger: ".pv-wizard-footer button.pv-btn-success:contains(Enviar)",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "Redirige al detalle del ticket, ya enviado",
            trigger: ".o_pv_portal .badge:contains(ABIERTO)",
        },
    ],
});

registry.category("web_tour.tours").add("posventa_portal_adjuntar_foto", {
    steps: () => [
        {
            content: "Elegir foto",
            trigger: ".o_pv_ticket_uploader input[type=file]",
            run() {
                elegirArchivo(this.anchor, "foto_tour.png", "image/png", "PNGDATA");
            },
        },
        {
            content: "Subir",
            trigger: ".o_pv_ticket_uploader button:contains(Subir)",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "La foto aparece en la lista de adjuntos",
            trigger: ".o_pv_portal a:contains(foto_tour.png)",
        },
    ],
});

