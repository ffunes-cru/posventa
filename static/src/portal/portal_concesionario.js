/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

import { TicketWizard } from "./wizards/ticket_wizard";
import { CertificadoWizard } from "./wizards/certificado_wizard";

export class PortalConcesionario extends Component {
    static template = "posventa.PortalConcesionario";
    static components = { TicketWizard, CertificadoWizard };
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            view: "home",
            loading: true,
            loadingMaquinas: false,
            // Home data
            portalData: null,
            // Machine list
            maquinas: [],
            searchTerm: "",
            estadoFilter: "",
            // Machine detail
            maquinaDetail: null,
            selectedMaquinaId: null,
        });

        this.searchTimeout = null;
        onWillStart(() => this.loadPortalData());
    }

    async loadPortalData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("pv.dashboard", "get_concesionario_portal_data", []);
            if (data.error) {
                this.notification.add(data.error, { type: "danger" });
                this.state.portalData = null;
            } else {
                this.state.portalData = data;
            }
        } catch (e) {
            this.notification.add(_t("Error al cargar datos del portal."), { type: "danger" });
        }
        this.state.loading = false;
    }

    // ==================== Navigation ====================

    navigateTo(view, params = {}) {
        this.state.view = view;
        if (params.maquinaId) {
            this.state.selectedMaquinaId = params.maquinaId;
        }
    }

    goHome() {
        this.state.view = "home";
        this.loadPortalData();
    }

    goToHome() {
        this.goHome();
    }

    async goToMaquinas() {
        this.state.view = "maquinas";
        this.state.searchTerm = "";
        this.state.estadoFilter = "";
        await this.loadMaquinas(true);
    }

    async goToMaquinaDetail(maquinaId) {
        this.state.view = "maquina_detail";
        this.state.selectedMaquinaId = maquinaId;
        await this.loadMaquinaDetail(maquinaId);
    }

    goToTicketWizard(maquinaId) {
        this.state.view = "ticket_wizard";
        this.state.selectedMaquinaId = maquinaId;
    }

    goToCertificadoWizard(maquinaId) {
        this.state.view = "certificado_wizard";
        this.state.selectedMaquinaId = maquinaId;
    }

    // ==================== Data Loading ====================

    async loadMaquinas(showFullLoader = false) {
        if (showFullLoader) {
            this.state.loading = true;
        } else {
            this.state.loadingMaquinas = true;
        }
        try {
            const data = await this.orm.call("pv.maquina", "get_portal_list_data", [], {
                search_term: this.state.searchTerm,
                estado_filter: this.state.estadoFilter,
            });
            this.state.maquinas = data;
        } catch (e) {
            this.notification.add(_t("Error al cargar máquinas."), { type: "danger" });
        } finally {
            if (showFullLoader) {
                this.state.loading = false;
            } else {
                this.state.loadingMaquinas = false;
            }
        }
    }

    async loadMaquinaDetail(maquinaId) {
        this.state.loading = true;
        this.state.maquinaDetail = null;
        try {
            const data = await this.orm.call("pv.maquina", "get_portal_detail_data", [maquinaId]);
            this.state.maquinaDetail = data;
        } catch (e) {
            this.notification.add(_t("Error al cargar detalle de máquina."), { type: "danger" });
        }
        this.state.loading = false;
    }

    // ==================== Machine List Actions ====================

    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
        this.searchTimeout = setTimeout(() => {
            this.loadMaquinas(false);
        }, 250);
    }

    setEstadoFilter(estado) {
        this.state.estadoFilter = this.state.estadoFilter === estado ? "" : estado;
        this.state.view = "maquinas";
        this.loadMaquinas(false);
    }

    // ==================== Transfer Actions ====================

    async openTransferModal() {
        try {
            const data = await this.orm.call("pv.maquina", "get_transfer_catalog_data", []);
            const myConcesionarioId = this.state.portalData?.concesionario_id;
            this.state.transferConcesionarios = (data.concesionarios || []).filter(c => c.id !== myConcesionarioId);
            this.state.transferProvincias = data.provincias || [];
            this.state.transferConcesionarioId = false;
            this.state.transferProvinciaId = false;
            this.state.transferCiudad = "";
            this.state.showTransferModal = true;
        } catch (e) {
            this.notification.add(_t("Error al obtener catálogo de transferencia."), { type: "danger" });
        }
    }

    closeTransferModal() {
        this.state.showTransferModal = false;
    }

    async submitTransferModal() {
        if (!this.state.transferConcesionarioId) {
            this.notification.add(_t("Seleccione el concesionario destino."), { type: "warning" });
            return;
        }
        if (!this.state.transferProvinciaId) {
            this.notification.add(_t("Seleccione la provincia destino."), { type: "warning" });
            return;
        }
        if (!this.state.transferCiudad || !this.state.transferCiudad.trim()) {
            this.notification.add(_t("Ingrese la ciudad destino."), { type: "warning" });
            return;
        }

        this.state.submittingTransfer = true;
        try {
            await this.orm.call("pv.maquina", "action_iniciar_transferencia_portal", [
                this.state.selectedMaquinaId,
                parseInt(this.state.transferConcesionarioId),
                parseInt(this.state.transferProvinciaId),
                this.state.transferCiudad,
            ]);
            this.notification.add(_t("Solicitud de traslado iniciada exitosamente."), { type: "success" });
            this.closeTransferModal();
            await this.loadMaquinaDetail(this.state.selectedMaquinaId);
        } catch (e) {
            this.notification.add(e.data?.message || e.message || _t("Error al iniciar traslado."), { type: "danger" });
        } finally {
            this.state.submittingTransfer = false;
        }
    }

    async aceptarTransferencia(maquinaId) {
        try {
            await this.orm.call("pv.maquina", "action_aceptar_transferencia", [maquinaId]);
            this.notification.add(_t("Transferencia aceptada exitosamente."), { type: "success" });
            await this.loadMaquinaDetail(maquinaId);
        } catch (e) {
            this.notification.add(e.data?.message || _t("Error al aceptar transferencia."), { type: "danger" });
        }
    }

    async rechazarTransferencia(maquinaId) {
        try {
            await this.orm.call("pv.maquina", "action_rechazar_transferencia", [maquinaId]);
            this.notification.add(_t("Transferencia rechazada."), { type: "warning" });
            await this.loadMaquinaDetail(maquinaId);
        } catch (e) {
            this.notification.add(e.data?.message || _t("Error al rechazar transferencia."), { type: "danger" });
        }
    }

    async cancelarTransferencia(maquinaId) {
        try {
            await this.orm.call("pv.maquina", "action_cancelar_transferencia", [maquinaId]);
            this.notification.add(_t("Solicitud de traslado cancelada."), { type: "info" });
            await this.loadMaquinaDetail(maquinaId);
        } catch (e) {
            this.notification.add(e.data?.message || _t("Error al cancelar traslado."), { type: "danger" });
        }
    }

    async liberarMaquina(maquinaId) {
        if (!confirm(_t("¿Está seguro de LIBERAR esta máquina? Sus certificados vigentes actuales quedarán marcados como 'Archivado Manualmente' y quedará disponible para cargar nuevos certificados desde cero."))) {
            return;
        }
        try {
            await this.orm.call("pv.maquina", "action_liberar_maquina", [maquinaId]);
            this.notification.add(_t("La máquina ha sido liberada exitosamente."), { type: "info" });
            await this.loadMaquinaDetail(maquinaId);
        } catch (e) {
            this.notification.add(e.data?.message || _t("Error al liberar máquina."), { type: "danger" });
        }
    }

    // ==================== Ticket navigation (opens standard Odoo view in readonly) ====================

    openTicketsByEstado(estado) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Mis Tickets — %s", estado.toUpperCase()),
            res_model: "pv.ticket",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [["estado", "=", estado]],
            target: "current",
            context: { create: false },
        });
    }

    // ==================== Breadcrumb helper ====================

    get breadcrumbs() {
        const crumbs = [{ label: _t("Inicio"), action: () => this.goHome() }];
        if (this.state.view === "maquinas") {
            crumbs.push({ label: _t("Máquinas"), action: null });
        } else if (this.state.view === "maquina_detail") {
            crumbs.push({ label: _t("Máquinas"), action: () => this.goToMaquinas() });
            crumbs.push({ label: this.state.maquinaDetail?.name || "...", action: null });
        } else if (this.state.view === "ticket_wizard") {
            crumbs.push({ label: _t("Máquinas"), action: () => this.goToMaquinas() });
            crumbs.push({ label: this.state.maquinaDetail?.name || "...", action: () => this.goToMaquinaDetail(this.state.selectedMaquinaId) });
            crumbs.push({ label: _t("Nuevo Ticket"), action: null });
        } else if (this.state.view === "certificado_wizard") {
            crumbs.push({ label: _t("Máquinas"), action: () => this.goToMaquinas() });
            crumbs.push({ label: this.state.maquinaDetail?.name || "...", action: () => this.goToMaquinaDetail(this.state.selectedMaquinaId) });
            crumbs.push({ label: _t("Nuevo Certificado"), action: null });
        }
        return crumbs;
    }
}

registry.category("actions").add("pv_portal_concesionario", PortalConcesionario);
