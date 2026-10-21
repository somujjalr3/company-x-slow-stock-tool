import os
from typing import Tuple, Union, Any, Dict
import pandas as pd
from src.logger import get_logger

logger = get_logger("DataLoader")

REQUIRED_SHEETS = ["Item_Master", "Stock_Aging", "Sales_Lines", "Customers"]


def _check_file_type_and_size(file_obj, expected_name="workbook"):
    """
    Validates file extension and ensures file is not empty (0 bytes).
    Raises ValueError with plain business language if invalid.
    """
    if file_obj is None:
        raise ValueError(f"No file was provided for '{expected_name}'. Please upload a valid Excel workbook.")

    # Filename check
    fname = getattr(file_obj, "name", None) or (file_obj if isinstance(file_obj, str) else "")
    if isinstance(fname, str) and fname:
        lower = fname.lower()
        if "." in lower:
            ext = lower.rsplit(".", 1)[-1]
            if ext not in ["xlsx", "xls", "xlsm", "xlsb"]:
                raise ValueError(
                    f"The uploaded file '{fname}' is not a supported Excel workbook (.xlsx, .xls). "
                    "Please upload an official Excel workbook exported from your enterprise system."
                )

    # 0 bytes check
    is_empty = False
    if hasattr(file_obj, "size") and file_obj.size == 0:
        is_empty = True
    elif isinstance(file_obj, str) and os.path.exists(file_obj) and os.path.getsize(file_obj) == 0:
        is_empty = True
    elif hasattr(file_obj, "getvalue") and len(file_obj.getvalue()) == 0:
        is_empty = True

    if is_empty:
        display_name = fname if isinstance(fname, str) and fname else expected_name
        raise ValueError(
            f"The uploaded file '{display_name}' is empty (0 bytes). "
            "Please upload a valid system export containing operational data."
        )


REQUIRED_SCHEMAS = {
    "Item_Master": [
        "SKU", "Item Name", "Category", "Master Pack Qty",
        "Unit Cost (Rs)", "Alternate Item (name)", "Alternate Flag", "Status"
    ],
    "Stock_Aging": [
        "SKU", "Qty 0-30 days", "Qty 31-60 days", "Qty 61-90 days",
        "Qty 91-180 days", "Qty 180+ days"
    ],
    "Sales_Lines": [
        "Month", "CustomerID", "CustomerName", "Industry", "SKU", "Qty", "Value (Rs)"
    ],
    "Customers": [
        "CustomerID", "CustomerName", "Industry", "Area"
    ],
}


def match_dataset_schema(columns: list, sheet_name: str = None) -> Union[str, None]:
    """
    Matches a collection of column names against the 4 Company X required schemas:
      - Item_Master
      - Stock_Aging
      - Sales_Lines
      - Customers

    Returns the identified dataset name if a clear schema signature matches, otherwise None.
    """
    if columns is None or len(columns) == 0:
        return None

    cols_set = {str(c).strip() for c in columns if c is not None and str(c).strip()}
    cols_lower = {c.lower() for c in cols_set}

    # 1. Stock_Aging Signature
    # Must have SKU and at least 2 aging bucket columns
    aging_indicators = {
        "qty 0-30 days", "qty 31-60 days", "qty 61-90 days",
        "qty 91-180 days", "qty 180+ days",
    }
    has_aging = len(cols_lower.intersection(aging_indicators)) >= 2
    if ("sku" in cols_lower) and has_aging and ("month" not in cols_lower) and ("area" not in cols_lower):
        return "Stock_Aging"

    # 2. Sales_Lines Signature
    # Must have Month, Value (Rs) / Value, and Qty
    has_month = "month" in cols_lower
    has_value = any("value" in c for c in cols_lower)
    has_sales_qty = any("qty" in c for c in cols_lower) and not has_aging
    if has_month and (has_value or has_sales_qty) and not has_aging:
        return "Sales_Lines"

    # 3. Customers Signature
    # Must have CustomerID and Area; must NOT have SKU or Month
    has_cust_id = ("customerid" in cols_lower) or ("customer id" in cols_lower)
    has_area = "area" in cols_lower
    has_sku = "sku" in cols_lower
    if has_cust_id and has_area and not has_sku and not has_month:
        return "Customers"

    # 4. Item_Master Signature
    # Must have SKU and at least 2 distinct Item Master attribute columns; no aging, month, or area
    im_indicators = {
        "item name", "category", "master pack qty", "master pack",
        "unit cost (rs)", "unit cost", "alternate item (name)",
        "alternate item", "alternate flag", "status"
    }
    matching_im_cols = cols_lower.intersection(im_indicators)
    if has_sku and len(matching_im_cols) >= 2 and not has_aging and not has_month and not has_area:
        return "Item_Master"

    # Fallback to sheet_name if sheet_name matches one of REQUIRED_SHEETS and has basic columns
    if sheet_name:
        clean_s = str(sheet_name).strip().replace(" ", "_")
        for req in REQUIRED_SHEETS:
            if clean_s.lower() == req.lower():
                return req

    return None


