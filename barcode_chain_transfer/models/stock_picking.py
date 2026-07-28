# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

# Fields that describe *how* the chain is routed. Changing any of them
# invalidates a previously granted manager approval.
CHAIN_CONFIG_FIELDS = (
    'chain_transit_location_id',
    'chain_dest_picking_type_id',
    'chain_end_location_id',
    'chain_use_putaway_rules',
)

# Locations goods may legitimately travel through or land in.
CHAIN_ALLOWED_USAGES = ('internal', 'transit')


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
        check_company=True,
        domain="[('usage', 'in', ['internal', 'transit'])]",
        help="Intermediate transit location. When set, this becomes the "
             "destination of the current transfer, and a second transfer "
             "is created from here to the End Location upon validation.",
        copy=False,
    )
    chain_dest_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Destination Picking Type',
        check_company=True,
        help="The picking type for the automatically created second transfer.",
        copy=False,
    )
    chain_end_location_id = fields.Many2one(
        'stock.location',
        string='End Location',
        check_company=True,
        domain="[('usage', 'in', ['internal', 'transit'])]",
        help="The final destination location for the second transfer.",
        copy=False,
    )
    chain_origin = fields.Char(
        string='Chain Reference',
        help="Auto-generated reference shared by both chain transfers.",
        copy=False,
        readonly=True,
        index='btree_not_null',
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_chain_configured(self) -> bool:
        """Return whether this picking holds a complete chain configuration."""
        self.ensure_one()
        return bool(
            self.chain_transit_location_id
            and self.chain_dest_picking_type_id
            and (self.chain_end_location_id or self.chain_use_putaway_rules)
        )

    def _get_chain_end_location(self):
        """Return the location the second transfer should deliver to.

        When putaway rules are used, the operation type's default destination is
        the entry point: Odoo's putaway strategy then refines it down to a child
        location while the second transfer's move lines are assigned.
        """
        self.ensure_one()
        if self.chain_use_putaway_rules:
            return self.chain_dest_picking_type_id.default_location_dest_id
        return (
            self.chain_end_location_id
            or self.chain_dest_picking_type_id.default_location_dest_id
        )

    def _chain_config_differs(self, vals: dict) -> bool:
        """Return whether ``vals`` actually changes this picking's chain routing.

        Re-saving identical values must not silently revoke a manager approval.
        """
        self.ensure_one()
        for field_name in CHAIN_CONFIG_FIELDS:
            if field_name not in vals:
                continue
            new_value = vals[field_name]
            if self._fields[field_name].type == 'many2one':
                if (self[field_name].id or False) != (new_value or False):
                    return True
            elif bool(self[field_name]) != bool(new_value):
                return True
        return False

    def _check_chain_configuration(self) -> None:
        """Validate the chain routing *before* anything is validated.

        Pre-mortem safeguard: every reason the second transfer could fail to be
        created is checked here, while the first transfer is still untouched.
        Raising later - after ``super().button_validate()`` has already posted
        the stock moves - would roll back the operator's whole scanning session.
        """
        for picking in self:
            transit = picking.chain_transit_location_id
            dest_type = picking.chain_dest_picking_type_id
            end_location = picking._get_chain_end_location()

            if transit.usage not in CHAIN_ALLOWED_USAGES:
                raise UserError(_(
                    "The Transit Location %(location)s cannot be used for a chain "
                    "transfer: only internal and transit locations can hold goods.",
                    location=transit.display_name,
                ))
            if not end_location:
                raise UserError(_(
                    "No End Location could be determined for the chain transfer of "
                    "%(picking)s. Set one explicitly, or give the Destination "
                    "Picking Type a default destination location.",
                    picking=picking.name,
                ))
            if end_location.usage not in CHAIN_ALLOWED_USAGES:
                raise UserError(_(
                    "The End Location %(location)s cannot receive goods: only "
                    "internal and transit locations can be used.",
                    location=end_location.display_name,
                ))
            if not dest_type.active:
                raise UserError(_(
                    "The Destination Picking Type %(picking_type)s is archived and "
                    "cannot be used for a chain transfer.",
                    picking_type=dest_type.display_name,
                ))

            company = picking.company_id
            for record, label in (
                (transit, _("Transit Location")),
                (end_location, _("End Location")),
                (dest_type, _("Destination Picking Type")),
            ):
                if record.company_id and record.company_id != company:
                    raise UserError(_(
                        "The %(label)s %(name)s belongs to %(other_company)s while "
                        "this transfer belongs to %(company)s.",
                        label=label,
                        name=record.display_name,
                        other_company=record.company_id.display_name,
                        company=company.display_name,
                    ))

    def _sync_chain_destination(self, vals: dict) -> None:
        """Keep ``location_dest_id`` aligned with the transit location.

        Core ``stock.picking.write`` resets ``location_dest_id`` to the operation
        type's default whenever ``picking_type_id`` changes, so the alignment is
        re-asserted after every write instead of being guarded by a constraint
        (a constraint would simply make changing the operation type impossible).
        """
        if self.env.context.get('chain_syncing_destination'):
            return
        for picking in self:
            if picking.state in ('cancel', 'done'):
                continue
            target = picking.chain_transit_location_id
            if not target:
                # The chain was just cleared: fall back to the standard default.
                if 'chain_transit_location_id' not in vals or vals['chain_transit_location_id']:
                    continue
                picking._compute_location_id()
                target = picking.location_dest_id
            if picking.location_dest_id != target:
                # Core's write propagates the new destination down to the moves.
                picking.with_context(chain_syncing_destination=True).write({
                    'location_dest_id': target.id,
                })
            else:
                moves_to_update = picking.move_ids.filtered(
                    lambda m: not m.scrapped and m.location_dest_id != target
                )
                if moves_to_update:
                    moves_to_update.write({'location_dest_id': target.id})

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------

    @api.depends('picking_type_id', 'partner_id', 'chain_transit_location_id')
    def _compute_location_id(self) -> None:
        """Override to set Destination Location to Transit Location if configured."""
        super()._compute_location_id()
        for picking in self:
            # Mirror core's guard: never touch a picking that is already settled.
            if picking.state in ('cancel', 'done') or picking.return_id:
                continue
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
                for move_field in ('move_ids', 'move_ids_without_package'):
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
        """Override write to keep the chain routing and its approval consistent."""
        # Never mutate the caller's dict: it may be reused across several writes.
        vals = dict(vals)

        # `chain_state` is an approval flag, not a regular field: it may only be
        # set through `action_approve_chain` or by this method's own reset below.
        if 'chain_state' in vals and not self.env.context.get('chain_approval_write'):
            raise UserError(_(
                "The chain approval state cannot be modified directly. "
                "Use the 'Approve Chain' button instead."
            ))

        # Only revoke an approval when the routing genuinely changes.
        pickings_to_unapprove = self.browse()
        if any(field in vals for field in CHAIN_CONFIG_FIELDS):
            pickings_to_unapprove = self.filtered(
                lambda p: p.chain_state == 'approved' and p._chain_config_differs(vals)
            )

        # Sync location_dest_id if chain_transit_location_id is changed
        if vals.get('chain_transit_location_id'):
            vals['location_dest_id'] = vals['chain_transit_location_id']

        # Auto-fill End Location if the destination picking type changes and the
        # end location is not set/changed in the same write.
        if 'chain_dest_picking_type_id' in vals and 'chain_end_location_id' not in vals:
            dest_picking_type = vals['chain_dest_picking_type_id']
            if dest_picking_type:
                picking_type = self.env['stock.picking.type'].browse(dest_picking_type)
                if picking_type.default_location_dest_id:
                    vals['chain_end_location_id'] = picking_type.default_location_dest_id.id

        res = super().write(vals)

        if pickings_to_unapprove:
            pickings_to_unapprove.with_context(chain_approval_write=True).write({
                'chain_state': 'draft',
            })

        self._sync_chain_destination(vals)
        return res

    def _create_backorder_picking(self):
        """Carry the chain configuration over to the backorder.

        The remaining goods must travel the same route as the part that was just
        transferred, so the backorder inherits the full chain setup - including
        its approval, since it is the same operation the manager already signed
        off on. ``chain_origin`` is deliberately not copied: the backorder starts
        its own chain when it is validated in turn.
        """
        backorder = super()._create_backorder_picking()
        if self.chain_transit_location_id:
            backorder.with_context(chain_approval_write=True).write({
                'chain_transit_location_id': self.chain_transit_location_id.id,
                'chain_dest_picking_type_id': self.chain_dest_picking_type_id.id,
                'chain_end_location_id': self.chain_end_location_id.id,
                'chain_use_putaway_rules': self.chain_use_putaway_rules,
                'chain_state': self.chain_state,
            })
        return backorder

    @api.onchange('chain_transit_location_id')
    def _onchange_chain_transit_location_id(self) -> None:
        """Propagate transit location change in UI."""
        if self.chain_transit_location_id:
            self.location_dest_id = self.chain_transit_location_id
            for move in (self.move_ids | self.move_ids_without_package):
                move.location_dest_id = self.chain_transit_location_id
        else:
            self._compute_location_id()
            for move in (self.move_ids | self.move_ids_without_package):
                move.location_dest_id = self.location_dest_id

    @api.onchange('chain_dest_picking_type_id')
    def _onchange_chain_dest_picking_type_id(self) -> None:
        """Set default End Location when Destination Picking Type changes."""
        if self.chain_dest_picking_type_id:
            self.chain_end_location_id = self.chain_dest_picking_type_id.default_location_dest_id

    # ------------------------------------------------------------------
    # Business methods
    # ------------------------------------------------------------------

    def button_validate(self) -> dict | bool:
        """Override to create a chain transfer after successful validation.

        Pre-mortem safeguards:
        - Manager approval and the whole chain configuration are verified BEFORE
          super() runs, so a misconfiguration can never roll back an already
          completed validation.
        - Quantities are read AFTER super() from the done moves, so the second
          transfer only ever carries what physically reached the transit
          location (unpicked quantities leave for the backorder instead).
        - Wizard returns (backorder dialog etc.) are detected and chain creation
          is deferred to the next validation call.
        - Pickings that already carry a chain origin are skipped.
        """
        chain_pickings = self.filtered(lambda p: p._is_chain_configured())

        # Check manager approval before validation if enabled
        for picking in chain_pickings:
            if picking.approve_chain_by_manager and picking.chain_state != 'approved':
                raise UserError(_(
                    "This chain transfer must be approved by an Inventory Manager before validation."
                ))
        chain_pickings._check_chain_configuration()

        # Execute standard validation
        res = super().button_validate()

        # If validation returned a wizard action (e.g., backorder), return it.
        # The chain transfer will be created on the next validation attempt.
        if res is not True:
            return res

        to_process = chain_pickings.exists().filtered(
            lambda p: p.state == 'done' and not p.chain_origin
        )
        if to_process:
            to_process._create_chain_transfers()

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
                picking.with_context(chain_approval_write=True).write({
                    'chain_state': 'approved',
                })

    def action_view_chain_pickings(self) -> dict:
        """Return a window action displaying all transfers in this chain.

        This allows navigating to/from the first and second step pickings.
        """
        self.ensure_one()
        if not self.chain_origin:
            raise UserError(_("This transfer is not part of a chain yet."))
        action = self.env['ir.actions.act_window']._for_xml_id(
            'stock.action_picking_tree_all'
        )
        action['domain'] = [('chain_origin', '=', self.chain_origin)]
        action['context'] = {'create': False}
        return action

    def _create_chain_transfers(self) -> models.BaseModel:
        """Create the second transfers in the chain, in bulk.

        Must be called on validated (``done``) pickings: the quantities of the
        second transfer are taken from the done moves, i.e. from what actually
        reached the transit location.

        :return: the created second-step pickings
        """
        picking_vals_list = []
        origin_by_picking = {}

        for source_picking in self:
            # Idempotency check: skip if it already has a chain origin
            if source_picking.chain_origin:
                continue

            end_location = source_picking._get_chain_end_location()
            transit_location = source_picking.chain_transit_location_id

            move_vals_list = []
            for move in source_picking.move_ids.filtered(lambda m: m.state == 'done'):
                # `quantity` on a done move is what was really moved.
                if move.quantity <= 0:
                    continue
                move_vals_list.append((0, 0, {
                    'product_id': move.product_id.id,
                    'product_uom_qty': move.quantity,
                    'product_uom': move.product_uom.id,
                    'name': move.name or move.product_id.display_name,
                    'location_id': transit_location.id,
                    'location_dest_id': end_location.id,
                }))

            if not move_vals_list:
                continue

            chain_origin = self.env['ir.sequence'].next_by_code('chain.transfer.origin')
            if not chain_origin:
                raise UserError(_(
                    "Could not generate a chain transfer sequence. "
                    "Please check the sequence 'chain.transfer.origin' exists."
                ))
            origin_by_picking[source_picking] = chain_origin

            picking_vals_list.append({
                'picking_type_id': source_picking.chain_dest_picking_type_id.id,
                'location_id': transit_location.id,
                'location_dest_id': end_location.id,
                'origin': chain_origin,
                'chain_origin': chain_origin,
                'move_ids': move_vals_list,
                'company_id': source_picking.company_id.id,
                'user_id': False,
            })

        if not picking_vals_list:
            return self.browse()

        # Create all second pickings in bulk
        second_pickings = self.env['stock.picking'].create(picking_vals_list)

        # Stamp the chain reference on the source pickings without losing the
        # document they originate from (a purchase order, a sale order, ...).
        for source_picking, chain_origin in origin_by_picking.items():
            source_picking.write({
                'chain_origin': chain_origin,
                'origin': (
                    '%s - %s' % (source_picking.origin, chain_origin)
                    if source_picking.origin else chain_origin
                ),
            })

        second_pickings.action_confirm()
        return second_pickings

    # ------------------------------------------------------------------
    # Barcode client action
    # ------------------------------------------------------------------

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

    def _get_stock_barcode_data(self) -> dict:
        """Push the chain-related records into the barcode client cache.

        ``_get_fields_stock_barcode`` only ships integer ids. The barcode cache
        raises as soon as the client asks for a record the server never sent
        (``LazyBarcodeCache.getRecord`` defaults to ``raiseErrorIfMissing``), and
        neither the destination operation type nor the end location belongs to
        the record sets core collects. Without this, opening the chain dialog on
        an already configured transfer crashes the whole client action.
        """
        data = super()._get_stock_barcode_data()
        records = data['records']

        extra_locations = (
            self.chain_transit_location_id
            | self.chain_end_location_id
            | self.company_chain_transit_location_id
        )
        known_location_ids = {rec['id'] for rec in records.get('stock.location', [])}
        extra_locations = extra_locations.filtered(
            lambda location: location.id not in known_location_ids
        )
        if extra_locations:
            records.setdefault('stock.location', []).extend(
                extra_locations.read(
                    extra_locations._get_fields_stock_barcode(), load=False
                )
            )

        extra_picking_types = self.chain_dest_picking_type_id
        known_type_ids = {rec['id'] for rec in records.get('stock.picking.type', [])}
        extra_picking_types = extra_picking_types.filtered(
            lambda picking_type: picking_type.id not in known_type_ids
        )
        if extra_picking_types:
            # `display_name` is not part of the standard barcode field list.
            records.setdefault('stock.picking.type', []).extend(
                extra_picking_types.read(
                    extra_picking_types._get_fields_stock_barcode() + ['display_name'],
                    load=False,
                )
            )

        return data
