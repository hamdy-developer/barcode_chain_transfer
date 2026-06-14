# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    """Inherit stock.picking to add chain transfer functionality.

    When chain transfer fields are filled and the picking is validated,
    a second transfer is automatically created from the transit location
    to the end location with the same products.
    """

    _inherit = 'stock.picking'

    chain_transit_location_id = fields.Many2one(
        'stock.location',
        string='Transit Location',
        help="Intermediate transit location. When set, this becomes the "
             "destination of the current transfer, and a second transfer "
             "is created from here to the End Location upon validation.",
        copy=False,
    )
    chain_dest_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Destination Picking Type',
        help="The picking type for the automatically created second transfer.",
        copy=False,
    )
    chain_end_location_id = fields.Many2one(
        'stock.location',
        string='End Location',
        help="The final destination location for the second transfer.",
        copy=False,
    )
    chain_origin = fields.Char(
        string='Chain Reference',
        help="Auto-generated reference shared by both chain transfers.",
        copy=False,
        readonly=True,
    )
    chain_state = fields.Selection(
        [('draft', 'Draft'), ('approved', 'Approved')],
        string='Chain State',
        default='draft',
        copy=False,
        readonly=True,
        help="Approval state of the chain transfer. Requires manager "
             "approval if enabled in settings."
    )
    approve_chain_by_manager = fields.Boolean(
        string='Approve Chain by Manager',
        related='company_id.approve_chain_by_manager',
        readonly=True,
    )
    company_chain_transit_location_id = fields.Many2one(
        'stock.location',
        related='company_id.company_chain_transit_location_id',
        readonly=True,
    )
    chain_use_putaway_rules = fields.Boolean(
        string='Use Putaway Rules',
        copy=False,
        help="If checked, the end location is determined automatically by Odoo's putaway rules.",
    )

    @api.depends('picking_type_id', 'partner_id', 'chain_transit_location_id')
    def _compute_location_id(self) -> None:
        """Override to set Destination Location to Transit Location if configured."""
        super()._compute_location_id()
        for picking in self:
            if picking.chain_transit_location_id:
                picking.location_dest_id = picking.chain_transit_location_id

    @api.model_create_multi
    def create(self, vals_list: list) -> models.BaseModel:
        """Override create to enforce Destination Location matching Transit Location."""
        for vals in vals_list:
            transit_loc = vals.get('chain_transit_location_id')
            if transit_loc:
                vals['location_dest_id'] = transit_loc
                # Propagate to moves inside vals
                for move_field in ('move_ids',):
                    if move_field in vals and isinstance(vals[move_field], list):
                        for command in vals[move_field]:
                            if isinstance(command, (list, tuple)) and len(command) >= 3:
                                cmd_type = command[0]
                                cmd_vals = command[2]
                                if cmd_type in (0, 1) and isinstance(cmd_vals, dict):
                                    cmd_vals['location_dest_id'] = transit_loc

            # Auto-fill End Location if not set
            dest_picking_type = vals.get('chain_dest_picking_type_id')
            if dest_picking_type and not vals.get('chain_end_location_id'):
                picking_type = self.env['stock.picking.type'].browse(dest_picking_type)
                if picking_type.default_location_dest_id:
                    vals['chain_end_location_id'] = picking_type.default_location_dest_id.id
        return super().create(vals_list)

    def write(self, vals: dict) -> bool:
        """Override write to reset chain_state to draft if fields change.

        Also ensures Destination Location matches Transit Location.
        """
        chain_fields = {
            'chain_transit_location_id',
            'chain_dest_picking_type_id',
            'chain_end_location_id',
            'chain_use_putaway_rules',
        }
        if any(field in vals for field in chain_fields):
            vals['chain_state'] = 'draft'

        # Sync location_dest_id if chain_transit_location_id is changed
        if 'chain_transit_location_id' in vals:
            transit_loc = vals['chain_transit_location_id']
            if transit_loc:
                vals['location_dest_id'] = transit_loc

        # Auto-fill End Location if destination picking type changes and end location is not set/changed
        if 'chain_dest_picking_type_id' in vals and 'chain_end_location_id' not in vals:
            dest_picking_type = vals['chain_dest_picking_type_id']
            if dest_picking_type:
                picking_type = self.env['stock.picking.type'].browse(dest_picking_type)
                if picking_type.default_location_dest_id:
                    vals['chain_end_location_id'] = picking_type.default_location_dest_id.id

        res = super().write(vals)

        # Ensure moves destination locations are synchronized with the transit location after write
        for picking in self:
            if picking.chain_transit_location_id:
                # Force picking destination to match transit
                if picking.location_dest_id != picking.chain_transit_location_id:
                    picking.location_dest_id = picking.chain_transit_location_id
                # Force moves destination to match transit
                moves_to_update = picking.move_ids.filtered(
                    lambda m: not m.scrap_id and m.location_dest_id != picking.chain_transit_location_id
                )
                if moves_to_update:
                    moves_to_update.write({'location_dest_id': picking.chain_transit_location_id.id})
            elif 'chain_transit_location_id' in vals and not vals['chain_transit_location_id']:
                # Recompute default location
                picking._compute_location_id()
                moves_to_update = picking.move_ids.filtered(
                    lambda m: not m.scrap_id and m.location_dest_id != picking.location_dest_id
                )
                if moves_to_update:
                    moves_to_update.write({'location_dest_id': picking.location_dest_id.id})

        return res

    @api.onchange('chain_transit_location_id')
    def _onchange_chain_transit_location_id(self) -> None:
        """Propagate transit location change in UI."""
        if self.chain_transit_location_id:
            self.location_dest_id = self.chain_transit_location_id
            for move in self.move_ids:
                move.location_dest_id = self.chain_transit_location_id
        else:
            self._compute_location_id()
            for move in self.move_ids:
                move.location_dest_id = self.location_dest_id

    @api.onchange('chain_dest_picking_type_id')
    def _onchange_chain_dest_picking_type_id(self) -> None:
        """Set default End Location when Destination Picking Type changes."""
        if self.chain_dest_picking_type_id:
            self.chain_end_location_id = self.chain_dest_picking_type_id.default_location_dest_id

    @api.constrains('location_dest_id', 'chain_transit_location_id')
    def _check_chain_destination_location(self) -> None:
        """Ensure destination location matches transit location for chain transfers."""
        for picking in self:
            if picking.chain_transit_location_id and picking.location_dest_id != picking.chain_transit_location_id:
                raise ValidationError(_(
                    "The Destination Location of a chain transfer must match its Transit Location."
                ))

    def button_validate(self) -> dict | bool:
        """Override to create a chain transfer after successful validation.

        After the standard validation completes, check if chain transfer
        fields are populated. If so, create a second transfer with the
        same products from the transit location to the end location.

        Pre-mortem safeguards:
        - Verify manager approval if required before running validation.
        - Move data is collected BEFORE super() call since state changes
          after validation and moves may no longer be accessible.
        - Wizard returns (backorder dialog etc.) are detected and chain
          creation is deferred to next validation call.
        - Empty move lists are skipped to avoid creating empty pickings.
        """
        # Check manager approval before validation if enabled
        for picking in self:
            if (picking.chain_transit_location_id
                    and picking.approve_chain_by_manager
                    and picking.chain_state != 'approved'):
                raise UserError(_(
                    "This chain transfer must be approved by an Inventory Manager before validation."
                ))

        # Collect chain data BEFORE validation (picking state changes after)
        chain_pickings = {}
        for picking in self:
            if (picking.chain_transit_location_id
                    and picking.chain_dest_picking_type_id
                    and (picking.chain_end_location_id or picking.chain_use_putaway_rules)):
                end_loc = picking.chain_end_location_id.id
                if picking.chain_use_putaway_rules:
                    end_loc = picking.chain_dest_picking_type_id.default_location_dest_id.id
                chain_pickings[picking.id] = {
                    'transit_location_id': picking.chain_transit_location_id.id,
                    'dest_picking_type_id': picking.chain_dest_picking_type_id.id,
                    'end_location_id': end_loc,
                    'move_lines_data': [],
                }
                # Collect product data from move lines (before they become 'done')
                for move in picking.move_ids.filtered(
                    lambda m: m.state not in ('done', 'cancel')
                ):
                    # Use the actual done quantity (quantity field)
                    # Fall back to demand if quantity is zero
                    qty = move.quantity or move.product_uom_qty
                    if qty > 0:
                        chain_pickings[picking.id]['move_lines_data'].append({
                            'product_id': move.product_id.id,
                            'product_uom_qty': qty,
                            'product_uom': move.product_uom.id,
                            'description_picking': move.description_picking or move.product_id.display_name,
                        })

        # Execute standard validation
        res = super().button_validate()

        # If validation returned a wizard action (e.g., backorder), return it.
        # The chain transfer will be created on the next validation attempt.
        if res is not True:
            return res

        # Create chain transfers for pickings that completed validation in bulk
        to_process = {}
        for picking in self:
            if (picking.id in chain_pickings
                    and picking.state == 'done'
                    and not picking.chain_origin):
                to_process[picking] = chain_pickings[picking.id]

        if to_process:
            self._create_chain_transfers_bulk(to_process)

        return res

    def action_approve_chain(self) -> None:
        """Approve the barcode chain transfer.

        Only users in the Inventory Manager group can approve.
        """
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_(
                "Only Inventory Managers are allowed to approve chain transfers."
            ))
        for picking in self:
            if picking.chain_transit_location_id and picking.chain_state == 'draft':
                picking.write({'chain_state': 'approved'})

    def action_view_chain_pickings(self) -> dict:
        """Return a window action displaying all transfers in this chain.

        This allows navigating to/from the first and second step pickings.
        """
        self.ensure_one()
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('chain_origin', '=', self.chain_origin)]
        action['context'] = {'create': False}
        return action

    def _create_chain_transfers_bulk(self, chain_data_by_picking: dict) -> None:
        """Create the second transfers in the chain in bulk.

        Generates a new ir.sequence for each chain origin, prepares picking
        values, and creates them in bulk to optimize DB operations.

        :param chain_data_by_picking: Dict mapping stock.picking records to their collected chain_data dicts
        """
        picking_vals_list = []
        source_pickings_to_write = {}

        for source_picking, chain_data in chain_data_by_picking.items():
            # Idempotency check: Skip if it already has a chain origin to avoid duplicates
            if source_picking.chain_origin:
                continue

            # Generate chain origin sequence
            chain_origin = self.env['ir.sequence'].next_by_code(
                'chain.transfer.origin'
            )
            if not chain_origin:
                raise UserError(_(
                    "Could not generate a chain transfer sequence. "
                    "Please check the sequence 'chain.transfer.origin' exists."
                ))

            # Store updates to write to source picking later
            source_pickings_to_write[source_picking] = {
                'chain_origin': chain_origin,
                'origin': chain_origin,
            }

            # Prepare move lines for the second picking
            move_vals_list = []
            for move_data in chain_data['move_lines_data']:
                move_vals_list.append((0, 0, {
                    'product_id': move_data['product_id'],
                    'product_uom_qty': move_data['product_uom_qty'],
                    'product_uom': move_data['product_uom'],
                    'description_picking': move_data['description_picking'],
                    'location_id': chain_data['transit_location_id'],
                    'location_dest_id': chain_data['end_location_id'],
                }))

            if not move_vals_list:
                continue

            # Prepare second picking vals
            picking_vals_list.append({
                'picking_type_id': chain_data['dest_picking_type_id'],
                'location_id': chain_data['transit_location_id'],
                'location_dest_id': chain_data['end_location_id'],
                'origin': chain_origin,
                'chain_origin': chain_origin,
                'move_ids': move_vals_list,
                'company_id': source_picking.company_id.id,
                'user_id': False,
            })

        if not picking_vals_list:
            return

        # Create all second pickings in bulk
        second_pickings = self.env['stock.picking'].create(picking_vals_list)

        # Write origin updates back to source pickings
        for source_picking, vals in source_pickings_to_write.items():
            source_picking.write(vals)

        # Confirm all second pickings
        second_pickings.action_confirm()

    def _get_fields_stock_barcode(self) -> list:
        """Extend barcode fields to include chain transfer fields.

        These fields are sent to the JS barcode client so the
        chain transfer dialog can read/write them.
        """
        fields_list = super()._get_fields_stock_barcode()
        fields_list.extend([
            'chain_transit_location_id',
            'chain_dest_picking_type_id',
            'chain_end_location_id',
            'chain_origin',
            'chain_state',
            'approve_chain_by_manager',
            'company_chain_transit_location_id',
            'chain_use_putaway_rules',
        ])
        return fields_list

