/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import MainComponent from "@stock_barcode/components/main";
import { ChainTransferDialog } from "./chain_transfer_dialog";

/**
 * Patch the MainComponent to add chain transfer button functionality.
 *
 * Adds a chain transfer icon to the barcode header that opens a dialog
 * for configuring transit location, destination picking type, and end location.
 */
patch(MainComponent.prototype, {

    /**
     * Check if the chain transfer button should be displayed.
     * Only show for stock.picking model (not stock.quant/inventory).
     * @returns {boolean}
     */
    get displayChainTransferButton() {
        return this.resModel === "stock.picking" && this.env.model.canBeProcessed;
    },

    /**
     * Check if chain transfer is configured on the current picking.
     * Used to show a visual indicator (colored icon) when configured.
     * @returns {boolean}
     */
    get hasChainTransferConfigured() {
        const record = this.env.model.record;
        return (
            record &&
            record.chain_transit_location_id &&
            record.chain_dest_picking_type_id &&
            (record.chain_end_location_id || record.chain_use_putaway_rules)
        );
    },

    /**
     * Open the chain transfer configuration dialog.
     * Pre-fills with existing chain data if available.
     */
    openChainTransferDialog() {
        const record = this.env.model.record;
        const currentChainData = {};

        if (record.chain_transit_location_id) {
            const val = record.chain_transit_location_id;
            currentChainData.chain_transit_location_id = Array.isArray(val) ? val[0] : (typeof val === 'object' ? val.id : val);
            currentChainData.chain_transit_location_name = Array.isArray(val) ? val[1] : "";
            if (!currentChainData.chain_transit_location_name && currentChainData.chain_transit_location_id) {
                const loc = this.env.model.cache.getRecord("stock.location", currentChainData.chain_transit_location_id);
                currentChainData.chain_transit_location_name = loc ? loc.display_name : "";
            }
        }
        if (record.chain_dest_picking_type_id) {
            const val = record.chain_dest_picking_type_id;
            currentChainData.chain_dest_picking_type_id = Array.isArray(val) ? val[0] : (typeof val === 'object' ? val.id : val);
            currentChainData.chain_dest_picking_type_name = Array.isArray(val) ? val[1] : "";
            if (!currentChainData.chain_dest_picking_type_name && currentChainData.chain_dest_picking_type_id) {
                const pt = this.env.model.cache.getRecord("stock.picking.type", currentChainData.chain_dest_picking_type_id);
                currentChainData.chain_dest_picking_type_name = pt ? pt.display_name : "";
            }
        }
        if (record.chain_end_location_id) {
            const val = record.chain_end_location_id;
            currentChainData.chain_end_location_id = Array.isArray(val) ? val[0] : (typeof val === 'object' ? val.id : val);
            currentChainData.chain_end_location_name = Array.isArray(val) ? val[1] : "";
            if (!currentChainData.chain_end_location_name && currentChainData.chain_end_location_id) {
                const loc = this.env.model.cache.getRecord("stock.location", currentChainData.chain_end_location_id);
                currentChainData.chain_end_location_name = loc ? loc.display_name : "";
            }
        }
        
        // Pass the default company transit location if any
        if (record.company_chain_transit_location_id) {
            const val = record.company_chain_transit_location_id;
            currentChainData.company_chain_transit_location_id = Array.isArray(val) ? val[0] : (typeof val === 'object' ? val.id : val);
            currentChainData.company_chain_transit_location_name = Array.isArray(val) ? val[1] : "";
        }

        currentChainData.chain_use_putaway_rules = record.chain_use_putaway_rules || false;
        currentChainData.chain_state = record.chain_state || "draft";
        currentChainData.approve_chain_by_manager = record.approve_chain_by_manager || false;

        this.dialog.add(ChainTransferDialog, {
            pickingId: this.resId,
            currentChainData: currentChainData,
            onApply: (result) => {
                // Update the record in the model cache
                if (this.env.model.record) {
                    this.env.model.record.chain_transit_location_id = result.chain_transit_location_id;
                    this.env.model.record.chain_dest_picking_type_id = result.chain_dest_picking_type_id;
                    this.env.model.record.chain_end_location_id = result.chain_end_location_id;
                    this.env.model.record.chain_use_putaway_rules = result.chain_use_putaway_rules;
                    this.env.model.record.chain_state = 'draft';
                    // Update location_dest_id to transit location
                    this.env.model.record.location_dest_id = result.chain_transit_location_id;
                }
                // Refresh the state to reflect new destination
                this._onRefreshState({});
            },
            onClear: () => {
                if (this.env.model.record) {
                    this.env.model.record.chain_transit_location_id = false;
                    this.env.model.record.chain_dest_picking_type_id = false;
                    this.env.model.record.chain_end_location_id = false;
                    this.env.model.record.chain_use_putaway_rules = false;
                    this.env.model.record.chain_state = 'draft';
                }
                this._onRefreshState({});
            },
        });
    },
});

// Register ChainTransferDialog as a sub-component of MainComponent
MainComponent.components = {
    ...MainComponent.components,
    ChainTransferDialog,
};