def identify_uploaded_files(files: list) -> dict:
    """
    Inspects multiple uploaded files by examining their columns and schemas
    and maps each file to its corresponding Company X dataset:
      - Item_Master
      - Stock_Aging
      - Sales_Lines
      - Customers

    Returns a structured dictionary:
      - 'identified': dict mapping dataset name -> matching file object (or None)
      - 'file_details': list of dicts for each file with status and metadata
      - 'duplicate_datasets': dict mapping dataset name -> list of filenames matching it
      - 'missing_datasets': list of required dataset names with 0 matching files
      - 'unidentified_files': list of filenames that could not be matched
      - 'errors': list of user-friendly error messages
      - 'all_identified': bool, True if exactly 4 files uniquely match the 4 required datasets
    """
    if not files:
        return {
            "Item_Master": None,
            "Stock_Aging": None,
            "Sales_Lines": None,
            "Customers": None,
            "identified": {s: None for s in REQUIRED_SHEETS},
            "file_details": [],
            "duplicate_datasets": {},
            "missing_datasets": list(REQUIRED_SHEETS),
            "unidentified_files": [],
            "errors": [],
            "all_identified": False,
        }

    file_details = []
    unidentified_files = []
    dataset_matches = {s: [] for s in REQUIRED_SHEETS}

    for idx, f in enumerate(files):
        fname = getattr(f, "name", None) or (os.path.basename(f) if isinstance(f, str) else f"File_{idx+1}")

        # Check empty file
        is_empty = False
        if hasattr(f, "size") and f.size == 0:
            is_empty = True
        elif isinstance(f, str) and os.path.exists(f) and os.path.getsize(f) == 0:
            is_empty = True
        elif hasattr(f, "getvalue") and len(f.getvalue()) == 0:
            is_empty = True

        if is_empty:
            file_details.append({
                "filename": fname,
                "file_obj": f,
                "dataset": None,
                "status": "⚠ Cannot identify",
                "error": "File is empty (0 bytes).",
            })
            unidentified_files.append(fname)
            continue

        # Check extension
        ext = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
        if ext not in ["xlsx", "xls", "xlsm", "xlsb"]:
            file_details.append({
                "filename": fname,
                "file_obj": f,
                "dataset": None,
                "status": "⚠ Cannot identify",
                "error": "Unsupported file format. Please upload an Excel workbook (.xlsx, .xls).",
            })
            unidentified_files.append(fname)
            continue

        # Open workbook
        try:
            if hasattr(f, "seek"):
                f.seek(0)
            xls = pd.ExcelFile(f)
        except Exception as exc:
            file_details.append({
                "filename": fname,
                "file_obj": f,
                "dataset": None,
                "status": "⚠ Cannot identify",
                "error": f"Unable to read file: {exc}",
            })
            unidentified_files.append(fname)
            continue

        try:
            if not xls.sheet_names:
                file_details.append({
                    "filename": fname,
                    "file_obj": f,
                    "dataset": None,
                    "status": "⚠ Cannot identify",
                    "error": "The workbook contains no worksheets.",
                })
                unidentified_files.append(fname)
                continue

            matched_sheets = {}
            for s_name in xls.sheet_names:
                try:
                    df = pd.read_excel(xls, sheet_name=s_name, nrows=2)
                    ds = match_dataset_schema(df.columns, sheet_name=s_name)
                    if ds:
                        matched_sheets[ds] = s_name
                except Exception:
                    pass

            if hasattr(f, "seek"):
                f.seek(0)

            if len(matched_sheets) > 1:
                sheets_joined = ", ".join(matched_sheets.keys())
                err = f"Multiple sheets with ambiguity ({sheets_joined})"
                file_details.append({
                    "filename": fname,
                    "file_obj": f,
                    "dataset": None,
                    "status": "⚠ Cannot identify",
                    "error": err,
                })
                unidentified_files.append(fname)
            elif len(matched_sheets) == 1:
                matched_ds = list(matched_sheets.keys())[0]
                item = {
                    "filename": fname,
                    "file_obj": f,
                    "dataset": matched_ds,
                    "status": "✓ Identified",
                    "error": None,
                }
                file_details.append(item)
                dataset_matches[matched_ds].append(item)
            else:
                file_details.append({
                    "filename": fname,
                    "file_obj": f,
                    "dataset": None,
                    "status": "⚠ Cannot identify",
                    "error": "Unable to identify this file from its column structure.",
                })
                unidentified_files.append(fname)
        finally:
            try:
                xls.close()
            except Exception:
                pass
            if hasattr(f, "seek"):
                f.seek(0)

    duplicate_datasets = {}
    for ds, m_list in dataset_matches.items():
        if len(m_list) > 1:
            duplicate_datasets[ds] = [m["filename"] for m in m_list]

    missing_datasets = [ds for ds, m_list in dataset_matches.items() if len(m_list) == 0]

    identified = {}
    for ds in REQUIRED_SHEETS:
        if len(dataset_matches[ds]) == 1:
            identified[ds] = dataset_matches[ds][0]["file_obj"]
        else:
            identified[ds] = None

    errors = []
    if len(files) < 4:
        errors.append("Please select all 4 required files.")
    elif len(files) > 4:
        errors.append(f"Please select exactly 4 Excel files. You have selected {len(files)} files.")

    for ds, f_names in duplicate_datasets.items():
        joined_names = ", ".join(f_names)
        errors.append(f"Multiple files appear to match {ds} ({joined_names}). Please select the correct files.")

    if len(files) == 4 and missing_datasets:
        joined_missing = ", ".join(missing_datasets)
        errors.append(f"Missing: {joined_missing}")

    for f_name in unidentified_files:
        errors.append(f'Unable to identify "{f_name}" from its column structure.')

    all_identified = (
        (len(files) == 4)
        and (len(missing_datasets) == 0)
        and (len(duplicate_datasets) == 0)
        and (len(unidentified_files) == 0)
    )

    return {
        "Item_Master": identified.get("Item_Master"),
        "Stock_Aging": identified.get("Stock_Aging"),
        "Sales_Lines": identified.get("Sales_Lines"),
        "Customers": identified.get("Customers"),
        "identified": identified,
        "file_details": file_details,
        "duplicate_datasets": duplicate_datasets,
        "missing_datasets": missing_datasets,
        "unidentified_files": unidentified_files,
        "errors": errors,
        "all_identified": all_identified,
    }


