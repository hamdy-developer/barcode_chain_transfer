# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError



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
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
        })

        # Get the source picking type (e.g., receipts or internal)
        cls.source_picking_type = cls.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id', '=', cls.warehouse.id),
        ], limit=1)

    def _create_picking_with_chain(self, quantity: float = 10.0):
        """Helper to create a picking with chain transfer fields set.

        :param quantity: Product quantity for the move
        :return: Created picking record
        """
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.source_picking_type.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.transit_location.id,
            'chain_transit_location_id': self.transit_location.id,
            'chain_dest_picking_type_id': self.dest_picking_type.id,
            'chain_end_location_id': self.end_location.id,
            'move_ids': [(0, 0, {
                'description_picking': self.product.display_name,
                'product_id': self.product.id,
                'product_uom_qty': quantity,
                'product_uom': self.product.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': self.transit_location.id,
            })],
        })
        return picking

    def test_chain_transfer_creation(self) -> None:
        """Test that validating a picking with chain fields creates a 2nd transfer."""
        picking = self._create_picking_with_chain(quantity=5.0)
        picking.action_confirm()

        # Set quantities done
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty

        # Validate the picking
        picking.with_context(
            skip_backorder=True,
            skip_sanity_check=True,
        ).button_validate()

        # Assert first picking is done
        self.assertEqual(picking.state, 'done')

        # Assert chain origin is set
        self.assertTrue(picking.chain_origin)
        self.assertTrue(picking.chain_origin.startswith('CHAIN/'))
        self.assertEqual(picking.origin, picking.chain_origin)

        # Find the second picking by chain origin
        second_picking = self.env['stock.picking'].search([
            ('chain_origin', '=', picking.chain_origin),
            ('id', '!=', picking.id),
        ])

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
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
            'move_ids': [(0, 0, {
                'description_picking': self.product.display_name,
                'product_id': self.product.id,
                'product_uom_qty': 3.0,
                'product_uom': self.product.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': self.warehouse.lot_stock_id.id,
            })],
        })
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty

        picking_count_before = self.env['stock.picking'].search_count([])

        picking.with_context(
            skip_backorder=True,
            skip_sanity_check=True,
        ).button_validate()

        self.assertEqual(picking.state, 'done')
        self.assertFalse(picking.chain_origin)

        picking_count_after = self.env['stock.picking'].search_count([])
        self.assertEqual(picking_count_after, picking_count_before, "No second picking should be created")


    def test_chain_transfer_multiple_products(self) -> None:
        """Test chain transfer with multiple product lines."""
        product2 = self.env['product.product'].create({
            'name': 'Chain Transfer Test Product 2',
            'type': 'consu',
            'uom_id': self.env.ref('uom.product_uom_unit').id,
        })

        picking = self.env['stock.picking'].create({
            'picking_type_id': self.source_picking_type.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.transit_location.id,
            'chain_transit_location_id': self.transit_location.id,
            'chain_dest_picking_type_id': self.dest_picking_type.id,
            'chain_end_location_id': self.end_location.id,
            'move_ids': [
                (0, 0, {
                    'description_picking': self.product.display_name,
                    'product_id': self.product.id,
                    'product_uom_qty': 10.0,
                    'product_uom': self.product.uom_id.id,
                    'location_id': self.env.ref('stock.stock_location_suppliers').id,
                    'location_dest_id': self.transit_location.id,
                }),
                (0, 0, {
                    'description_picking': product2.display_name,
                    'product_id': product2.id,
                    'product_uom_qty': 7.0,
                    'product_uom': product2.uom_id.id,
                    'location_id': self.env.ref('stock.stock_location_suppliers').id,
                    'location_dest_id': self.transit_location.id,
                }),
            ],
        })

        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty

        picking.with_context(
            skip_backorder=True,
            skip_sanity_check=True,
        ).button_validate()

        self.assertEqual(picking.state, 'done')

        second_picking = self.env['stock.picking'].search([
            ('chain_origin', '=', picking.chain_origin),
            ('id', '!=', picking.id),
        ])

        self.assertEqual(len(second_picking), 1)
        self.assertEqual(len(second_picking.move_ids), 2)

        # Verify products match
        product_ids = second_picking.move_ids.mapped('product_id.id')
        self.assertIn(self.product.id, product_ids)
        self.assertIn(product2.id, product_ids)

    def test_chain_transfer_approval_flow(self) -> None:
        """Test chain transfer validation with manager approval flow."""
        # Enable manager approval setting
        self.env.company.approve_chain_by_manager = True

        picking = self._create_picking_with_chain(quantity=5.0)
        picking.action_confirm()

        # Set quantities done
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty

        # 1. Validation should fail because it's not approved
        with self.assertRaises(UserError):
            picking.with_context(
                skip_backorder=True,
                skip_sanity_check=True,
            ).button_validate()

        # 2. Try to approve as a normal user (should fail)
        normal_user = self.env['res.users'].create({
            'name': 'Normal Stock Operator',
            'login': 'operator1',
            'email': 'op1@example.com',
            'group_ids': [(6, 0, [self.env.ref('stock.group_stock_user').id])],
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
        picking.with_context(
            skip_backorder=True,
            skip_sanity_check=True,
        ).button_validate()

        self.assertEqual(picking.state, 'done')

        # Find second picking
        second_picking = self.env['stock.picking'].search([
            ('chain_origin', '=', picking.chain_origin),
            ('id', '!=', picking.id),
        ])
        self.assertEqual(len(second_picking), 1)

    def test_destination_location_sync_create_and_write(self) -> None:
        """Test that picking location_dest_id and its moves' location_dest_id
        are automatically synchronized with chain_transit_location_id.
        """
        # 1. Sync on Create
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.source_picking_type.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'chain_transit_location_id': self.transit_location.id,
            'chain_dest_picking_type_id': self.dest_picking_type.id,
            'chain_end_location_id': self.end_location.id,
            'move_ids': [(0, 0, {
                'description_picking': self.product.display_name,
                'product_id': self.product.id,
                'product_uom_qty': 5.0,
                'product_uom': self.product.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
            })],
        })
        self.assertEqual(picking.location_dest_id.id, self.transit_location.id)
        self.assertEqual(picking.move_ids[0].location_dest_id.id, self.transit_location.id)

        # 2. Sync on Write
        # Change transit location to end location (just as a test location)
        picking.write({
            'chain_transit_location_id': self.end_location.id
        })
        self.assertEqual(picking.location_dest_id.id, self.end_location.id)
        self.assertEqual(picking.move_ids[0].location_dest_id.id, self.end_location.id)

        # 3. Constraint Validation
        # If we try to change location_dest_id manually to something else while chain is set, it should raise ValidationError
        with self.assertRaises(ValidationError):
            picking.write({
                'location_dest_id': self.transit_location.id
            })

    def test_end_location_autofill_create_and_write(self) -> None:
        """Test that setting chain_dest_picking_type_id automatically defaults
        chain_end_location_id to the picking type's default destination.
        """
        # 1. Autofill on Create
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.source_picking_type.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'chain_transit_location_id': self.transit_location.id,
            'chain_dest_picking_type_id': self.dest_picking_type.id,
            'move_ids': [(0, 0, {
                'description_picking': self.product.display_name,
                'product_id': self.product.id,
                'product_uom_qty': 5.0,
                'product_uom': self.product.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
            })],
        })
        self.assertEqual(picking.chain_end_location_id.id, self.dest_picking_type.default_location_dest_id.id)

        # Clear it
        picking.write({'chain_end_location_id': False})
        self.assertFalse(picking.chain_end_location_id)

        # 2. Autofill on Write
        picking.write({
            'chain_dest_picking_type_id': self.dest_picking_type.id
        })
        self.assertEqual(picking.chain_end_location_id.id, self.dest_picking_type.default_location_dest_id.id)

