# -*- encoding: utf-8 -*-
{
    'name' : 'MPFE - create invoice',
    'version': '0.0.1',
    'summary': 'Module customization',
    'category': 'Custom Development',
    'author': 'Silvio Benvegnù @ Digital Automations',
    'description':
        """

Digital Automations
-------------------

MPFE-create-order


Copy fields from res.partner to sale.order

This module copy:

- res_partner['x_studio_incoterms_1.code'] -> sale_order.x_studio_incoterms

when a partner is selected.  

""",
    'data': [
    ],
    'depends': ['sale'],
}
