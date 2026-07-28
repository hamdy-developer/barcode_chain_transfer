# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.addons.stock_barcode.controllers.stock_barcode import StockBarcodeController

# Locations goods may legitimately travel through or land in.
CHAIN_ALLOWED_USAGES = ('internal', 'transit')


class StockBarcodeControllerInherit(StockBarcodeController):
    """Extend barcode controller to provide chain transfer data to frontend.

    Adds location and picking type search endpoints used by the
    chain transfer dialog OWL component.
    """

    def _chain_check_access(self) -> None:
        """Reject anyone who is not an inventory user.

        ``http.route`` has no ``groups`` option, so the group is enforced here.
        Without it, every ``auth='user'`` account - including portal users, who
        have no business in the barcode app - could enumerate the warehouse's
        locations and operation types.
        """
        if not request.env.user.has_group('stock.group_stock_user'):
            raise AccessError(_(
                "You are not allowed to access chain transfer data."
            ))

    def _chain_env(self):
        """Return an environment scoped to the companies selected in the UI.

        ``request.env`` inside a controller ignores the company switcher, which
        would leak (or hide) records across companies.
        """
        return request.env(context=dict(
            request.env.context,
            allowed_company_ids=self._get_allowed_company_ids(),
        ))

    @http.route(
        '/barcode_chain_transfer/get_locations',
        type='json',
        auth='user',
    )
    def get_chain_locations(self, search_term='', limit=40) -> list:
        """Search stock locations using standard name_search.

        :param search_term: Partial name to filter locations
        :param limit: Maximum number of results
        :return: List of dicts with id and display_name
        """
        self._chain_check_access()
        domain = [('usage', 'in', list(CHAIN_ALLOWED_USAGES))]
        results = self._chain_env()['stock.location'].name_search(
            name=search_term,
            args=domain,
            operator='ilike',
            limit=limit,
        )
        return [{'id': res[0], 'display_name': res[1]} for res in results]

    @http.route(
        '/barcode_chain_transfer/get_picking_types',
        type='json',
        auth='user',
    )
    def get_chain_picking_types(self, search_term='', limit=40) -> list:
        """Search picking types using standard name_search and retrieve default destinations.

        :param search_term: Partial name to filter picking types
        :param limit: Maximum number of results
        :return: List of dicts with id, display_name, and default destination location details
        """
        self._chain_check_access()
        env = self._chain_env()
        domain = [('active', '=', True)]
        results = env['stock.picking.type'].name_search(
            name=search_term,
            args=domain,
            operator='ilike',
            limit=limit,
        )
        picking_types = env['stock.picking.type'].browse([res[0] for res in results])

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
        type='json',
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
        :param chain_use_putaway_rules: Let putaway rules pick the end location
        :return: Dict with success status and updated picking data
        """
        self._chain_check_access()
        env = self._chain_env()
        picking = env['stock.picking'].browse(picking_id)
        if not picking.exists():
            return {'success': False, 'error': _("Transfer not found.")}

        if not transit_location_id or not dest_picking_type_id:
            return {
                'success': False,
                'error': _("A Transit Location and a Destination Picking Type are required."),
            }
        if not end_location_id and not chain_use_putaway_rules:
            return {
                'success': False,
                'error': _("Set an End Location or enable the putaway rules."),
            }

        # The dialog only offers internal/transit locations; make sure a crafted
        # RPC call cannot route goods to a view or partner location either.
        locations = env['stock.location'].browse(
            [loc_id for loc_id in (transit_location_id, end_location_id) if loc_id]
        )
        if not locations.exists() or any(
            location.usage not in CHAIN_ALLOWED_USAGES for location in locations
        ):
            return {
                'success': False,
                'error': _("Only internal and transit locations can be used for a chain transfer."),
            }

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
        type='json',
        auth='user',
    )
    def clear_chain_data(self, picking_id: int) -> dict:
        """Clear chain transfer fields from the picking.

        :param picking_id: The picking record ID
        :return: Dict with success status
        """
        self._chain_check_access()
        picking = self._chain_env()['stock.picking'].browse(picking_id)
        if not picking.exists():
            return {'success': False, 'error': _("Transfer not found.")}

        picking.write({
            'chain_transit_location_id': False,
            'chain_dest_picking_type_id': False,
            'chain_end_location_id': False,
            'chain_use_putaway_rules': False,
        })

        return {'success': True}
