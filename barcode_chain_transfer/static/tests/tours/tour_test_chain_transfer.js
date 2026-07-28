/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Regression tour for the chain transfer dialog.
 *
 * The dialog resolves the display names of the transit location, the end
 * location and the destination operation type through the barcode cache.
 * Those records are not part of the payload core builds, so the client action
 * used to crash as soon as the dialog was reopened on a configured transfer.
 * This tour opens it twice on purpose.
 */
registry.category("web_tour.tours").add("test_chain_transfer_dialog_reopen", {
    steps: () => [
        {
            content: "Open the chain transfer dialog",
            trigger: ".o_chain_transfer_btn",
            run: "click",
        },
        {
            content: "The transit location is pre-filled with its display name",
            trigger: ".o_chain_transfer_dialog .badge:contains('Test Transit Zone')",
        },
        {
            content: "The destination operation type is pre-filled",
            trigger: ".o_chain_transfer_dialog .badge:contains('Test Chain Internal')",
        },
        {
            content: "The end location is pre-filled",
            trigger: ".o_chain_transfer_dialog .badge:contains('Test End Location')",
        },
        {
            content: "Close the dialog",
            trigger: ".modal-footer .btn-secondary",
            run: "click",
        },
        {
            content: "The barcode screen is still alive",
            trigger: ".o_barcode_client_action",
        },
        {
            content: "Reopen the dialog: this is what used to crash",
            trigger: ".o_chain_transfer_btn",
            run: "click",
        },
        {
            content: "The transit location is still resolved",
            trigger: ".o_chain_transfer_dialog .badge:contains('Test Transit Zone')",
        },
        {
            content: "Close the dialog again",
            trigger: ".modal-footer .btn-secondary",
            run: "click",
        },
        {
            content: "Validate the transfer",
            trigger: ".o_validate_page",
            run: "click",
        },
        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});