def load_workbook(uploaded_file):
    """
    Mode 1: Load data from a combined Excel workbook.
    Accepts a single workbook file (file path, file-like object, or BytesIO)
    containing all 4 required sheets:
      - Item_Master
      - Stock_Aging
      - Sales_Lines
      - Customers

    Returns:
      tuple of (item_master, stock_aging, sales_lines, customers)
    """
    if isinstance(uploaded_file, dict):
        return load_separate_files(**uploaded_file)
    if isinstance(uploaded_file, (list, tuple)) and len(uploaded_file) == 4:
        return load_separate_files(*uploaded_file)

    _check_file_type_and_size(uploaded_file, expected_name="Combined Workbook")

    fname = getattr(uploaded_file, "name", None) or (uploaded_file if isinstance(uploaded_file, str) else "workbook")

    try:
        xls = pd.ExcelFile(uploaded_file)
    except Exception as exc:
        raise ValueError(
            f"The uploaded Excel file '{fname}' appears corrupted or cannot be read. "
            f"Please ensure it is a valid, uncorrupted Excel spreadsheet (.xlsx or .xls). Detail: {exc}"
        )

    missing = [s for s in REQUIRED_SHEETS if s not in xls.sheet_names]
    if missing:
        raise ValueError(
            f"The uploaded combined workbook is missing required sheet(s): {', '.join(missing)}. "
            f"Found sheets: {', '.join(xls.sheet_names)}. "
            "Please ensure all four sheets (Item_Master, Stock_Aging, Sales_Lines, Customers) are present."
        )

    try:
        tables = tuple(pd.read_excel(xls, sheet_name=s) for s in REQUIRED_SHEETS)
        logger.info(
            "Successfully loaded combined workbook with 4 sheets (Item_Master: %d rows, Stock_Aging: %d rows, Sales_Lines: %d rows, Customers: %d rows)",
            len(tables[0]), len(tables[1]), len(tables[2]), len(tables[3])
        )
        return tables
    except Exception as exc:
        logger.error("Failed to read sheets from workbook: %s", exc)
        raise ValueError(f"Failed to read sheets from the workbook: {exc}")


