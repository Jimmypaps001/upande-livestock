"""Livestock asset disposal API endpoints, ported from sandboxed Frappe Server Scripts."""

import frappe


@frappe.whitelist()
def scrap_livestock_asset(animal=None, asset_name=None, reason=None, scrapping_date=None):
    animal_name = animal or asset_name
    reason = reason or ''
    scrapping_date = scrapping_date or frappe.utils.today()

    if not animal_name:
        frappe.throw('animal is required')

    animal_doc = frappe.get_doc('Animal', animal_name)
    asset_name = animal_doc.asset_link
    if not asset_name:
        frappe.throw('Animal ' + str(animal_name) + ' is not capitalised (no linked Asset); cannot scrap.')

    asset = frappe.get_doc('Asset', asset_name)

    if asset.docstatus != 1:
        frappe.throw('Asset must be submitted before scrapping')

    if asset.status in ('Cancelled', 'Sold', 'Scrapped'):
        frappe.throw('Asset is already ' + asset.status)

    company = asset.company

    # ── Fetch Company defaults ──
    company_doc = frappe.get_doc('Company', company)
    company_disposal_account = getattr(company_doc, 'disposal_account', None)
    company_dep_expense_account = getattr(company_doc, 'depreciation_expense_account', None)
    company_dep_cost_center = getattr(company_doc, 'depreciation_cost_center', None)
    company_default_cost_center = company_doc.cost_center

    # ── Fetch accounts from Asset Category ──
    asset_category = asset.asset_category
    category_fixed_asset_account = None
    category_accumulated_dep = None
    category_dep_expense = None

    if asset_category:
        cat_doc = frappe.get_doc('Asset Category', asset_category)
        for row in cat_doc.accounts:
            if row.company_name == company:
                category_fixed_asset_account = row.fixed_asset_account
                category_accumulated_dep = getattr(row, 'accumulated_depreciation_account', None)
                category_dep_expense = getattr(row, 'depreciation_expense_account', None)
                break

    # ── Resolve Disposal Account ──
    # Priority: Company disposal account > Asset Category fixed asset account > search by name
    disposal_account = company_disposal_account

    if not disposal_account:
        try:
            disposal_account = frappe.get_cached_value('Company', company, 'gain_loss_on_asset_disposal')
        except Exception:
            pass

    if not disposal_account:
        disposal_account = frappe.db.get_value(
            'Account',
            {'company': company, 'account_name': ['like', '%Gain%Loss%Asset%']},
            'name'
        )

    # ── Resolve Depreciation Expense Account ──
    # Priority: Asset Category > Company > search by name
    depreciation_expense_account = category_dep_expense or company_dep_expense_account

    if not depreciation_expense_account:
        depreciation_expense_account = frappe.db.get_value(
            'Account',
            {'company': company, 'root_type': 'Expense', 'account_name': ['like', '%Depreciation%']},
            'name'
        )

    if not disposal_account or not depreciation_expense_account:
        frappe.throw('Please set Disposal Account and Depreciation Expense Account in Company ' + company + ' or in Asset Category ' + (asset_category or '(none)'))

    # ── Resolve Cost Center: asset-level > company depreciation cost center > company default ──
    cost_center = asset.cost_center or company_dep_cost_center or company_default_cost_center or ''

    # ── Resolve Accumulated Depreciation Account for write-off ──
    accumulated_dep_account = category_accumulated_dep
    if not accumulated_dep_account:
        accumulated_dep_account = getattr(company_doc, 'accumulated_depreciation_account', None)

    # ── Calculate values ──
    gross_amount = asset.gross_purchase_amount or 0
    accumulated_depreciation = asset.opening_accumulated_depreciation or 0
    value_after_dep = asset.value_after_depreciation if asset.value_after_depreciation is not None else gross_amount

    # ── Create Journal Entry ──
    je = frappe.new_doc('Journal Entry')
    je.voucher_type = 'Depreciation Entry'
    je.naming_series = 'ACC-JV-.YYYY.-'
    je.company = company
    je.posting_date = scrapping_date
    je.remark = 'Scrap Entry for asset ' + asset_name + ('. Reason: ' + reason if reason else '')

    # Debit the disposal account (write off the remaining value)
    je.append('accounts', {
        'account': disposal_account,
        'debit_in_account_currency': value_after_dep,
        'cost_center': cost_center
    })

    # If there is accumulated depreciation, debit it to clear the balance
    if accumulated_depreciation and accumulated_dep_account:
        je.append('accounts', {
            'account': accumulated_dep_account,
            'debit_in_account_currency': accumulated_depreciation,
            'cost_center': cost_center
        })
        # Credit the fixed asset account for the full gross amount
        credit_account = category_fixed_asset_account or depreciation_expense_account
        je.append('accounts', {
            'account': credit_account,
            'credit_in_account_currency': gross_amount,
            'cost_center': cost_center,
            'reference_type': 'Asset',
            'reference_name': asset_name
        })
    else:
        # Simple case: credit the depreciation expense account
        je.append('accounts', {
            'account': depreciation_expense_account,
            'credit_in_account_currency': value_after_dep,
            'cost_center': cost_center,
            'reference_type': 'Asset',
            'reference_name': asset_name
        })

    je.insert(ignore_permissions=True)
    je.submit()

    # ── Update Asset status ──
    update_fields = {
        'status': 'Scrapped',
        'journal_entry_for_scrap': je.name,
        'disposal_date': scrapping_date
    }

    if reason:
        update_fields['custom_reason_for_scrapping'] = reason

    frappe.db.set_value('Asset', asset_name, update_fields)
    frappe.db.set_value('Animal', animal_name, 'status', 'Dead')
    frappe.db.commit()

    return {
        'success': True,
        'asset': asset_name,
        'status': 'Scrapped',
        'journal_entry': je.name,
        'reason': reason
    }


