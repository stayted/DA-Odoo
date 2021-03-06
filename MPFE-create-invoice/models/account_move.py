# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import RedirectWarning, UserError, ValidationError, AccessError
from odoo.tools import float_compare, date_utils, email_split, email_re
from odoo.tools.misc import formatLang, format_date, get_lang

from datetime import date, timedelta
from collections import defaultdict
from itertools import zip_longest
from hashlib import sha256
from json import dumps

import ast
import json
import re
import warnings

#forbidden fields
INTEGRITY_HASH_MOVE_FIELDS = ('date', 'journal_id', 'company_id')
INTEGRITY_HASH_LINE_FIELDS = ('debit', 'credit', 'account_id', 'partner_id')


def calc_check_digits(number):
    """Calculate the extra digits that should be appended to the number to make it a valid number.
    Source: python-stdnum iso7064.mod_97_10.calc_check_digits
    """
    number_base10 = ''.join(str(int(x, 36)) for x in number)
    checksum = int(number_base10) % 97
    return '%02d' % ((98 - 100 * checksum) % 97)


class AccountMove(models.Model):
    _inherit = "account.move"

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
            category_name = line.product_id.product_tmpl_id.categ_id.name
            if category_name == False:
                continue
            tot['pezzi']   += line['x_studio_da_n_pezzi']
            tot['pallet']  += line['x_studio_da_pallet']
            tot['cartoni'] += line['x_studio_da_cartoni']
            # tot['test_string'] += ' ' + str( category_name ) # test
            if ( line.product_uom_id == 1 and re.search( 'serviz', category_name, re.IGNORECASE ) != None ) == False:
                tot['qta'] += 1
                unit = unit_translations[ line.product_uom_id.name ] if line.product_uom_id.name in unit_translations.keys() else line.product_uom_id.name
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

    @api.depends(
        'line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.debit',
        'line_ids.credit',
        'line_ids.currency_id',
        'line_ids.amount_currency',
        'line_ids.amount_residual',
        'line_ids.amount_residual_currency',
        'line_ids.payment_id.state',
        'line_ids.full_reconcile_id')
    def _compute_amount(self):
        for move in self:

            if move.payment_state == 'invoicing_legacy':
                # invoicing_legacy state is set via SQL when setting setting field
                # invoicing_switch_threshold (defined in account_accountant).
                # The only way of going out of this state is through this setting,
                # so we don't recompute it here.
                move.payment_state = move.payment_state
                continue

            total_untaxed = 0.0
            total_untaxed_currency = 0.0
            total_tax = 0.0
            total_tax_currency = 0.0
            total_to_pay = 0.0
            total_residual = 0.0
            total_residual_currency = 0.0
            total = 0.0
            total_currency = 0.0
            currencies = move._get_lines_onchange_currency().currency_id

            sums_data = [] # custom
            for line in move.line_ids:
                sums_data.append( line ) # custom
                if move.is_invoice(include_receipts=True):
                    # === Invoices ===

                    if not line.exclude_from_invoice_tab:
                        # Untaxed amount.
                        total_untaxed += line.balance
                        total_untaxed_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.tax_line_id:
                        # Tax amount.
                        total_tax += line.balance
                        total_tax_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.account_id.user_type_id.type in ('receivable', 'payable'):
                        # Residual amount.
                        total_to_pay += line.balance
                        total_residual += line.amount_residual
                        total_residual_currency += line.amount_residual_currency
                else:
                    # === Miscellaneous journal entry ===
                    if line.debit:
                        total += line.balance
                        total_currency += line.amount_currency

            if move.move_type == 'entry' or move.is_outbound():
                sign = 1
            else:
                sign = -1
            move.amount_untaxed = sign * (total_untaxed_currency if len(currencies) == 1 else total_untaxed)
            move.amount_tax = sign * (total_tax_currency if len(currencies) == 1 else total_tax)
            move.amount_total = sign * (total_currency if len(currencies) == 1 else total)
            move.amount_residual = -sign * (total_residual_currency if len(currencies) == 1 else total_residual)
            move.amount_untaxed_signed = -total_untaxed
            move.amount_tax_signed = -total_tax
            move.amount_total_signed = abs(total) if move.move_type == 'entry' else -total
            move.amount_residual_signed = total_residual
            tots = self._get_totals( sums_data ) # custom
            move['x_studio_da_tot_pallet']    = tots['pallet']
            move['x_studio_da_tot_cartoni_2'] = tots['cartoni']
            move['x_studio_da_tot_pezzi_2']   = tots['pezzi']
            move['x_studio_da_tot_kg']        = tots['kg']
            move['x_studio_da_tot_unit']      = tots['unit']
            move['x_studio_da_tot_box']       = tots['box']
            # move['narration'] += tots['test_string'] # test

            currency = len(currencies) == 1 and currencies or move.company_id.currency_id

            # Compute 'payment_state'.
            new_pmt_state = 'not_paid' if move.move_type != 'entry' else False

            if move.is_invoice(include_receipts=True) and move.state == 'posted':

                if currency.is_zero(move.amount_residual):
                    reconciled_payments = move._get_reconciled_payments()
                    if not reconciled_payments or all(payment.is_matched for payment in reconciled_payments):
                        new_pmt_state = 'paid'
                    else:
                        new_pmt_state = move._get_invoice_in_payment_state()
                elif currency.compare_amounts(total_to_pay, total_residual) != 0:
                    new_pmt_state = 'partial'

            if new_pmt_state == 'paid' and move.move_type in ('in_invoice', 'out_invoice', 'entry'):
                reverse_type = move.move_type == 'in_invoice' and 'in_refund' or move.move_type == 'out_invoice' and 'out_refund' or 'entry'
                reverse_moves = self.env['account.move'].search([('reversed_entry_id', '=', move.id), ('state', '=', 'posted'), ('move_type', '=', reverse_type)])

                # We only set 'reversed' state in cas of 1 to 1 full reconciliation with a reverse entry; otherwise, we use the regular 'paid' state
                reverse_moves_full_recs = reverse_moves.mapped('line_ids.full_reconcile_id')
                if reverse_moves_full_recs.mapped('reconciled_line_ids.move_id').filtered(lambda x: x not in (reverse_moves + reverse_moves_full_recs.mapped('exchange_move_id'))) == move:
                    new_pmt_state = 'reversed'

            move.payment_state = new_pmt_state

