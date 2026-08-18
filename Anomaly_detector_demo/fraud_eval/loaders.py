"""
File loaders for the two input datasets:
  - the ML rule-trigger table (Excel) with comma-separated rule markers
  - the AI rule table (Excel) with binary rule columns (R01-R27)

Both raise a clear ValueError naming the offending file/row rather than
failing with a bare KeyError deep in some other function.
"""
import os
import sys
import pandas as pd
import warnings

warnings.filterwarnings('ignore')

from .rules import RULE_FLAGS


def load_ml_table(excel_path):
    """Load ML table (Excel) with comma-separated rule marker.
    
    Expected columns: [Company Code], [Document Nr], [Supplier Nr], [Supplier name], [Rule Marker]
    Creates transaction_id from company_code + document_nr.
    Parses [Rule Marker] (comma-separated rule IDs) into {rule_id: bool}.
    Returns {transaction_id: {"ml_decision": str, "ml_flags": {rule_id: bool}, "metadata": {...}}}.
    """
    if not os.path.isfile(excel_path):
        raise ValueError(f"ML table not found: {excel_path}")

    ground_truth = {}
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        raise ValueError(f"Failed to read ML table {excel_path}: {e}")
    
    required_cols = {"[Company Code]", "[Document Nr]", "[Rule Marker]"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"ML table {excel_path} is missing required column(s): {sorted(missing_cols)}"
        )
    
    for idx, row in df.iterrows():
        company_code = str(row.get("[Company Code]", "")).strip()
        doc_nr = str(row.get("[Document Nr]", "")).strip()
        rule_marker = str(row.get("[Rule Marker]", "")).strip()
        
        if not company_code or not doc_nr:
            raise ValueError(f"ML table {excel_path}, row {idx + 2}: empty company_code or doc_nr")
        
        # Create transaction_id from company_code + document_nr
        transaction_id = f"{company_code}_{doc_nr}"
        
        # Parse comma-separated rule marker into {rule_id: bool}
        triggered_rules = {r.strip() for r in rule_marker.split(",") if r.strip()}
        flags = {rule_id: rule_id in triggered_rules for rule_id in RULE_FLAGS}
        
        ground_truth[transaction_id] = {
            "ml_decision": "High",  # Default; adjust if your data has explicit decision column
            "ml_flags": flags,
            "metadata": {
                "company_code": company_code,
                "document_nr": doc_nr,
                "supplier_nr": str(row.get("[Supplier Nr]", "")).strip(),
                "supplier_name": str(row.get("[Supplier name]", "")).strip(),
            }
        }

    if not ground_truth:
        raise ValueError(f"ML table {excel_path} has a header but no data rows")
    return ground_truth


def load_AI_table(excel_path):
    """Load AI table (Excel) with binary rule columns (R01-R27).
    
    Expected columns: COMPANY_CODE, DOCUMENT_NR, SUPPLIER_NR, COMPANY_NAME, R01, R02, ..., R27
    Creates transaction_id from COMPANY_CODE + DOCUMENT_NR.
    Extracts R01-R27 as {rule_id: bool}.
    Returns {transaction_id: {"report_text": str, "ai_flags": {rule_id: bool}, "metadata": {...}}}.
    """
    if not os.path.isfile(excel_path):
        raise ValueError(f"AI table not found: {excel_path}")

    reports = {}
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        raise ValueError(f"Failed to read AI table {excel_path}: {e}")
    
    required_cols = {"COMPANY_CODE", "DOCUMENT_NR"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"AI table {excel_path} is missing required column(s): {sorted(missing_cols)}"
        )
    
    for idx, row in df.iterrows():
        company_code = str(row.get("COMPANY_CODE", "")).strip()
        doc_nr = str(row.get("DOCUMENT_NR", "")).strip()
        
        if not company_code or not doc_nr:
            raise ValueError(f"AI table {excel_path}, row {idx + 2}: empty COMPANY_CODE or DOCUMENT_NR")
        
        # Create transaction_id from COMPANY_CODE + DOCUMENT_NR
        transaction_id = f"{company_code}_{doc_nr}"
        
        # Extract R01-R27 as {rule_id: bool}
        flags = {
            rule_id: str(row.get(rule_id, "")).strip().lower() in ("true", "1", "yes")
            for rule_id in RULE_FLAGS
        }
        
        # Concatenate report-like text from available fields
        report_text = f"Company: {company_code}, Doc: {doc_nr}, Supplier: {row.get('COMPANY_NAME', '')}"
        
        reports[transaction_id] = {
            "report_text": report_text,
            "ai_flags": flags,
            "metadata": {
                "company_code": company_code,
                "document_nr": doc_nr,
                "supplier_nr": str(row.get("SUPPLIER_NR", "")).strip(),
                "supplier_name": str(row.get("COMPANY_NAME", "")).strip(),
            }
        }

    if not reports:
        raise ValueError(f"AI table {excel_path} has a header but no data rows")
    return reports
