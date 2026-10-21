"""
Error handling and plain business language translation module for Company X Slow Stock Action Tool.

Translates technical exceptions (KeyError, ValueError, corrupted files, missing columns)
into plain business language for executive users, while capturing complete technical diagnostics
for Developer Mode.
"""
import os
import traceback
from typing import Dict, Any
from src.logger import get_logger

logger = get_logger("ErrorHandler")


def format_user_friendly_error(exc: Exception) -> Dict[str, Any]:
    """
    Translates a Python exception into an executive-friendly explanation
    with a clear recommended source-level action.

    Returns:
        dict with keys:
            - 'title': Short descriptive business title
            - 'message': Clear, professional business explanation
            - 'source_fix': Recommended action for data owners
            - 'traceback': Full Python traceback string for developer mode
            - 'error_type': Name of the original exception class
    """
    err_str = str(exc)
    err_type = exc.__class__.__name__
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc.__traceback__ else f"{err_type}: {err_str}"
    logger.error("Processing exception: %s: %s", err_type, err_str)

    # 1. Missing Column / KeyError
    # Example requirement: CustomerID is missing from Sales_Lines. Please upload the latest system export containing the required CustomerID column.
    if isinstance(exc, KeyError) or "is missing columns" in err_str or "missing column" in err_str.lower():
        if "CustomerID" in err_str or (isinstance(exc, KeyError) and "CustomerID" in [str(a) for a in exc.args]):
            table_name = "Customers" if "Customers" in err_str else "Sales_Lines"
            return {
                "title": "Missing CustomerID Column",
                "message": f"CustomerID is missing from {table_name}. Please upload the latest system export containing the required CustomerID column.",
                "source_fix": f"Verify that your {table_name} export includes the 'CustomerID' column.",
                "traceback": tb_str,
                "error_type": err_type,
            }
        if "SKU" in err_str or (isinstance(exc, KeyError) and "SKU" in [str(a) for a in exc.args]):
            table_name = "Item_Master" if "Item_Master" in err_str else ("Stock_Aging" if "Stock_Aging" in err_str else "Sales_Lines")
            return {
                "title": "Missing SKU Identifier Column",
                "message": f"SKU is missing from {table_name}. Please upload the latest system export containing the required SKU column.",
                "source_fix": f"Verify that your {table_name} export includes the 'SKU' column.",
                "traceback": tb_str,
                "error_type": err_type,
            }
        # Generic missing column
        return {
            "title": "Missing Required Column",
            "message": err_str if "Please upload" in err_str else f"A required column is missing: {err_str}. Please upload the latest system export containing all standard columns.",
            "source_fix": "Verify that all required columns are present in your monthly export files.",
            "traceback": tb_str,
            "error_type": err_type,
        }

    # 2. Missing workbook sheets
    if "missing required sheet" in err_str.lower():
        return {
            "title": "Missing Workbook Sheets",
            "message": err_str,
            "source_fix": "Ensure your Excel workbook contains all four required sheets: Item_Master, Stock_Aging, Sales_Lines, and Customers.",
            "traceback": tb_str,
            "error_type": err_type,
        }

    # 3. Wrong file type (e.g. .csv, .txt, .pdf, .zip uploaded instead of Excel)
    if "not a supported excel workbook" in err_str.lower() or "not a valid excel" in err_str.lower() or "not an excel" in err_str.lower():
        return {
            "title": "Unsupported File Type",
            "message": err_str,
            "source_fix": "Please export and upload files in standard Excel format (.xlsx or .xls).",
            "traceback": tb_str,
            "error_type": err_type,
        }

    # 4. Empty file (0 bytes) or empty worksheet
    if "empty (0 bytes)" in err_str.lower() or "contains no readable worksheets" in err_str.lower():
        return {
            "title": "Empty File Uploaded",
            "message": err_str,
            "source_fix": "Ensure the exported file contains valid operational records and is not a 0-byte blank file.",
            "traceback": tb_str,
            "error_type": err_type,
        }

    # 5. Corrupted Excel file
    if any(term in err_str.lower() for term in ["corrupted", "cannot be read", "badzipfile", "invalidfile", "failed to open"]):
        return {
            "title": "Corrupted Excel File",
            "message": "The uploaded Excel file appears corrupted or cannot be read. Please re-export the file from your ERP/accounting system and upload again.",
            "source_fix": "Re-export a fresh copy of the workbook from your ERP or spreadsheet software.",
            "traceback": tb_str,
            "error_type": err_type,
        }

    # 6. Incomplete upload (missing 1 of 4 files)
    if "incomplete upload" in err_str.lower():
        return {
            "title": "Incomplete File Upload",
            "message": err_str,
            "source_fix": "Please upload all four separate files (Item_Master, Stock_Aging, Sales_Lines, Customers) before clicking Run Review.",
            "traceback": tb_str,
            "error_type": err_type,
        }

    # 7. Standard ValueError with descriptive message
    if isinstance(exc, ValueError):
        return {
            "title": "Data Validation Issue",
            "message": err_str,
            "source_fix": "Please review the uploaded data to ensure it conforms to required operational formats.",
            "traceback": tb_str,
            "error_type": err_type,
        }

    # 8. Unhandled technical exception
    return {
        "title": "Review Processing Notice",
        "message": f"A processing exception occurred during data review: {err_str}",
        "source_fix": "Please verify input files or contact your administrator with the developer diagnostic details.",
        "traceback": tb_str,
        "error_type": err_type,
    }
