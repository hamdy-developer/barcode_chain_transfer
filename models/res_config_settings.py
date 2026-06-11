# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    """Inherit settings to add Manager Approval for Chain Transfers."""

    _inherit = 'res.config.settings'

    approve_chain_by_manager = fields.Boolean(
        string="Approve Chain Transfers by Manager",
        related="company_id.approve_chain_by_manager",
        readonly=False,
        help="If enabled, all barcode chain transfers will require approval "
             "by an Inventory Manager before they can be validated."
    )
    company_chain_transit_location_id = fields.Many2one(
        'stock.location',
        related="company_id.company_chain_transit_location_id",
        readonly=False,
        string="Default Transit Location",
        domain=[('usage', 'in', ['internal', 'transit'])],
        help="Default transit location pre-filled in the Barcode Chain Transfer dialog."
    )


class ResCompany(models.Model):
    """Inherit company to store the settings value."""

    _inherit = 'res.company'

    approve_chain_by_manager = fields.Boolean(
        string="Approve Chain Transfers by Manager",
        default=False
    )
    company_chain_transit_location_id = fields.Many2one(
        'stock.location',
        string="Default Transit Location",
        domain=[('usage', 'in', ['internal', 'transit'])]
    )
