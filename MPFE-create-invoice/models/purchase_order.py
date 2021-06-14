# -*- coding: utf-8 -*-
# Al momento della creazione di una fattura:
#   prende sale_order.x_studio_incoterms e lo copia in account_move.x_da_incoterms


from odoo import models

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _prepare_invoice(self):
        res = super()._prepare_invoice()
        #res["x_studio_incoterms"] = self.x_studio_incoterms
        return res

