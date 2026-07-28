# -*- coding: utf-8 -*-
{
    'name': 'Auto-Chain Transfer & Putaway for Barcode',
    'summary': """
        Two-step chain transfer from the barcode scanning screen and backend.
        Automatically creates a second transfer upon validation.""",
    'description': """
        Adds a chain transfer feature to the stock barcode interface and backend picking form.
        Users can configure a Transit Location, Destination Picking Type,
        and End Location. On validation, a second transfer is automatically
        created with the same products, routing from transit to the end location.
    """,
    'author': 'ENG/Mohamed Hamdy',
    'website': 'https://bps-solution.odoo.com',
    'category': 'Inventory/Inventory',
    'version': '18.0.2.2.0',
    'depends': ['stock', 'stock_barcode'],
    'data': [
        'data/sequence_data.xml',
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/stock_picking_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'barcode_chain_transfer/static/src/**/*.css',
            'barcode_chain_transfer/static/src/**/*.js',
            'barcode_chain_transfer/static/src/**/*.xml',
        ],
        'web.assets_tests': [
            'barcode_chain_transfer/static/tests/tours/**/*',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'OPL-1',
    'price': 29.00,
    'currency': 'USD',
    'images': [
        'static/description/main_screenshot.png'
    ],
}
