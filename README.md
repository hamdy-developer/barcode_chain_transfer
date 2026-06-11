# Barcode Chain Transfer

## Overview

This module adds a **two-step chain transfer** feature to the Odoo Barcode scanning interface. It allows users to configure a transit (intermediate) location and automatically create a second transfer upon validation of the first one.

## Features

- **Chain Transfer Icon**: A link/chain icon button in the barcode header that opens configuration dialog
- **Transit Location**: Set an intermediate location where goods will pass through
- **Destination Picking Type**: Define the operation type for the second (auto-created) transfer
- **End Location**: Set the final destination for the goods
- **Automatic Second Transfer**: On validation, a second transfer is automatically created with the same products
- **Shared Origin**: Both transfers share a unique chain reference (e.g., `CHAIN/00001`)
- **Visual Indicator**: The chain icon turns yellow/warning when chain transfer is configured
- **Destination Location Auto-Sync**: Setting a Transit Location automatically updates the first picking's Destination Location (`location_dest_id`) and its moves to ensure correct physical routing
- **Manager Approval Flow**: Supports requiring Inventory Manager approval before a chain transfer can be validated (configurable in Settings)

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
   - Generates a chain reference and sets it as the origin on both transfers
   - Confirms the second transfer (marks as TODO)

## Dependencies

- `stock`
- `stock_barcode` (Enterprise)

## Author

ENG/Mohamed Hamdy
