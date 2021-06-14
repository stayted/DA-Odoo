# DA - Odoo Modules

> This repository containes all Odoo Modules developed by Digital Automations

## MPFE-create-invoice

> Copy fields from sale.order and purchase.order to account.move

This module copy:

- `x_studio_incoterms` from `sale.order` -> `x_studio_incoterms` in `account.move`
- `x_studio_metodo_di_pagamento_per_questo_ordine` from `sale.order` -> `x_studio_metodo_di_pagamento_per_questa_fattura` in `account.move`
- `x_studio_da_n_pezzi` from `sale.order.line` -> `x_studio_da_n_pezzi` in `account.move.line`
- `x_studio_da_cartoni` from `sale.order.line` -> `x_studio_da_cartoni` in `account.move.line`
- `x_studio_da_pallet` from `sale.order.line` -> `x_studio_da_pallet` in `account.move.line`
- `x_studio_supplier` from `sale.order.line` -> `x_studio_supplier` in `account.move.linecamp`

when an account\_invoice is generated.

