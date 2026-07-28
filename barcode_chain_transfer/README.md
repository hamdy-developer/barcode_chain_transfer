# Barcode Chain Transfer

## Overview

This module adds a **two-step chain transfer** feature to the Odoo Barcode scanning interface. It allows users to configure a transit (intermediate) location and automatically create a second transfer upon validation of the first one.

## Features

- **Chain Transfer Icon**: A link/chain icon button in the barcode header that opens configuration dialog
- **Transit Location**: Set an intermediate location where goods will pass through
- **Destination Picking Type**: Define the operation type for the second (auto-created) transfer
- **End Location**: Set the final destination for the goods
- **Automatic Second Transfer**: On validation, a second transfer is automatically created with the quantities that were actually received
- **Shared Origin**: Both transfers share a unique chain reference (e.g., `CHAIN/00001`)
- **Visual Indicator**: The chain icon turns yellow/warning when chain transfer is configured
- **Destination Location Auto-Sync**: Setting a Transit Location automatically updates the first picking's Destination Location (`location_dest_id`) and its moves to ensure correct physical routing
- **Manager Approval Flow**: Supports requiring Inventory Manager approval before a chain transfer can be validated (configurable in Settings)
- **Backorder Aware**: A backorder inherits the whole chain configuration, so the remaining goods travel the same route
- **Pre-flight Validation**: The chain setup is verified *before* the transfer is validated, so a misconfiguration can never discard a scanning session

## Behaviour Notes

- **Quantities**: the second transfer carries the quantities that were really
  moved (the done quantities), not the original demand. Whatever is left goes
  to the backorder, which starts its own chain when it is validated in turn.
- **Origin**: the chain reference is *appended* to the source document rather
  than replacing it, so a receipt keeps its purchase order reference
  (`PO00042 - CHAIN/00001`). The second transfer's origin is the chain
  reference alone.
- **Lots / Serials**: the second transfer is created without pre-assigned lots
  on purpose. The operator handling the transit-to-final step scans the goods
  again, which double-checks what physically arrived.
- **Approval**: `chain_state` can only be changed through the **Approve Chain**
  button; a direct write is rejected. Re-saving an unchanged configuration
  keeps an existing approval, changing the routing revokes it.
- **Destination**: while a Transit Location is set, the transfer's destination
  is continuously realigned to it - including after an operation type change,
  which core resets to the operation type's own default.

## Workflow

1. Open the **Barcode** app → select an operation type → create a new transfer
2. Click the **🔗 Chain Transfer** icon in the header
3. Fill in:
   - **Transit Location** (becomes the destination of the current transfer)
   - **Destination Picking Type** (operation type for the 2nd transfer)
   - **End Location** (final destination)
4. Click **Apply**
5. Scan products as usual
6. Click **Validate**
7. The system automatically:
   - Validates the first transfer (to the transit location)
   - Creates a second transfer (from transit to end location)
   - Generates a chain reference, stamps it on both transfers and appends it to the source document
   - Confirms the second transfer (marks as TODO)

## Testing

```bash
odoo-bin -d <db> -u barcode_chain_transfer --test-enable --test-tags=/barcode_chain_transfer --stop-after-init
```

The tour test (`TestChainTransferTour`) additionally needs `websocket-client`
and a Chrome binary; without them Odoo skips it.

## Dependencies

- `stock`
- `stock_barcode` (Enterprise)

## Author

ENG/Mohamed Hamdy
