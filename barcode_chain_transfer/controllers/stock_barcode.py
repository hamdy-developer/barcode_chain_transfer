# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.addons.stock_barcode.controllers.stock_barcode import StockBarcodeController


class StockBarcodeControllerInherit(StockBarcodeController):
    """Extend barcode controller to provide chain transfer data to frontend.

    Adds location and picking type search endpoints used by the
    chain transfer dialog OWL component.
    """

    @http.route(
        '/barcode_chain_transfer/get_locations',
        type='jsonrpc',
        auth='user',
    )
    def get_chain_locations(self, search_term='', limit=40) -> list:
        """Search stock locations using standard name_search.

        :param search_term: Partial name to filter locations
        :param limit: Maximum number of results
        :return: List of dicts with id and display_name
        """
        domain = [('usage', 'in', ['internal', 'transit'])]
        results = request.env['stock.location'].name_search(
            name=search_term,
            args=domain,
            operator='ilike',
            limit=limit,
        )
        return [{'id': res[0], 'display_name': res[1]} for res in results]

    @http.route(
        '/barcode_chain_transfer/get_picking_types',
        type='jsonrpc',
        auth='user',
    )
    def get_chain_picking_types(self, search_term='', limit=40) -> list:
        """Search picking types using standard name_search and retrieve default destinations.

        :param search_term: Partial name to filter picking types
        :param limit: Maximum number of results
        :return: List of dicts with id, display_name, and default destination location details
        """
        domain = [('active', '=', True)]
        results = request.env['stock.picking.type'].name_search(
            name=search_term,
            args=domain,
            operator='ilike',
            limit=limit,
        )
        picking_type_ids = [res[0] for res in results]
        picking_types = request.env['stock.picking.type'].browse(picking_type_ids)
        
        data = []
        for pt in picking_types:
            dest_loc = pt.default_location_dest_id
            data.append({
                'id': pt.id,
                'display_name': pt.display_name,
                'default_dest_location_id': dest_loc.id if dest_loc else False,
                'default_dest_location_name': dest_loc.display_name if dest_loc else "",
            })
        return data

    @http.route(
        '/barcode_chain_transfer/save_chain_data',
        type='jsonrpc',
        auth='user',
    )
    def save_chain_data(
        self,
        picking_id: int,
        transit_location_id: int,
        dest_picking_type_id: int,
        end_location_id: int = False,
        chain_use_putaway_rules: bool = False,
    ) -> dict:
        """Save chain transfer fields on the picking and update destination.

        Sets the chain transfer fields on the picking record and updates
        the picking's location_dest_id to the transit location.

        :param picking_id: The picking record ID
        :param transit_location_id: Transit location ID
        :param dest_picking_type_id: Destination picking type ID
        :param end_location_id: End location ID
        :return: Dict with success status and updated picking data
        """
        picking = request.env['stock.picking'].browse(picking_id)
        if not picking.exists():
            return {'success': False, 'error': 'Picking not found'}

        # Write chain fields and update destination to transit location
        picking.write({
            'chain_transit_location_id': transit_location_id,
            'chain_dest_picking_type_id': dest_picking_type_id,
            'chain_end_location_id': end_location_id,
            'chain_use_putaway_rules': chain_use_putaway_rules,
            'location_dest_id': transit_location_id,
        })

        return {
            'success': True,
            'chain_transit_location_id': transit_location_id,
            'chain_dest_picking_type_id': dest_picking_type_id,
            'chain_end_location_id': end_location_id,
            'chain_use_putaway_rules': chain_use_putaway_rules,
        }

    @http.route(
        '/barcode_chain_transfer/clear_chain_data',
        type='jsonrpc',
        auth='user',
    )
    def clear_chain_data(self, picking_id: int) -> dict:
        """Clear chain transfer fields from the picking.

        :param picking_id: The picking record ID
        :return: Dict with success status
        """
        picking = request.env['stock.picking'].browse(picking_id)
        if not picking.exists():
            return {'success': False, 'error': 'Picking not found'}

        picking.write({
            'chain_transit_location_id': False,
            'chain_dest_picking_type_id': False,
            'chain_end_location_id': False,
            'chain_use_putaway_rules': False,
        })

        return {'success': True}
