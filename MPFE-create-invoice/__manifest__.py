# -*- encoding: utf-8 -*-
{
    'name' : 'MPFE - create_invoice',
    'version': '0.0.1',
    'summary': 'Module customization',
    'category': 'Custom Development',
    'author': 'Silvio Benvegnù @ Digital Automations',
    'description':
        "Copy fields when an account invoice is created",
    'data': [
        'views/account_move.xml',
    ],
    'depends': ['account', 'sale', 'purchase'],
}
