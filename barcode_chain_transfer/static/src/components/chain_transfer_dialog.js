/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

// Handheld scanners are often on a weak warehouse network: searching on every
// keystroke would queue a request per character.
const SEARCH_DELAY = 250;

/**
 * ChainTransferDialog
 *
 * OWL dialog for configuring chain transfer fields on a picking
 * from within the barcode scanning interface.
 *
 * Provides searchable dropdowns for:
 *  - Transit Location (stock.location)
 *  - Destination Picking Type (stock.picking.type)
 *  - End Location (stock.location)
 */
export class ChainTransferDialog extends Component {
    static template = "barcode_chain_transfer.ChainTransferDialog";
    static components = { Dialog };
    static props = {
        pickingId: { type: Number },
        currentChainData: { type: Object, optional: true },
        onApply: { type: Function },
        onClear: { type: Function, optional: true },
        close: { type: Function },
    };

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            // Selected values
            transitLocationId: false,
            transitLocationName: "",
            destPickingTypeId: false,
            destPickingTypeName: "",
            endLocationId: false,
            endLocationName: "",
            // Search results
            locationResults: [],
            pickingTypeResults: [],
            endLocationResults: [],
            usePutawayRules: false,
            // Dropdown visibility
            transitOpen: false,
            pickingTypeOpen: false,
            endLocationOpen: false,
            // In-flight searches
            transitLoading: false,
            pickingTypeLoading: false,
            endLocationLoading: false,
            transitSearch: "",
            pickingTypeSearch: "",
            endLocationSearch: "",
            chainState: "draft",
            approveChainByManager: false,
            saving: false,
        });

        // Discards responses that come back after a newer search was fired.
        this._searchSequence = { transit: 0, pickingType: 0, endLocation: 0 };

        this.searchTransitDebounced = useDebounced(
            () => this._searchLocations("transit"), SEARCH_DELAY
        );
        this.searchPickingTypeDebounced = useDebounced(
            () => this._searchPickingTypes(), SEARCH_DELAY
        );
        this.searchEndLocationDebounced = useDebounced(
            () => this._searchLocations("endLocation"), SEARCH_DELAY
        );

        onWillStart(async () => {
            // Pre-fill from existing chain data if available
            const data = this.props.currentChainData || {};
            if (data.chain_transit_location_id) {
                this.state.transitLocationId = data.chain_transit_location_id;
                this.state.transitLocationName = data.chain_transit_location_name || "";
                this.state.transitSearch = data.chain_transit_location_name || "";
            } else if (data.company_chain_transit_location_id) {
                this.state.transitLocationId = data.company_chain_transit_location_id;
                this.state.transitLocationName = data.company_chain_transit_location_name || "";
                this.state.transitSearch = data.company_chain_transit_location_name || "";
            }
            if (data.chain_dest_picking_type_id) {
                this.state.destPickingTypeId = data.chain_dest_picking_type_id;
                this.state.destPickingTypeName = data.chain_dest_picking_type_name || "";
                this.state.pickingTypeSearch = data.chain_dest_picking_type_name || "";
            }
            if (data.chain_end_location_id) {
                this.state.endLocationId = data.chain_end_location_id;
                this.state.endLocationName = data.chain_end_location_name || "";
                this.state.endLocationSearch = data.chain_end_location_name || "";
            }
            this.state.usePutawayRules = data.chain_use_putaway_rules || false;
            this.state.chainState = data.chain_state || "draft";
            this.state.approveChainByManager = data.approve_chain_by_manager || false;

            // Auto-fill End Location on load if Picking Type is set but End Location is empty
            if (this.state.destPickingTypeId && !this.state.endLocationId) {
                const results = await this._rpcSafe(
                    "/barcode_chain_transfer/get_picking_types",
                    { search_term: this.state.destPickingTypeName }
                );
                const pt = (results || []).find(r => r.id === this.state.destPickingTypeId);
                if (pt && pt.default_dest_location_id) {
                    this.state.endLocationId = pt.default_dest_location_id;
                    this.state.endLocationName = pt.default_dest_location_name;
                    this.state.endLocationSearch = pt.default_dest_location_name;
                }
            }
        });
    }

    get dialogTitle() {
        return _t("Chain Transfer Settings");
    }

    get canApply() {
        return (
            this.state.transitLocationId &&
            this.state.destPickingTypeId &&
            (this.state.endLocationId || this.state.usePutawayRules) &&
            !this.state.saving
        );
    }

    get hasChainData() {
        return (
            this.state.transitLocationId ||
            this.state.destPickingTypeId ||
            this.state.endLocationId ||
            this.state.usePutawayRules
        );
    }

    /**
     * Perform an RPC and surface any failure as a notification.
     *
     * A dropped connection in the middle of a warehouse must not throw the
     * operator into the generic crash dialog.
     * @returns {Promise<any|null>} the result, or null when the call failed
     */
    async _rpcSafe(route, params) {
        try {
            return await rpc(route, params);
        } catch (error) {
            this.notification.add(
                error.data && error.data.message
                    ? error.data.message
                    : _t("The server could not be reached. Please try again."),
                { type: "danger" }
            );
            return null;
        }
    }

    // --- Searches ---

    /**
     * @param {"transit"|"endLocation"} target which location field is searched
     */
    async _searchLocations(target) {
        const isTransit = target === "transit";
        const loadingKey = isTransit ? "transitLoading" : "endLocationLoading";
        const resultsKey = isTransit ? "locationResults" : "endLocationResults";
        const term = isTransit ? this.state.transitSearch : this.state.endLocationSearch;

        const sequence = ++this._searchSequence[target];
        this.state[loadingKey] = true;
        const results = await this._rpcSafe(
            "/barcode_chain_transfer/get_locations", { search_term: term }
        );
        if (sequence !== this._searchSequence[target]) {
            return; // A newer search already took over.
        }
        this.state[loadingKey] = false;
        this.state[resultsKey] = results || [];
    }

    async _searchPickingTypes() {
        const sequence = ++this._searchSequence.pickingType;
        this.state.pickingTypeLoading = true;
        const results = await this._rpcSafe(
            "/barcode_chain_transfer/get_picking_types",
            { search_term: this.state.pickingTypeSearch }
        );
        if (sequence !== this._searchSequence.pickingType) {
            return;
        }
        this.state.pickingTypeLoading = false;
        this.state.pickingTypeResults = results || [];
    }

    // --- Transit Location ---

    onTransitSearchInput(ev) {
        this.state.transitSearch = ev.target.value;
        this.state.transitOpen = true;
        this.searchTransitDebounced();
    }

    onTransitFocus() {
        this.state.transitOpen = true;
        this.searchTransitDebounced();
    }

    selectTransitLocation(location) {
        const locId = location.id;
        const locName = location.display_name;
        this.state.transitLocationId = locId;
        this.state.transitLocationName = locName;
        this.state.transitSearch = locName;
        this.state.transitOpen = false;
        this.state.locationResults = [];
    }

    clearTransitLocation() {
        this.state.transitLocationId = false;
        this.state.transitLocationName = "";
        this.state.transitSearch = "";
    }

    // --- Destination Picking Type ---

    onPickingTypeSearchInput(ev) {
        this.state.pickingTypeSearch = ev.target.value;
        this.state.pickingTypeOpen = true;
        this.searchPickingTypeDebounced();
    }

    onPickingTypeFocus() {
        this.state.pickingTypeOpen = true;
        this.searchPickingTypeDebounced();
    }

    selectPickingType(pickingType) {
        // Extract ALL values from the reactive proxy BEFORE clearing the
        // results array, because OWL's reactive proxy may lose its target
        // once the parent array is replaced with a new empty array.
        const ptId = pickingType.id;
        const ptDisplayName = pickingType.display_name;
        const defaultDestLocId = pickingType.default_dest_location_id;
        const defaultDestLocName = pickingType.default_dest_location_name;

        this.state.destPickingTypeId = ptId;
        this.state.destPickingTypeName = ptDisplayName;
        this.state.pickingTypeSearch = ptDisplayName;
        this.state.pickingTypeOpen = false;
        this.state.pickingTypeResults = [];

        // Auto-fill End Location from the selected Picking Type's default
        if (defaultDestLocId) {
            this.state.endLocationId = defaultDestLocId;
            this.state.endLocationName = defaultDestLocName;
            this.state.endLocationSearch = defaultDestLocName;
        }
    }

    clearPickingType() {
        this.state.destPickingTypeId = false;
        this.state.destPickingTypeName = "";
        this.state.pickingTypeSearch = "";
        this.clearEndLocation();
    }

    // --- End Location ---

    onEndLocationSearchInput(ev) {
        this.state.endLocationSearch = ev.target.value;
        this.state.endLocationOpen = true;
        this.searchEndLocationDebounced();
    }

    onEndLocationFocus() {
        this.state.endLocationOpen = true;
        this.searchEndLocationDebounced();
    }

    selectEndLocation(location) {
        const locId = location.id;
        const locName = location.display_name;
        this.state.endLocationId = locId;
        this.state.endLocationName = locName;
        this.state.endLocationSearch = locName;
        this.state.endLocationOpen = false;
        this.state.endLocationResults = [];
    }

    clearEndLocation() {
        this.state.endLocationId = false;
        this.state.endLocationName = "";
        this.state.endLocationSearch = "";
    }

    onPutawayRulesChange() {
        if (this.state.usePutawayRules) {
            this.clearEndLocation();
        }
    }

    // --- Actions ---

    async onApply() {
        if (!this.canApply) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this._rpcSafe(
                "/barcode_chain_transfer/save_chain_data",
                {
                    picking_id: this.props.pickingId,
                    transit_location_id: this.state.transitLocationId,
                    dest_picking_type_id: this.state.destPickingTypeId,
                    end_location_id: this.state.endLocationId,
                    chain_use_putaway_rules: this.state.usePutawayRules,
                }
            );
            if (!result) {
                return; // The RPC failed and was already reported.
            }
            if (!result.success) {
                this.notification.add(
                    result.error || _t("The chain transfer could not be saved."),
                    { type: "danger" }
                );
                return;
            }
            this.props.onApply(result);
            this.props.close();
        } finally {
            this.state.saving = false;
        }
    }

    async onClear() {
        this.state.saving = true;
        try {
            const result = await this._rpcSafe(
                "/barcode_chain_transfer/clear_chain_data",
                { picking_id: this.props.pickingId }
            );
            if (!result) {
                return;
            }
            if (!result.success) {
                this.notification.add(
                    result.error || _t("The chain transfer could not be cleared."),
                    { type: "danger" }
                );
                return;
            }
            this.clearTransitLocation();
            this.clearPickingType();
            this.clearEndLocation();
            this.state.usePutawayRules = false;
            if (this.props.onClear) {
                this.props.onClear();
            }
            this.props.close();
        } finally {
            this.state.saving = false;
        }
    }

    onCloseDropdowns() {
        this.state.transitOpen = false;
        this.state.pickingTypeOpen = false;
        this.state.endLocationOpen = false;
    }
}
