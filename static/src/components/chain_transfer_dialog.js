/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

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
            // UI state
            searchingTransit: false,
            searchingPickingType: false,
            searchingEndLocation: false,
            transitSearch: "",
            pickingTypeSearch: "",
            endLocationSearch: "",
            chainState: "draft",
            approveChainByManager: false,
            saving: false,
        });

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
                try {
                    const results = await rpc(
                        "/barcode_chain_transfer/get_picking_types",
                        { search_term: this.state.destPickingTypeName }
                    );
                    const pt = results.find(r => r.id === this.state.destPickingTypeId);
                    if (pt && pt.default_dest_location_id) {
                        this.state.endLocationId = pt.default_dest_location_id;
                        this.state.endLocationName = pt.default_dest_location_name;
                        this.state.endLocationSearch = pt.default_dest_location_name;
                    }
                } catch (error) {
                    console.error("Error auto-filling default destination location on load:", error);
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

    // --- Transit Location Search ---

    async onTransitSearchInput(ev) {
        const searchTerm = ev.target.value;
        this.state.transitSearch = searchTerm;
        if (searchTerm.length >= 1) {
            this.state.searchingTransit = true;
            this.state.locationResults = await rpc(
                "/barcode_chain_transfer/get_locations",
                { search_term: searchTerm }
            );
        } else {
            this.state.searchingTransit = true;
            this.state.locationResults = await rpc(
                "/barcode_chain_transfer/get_locations",
                { search_term: "" }
            );
        }
    }

    onTransitFocus() {
        this.onTransitSearchInput({ target: { value: this.state.transitSearch } });
    }

    selectTransitLocation(location) {
        const locId = location.id;
        const locName = location.display_name;
        this.state.transitLocationId = locId;
        this.state.transitLocationName = locName;
        this.state.transitSearch = locName;
        this.state.searchingTransit = false;
        this.state.locationResults = [];
    }

    clearTransitLocation() {
        this.state.transitLocationId = false;
        this.state.transitLocationName = "";
        this.state.transitSearch = "";
    }

    // --- Destination Picking Type Search ---

    async onPickingTypeSearchInput(ev) {
        const searchTerm = ev.target.value;
        this.state.pickingTypeSearch = searchTerm;
        if (searchTerm.length >= 1) {
            this.state.searchingPickingType = true;
            this.state.pickingTypeResults = await rpc(
                "/barcode_chain_transfer/get_picking_types",
                { search_term: searchTerm }
            );
        } else {
            this.state.searchingPickingType = true;
            this.state.pickingTypeResults = await rpc(
                "/barcode_chain_transfer/get_picking_types",
                { search_term: "" }
            );
        }
    }

    onPickingTypeFocus() {
        this.onPickingTypeSearchInput({ target: { value: this.state.pickingTypeSearch } });
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
        this.state.searchingPickingType = false;
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

    // --- End Location Search ---

    async onEndLocationSearchInput(ev) {
        const searchTerm = ev.target.value;
        this.state.endLocationSearch = searchTerm;
        if (searchTerm.length >= 1) {
            this.state.searchingEndLocation = true;
            this.state.endLocationResults = await rpc(
                "/barcode_chain_transfer/get_locations",
                { search_term: searchTerm }
            );
        } else {
            this.state.searchingEndLocation = true;
            this.state.endLocationResults = await rpc(
                "/barcode_chain_transfer/get_locations",
                { search_term: "" }
            );
        }
    }

    onEndLocationFocus() {
        this.onEndLocationSearchInput({ target: { value: this.state.endLocationSearch } });
    }

    selectEndLocation(location) {
        const locId = location.id;
        const locName = location.display_name;
        this.state.endLocationId = locId;
        this.state.endLocationName = locName;
        this.state.endLocationSearch = locName;
        this.state.searchingEndLocation = false;
        this.state.endLocationResults = [];
    }

    clearEndLocation() {
        this.state.endLocationId = false;
        this.state.endLocationName = "";
        this.state.endLocationSearch = "";
    }

    onPutawayRulesChange(ev) {
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
            const result = await rpc(
                "/barcode_chain_transfer/save_chain_data",
                {
                    picking_id: this.props.pickingId,
                    transit_location_id: this.state.transitLocationId,
                    dest_picking_type_id: this.state.destPickingTypeId,
                    end_location_id: this.state.endLocationId,
                    chain_use_putaway_rules: this.state.usePutawayRules,
                }
            );
            if (result.success) {
                this.props.onApply(result);
                this.props.close();
            }
        } finally {
            this.state.saving = false;
        }
    }

    async onClear() {
        this.state.saving = true;
        try {
            const result = await rpc(
                "/barcode_chain_transfer/clear_chain_data",
                { picking_id: this.props.pickingId }
            );
            if (result.success) {
                this.clearTransitLocation();
                this.clearPickingType();
                this.clearEndLocation();
                if (this.props.onClear) {
                    this.props.onClear();
                }
                this.props.close();
            }
        } finally {
            this.state.saving = false;
        }
    }

    onCloseDropdowns() {
        this.state.searchingTransit = false;
        this.state.searchingPickingType = false;
        this.state.searchingEndLocation = false;
    }
}
