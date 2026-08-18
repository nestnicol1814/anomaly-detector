"""
Single source of truth for the rule catalogue.

Maps each rule ID to the underlying boolean flag field name used in the
ICCC Non-PO system prompt ("COMPUTED FIELDS AND RULE LOGIC" section).
These flag names are the join key between the AI report's Control Flags
justification cell and the ML model's rule output columns.
"""

RULE_FLAGS = {
    "R01": "record_at_weekend",
    "R02": "payment_at_weekend",
    "R03": "less_than_30_days_vendor_creation_non_po",
    "R04": "less_than_30_days_bank_change_non_po",
    "R05": "supplier_non_po_last_two_months",
    "R06": "company_vendor_amount_500k",
    "R07": "single_record_supplier_100k",
    "R08": "single_record_employee_10k",
    "R09": "supplier_name_starts_zz",
    "R10": "government_multiple_bank_accounts",
    "R11": "bank_account_10_percent_non_po",
    "R12": "one_time_vendor",
    "R13": "bank_tax_haven_vendor_country_mismatch",
    "R14": "bank_tax_haven_vendor_zone_mismatch",
    "R15": "vendor_bank_zone_mismatch",
    "R16": "bank_exotic_danger_country",
    "R17": "user_non_po_own_employee",
    "R18": "technical_gl_accounts",
    "R19": "pl_trade_allowances",
    "R20": "gr_ir_gl_accounts",
    "R21": "unusual_debit_credit",
    "R22": "debit_gl_credit_vendor",
    "R23": "credit_bank_account",
    "R24": "payment_trade_receivables",
    "R25": "payment_gl_group_7",
    "R26": "petty_cash_high_amounts",
    "R27": "document_before_vendor_creation",
}
