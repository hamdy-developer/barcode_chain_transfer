# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestChainTransfer(TransactionCase):
    """Test suite for the barcode chain transfer functionality.

    Tests that when chain transfer fields are set on a picking and
    validated, a second transfer is automatically created with
    the correct configuration.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test data: warehouse, locations, picking types, product."""
        super().setUpClass()

        cls.warehouse = cls.env['stock.warehouse'].search([], limit=1)

        # Create transit location
        cls.transit_location = cls.env['stock.location'].create({
            'name': 'Test Transit Zone',
            'usage': 'transit',
            'company_id': cls.env.company.id,
        })

        # Create end location
        cls.end_location = cls.env['stock.location'].create({
            'name': 'Test End Location',
            'usage': 'internal',
            'location_id': cls.warehouse.lot_stock_id.id,
            'company_id': cls.env.company.id,
        })

        # Get an existing picking type for the second transfer
        cls.dest_picking_type = cls.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', cls.warehouse.id),
        ], limit=1)

        if not cls.dest_picking_type:
            cls.dest_picking_type = cls.env['stock.picking.type'].create({
                'name': 'Test Internal Transfer',
                'code': 'internal',
                'sequence_code': 'TINT',
                'warehouse_id': cls.warehouse.id,
                'default_location_src_id': cls.transit_location.id,
                'default_location_dest_id': cls.end_location.id,
            })

        # Create a test product
        cls.product = cls.env['product.product'].create({
            'name': 'Chain Transfer Test Product',
            'type': 'consu',
            'is_storable': True,
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
        })

        # Get the source picking type (e.g., receipts or internal)
        cls.source_picking_type = cls.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id', '=', cls.warehouse.id),
        ], limit=1)

        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')

    def _create_picking_with_chain(self, quantity: float = 10.0, **picking_vals):
        """Helper to create a picking with chain transfer fields set.

        :param quantity: Product quantity for the move
        :param picking_vals: Extra values written on the picking
        :return: Created picking record
        """
        vals = {
            'picking_type_id': self.source_picking_type.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.transit_location.id,
            'chain_transit_location_id': self.transit_location.id,
            'chain_dest_picking_type_id': self.dest_picking_type.id,
            'chain_end_location_id': self.end_location.id,
            'move_ids': [(0, 0, {
                'name': self.product.display_name,
                'product_id': self.product.id,
                'product_uom_qty': quantity,
                'product_uom': self.product.uom_id.id,
                'location_id': self.supplier_location.id,
                'location_dest_id': self.transit_location.id,
            })],
        }
        vals.update(picking_vals)
        return self.env['stock.picking'].create(vals)

    def _validate(self, picking):
        """Validate a picking without any interactive wizard."""
        return picking.with_context(
            skip_backorder=True,
            skip_sanity_check=True,
        ).button_validate()

    def _get_second_picking(self, picking):
        """Return the second-step transfer of ``picking``'s chain."""
        return self.env['stock.picking'].search([
            ('chain_origin', '=', picking.chain_origin),
            ('id', '!=', picking.id),
        ])

    # ------------------------------------------------------------------
    # Chain creation
    # ------------------------------------------------------------------

    def test_chain_transfer_creation(self) -> None:
        """Test that validating a picking with chain fields creates a 2nd transfer."""
        picking = self._create_picking_with_chain(quantity=5.0)
        picking.action_confirm()

        # Set quantities done
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True

        self._validate(picking)

        # Assert first picking is done
        self.assertEqual(picking.state, 'done')

        # Assert chain origin is set
        self.assertTrue(picking.chain_origin)
        self.assertTrue(picking.chain_origin.startswith('CHAIN/'))

        second_picking = self._get_second_picking(picking)

        # Assert second picking exists
        self.assertEqual(len(second_picking), 1, "A second chain transfer should be created")

        # Assert second picking configuration
        self.assertEqual(
            second_picking.location_id.id,
            self.transit_location.id,
            "Second picking source should be transit location",
        )
        self.assertEqual(
            second_picking.location_dest_id.id,
            self.end_location.id,
            "Second picking destination should be end location",
        )
        self.assertEqual(
            second_picking.picking_type_id.id,
            self.dest_picking_type.id,
            "Second picking type should match dest picking type",
        )
        self.assertEqual(
            second_picking.origin,
            picking.chain_origin,
            "Second picking origin should match chain reference",
        )

        # Assert second picking has the same products
        self.assertEqual(len(second_picking.move_ids), 1)
        second_move = second_picking.move_ids[0]
        self.assertEqual(second_move.product_id.id, self.product.id)
        self.assertEqual(second_move.product_uom_qty, 5.0)

        # Assert second picking is confirmed (TODO state)
        self.assertIn(
            second_picking.state,
            ['confirmed', 'assigned', 'waiting'],
            "Second picking should be confirmed (TODO)",
        )

    def test_no_chain_transfer_without_fields(self) -> None:
        """Test that validation without chain fields does NOT create a 2nd transfer."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.source_picking_type.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
            'move_ids': [(0, 0, {
                'name': self.product.display_name,
                'product_id': self.product.id,
                'product_uom_qty': 3.0,
                'product_uom': self.product.uom_id.id,
                'location_id': self.supplier_location.id,
                'location_dest_id': self.warehouse.lot_stock_id.id,
            })],
        })
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True

        picking_count_before = self.env['stock.picking'].search_count([])

        self._validate(picking)

        self.assertEqual(picking.state, 'done')
        self.assertFalse(picking.chain_origin)

        picking_count_after = self.env['stock.picking'].search_count([])
        self.assertEqual(picking_count_after, picking_count_before, "No second picking should be created")

    def test_chain_transfer_multiple_products(self) -> None:
        """Test chain transfer with multiple product lines."""
        product2 = self.env['product.product'].create({
            'name': 'Chain Transfer Test Product 2',
            'type': 'consu',
            'is_storable': True,
            'uom_id': self.env.ref('uom.product_uom_unit').id,
        })

        picking = self._create_picking_with_chain(quantity=10.0)
        picking.write({
            'move_ids': [(0, 0, {
                'name': product2.display_name,
                'product_id': product2.id,
                'product_uom_qty': 7.0,
                'product_uom': product2.uom_id.id,
                'location_id': self.supplier_location.id,
                'location_dest_id': self.transit_location.id,
            })],
        })

        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True

        self._validate(picking)

        self.assertEqual(picking.state, 'done')

        second_picking = self._get_second_picking(picking)

        self.assertEqual(len(second_picking), 1)
        self.assertEqual(len(second_picking.move_ids), 2)

        # Verify products match
        product_ids = second_picking.move_ids.mapped('product_id.id')
        self.assertIn(self.product.id, product_ids)
        self.assertIn(product2.id, product_ids)

    def test_chain_uses_done_quantities_not_demand(self) -> None:
        """The second transfer must carry what really reached the transit location.

        Reading the quantities before validation would ship the full demand even
        though only part of it was picked, creating stock that never existed in
        the transit location.
        """
        picking = self._create_picking_with_chain(quantity=10.0)
        picking.action_confirm()

        # Only 4 of the 10 demanded units are actually received.
        move = picking.move_ids
        move.quantity = 4.0
        move.picked = True

        self._validate(picking)

        self.assertEqual(picking.state, 'done')
        second_picking = self._get_second_picking(picking)
        self.assertEqual(len(second_picking), 1)
        self.assertEqual(
            second_picking.move_ids.product_uom_qty,
            4.0,
            "The chained transfer must only move the quantity that was really received",
        )

    def test_backorder_inherits_chain_configuration(self) -> None:
        """The backorder keeps travelling the same route as its source."""
        self.env.company.approve_chain_by_manager = True
        picking = self._create_picking_with_chain(quantity=10.0)
        picking.action_confirm()
        picking.action_approve_chain()

        move = picking.move_ids
        move.quantity = 4.0
        move.picked = True

        self._validate(picking)

        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertEqual(len(backorder), 1, "A backorder should have been created")
        self.assertEqual(backorder.chain_transit_location_id, self.transit_location)
        self.assertEqual(backorder.chain_dest_picking_type_id, self.dest_picking_type)
        self.assertEqual(backorder.chain_end_location_id, self.end_location)
        self.assertEqual(
            backorder.chain_state, 'approved',
            "The backorder is the same operation the manager already approved",
        )
        self.assertFalse(
            backorder.chain_origin,
            "The backorder starts its own chain when it is validated",
        )
        self.assertEqual(
            backorder.location_dest_id, self.transit_location,
            "The backorder must also be routed through the transit location",
        )

    def test_source_origin_is_preserved(self) -> None:
        """Stamping the chain reference must not erase the source document."""
        picking = self._create_picking_with_chain(quantity=5.0, origin='PO00042')
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True

        self._validate(picking)

        self.assertIn('PO00042', picking.origin, "The originating document must survive")
        self.assertIn(picking.chain_origin, picking.origin)

    # ------------------------------------------------------------------
    # Approval flow
    # ------------------------------------------------------------------

    def test_chain_transfer_approval_flow(self) -> None:
        """Test chain transfer validation with manager approval flow."""
        # Enable manager approval setting
        self.env.company.approve_chain_by_manager = True

        picking = self._create_picking_with_chain(quantity=5.0)
        picking.action_confirm()

        # Set quantities done
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True

        # 1. Validation should fail because it's not approved
        with self.assertRaises(UserError):
            self._validate(picking)

        # 2. Try to approve as a normal user (should fail)
        normal_user = self.env['res.users'].create({
            'name': 'Normal Stock Operator',
            'login': 'operator1',
            'email': 'op1@example.com',
            'groups_id': [(6, 0, [self.env.ref('stock.group_stock_user').id])],
        })
        with self.assertRaises(UserError):
            picking.with_user(normal_user).action_approve_chain()

        # 3. Approve as manager (should succeed)
        picking.action_approve_chain()
        self.assertEqual(picking.chain_state, 'approved')

        # 4. Modify fields should reset state to draft
        picking.write({'chain_end_location_id': self.warehouse.lot_stock_id.id})
        self.assertEqual(picking.chain_state, 'draft')

        # Re-approve and validate
        picking.action_approve_chain()
        self._validate(picking)

        self.assertEqual(picking.state, 'done')
        self.assertEqual(len(self._get_second_picking(picking)), 1)

    def test_approval_cannot_be_granted_by_a_direct_write(self) -> None:
        """`chain_state` is an approval flag, not a writable field."""
        picking = self._create_picking_with_chain(quantity=5.0)
        with self.assertRaises(UserError):
            picking.write({'chain_state': 'approved'})
        self.assertEqual(picking.chain_state, 'draft')

    def test_rewriting_identical_values_keeps_the_approval(self) -> None:
        """Saving the same configuration again must not revoke the approval."""
        self.env.company.approve_chain_by_manager = True
        picking = self._create_picking_with_chain(quantity=5.0)
        picking.action_approve_chain()
        self.assertEqual(picking.chain_state, 'approved')

        # Exactly what the barcode dialog sends back when nothing was changed.
        picking.write({
            'chain_transit_location_id': self.transit_location.id,
            'chain_dest_picking_type_id': self.dest_picking_type.id,
            'chain_end_location_id': self.end_location.id,
            'chain_use_putaway_rules': False,
        })
        self.assertEqual(picking.chain_state, 'approved')

        # A real change still revokes it.
        picking.write({'chain_end_location_id': self.warehouse.lot_stock_id.id})
        self.assertEqual(picking.chain_state, 'draft')

    # ------------------------------------------------------------------
    # Routing / destination synchronisation
    # ------------------------------------------------------------------

    def test_destination_location_sync_create_and_write(self) -> None:
        """Test that picking location_dest_id and its moves' location_dest_id
        are automatically synchronized with chain_transit_location_id.
        """
        # 1. Sync on Create
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.source_picking_type.id,
            'location_id': self.supplier_location.id,
            'chain_transit_location_id': self.transit_location.id,
            'chain_dest_picking_type_id': self.dest_picking_type.id,
            'chain_end_location_id': self.end_location.id,
            'move_ids': [(0, 0, {
                'name': self.product.display_name,
                'product_id': self.product.id,
                'product_uom_qty': 5.0,
                'product_uom': self.product.uom_id.id,
                'location_id': self.supplier_location.id,
            })],
        })
        self.assertEqual(picking.location_dest_id.id, self.transit_location.id)
        self.assertEqual(picking.move_ids[0].location_dest_id.id, self.transit_location.id)

        # 2. Sync on Write
        picking.write({'chain_transit_location_id': self.end_location.id})
        self.assertEqual(picking.location_dest_id.id, self.end_location.id)
        self.assertEqual(picking.move_ids[0].location_dest_id.id, self.end_location.id)

        # 3. A manual destination override is corrected back to the transit location
        picking.write({'location_dest_id': self.transit_location.id})
        self.assertEqual(
            picking.location_dest_id.id, self.end_location.id,
            "The destination must stay aligned with the transit location",
        )
        self.assertEqual(picking.move_ids[0].location_dest_id.id, self.end_location.id)

    def test_operation_type_can_still_be_changed(self) -> None:
        """Changing the operation type must not be blocked by the chain routing.

        Core resets `location_dest_id` to the operation type's default whenever
        `picking_type_id` changes; the chain must re-align it instead of raising.
        """
        picking = self._create_picking_with_chain(quantity=5.0)
        internal_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', self.warehouse.id),
        ], limit=1)

        picking.write({'picking_type_id': internal_type.id})

        self.assertEqual(picking.picking_type_id, internal_type)
        self.assertEqual(
            picking.location_dest_id, self.transit_location,
            "The transit routing must survive an operation type change",
        )

    def test_end_location_autofill_create_and_write(self) -> None:
        """Test that setting chain_dest_picking_type_id automatically defaults
        chain_end_location_id to the picking type's default destination.
        """
        # 1. Autofill on Create
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.source_picking_type.id,
            'location_id': self.supplier_location.id,
            'chain_transit_location_id': self.transit_location.id,
            'chain_dest_picking_type_id': self.dest_picking_type.id,
            'move_ids': [(0, 0, {
                'name': self.product.display_name,
                'product_id': self.product.id,
                'product_uom_qty': 5.0,
                'product_uom': self.product.uom_id.id,
                'location_id': self.supplier_location.id,
            })],
        })
        self.assertEqual(picking.chain_end_location_id.id, self.dest_picking_type.default_location_dest_id.id)

        # Clear it
        picking.write({'chain_end_location_id': False})
        self.assertFalse(picking.chain_end_location_id)

        # 2. Autofill on Write
        picking.write({'chain_dest_picking_type_id': self.dest_picking_type.id})
        self.assertEqual(picking.chain_end_location_id.id, self.dest_picking_type.default_location_dest_id.id)

    # ------------------------------------------------------------------
    # Pre-flight validation
    # ------------------------------------------------------------------

    def test_invalid_end_location_is_rejected_before_validation(self) -> None:
        """A broken chain must fail before the first transfer is processed.

        Raising after `super().button_validate()` would roll back the whole
        scanning session, so the operator would lose everything.
        """
        picking = self._create_picking_with_chain(quantity=5.0)
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True

        # A view location can never hold goods.
        picking.chain_end_location_id = self.warehouse.view_location_id

        with self.assertRaises(UserError):
            self._validate(picking)

        self.assertNotEqual(
            picking.state, 'done',
            "Nothing may be validated when the chain configuration is invalid",
        )
        self.assertFalse(picking.chain_origin)

    # ------------------------------------------------------------------
    # Barcode client payload
    # ------------------------------------------------------------------

    def test_barcode_data_contains_chain_records(self) -> None:
        """The barcode client cache must hold every record the dialog resolves.

        `LazyBarcodeCache.getRecord` raises for records the server never sent,
        which used to crash the client action when reopening the chain dialog.
        """
        picking = self._create_picking_with_chain(quantity=5.0)
        picking.action_confirm()

        data = picking._get_stock_barcode_data()['records']

        location_ids = {rec['id'] for rec in data['stock.location']}
        picking_type_ids = {rec['id'] for rec in data['stock.picking.type']}

        self.assertIn(self.transit_location.id, location_ids)
        self.assertIn(self.end_location.id, location_ids)
        self.assertIn(self.dest_picking_type.id, picking_type_ids)

        chain_type_data = next(
            rec for rec in data['stock.picking.type']
            if rec['id'] == self.dest_picking_type.id
        )
        self.assertTrue(
            chain_type_data.get('display_name'),
            "The dialog needs the operation type's display name",
        )
