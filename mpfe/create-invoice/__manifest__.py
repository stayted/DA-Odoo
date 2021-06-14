# -*- encoding: utf-8 -*-
{
    'name' : 'DA - odoo_sale_purchase_to_account',
    'version': '0.0.1',
    'summary': 'Module customization',
    'category': 'Custom Development',
    'author': 'Silvio Benvegnù @ Digital Automations',
    'description':
        """
Digital Automations
====================

Copy fields from sale.order and purchase.order to account.move

This module copies:

- x_studio_incoterms from sale.order

        """,
    'data': [
        'views/account_move.xml',
    ],
    'depends': ['account', 'sale', 'purchase'],
}
