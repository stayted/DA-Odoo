# -*- coding: utf-8 -*-
# Al momento della creazione di una fattura:
#   prende sale_order.x_studio_incoterms e lo copia in account_move.x_da_incoterms


from odoo import models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_invoice(self):
        res = super()._prepare_invoice()
        res["x_studio_incoterms"] = self.x_studio_incoterms
        res["x_studio_metodo_di_pagamento_per_questa_fattura"] = self.x_studio_metodo_di_pagamento_per_questo_ordine
        return res

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line( **optional_values )
        res["x_studio_da_n_pezzi"]  = self.x_studio_da_n_pezzi
        res["x_studio_da_cartoni"]  = self.x_studio_da_cartoni
        res["x_studio_da_pallet"]   = self.x_studio_da_pallet
        res["x_studio_supplier"] = self.x_studio_supplier
        return res