@frappe.whitelist()
def sell_livestock_asset(animal=None, asset_name=None, customer=None, selling_amount=None,
                         posting_date=None, farm=None, business_unit=None):
    animal_name = animal or asset_name
    posting_date = posting_date or frappe.utils.today()
    farm = farm or ''
    business_unit = business_unit or ''

    if not animal_name:
        frappe.throw('animal is required')
    if not customer:
        frappe.throw('customer is required')
    if not selling_amount:
        frappe.throw('selling_amount is required')

    selling_amount = float(selling_amount)

    animal_doc = frappe.get_doc('Animal', animal_name)
    asset_name = animal_doc.asset_link
    if not asset_name:
        frappe.throw('Animal ' + str(animal_name) + ' is not capitalised (no linked Asset); cannot sell as fixed asset.')
    asset = frappe.get_doc('Asset', asset_name)

    if asset.docstatus != 1:
        frappe.throw('Asset must be submitted before selling')

    if asset.status in ('Cancelled', 'Sold', 'Scrapped'):
        frappe.throw('Asset is already ' + asset.status)

    company = asset.company

    company_doc = frappe.get_doc('Company', company)
    company_currency = company_doc.default_currency or 'KES'
    default_receivable = company_doc.default_receivable_account
    default_expense = company_doc.default_expense_account
    default_cost_center = company_doc.cost_center
    default_income = company_doc.default_income_account

    asset_category = asset.asset_category
    category_fixed_asset_account = None

    if asset_category:
        cat_doc = frappe.get_doc('Asset Category', asset_category)
        for row in cat_doc.accounts:
            if row.company_name == company:
                category_fixed_asset_account = row.fixed_asset_account
                break

    disposal_account = None
    try:
        disposal_account = frappe.get_cached_value('Company', company, 'disposal_account')
    except Exception:
        pass

    if not disposal_account:
        try:
            disposal_account = frappe.get_cached_value('Company', company, 'gain_loss_on_asset_disposal')
        except Exception:
            pass

    if not disposal_account:
        disposal_account = category_fixed_asset_account or default_income

    income_account = disposal_account or default_income
    expense_account = default_expense
    cost_center = asset.cost_center or default_cost_center
    debit_to = default_receivable

    default_price_list = frappe.db.get_value('Selling Settings', None, 'selling_price_list') or ''
    price_list_currency = company_currency
    plc_conversion_rate = 1

    if default_price_list:
        pl_currency = frappe.db.get_value('Price List', default_price_list, 'currency')
        if pl_currency:
            price_list_currency = pl_currency
            if pl_currency != company_currency:
                try:
                    plc_conversion_rate = frappe.db.get_value(
                        'Currency Exchange',
                        {'from_currency': pl_currency, 'to_currency': company_currency},
                        'exchange_rate',
                        order_by='date desc'
                    ) or 1
                except Exception:
                    plc_conversion_rate = 1

    si = frappe.get_doc({
        'doctype': 'Sales Invoice',
        'customer': customer,
        'company': company,
        'posting_date': posting_date,
        'due_date': posting_date,
        'naming_series': 'SINV-.YYYY.-',
        'currency': company_currency,
        'conversion_rate': 1,
        'selling_price_list': default_price_list,
        'price_list_currency': price_list_currency,
        'plc_conversion_rate': plc_conversion_rate,
        'debit_to': debit_to,
        'update_stock': 0,
        'custom_farm': farm,
        'custom_business_unit': business_unit,
        'remarks': 'Livestock sale - ' + asset_name,
        'items': [{
            'item_code': asset.item_code or 'herd',
            'item_name': asset.item_name or asset.asset_name or 'herd',
            'description': 'Livestock sale: ' + (asset.asset_name or asset_name),
            'item_group': 'Assets',
            'stock_uom': 'Nos',
            'uom': 'Nos',
            'conversion_factor': 1,
            'qty': 1,
            'rate': selling_amount,
            'price_list_rate': selling_amount,
            'discount_percentage': 0,
            'income_account': income_account,
            'expense_account': expense_account,
            'is_fixed_asset': 1,
            'asset': asset_name,
            'cost_center': cost_center
        }]
    })

    si.flags.ignore_pricing_rule = True
    si.flags.ignore_permissions = True
    si.insert(ignore_permissions=True)

    frappe.db.set_value('Animal', animal_name, 'status', 'Sold')
    frappe.db.commit()

    return {
        'success': True,
        'asset': asset_name,
        'sales_invoice': si.name,
        'workflow_state': si.workflow_state or 'Draft',
        'customer': customer,
        'selling_amount': selling_amount,
        'grand_total': si.grand_total,
        'currency': si.currency
    }