def load_separate_files(
    item_master_file=None,
    stock_aging_file=None,
    sales_lines_file=None,
    customers_file=None,
    **kwargs
):
    """
    Mode 2: Load data from four separate Excel files.
    Accepts 4 positional or keyword file arguments:
      - item_master_file: Item_Master.xlsx
      - stock_aging_file: Stock_Aging.xlsx
      - sales_lines_file: Sales_Lines.xlsx
      - customers_file: Customers.xlsx

    Validates that all four files are provided and valid before reading.
    Returns:
      tuple of (item_master, stock_aging, sales_lines, customers)
    """
    file_map = {
        "Item_Master": item_master_file or kwargs.get("Item_Master") or kwargs.get("item_master"),
        "Stock_Aging": stock_aging_file or kwargs.get("Stock_Aging") or kwargs.get("stock_aging"),
        "Sales_Lines": sales_lines_file or kwargs.get("Sales_Lines") or kwargs.get("sales_lines"),
        "Customers": customers_file or kwargs.get("Customers") or kwargs.get("customers"),
    }

    # Validate that none of the 4 files are missing
    missing_files = [sheet for sheet, f in file_map.items() if f is None]
    if missing_files:
        raise ValueError(
            f"Incomplete upload: Missing file(s) for {', '.join(missing_files)}. "
            "Please provide all four separate files (Item_Master, Stock_Aging, Sales_Lines, Customers)."
        )

    results = []
    for sheet_name in REQUIRED_SHEETS:
        f = file_map[sheet_name]
        if isinstance(f, pd.DataFrame):
            results.append(f.copy())
            continue

        _check_file_type_and_size(f, expected_name=sheet_name)

        fname = getattr(f, "name", None) or (f if isinstance(f, str) else sheet_name)

        try:
            xls = pd.ExcelFile(f)
        except Exception as exc:
            raise ValueError(
                f"The file uploaded for '{sheet_name}' ('{fname}') appears corrupted or cannot be opened. "
                f"Please ensure it is a valid, uncorrupted Excel spreadsheet (.xlsx or .xls). Detail: {exc}"
            )

        if not xls.sheet_names:
            raise ValueError(
                f"The file uploaded for '{sheet_name}' contains no readable worksheets."
            )

        # Use the sheet named after the required table if present; otherwise default to the first sheet
        target_sheet = sheet_name if sheet_name in xls.sheet_names else xls.sheet_names[0]

        try:
            df = pd.read_excel(xls, sheet_name=target_sheet)
        except Exception as exc:
            raise ValueError(
                f"Error reading data from sheet '{target_sheet}' in '{sheet_name}' file: {exc}"
            )

        results.append(df)

    logger.info(
        "Successfully loaded 4 separate files (Item_Master: %d rows, Stock_Aging: %d rows, Sales_Lines: %d rows, Customers: %d rows)",
        len(results[0]), len(results[1]), len(results[2]), len(results[3])
    )
    return tuple(results)


def load_data(source, *args, **kwargs):
    """
    Unified entry point for loading data from either Mode 1 or Mode 2.
    - If 4 positional arguments are provided, loads 4 separate files.
    - If kwargs contain separate files, loads 4 separate files.
    - If source is a dict of 4 files, loads 4 separate files.
    - If source is a list/tuple of files, identifies and loads them.
    - Otherwise loads source as a combined workbook.
    """
    if len(args) == 3:
        return load_separate_files(source, *args)
    if any(k in kwargs for k in REQUIRED_SHEETS) or any(
        k in kwargs for k in ["item_master_file", "item_master"]
    ):
        return load_separate_files(source, **kwargs)
    if isinstance(source, dict):
        return load_separate_files(**source)
    if isinstance(source, (list, tuple)):
        id_res = identify_uploaded_files(source)
        if id_res.get("all_identified"):
            return load_separate_files(**id_res["identified"])
        if len(source) == 4:
            return load_separate_files(*source)
    return load_workbook(source)
