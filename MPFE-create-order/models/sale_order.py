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

class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        """
        Update the following fields when the partner is changed:
        - Pricelist
        - Payment terms
        - Invoice address
        - Delivery address
        - Sales Team
        - Incoterms
        # - Agente Esterno
        """
        if not self.partner_id:
            self.update({
                'partner_invoice_id': False,
                'partner_shipping_id': False,
                'fiscal_position_id': False,
                'x_studio_incoterms': '',
                # 'x_studio_agente_esterno' : '',
            })
            return

        self = self.with_company(self.company_id)

        addr = self.partner_id.address_get(['delivery', 'invoice'])
        partner_user = self.partner_id.user_id or self.partner_id.commercial_partner_id.user_id
        incoterms = self.partner_id.x_studio_incoterms_1.code
        # agente_esterno = self.partner_id._studio_many2one_field_6csFz.display_name
        values = {
            'pricelist_id': self.partner_id.property_product_pricelist and self.partner_id.property_product_pricelist.id or False,
            'payment_term_id': self.partner_id.property_payment_term_id and self.partner_id.property_payment_term_id.id or False,
            'partner_invoice_id': addr['invoice'],
            'partner_shipping_id': addr['delivery'],
            'x_studio_incoterms': incoterms,
            # 'x_studio_agente_esterno' : ageste_esterno,
        }
        user_id = partner_user.id
        if not self.env.context.get('not_self_saleperson'):
            user_id = user_id or self.env.uid
        if user_id and self.user_id.id != user_id:
            values['user_id'] = user_id

        if self.env['ir.config_parameter'].sudo().get_param('account.use_invoice_terms') and self.env.company.invoice_terms:
            values['note'] = self.with_context(lang=self.partner_id.lang).env.company.invoice_terms
        if not self.env.context.get('not_self_saleperson') or not self.team_id:
            values['team_id'] = self.env['crm.team'].with_context(
                default_team_id=self.partner_id.team_id.id
            )._get_default_team_id(domain=['|', ('company_id', '=', self.company_id.id), ('company_id', '=', False)], user_id=user_id)
        self.update(values)

#   def create(self, vals):
#       if 'company_id' in vals:
#           self = self.with_company(vals['company_id'])
#       if vals.get('name', _('New')) == _('New'):
#           seq_date = None
#           if 'date_order' in vals:
#               seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals['date_order']))
#           vals['name'] = self.env['ir.sequence'].next_by_code('sale.order', sequence_date=seq_date) or _('New')

#       # Makes sure partner_invoice_id', 'partner_shipping_id' and 'pricelist_id' are defined
#       if any(f not in vals for f in ['partner_invoice_id', 'partner_shipping_id', 'pricelist_id']):
#           partner = self.env['res.partner'].browse(vals.get('partner_id'))
#           addr = partner.address_get(['delivery', 'invoice'])
#           vals['partner_invoice_id'] = vals.setdefault('partner_invoice_id', addr['invoice'])
#           vals['partner_shipping_id'] = vals.setdefault('partner_shipping_id', addr['delivery'])
#           vals['pricelist_id'] = vals.setdefault('pricelist_id', partner.property_product_pricelist.id)
#           vals['x_studio_incoterms'] = partner.x_studio_incoterms_1.code
#       result = super(SaleOrder, self).create(vals)
#       return result

