# -*- coding: utf-8 -*-

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestChainTransferTour(HttpCase):
    """Browser-side coverage of the chain transfer dialog.

    The dialog lives inside the barcode client action, so a Python test cannot
    catch a client-side crash: only a tour can.
    """

    def setUp(self) -> None:
        super().setUp()
        self.env['ir.config_parameter'].set_param(
            'stock_barcode.mute_sound_notifications', True
        )
        self.uid = self.env.ref('base.user_admin').id

        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.transit_location = self.env['stock.location'].create({
            'name': 'Test Transit Zone',
            'usage': 'transit',
            'company_id': self.env.company.id,
        })
        self.end_location = self.env['stock.location'].create({
            'name': 'Test End Location',
            'usage': 'internal',
            'location_id': warehouse.lot_stock_id.id,
            'company_id': self.env.company.id,
        })
        # A dedicated operation type: the tour asserts on its display name, and
        # it must not be the one already shipped in the barcode payload.
        self.dest_picking_type = self.env['stock.picking.type'].create({
            'name': 'Test Chain Internal',
            'code': 'internal',
            'sequence_code': 'TCI',
            'warehouse_id': warehouse.id,
            'default_location_src_id': self.transit_location.id,
            'default_location_dest_id': self.end_location.id,
        })
        product = self.env['product.product'].create({
            'name': 'Chain Tour Product',
            'type': 'consu',
            'is_storable': True,
            'barcode': 'chain-tour-product',
        })
        picking_type_in = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id', '=', warehouse.id),
        ], limit=1)

        self.picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_in.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'chain_transit_location_id': self.transit_location.id,
            'chain_dest_picking_type_id': self.dest_picking_type.id,
            'chain_end_location_id': self.end_location.id,
            'move_ids': [(0, 0, {
                'name': product.display_name,
                'product_id': product.id,
                'product_uom_qty': 2.0,
                'product_uom': product.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
            })],
        })
        self.picking.action_confirm()

    def test_chain_transfer_dialog_reopen(self) -> None:
        """Opening the dialog twice must not take the client action down."""
        url = f'/odoo/{self.picking.id}/action-stock_barcode.stock_barcode_picking_client_action'
        self.start_tour(url, 'test_chain_transfer_dialog_reopen', login='admin', timeout=180)

        self.picking.invalidate_recordset()
        self.assertEqual(self.picking.state, 'done')
        second_picking = self.env['stock.picking'].search([
            ('chain_origin', '=', self.picking.chain_origin),
            ('id', '!=', self.picking.id),
        ])
        self.assertEqual(len(second_picking), 1)
