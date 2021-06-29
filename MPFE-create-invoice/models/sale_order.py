# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from functools import partial
from itertools import groupby

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import formatLang, get_lang
from odoo.osv import expression
from odoo.tools import float_is_zero, float_compare


from werkzeug.urls import url_encode
import re

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_invoice(self):
        res = super()._prepare_invoice()
        res["x_studio_incoterms"] = self.x_studio_incoterms
        res["x_studio_metodo_di_pagamento_per_questa_fattura"] = self.x_studio_metodo_di_pagamento_per_questo_ordine
        return res

    def _get_totals( self, lines ):
        unit_translations = { 'kg': 'kg', 'Box': 'box', 'Unità': 'unit' }
        res = {}
        tot = {
            'pezzi'   : 0,
            'cartoni' : 0,
            'pallet'  : 0,
            'qta'     : 0,
            'd_qta'   : {
                'kg'   : 0,
                'box'  : 0,
                'unit' : 0,
            },
            # 'test_string' : '', # test
        };
        for line in lines:
            # tot['test_string'] += ' ' + line['x_studio_da_product'] # test
            tot['pezzi']   += line['x_studio_da_n_pezzi']
            tot['pallet']  += line['x_studio_da_pallet']
            tot['cartoni'] += line['x_studio_da_cartoni']
            if ( line['product_uom_id'] == 1 and re.search( 'serviz', line['x_studio_da_product'], re.IGNORECASE ) != None ) == False:
                tot['qta'] += 1
                unit = unit_translations[ line['x_studio_da_uom_1'] ] if line['x_studio_da_uom_1'] in unit_translations.keys() else line['x_studio_da_uom_1']
                if unit in tot['d_qta'].keys():
                    tot['d_qta'][ unit ] += line['quantity']
                else:
                    tot['d_qta'][ unit ] = line['quantity']
        res['pezzi']   = re.sub( '^(\d+)\.(\d+)$', r'\1,\2', str( tot['pezzi'] ) ) if tot['pezzi'] > 0 else None
        res['cartoni'] = re.sub( '^(\d+)\.(\d+)$', r'\1,\2', str( tot['cartoni'] ) ) if tot['cartoni'] > 0 else None
        res['pallet']  = re.sub( '^(\d+)\.(\d+)$', r'\1,\2', str( tot['pallet'] ) ) if tot['pallet'] > 0 else None
        res['kg']      = re.sub( '^(\d+)\.(\d+)$', r'\1,\2', str( tot['d_qta']['kg'] ) ) if tot['d_qta']['kg'] > 0 else None
        res['box']     = re.sub( '^(\d+)\.(\d+)$', r'\1', str( tot['d_qta']['box'] ) ) if tot['d_qta']['box'] > 0 else None
        res['unit']    = re.sub( '^(\d+)\.(\d+)$', r'\1', str( tot['d_qta']['unit'] ) ) if tot['d_qta']['unit'] > 0 else None
        # res['test_string'] = tot['test_string'] # test

        return res

    def _create_invoices(self, grouped=False, final=False, date=None):
        """
        Create the invoice associated to the SO.
        :param grouped: if True, invoices are grouped by SO id. If False, invoices are grouped by
                        (partner_invoice_id, currency)
        :param final: if True, refunds will be generated if necessary
        :returns: list of created invoices
        """
        if not self.env['account.move'].check_access_rights('create', False):
            try:
                self.check_access_rights('write')
                self.check_access_rule('write')
            except AccessError:
                return self.env['account.move']

        # 1) Create invoices.
        invoice_vals_list = []
        invoice_item_sequence = 0 # Incremental sequencing to keep the lines order on the invoice.
        for order in self:
            order = order.with_company(order.company_id)
            current_section_vals = None
            down_payments = order.env['sale.order.line']

            invoice_vals = order._prepare_invoice()
            invoiceable_lines = order._get_invoiceable_lines(final)

            if not any(not line.display_type for line in invoiceable_lines):
                raise self._nothing_to_invoice_error()

            invoice_line_vals = []
            down_payment_section_added = False
            sums_data = []
            for line in invoiceable_lines:
                if not down_payment_section_added and line.is_downpayment:
                    # Create a dedicated section for the down payments
                    # (put at the end of the invoiceable_lines)
                    invoice_line_vals.append(
                        (0, 0, order._prepare_down_payment_section_line(
                            sequence=invoice_item_sequence,
                        )),
                    )
                    dp_section = True
                    invoice_item_sequence += 1
                invoice_line = line._prepare_invoice_line( sequence=invoice_item_sequence, )
                sums_data.append( invoice_line.copy() )
                invoice_line.pop('x_studio_da_product', None)
                invoice_line.pop('x_studio_da_uom_1', None)
                invoice_line_vals.append(
                    (0, 0, invoice_line),
                )
                invoice_item_sequence += 1

            invoice_vals['invoice_line_ids'] += invoice_line_vals
            tots = self._get_totals( sums_data )
            invoice_vals['x_studio_da_tot_pallet']    = tots['pallet']
            invoice_vals['x_studio_da_tot_cartoni_2'] = tots['cartoni']
            invoice_vals['x_studio_da_tot_pezzi_2']   = tots['pezzi']
            invoice_vals['x_studio_da_tot_kg']        = tots['kg']
            invoice_vals['x_studio_da_tot_unit']      = tots['unit']
            invoice_vals['x_studio_da_tot_box']       = tots['box']
            # invoice_vals['narration'] += tots['test_string'] # test
            invoice_vals_list.append(invoice_vals)

        if not invoice_vals_list:
            raise self._nothing_to_invoice_error()

        # 2) Manage 'grouped' parameter: group by (partner_id, currency_id).
        if not grouped:
            new_invoice_vals_list = []
            invoice_grouping_keys = self._get_invoice_grouping_keys()
            for grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: [x.get(grouping_key) for grouping_key in invoice_grouping_keys]):
                origins = set()
                payment_refs = set()
                refs = set()
                ref_invoice_vals = None
                for invoice_vals in invoices:
                    if not ref_invoice_vals:
                        ref_invoice_vals = invoice_vals
                    else:
                        ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                    origins.add(invoice_vals['invoice_origin'])
                    payment_refs.add(invoice_vals['payment_reference'])
                    refs.add(invoice_vals['ref'])
                ref_invoice_vals.update({
                    'ref': ', '.join(refs)[:2000],
                    'invoice_origin': ', '.join(origins),
                    'payment_reference': len(payment_refs) == 1 and payment_refs.pop() or False,
                })
                new_invoice_vals_list.append(ref_invoice_vals)
            invoice_vals_list = new_invoice_vals_list

        # 3) Create invoices.

        # As part of the invoice creation, we make sure the sequence of multiple SO do not interfere
        # in a single invoice. Example:
        # SO 1:
        # - Section A (sequence: 10)
        # - Product A (sequence: 11)
        # SO 2:
        # - Section B (sequence: 10)
        # - Product B (sequence: 11)
        #
        # If SO 1 & 2 are grouped in the same invoice, the result will be:
        # - Section A (sequence: 10)
        # - Section B (sequence: 10)
        # - Product A (sequence: 11)
        # - Product B (sequence: 11)
        #
        # Resequencing should be safe, however we resequence only if there are less invoices than
        # orders, meaning a grouping might have been done. This could also mean that only a part
        # of the selected SO are invoiceable, but resequencing in this case shouldn't be an issue.
        if len(invoice_vals_list) < len(self):
            SaleOrderLine = self.env['sale.order.line']
            for invoice in invoice_vals_list:
                sequence = 1
                for line in invoice['invoice_line_ids']:
                    line[2]['sequence'] = SaleOrderLine._get_invoice_line_sequence(new=sequence, old=line[2]['sequence'])
                    sequence += 1

        # Manage the creation of invoices in sudo because a salesperson must be able to generate an invoice from a
        # sale order without "billing" access rights. However, he should not be able to create an invoice from scratch.
        moves = self.env['account.move'].sudo().with_context(default_move_type='out_invoice').create(invoice_vals_list)

        # 4) Some moves might actually be refunds: convert them if the total amount is negative
        # We do this after the moves have been created since we need taxes, etc. to know if the total
        # is actually negative or not
        if final:
            moves.sudo().filtered(lambda m: m.amount_total < 0).action_switch_invoice_into_refund_credit_note()
        for move in moves:
            move.message_post_with_view('mail.message_origin_link',
                values={'self': move, 'origin': move.line_ids.mapped('sale_line_ids.order_id')},
                subtype_id=self.env.ref('mail.mt_note').id
            )
        return moves

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.model
    def _prepare_down_payment_section_line(self, **optional_values):
        """
        Prepare the dict of values to create a new down payment section for a sales order line.

        :param optional_values: any parameter that should be added to the returned down payment section
        """
        down_payments_section_line = {
            'display_type': 'line_section',
            'name': _('Down Payments'),
            'product_id': False,
            'product_uom_id': False,
            'quantity': 0,
            'discount': 0,
            'price_unit': 0,
            'account_id': False,
            'x_studio_da_product': self.product_id.name,
            'x_studio_da_uom_1': self.product_uom.name,
        }
        if optional_values:
            down_payments_section_line.update(optional_values)
        down_payments_section_line["x_studio_da_n_pezzi"]  = 0
        down_payments_section_line["x_studio_da_cartoni"]  = 0
        down_payments_section_line["x_studio_da_pallet"]   = 0
        down_payments_section_line["x_studio_supplier"]    = 0
        return down_payments_section_line

    def _prepare_invoice_line(self, **optional_values):
        self.ensure_one()
        res = {
            'display_type': self.display_type,
            'sequence': self.sequence,
            'name': self.name,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'quantity': self.qty_to_invoice,
            'discount': self.discount,
            'price_unit': self.price_unit,
            'tax_ids': [(6, 0, self.tax_id.ids)],
            'analytic_account_id': self.order_id.analytic_account_id.id,
            'analytic_tag_ids': [(6, 0, self.analytic_tag_ids.ids)],
            'sale_line_ids': [(4, self.id)],
            'x_studio_da_product': self.product_id.product_tmpl_id.categ_id.name,
            'x_studio_da_uom_1': self.product_uom.name,
        }
        if optional_values:
            res.update(optional_values)
        if self.display_type:
            res['account_id'] = False
        res["x_studio_da_n_pezzi"]  = self.x_studio_da_n_pezzi
        res["x_studio_da_cartoni"]  = self.x_studio_da_cartoni
        res["x_studio_da_pallet"]   = self.x_studio_da_pallet
        res["x_studio_supplier"]    = self.x_studio_supplier
        return res

