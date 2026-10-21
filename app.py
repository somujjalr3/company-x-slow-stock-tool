import io
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.logger import get_logger

logger = get_logger("App")

from src.ai_outreach import (
    generate_sales_outreach_message,
    generate_sales_communication_suite,
)
from src.business_logic import (
    run_analysis,
    build_audit_trail,
    calculate_working_capital_impact,
    generate_sku_classification_explanation,
)
from src.sales_trends import (
    calculate_monthly_sales_trends,
    get_top_declining_push_items,
    get_top_growing_push_items,
)
from src.sales_priority import (
    calculate_sales_priority,
    get_ranked_push_table,
)
from src.customer_targets import build_customer_targets
from src.sales_action_center import (
    build_sales_action_table,
    filter_sales_action_table,
    sort_sales_action_table,
    generate_customer_sku_action,
    export_sales_action_excel,
    init_sales_tracker,
    update_sales_tracker_lead,
    calculate_sales_tracker_kpis,
    export_sales_tracker_excel,
    TRACKER_STATUS_OPTIONS,
)
from src.scenario_simulator import (
    simulate_sku_sales_uplift,
    simulate_portfolio_uplift,
)
from src.dead_stock import (
    identify_dead_stock,
    get_dead_stock_summary,
    get_top_dead_stock_by_value,
    export_dead_stock_excel,
)
from src.data_lineage import (
    build_data_lineage,
    export_data_lineage_excel,
)
from src.data_loader import load_data, identify_uploaded_files, REQUIRED_SHEETS
from src.config import (
    CaseConfig,
    get_default_config,
    is_case_default,
    get_current_case_rules,
)
from src.error_handler import format_user_friendly_error
from src.export import create_excel_report
from src.validation import validate_data, EXPECTED_COLUMNS
from src.ai_management_assistant import (
    build_management_structured_context,
    interpret_management_query,
    AI_DISCLAIMER,
)

st.set_page_config(
    page_title="Company X | Slow Stock Action Tool",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _clean_html_block(html_text: str) -> str:
    """
    Strips leading and trailing whitespace from every line and removes blank lines.
    This guarantees that CommonMark Markdown parsers never encounter lines with >=4 leading
    spaces (which trigger indented code blocks) and never split HTML blocks on empty lines.
    """
    return "\n".join(line.strip() for line in html_text.splitlines() if line.strip())


# Professional Executive / MBA Case Study Theme
st.markdown("""
<style>
/* Base Theme */
body, .stApp {
    background-color: #ffffff;
    color: #0f172a;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

.block-container {
    padding-top: 1.25rem;
    padding-bottom: 2.5rem;
    max-width: 1280px;
}

/* Header */
.app-header {
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 0.85rem;
    margin-bottom: 1.25rem;
}
.app-title-main {
    font-size: 1.65rem;
    font-weight: 700;
    color: #0f294a;
    letter-spacing: -0.02em;
    margin: 0;
    line-height: 1.2;
}
.app-subtitle {
    font-size: 0.92rem;
    color: #475569;
    margin-top: 0.25rem;
    margin-bottom: 0;
}

/* Status Pill */
.status-banner {
    background-color: #f0f9ff;
    border: 1px solid #bae6fd;
    color: #0369a1;
    padding: 0.55rem 0.9rem;
    border-radius: 6px;
    font-size: 0.88rem;
    font-weight: 500;
    margin-bottom: 1.25rem;
}

/* Executive KPI Cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
}
.kpi-card {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1rem 1.15rem;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03);
}
.kpi-card.push {
    border-top: 3px solid #2563eb;
    background-color: #f0f7ff;
}
.kpi-card.noaction {
    border-top: 3px solid #059669;
}
.kpi-card.redlist {
    border-top: 3px solid #dc2626;
}
.kpi-card.value {
    border-top: 3px solid #1e3a8a;
    background-color: #f8fafc;
}
.kpi-card.exec-total {
    border-top: 3px solid #0f294a;
}
.kpi-card.exec-aged {
    border-top: 3px solid #b91c1c;
    background-color: #fef2f2;
}
.kpi-card.exec-risk {
    border-top: 3px solid #ea580c;
    background-color: #fff7ed;
}

/* Executive Brief Container & Section Headers */
.exec-brief-container {
    background-color: #f8fafc;
    border: 1px solid #cbd5e1;
    border-left: 5px solid #0f294a;
    border-radius: 8px;
    padding: 1.05rem 1.25rem;
    margin-bottom: 1.25rem;
}
.exec-section-header {
    margin-top: 1.85rem;
    margin-bottom: 0.65rem;
    padding-bottom: 0.45rem;
    border-bottom: 2px solid #e2e8f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.4rem;
}
.exec-section-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f294a;
    letter-spacing: -0.01em;
}
.exec-section-badge {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #475569;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    padding: 0.2rem 0.55rem;
    border-radius: 4px;
}
.kpi-label {
    font-size: 0.78rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
}
.kpi-number {
    font-size: 1.7rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.2;
}
.kpi-desc {
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 0.25rem;
}

/* Section Card */
.content-box {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1.15rem;
    margin-bottom: 1.25rem;
}
.content-box-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #0f294a;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

/* Summary metrics container */
.metric-row {
    display: flex;
    flex-wrap: wrap;
    gap: 1.5rem;
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 0.85rem 1.15rem;
    margin-bottom: 1rem;
}
.metric-col {
    flex: 1;
    min-width: 140px;
}
.metric-col-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
}
.metric-col-val {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0f294a;
    margin-top: 0.15rem;
}

/* Responsive View Handling for Sales Action List */
.sales-desktop-container {
    display: block;
}
.sales-mobile-container {
    display: none;
}

@media (max-width: 768px) {
    .sales-desktop-container {
        display: none !important;
    }
    .sales-mobile-container {
        display: block !important;
    }
}

/* Mobile Action Cards */
.mobile-action-card {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 0.95rem 1.1rem;
    margin-bottom: 0.85rem;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04);
}
.mobile-action-card.bucket-1 {
    border-left: 4px solid #1e40af;
}
.mobile-action-card.bucket-2 {
    border-left: 4px solid #0284c7;
}
.mobile-action-card.bucket-3 {
    border-left: 4px solid #64748b;
}
.mobile-card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.25rem;
}
.mobile-priority-badge {
    background-color: #0f294a;
    color: #ffffff;
    font-size: 0.78rem;
    font-weight: 700;
    padding: 0.22rem 0.55rem;
    border-radius: 4px;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}
.mobile-customer-name {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f294a;
    margin: 0.25rem 0 0.1rem 0;
}
.mobile-customer-id {
    font-size: 0.82rem;
    color: #64748b;
    font-weight: 500;
}
.mobile-bucket-title {
    font-size: 0.82rem;
    font-weight: 600;
    padding: 0.22rem 0.55rem;
    border-radius: 4px;
    display: inline-block;
    margin: 0.35rem 0 0.45rem 0;
}
.mobile-bucket-1-pill {
    background-color: #eff6ff;
    color: #1e40af;
    border: 1px solid #bfdbfe;
}
.mobile-bucket-2-pill {
    background-color: #f0fdf4;
    color: #166534;
    border: 1px solid #bbf7d0;
}
.mobile-bucket-3-pill {
    background-color: #f8fafc;
    color: #475569;
    border: 1px solid #e2e8f0;
}
.mobile-card-details {
    font-size: 0.88rem;
    color: #334155;
    line-height: 1.6;
    border-top: 1px solid #f1f5f9;
    padding-top: 0.45rem;
}
.mobile-card-details strong {
    color: #0f172a;
    font-weight: 600;
}
.mobile-spend-value {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1e3a8a;
}

/* Styled Action Table for Desktop View */
.styled-action-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 0.5rem;
    margin-bottom: 1.25rem;
    font-size: 0.88rem;
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    overflow: hidden;
}
.styled-action-table th {
    background-color: #0f294a;
    color: #ffffff;
    font-weight: 600;
    padding: 0.65rem 0.85rem;
    text-align: left;
    border-bottom: 2px solid #0a1e36;
    letter-spacing: 0.02em;
}
.styled-action-table td {
    padding: 0.65rem 0.85rem;
    border-bottom: 1px solid #e2e8f0;
    color: #1e293b;
    vertical-align: middle;
}
.styled-action-table tr:nth-child(even) {
    background-color: #f8fafc;
}
.styled-action-table tr:hover {
    background-color: #f1f5f9;
}
.priority-pill {
    background-color: #0f294a;
    color: #ffffff;
    font-weight: 700;
    font-size: 0.76rem;
    padding: 0.2rem 0.55rem;
    border-radius: 4px;
    display: inline-block;
}
.bucket-badge {
    font-size: 0.78rem;
    font-weight: 600;
    padding: 0.2rem 0.55rem;
    border-radius: 4px;
    display: inline-block;
}
.bucket-badge-1 {
    background-color: #eff6ff;
    color: #1e40af;
    border: 1px solid #bfdbfe;
}
.bucket-badge-2 {
    background-color: #f0fdf4;
    color: #166534;
    border: 1px solid #bbf7d0;
}
.bucket-badge-3 {
    background-color: #f8fafc;
    color: #475569;
    border: 1px solid #cbd5e1;
}

/* Data Quality Notice Banner */
.dq-notice-banner {
    background-color: #f0f9ff;
    border-left: 4px solid #0284c7;
    border-top: 1px solid #bae6fd;
    border-right: 1px solid #bae6fd;
    border-bottom: 1px solid #bae6fd;
    color: #0c4a6e;
    padding: 0.85rem 1.15rem;
    border-radius: 6px;
    font-size: 0.92rem;
    line-height: 1.5;
    margin-bottom: 1.25rem;
}
.dq-section-header {
    font-size: 1.02rem;
    font-weight: 700;
    color: #0f294a;
    margin-top: 1.25rem;
    margin-bottom: 0.4rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.dq-badge-clean {
    background-color: #ecfdf5;
    color: #065f46;
    border: 1px solid #a7f3d0;
    padding: 0.65rem 0.95rem;
    border-radius: 6px;
    font-size: 0.88rem;
    font-weight: 500;
    margin-bottom: 0.75rem;
}

/* Clean sidebar */
section[data-testid="stSidebar"] {
    background-color: #f8fafc;
    border-right: 1px solid #e2e8f0;
}
</style>
""", unsafe_allow_html=True)

# Application Header
st.markdown("""
<div class="app-header">
    <div class="app-title-main">Company X &mdash; Slow Stock Action Tool</div>
    <div class="app-subtitle">Operations & Inventory Review System | Rules R1&ndash;R7 Compliant</div>
</div>
""", unsafe_allow_html=True)

# Sidebar: Input Configuration
with st.sidebar:
    st.markdown("### Monthly Data Review")
    st.caption("Upload monthly system exports to trigger classification and sales targeting.")

    upload_mode = st.radio(
        "Choose Input Mode",
        ["Combined Workbook", "Four Separate Files"],
        help="Select whether to ingest a single combined Excel export or four separate table files."
    )

    if upload_mode == "Combined Workbook":
        uploaded_combined = st.file_uploader(
            "Combined Excel Workbook (.xlsx, .xls)",
            type=["xlsx", "xls"],
            help="Must contain Item_Master, Stock_Aging, Sales_Lines, and Customers sheets."
        )
        source_input = uploaded_combined
        uploaded_files = None
        can_run = (uploaded_combined is not None)
    else:
        st.markdown("**Upload 4 Excel Files:**")
        uploaded_files = st.file_uploader(
            "Upload 4 Excel Files",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            help="Select the four required Excel files at once: Item_Master, Stock_Aging, Sales_Lines and Customers.",
            key="up_four_excel_files",
        )
        uploaded_combined = None
        id_result = identify_uploaded_files(uploaded_files or [])
        source_input = id_result["identified"]
        can_run = id_result["all_identified"]

        if uploaded_files:
            preview_data = []
            for ds in REQUIRED_SHEETS:
                matched_f = id_result["identified"].get(ds)
                if matched_f is not None:
                    fname = getattr(matched_f, "name", str(matched_f))
                    st_txt = "✓ Identified"
                else:
                    fname = "—"
                    st_txt = "❌ Missing"
                preview_data.append({
                    "Dataset": ds,
                    "File": fname,
                    "Status": st_txt,
                })

            for unk in id_result.get("unidentified_files", []):
                preview_data.append({
                    "Dataset": "Unassigned",
                    "File": unk,
                    "Status": "⚠ Cannot identify",
                })

            st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)

            if id_result["all_identified"]:
                st.markdown("""
                <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; padding: 0.6rem 0.8rem; border-radius: 6px; font-size: 0.82rem; margin-top: 0.5rem; margin-bottom: 0.5rem;">
                    ✓ <strong>Item_Master identified</strong><br>
                    ✓ <strong>Stock_Aging identified</strong><br>
                    ✓ <strong>Sales_Lines identified</strong><br>
                    ✓ <strong>Customers identified</strong>
                </div>
                """, unsafe_allow_html=True)
            else:
                for err_msg in id_result["errors"]:
                    st.error(f"⚠️ {err_msg}")

    run_button = st.button("Run Review", type="primary", disabled=not can_run, use_container_width=True)

    if st.session_state.get("results") is not None:
        st.markdown("""
<div style="background-color: #f0f9ff; border: 1px solid #bae6fd; color: #0369a1; padding: 0.6rem; border-radius: 6px; font-size: 0.82rem; margin-top: 0.75rem;">
✓ <strong>File received</strong><br>
✓ <strong>Required columns detected</strong><br>
✓ <strong>Data validation complete</strong>
</div>
""", unsafe_allow_html=True)

    st.divider()
    st.markdown("**Business Logic Rules:**")
    st.markdown("""
<div style="font-size: 0.8rem; color: #64748b; line-height: 1.4;">
<strong>R1:</strong> Combined or 4-file input<br>
<strong>R2:</strong> Validation audit trail<br>
<strong>R3:</strong> Alternate SWITCH rollup<br>
<strong>R4:</strong> Inactive stock isolation<br>
<strong>R5:</strong> Red List &gt; No Action &gt; Push<br>
<strong>R6:</strong> 3-tier customer targeting<br>
<strong>R7:</strong> Priority ranking (Bucket, Spend)
</div>
""", unsafe_allow_html=True)

    dev_mode = False

if "results" not in st.session_state:
    st.session_state.results = None

if "config" not in st.session_state:
    st.session_state.config = get_default_config()


def inspect_uploaded_file_columns(source_input, upload_mode):
    """
    Safely inspects the headers of an uploaded workbook or separate files
    without loading all data rows into memory or mutating anything.
    Returns: dict of sheet_name -> dict(expected=[], detected=[], missing=[], extra=[], status="...")
    """
    inspection = {}
    if upload_mode == "Combined Workbook":
        if source_input is not None:
            try:
                if hasattr(source_input, "seek"):
                    source_input.seek(0)
                xls = pd.ExcelFile(source_input)
                sheet_names = xls.sheet_names
                for sheet, expected in EXPECTED_COLUMNS.items():
                    if sheet not in sheet_names:
                        inspection[sheet] = {
                            "expected": expected,
                            "detected": [],
                            "missing": expected,
                            "extra": [],
                            "status": "MISSING_SHEET",
                        }
                    else:
                        df = pd.read_excel(xls, sheet_name=sheet, nrows=1)
                        detected = [str(c).strip() for c in df.columns]
                        missing = [c for c in expected if c not in detected]
                        extra = [c for c in detected if c not in expected]
                        inspection[sheet] = {
                            "expected": expected,
                            "detected": detected,
                            "missing": missing,
                            "extra": extra,
                            "status": "CONFORMING" if not missing else "MISSING_COLUMNS",
                        }
                if hasattr(source_input, "seek"):
                    source_input.seek(0)
            except Exception as e:
                inspection["_error"] = str(e)
    else:  # Four Separate Files
        if isinstance(source_input, dict):
            for sheet, expected in EXPECTED_COLUMNS.items():
                f = source_input.get(sheet)
                if f is None:
                    inspection[sheet] = {
                        "expected": expected,
                        "detected": [],
                        "missing": expected,
                        "extra": [],
                        "status": "NOT_UPLOADED",
                    }
                else:
                    try:
                        if hasattr(f, "seek"):
                            f.seek(0)
                        df = pd.read_excel(f, nrows=1)
                        detected = [str(c).strip() for c in df.columns]
                        missing = [c for c in expected if c not in detected]
                        extra = [c for c in detected if c not in expected]
                        inspection[sheet] = {
                            "expected": expected,
                            "detected": detected,
                            "missing": missing,
                            "extra": extra,
                            "status": "CONFORMING" if not missing else "MISSING_COLUMNS",
                        }
                        if hasattr(f, "seek"):
                            f.seek(0)
                    except Exception as e:
                        inspection[sheet] = {
                            "expected": expected,
                            "detected": [],
                            "missing": expected,
                            "extra": [],
                            "status": f"ERROR: {e}",
                        }
    return inspection


def render_schema_inspector_ui(inspection=None, file_uploaded=False):
    st.markdown(_clean_html_block("""
    <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 5px solid #0284c7; border-radius: 6px; padding: 1rem 1.25rem; margin-bottom: 1.25rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.35rem;">
            <div style="font-size: 1.05rem; font-weight: 700; color: #0f294a;">
                📋 Company X Case Input Schema (Source of Truth &mdash; Rules R1&ndash;R2)
            </div>
            <span style="font-size: 0.74rem; font-weight: 700; color: #0369a1; background: #e0f2fe; border: 1px solid #bae6fd; padding: 0.2rem 0.55rem; border-radius: 4px;">
                Strict Ingestion Validation
            </span>
        </div>
        <div style="font-size: 0.85rem; color: #334155; line-height: 1.55;">
            The application strictly enforces the standard Company X Case Schema across all four worksheets. 
            Column names must match the exact case schema. Incompatible or arbitrary third-party column names will <strong>not</strong> be silently renamed or loosely accepted.
        </div>
    </div>
    """), unsafe_allow_html=True)

    if file_uploaded and inspection and "_error" not in inspection:
        has_missing = any(data.get("missing") for sheet, data in inspection.items() if isinstance(data, dict))
        if has_missing:
            st.markdown(_clean_html_block("""
            <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-left: 5px solid #dc2626; border-radius: 6px; padding: 0.95rem 1.2rem; margin-bottom: 1.25rem;">
                <div style="font-size: 0.95rem; font-weight: 700; color: #991b1b; margin-bottom: 0.3rem;">
                    ⚠️ Incompatible Column Names Detected in Uploaded File
                </div>
                <div style="font-size: 0.85rem; color: #7f1d1d; line-height: 1.5;">
                    The uploaded workbook contains columns that do not match the expected Company X Case Schema. 
                    Review the detected vs. required columns below and rename the incompatible headers in your test workbook before clicking <strong>Run Review</strong>.
                </div>
            </div>
            """), unsafe_allow_html=True)
        else:
            st.success("✅ Case Schema Conformance Verified: All 4 worksheets contain 100% of the required standard columns.")
    elif file_uploaded and inspection and "_error" in inspection:
        st.error(f"⚠️ Unable to inspect uploaded workbook: {inspection['_error']}")

    sheet_list = ["Item_Master", "Stock_Aging", "Sales_Lines", "Customers"]
    col_left, col_right = st.columns(2)

    for idx, sheet in enumerate(sheet_list):
        target_col = col_left if idx % 2 == 0 else col_right
        expected_cols = EXPECTED_COLUMNS.get(sheet, [])
        sheet_data = inspection.get(sheet, {}) if (inspection and isinstance(inspection, dict)) else {}
        detected_cols = sheet_data.get("detected", [])
        missing_cols = sheet_data.get("missing", [])
        extra_cols = sheet_data.get("extra", [])
        status = sheet_data.get("status", "REFERENCE_ONLY")

        with target_col:
            if status == "CONFORMING":
                badge = '<span style="background-color: #dcfce7; color: #15803d; border: 1px solid #86efac; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.74rem;">✅ CONFORMING</span>'
            elif status == "MISSING_COLUMNS":
                badge = f'<span style="background-color: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.74rem;">❌ {len(missing_cols)} MISSING</span>'
            elif status == "MISSING_SHEET":
                badge = '<span style="background-color: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.74rem;">❌ SHEET MISSING</span>'
            else:
                badge = f'<span style="background-color: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.74rem;">REQUIRED ({len(expected_cols)} COLS)</span>'

            st.markdown(_clean_html_block(f"""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem 1rem; margin-bottom: 0.5rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-weight: 700; color: #0f294a; font-size: 0.95rem;">📄 Sheet: <code>{sheet}</code></div>
                    <div>{badge}</div>
                </div>
            </div>
            """), unsafe_allow_html=True)

            if file_uploaded and sheet_data:
                comp_rows = []
                for exp in expected_cols:
                    is_found = exp in detected_cols
                    comp_rows.append({
                        "Required Column": exp,
                        "Status": "✅ Found" if is_found else "❌ Missing",
                    })
                st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

                if missing_cols:
                    st.error(f"**Missing Required:** {', '.join(f'`{c}`' for c in missing_cols)}")
                if extra_cols:
                    st.warning(f"**Detected Non-Standard / Extra:** {', '.join(f'`{c}`' for c in extra_cols)}")
            else:
                st.dataframe(
                    pd.DataFrame([{"#": i + 1, "Required Column Name": col} for i, col in enumerate(expected_cols)]),
                    use_container_width=True,
                    hide_index=True
                )
            st.markdown("<div style='margin-bottom: 1.25rem;'></div>", unsafe_allow_html=True)


def apply_config_and_rerun(new_cfg: CaseConfig):
    """
    Applies custom or reset configuration settings and re-runs the operational analysis
    strictly using the immutable in-memory raw source dataset.
    Never corrupts or mutates the underlying workbook.
    """
    st.session_state.config = new_cfg
    if st.session_state.get("results") is not None:
        r = st.session_state.results
        raw = r["raw"]
        val = r["validation"]
        analysis = run_analysis(*raw, validation=val, config=new_cfg)
        targets = build_customer_targets(
            analysis["clean_item_master"],
            analysis["clean_sales"],
            analysis["analysis_items"],
            val,
            customers=raw[3],
            config=new_cfg,
        )
        audit_trail = build_audit_trail(raw, val, analysis, targets, config=new_cfg)
        sales_action_table = build_sales_action_table(
            analysis["analysis_items"], targets, sales_trends=analysis.get("sales_trends")
        )
        lineage_data = build_data_lineage(raw, val, analysis, targets)

        st.session_state.results["analysis"] = analysis
        st.session_state.results["targets"] = targets
        st.session_state.results["audit_trail"] = audit_trail
        st.session_state.results["sales_action_table"] = sales_action_table
        st.session_state.results["lineage_data"] = lineage_data
        st.session_state.results["config"] = new_cfg
        st.session_state.results["excel_report_bytes"] = None
        st.session_state.pop("sa_excel_data", None)
        st.session_state.pop("sa_excel_key", None)
        logger.info("apply_config_and_rerun: re-analyzed catalog under new configuration")
        st.rerun()


# Review Trigger & Execution
if run_button:
    # Ambiguous / Incomplete upload guards
    if upload_mode == "Combined Workbook":
        if uploaded_combined is None:
            st.error("⚠️ Incomplete upload: Please upload the combined Excel workbook before clicking Run Review.")
            st.stop()
    else:
        if not can_run:
            missing_files = [k for k, v in source_input.items() if v is None] if isinstance(source_input, dict) else []
            if missing_files:
                st.error(
                    f"⚠️ Incomplete upload: Please provide all four separate files. "
                    f"Missing: {', '.join(missing_files)}."
                )
            else:
                st.error("⚠️ Please resolve file identification errors before clicking Run Review.")
            st.stop()

    try:
        with st.spinner("Executing data ingestion, validation, and slow stock review..."):
            # 1. Ingestion
            raw = load_data(source_input)

            # 2. Validation
            validation = validate_data(*raw)
            if validation.get("has_errors"):
                err_issues = [i for i in validation.get("issues", []) if i.get("Severity") == "ERROR"]
                err_msgs = [f"• {i.get('Sheet', '')} ({i.get('Column', 'Schema')}): {i.get('Description', '')}" for i in err_issues]
                err_summary = "\n".join(err_msgs) if err_msgs else "Critical validation errors detected."
                raise ValueError(f"Analysis prevented due to critical data integrity errors:\n{err_summary}")

            # Active CaseConfig (defaults or pre-configured)
            config = st.session_state.get("config", get_default_config())

            # 3. Core Slow Stock Analysis
            analysis = run_analysis(*raw, validation=validation, config=config)

            # 4. Customer Targeting
            targets = build_customer_targets(
                analysis["clean_item_master"],
                analysis["clean_sales"],
                analysis["analysis_items"],
                validation,
                customers=raw[3],
                config=config,
            )

            # 5. Transformation Audit Trail (Management & Evaluator Traceability)
            audit_trail = build_audit_trail(raw, validation, analysis, targets, config=config)

            # 6. Precompute Consolidated Cross-Portfolio Sales Action Table
            sales_action_table = build_sales_action_table(
                analysis["analysis_items"], targets, sales_trends=analysis.get("sales_trends")
            )

            # 7. Precompute End-to-End Data Lineage
            lineage_data = build_data_lineage(raw, validation, analysis, targets)

        st.session_state.results = {
            "raw": raw,
            "validation": validation,
            "analysis": analysis,
            "targets": targets,
            "audit_trail": audit_trail,
            "sales_action_table": sales_action_table,
            "lineage_data": lineage_data,
            "upload_mode": upload_mode,
            "config": config,
            "excel_report_bytes": None,
        }
        st.session_state.config = config
        st.session_state.pop("sa_excel_data", None)
        st.session_state.pop("sa_excel_key", None)
        logger.info("Review analysis pipeline completed successfully.")
        st.rerun()

    except Exception as exc:
        err = format_user_friendly_error(exc)
        st.markdown(_clean_html_block(f"""
        <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; border-top: 1px solid #fee2e2; border-right: 1px solid #fee2e2; border-bottom: 1px solid #fee2e2; border-radius: 6px; padding: 1rem 1.15rem; margin-bottom: 1.25rem;">
            <div style="font-weight: 700; color: #991b1b; font-size: 1rem; margin-bottom: 0.35rem;">
                ⚠️ {err['title']}
            </div>
            <div style="color: #7f1d1d; font-size: 0.92rem; line-height: 1.5; margin-bottom: 0.55rem;">
                {err['message']}
            </div>
            <div style="color: #450a0a; font-size: 0.84rem; background: #fee2e2; padding: 0.45rem 0.75rem; border-radius: 4px;">
                <strong>Recommended Action:</strong> {err['source_fix']}
            </div>
        </div>
        """), unsafe_allow_html=True)

        file_uploaded = (uploaded_combined is not None) if upload_mode == "Combined Workbook" else bool(uploaded_files)
        inspection = inspect_uploaded_file_columns(source_input, upload_mode) if file_uploaded else None
        render_schema_inspector_ui(inspection=inspection, file_uploaded=file_uploaded)

        if dev_mode:
            with st.expander("🛠️ Developer Diagnostic Details (Active in Developer Mode)", expanded=True):
                st.markdown(f"**Exception Class:** `{exc.__class__.__name__}`")
                st.markdown(f"**Raw Error Message:** `{str(exc)}`")
                st.code(err.get("traceback", ""), language="python")
        else:
            st.caption("ℹ️ Running in user mode. Raw technical tracebacks are suppressed.")
        st.stop()

# Gatekeeper: Prompt user to upload if not yet run
if st.session_state.results is None:
    file_uploaded = (uploaded_combined is not None) if upload_mode == "Combined Workbook" else bool(uploaded_files)
    inspection = inspect_uploaded_file_columns(source_input, upload_mode) if file_uploaded else None

    if file_uploaded and inspection:
        has_missing = any(data.get("missing") for s, data in inspection.items() if isinstance(data, dict))
        if has_missing:
            st.error("⚠️ The uploaded dataset cannot be processed because it uses different column names from the actual Company X case schema. Please review the detected vs. required schema below and adjust the test workbook headers.")
        else:
            st.info("Uploaded workbook conforms to Company X Case Schema. Click **Run Review** in the sidebar to generate the executive analysis.")
    else:
        st.info("Select an input mode in the sidebar, upload the monthly export, and click **Run Review** to generate the executive analysis.")

    render_schema_inspector_ui(inspection=inspection, file_uploaded=file_uploaded)
    st.stop()

# Retrieve analysis state
r = st.session_state.results
analysis = r["analysis"]
validation = r["validation"]
targets = r["targets"]
items = analysis["analysis_items"]

# Upload & Configuration Status Checklist Banner
active_cfg = st.session_state.get("config", r.get("config", get_default_config()))
if active_cfg.is_default():
    cfg_badge = '<span style="background-color: #dcfce7; color: #15803d; border: 1px solid #86efac; padding: 3px 9px; border-radius: 4px; font-weight: 700; font-size: 0.78rem; letter-spacing: 0.04em;">CASE DEFAULT SETTINGS</span>'
else:
    cfg_badge = '<span style="background-color: #fef3c7; color: #b45309; border: 1px solid #fcd34d; padding: 3px 9px; border-radius: 4px; font-weight: 700; font-size: 0.78rem; letter-spacing: 0.04em;">CUSTOM SETTINGS</span>'

st.markdown(_clean_html_block(f"""
<div class="status-banner" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
    <div>
        ✓ <strong>File received</strong> &nbsp;&nbsp;|&nbsp;&nbsp; 
        ✓ <strong>Required columns detected</strong> &nbsp;&nbsp;|&nbsp;&nbsp; 
        ✓ <strong>Data validation complete</strong> &nbsp;&nbsp;|&nbsp;&nbsp;
        Mode: <strong>{r.get('upload_mode', 'Combined Workbook')}</strong>
    </div>
    <div style="display: flex; align-items: center; gap: 0.4rem;">
        <span style="font-size: 0.8rem; color: #475569; font-weight: 600;">Configuration:</span>
        {cfg_badge}
    </div>
</div>
"""), unsafe_allow_html=True)


def render_explainability_panel(item_row, sales_trends=None, sku_code=None):
    """
    Renders an interactive Explainability Panel answering:
    'WHY THIS ITEM IS CLASSIFIED THIS WAY'

    Shows:
      - Deterministic explanation
      - Business Rule Triggered
      - Supporting Metrics (all 9 operational dimensions)
      - Recommended Next Step
      - Commercial Decision Support: Case Classification vs. Sales Trend
      - Chart 1: Monthly sales trend for selected SKU

    100% deterministic Python logic. Never uses AI.
    """
    expl = generate_sku_classification_explanation(item_row)
    sku = sku_code or expl.get("sku")
    if (not sku or sku == "Unknown SKU") and hasattr(item_row, "name") and item_row.name:
        sku = str(item_row.name).strip()
    if not sku:
        sku = "Unknown SKU"
    cls = expl["classification"]
    explanation = expl["explanation"]
    rule = expl["rule_triggered"]
    action = expl["recommended_action"]
    m = expl["supporting_metrics"]

    # Class styling
    if cls == "Push":
        badge_style = "background-color: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;"
        border_accent = "#2563eb"
        card_bg = "#f0f7ff"
    elif cls == "Red List":
        badge_style = "background-color: #fef2f2; color: #b91c1c; border: 1px solid #fecaca;"
        border_accent = "#dc2626"
        card_bg = "#fff5f5"
    else:  # No Action
        badge_style = "background-color: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0;"
        border_accent = "#16a34a"
        card_bg = "#f4fbf7"

    risk_color_map = {
        "Critical": "#dc2626",
        "High": "#ea580c",
        "Medium": "#ca8a04",
        "Low": "#16a34a"
    }
    r_color = risk_color_map.get(m["Risk Level"], "#ca8a04")

    mtc_disp = "∞ (Stagnant)" if np.isinf(m["Months to Clear"]) else f"{m['Months to Clear']:.2f} mths"
    item_name = str(item_row.get("Item Name", "") if hasattr(item_row, "get") else getattr(item_row, "Item Name", ""))

    priority = expl.get("priority", "Medium")
    reason = expl.get("reason", "")
    pri_styles = {
        "Urgent": ("#dc2626", "background-color: #fef2f2; color: #b91c1c; border: 1px solid #fecaca;"),
        "High": ("#ea580c", "background-color: #fff7ed; color: #c2410c; border: 1px solid #ffedd5;"),
        "Medium": ("#ca8a04", "background-color: #fefce8; color: #a16207; border: 1px solid #fef08a;"),
        "Low": ("#16a34a", "background-color: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0;"),
    }
    pri_border, pri_badge_style = pri_styles.get(priority, ("#2563eb", "background-color: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;"))

    # Sales Trend Metrics & Styling
    sales_trend = str(item_row.get("Sales Trend", "Insufficient Data") if hasattr(item_row, "get") else getattr(item_row, "Sales Trend", "Insufficient Data"))
    trend_reason = str(item_row.get("Sales Trend Reason", "") if hasattr(item_row, "get") else getattr(item_row, "Sales Trend Reason", ""))
    latest_qty = item_row.get("Latest Month Sales", item_row.get("Latest Month Qty", None) if hasattr(item_row, "get") else getattr(item_row, "Latest Month Qty", None))
    prev_qty = item_row.get("Previous Month Sales", item_row.get("Previous Month Qty", None) if hasattr(item_row, "get") else getattr(item_row, "Previous Month Qty", None))
    growth_pct = item_row.get("Sales Growth %", None) if hasattr(item_row, "get") else getattr(item_row, "Sales Growth %", None)
    latest_m = str(item_row.get("Latest Month", "Latest Month") if hasattr(item_row, "get") else getattr(item_row, "Latest Month", "Latest Month"))
    prev_m = str(item_row.get("Previous Month", "Previous Month") if hasattr(item_row, "get") else getattr(item_row, "Previous Month", "Previous Month"))

    trend_badges = {
        "Growing": ("#16a34a", "background-color: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0;"),
        "Stable": ("#2563eb", "background-color: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;"),
        "Declining": ("#ea580c", "background-color: #fff7ed; color: #c2410c; border: 1px solid #ffedd5;"),
        "No Sales": ("#64748b", "background-color: #f8fafc; color: #64748b; border: 1px solid #e2e8f0;"),
        "Insufficient Data": ("#ca8a04", "background-color: #fefce8; color: #a16207; border: 1px solid #fef08a;"),
    }
    t_border, t_badge_style = trend_badges.get(sales_trend, ("#64748b", "background-color: #f8fafc; color: #64748b; border: 1px solid #e2e8f0;"))

    # Sales Priority Metrics (for Push items)
    p_score = item_row.get("Priority Score", None) if hasattr(item_row, "get") else getattr(item_row, "Priority Score", None)
    p_level = str(item_row.get("Priority Level", "Medium") if hasattr(item_row, "get") else getattr(item_row, "Priority Level", "Medium"))
    p_rank = item_row.get("Priority Rank", None) if hasattr(item_row, "get") else getattr(item_row, "Priority Rank", None)
    why_priority = str(item_row.get("Why Priority", "") if hasattr(item_row, "get") else getattr(item_row, "Why Priority", ""))

    priority_html = ""
    if cls == "Push" and p_score is not None and pd.notna(p_score):
        rank_text = f"RANK #{int(p_rank)} OF 18" if (p_rank is not None and pd.notna(p_rank)) else "PUSH PRIORITY"
        priority_html = f"""
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #7c3aed; border-radius: 6px; padding: 0.85rem 1.1rem; margin-top: 0.85rem; font-size: 0.88rem; line-height: 1.55;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem; flex-wrap: wrap; gap: 0.3rem;">
            <span style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #6d28d9;">
                Sales Priority Engine (Commercial Outreach Urgency)
            </span>
            <span style="font-size: 0.74rem; font-weight: 700; padding: 0.15rem 0.55rem; border-radius: 4px; background-color: #f5f3ff; color: #6d28d9; border: 1px solid #ddd6fe;">
                {rank_text} &bull; {p_level.upper()} PRIORITY ({p_score}/100)
            </span>
        </div>
        <div style="font-size: 0.95rem; font-weight: 700; color: #0f294a; margin-bottom: 0.3rem;">
            Why Priority?
        </div>
        <div style="font-size: 0.86rem; color: #334155;">
            {why_priority}
        </div>
    </div>
"""

    html_card = f"""
<div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-top: 4px solid {border_accent}; border-radius: 8px; padding: 1.25rem; margin-top: 0.75rem; margin-bottom: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; gap: 0.5rem;">
        <div>
            <div style="font-size: 1.05rem; font-weight: 800; color: #0f294a; letter-spacing: 0.03em;">
                WHY THIS ITEM IS CLASSIFIED THIS WAY
            </div>
            <div style="font-size: 0.82rem; color: #64748b;">
                Deterministic R5 Business Logic Explanation &bull; Item: <strong>{sku}</strong> ({item_name})
            </div>
        </div>
        <div style="display: flex; gap: 0.4rem; align-items: center;">
            <span style="font-size: 0.78rem; font-weight: 700; padding: 0.25rem 0.65rem; border-radius: 4px; {badge_style}">
                {cls.upper()}
            </span>
            <span style="font-size: 0.78rem; font-weight: 700; padding: 0.25rem 0.65rem; border-radius: 4px; background-color: #f8fafc; border: 1px solid #e2e8f0; color: {r_color};">
                {m['Risk Level']} Risk ({m['Risk Score']}/100)
            </span>
        </div>
    </div>
    
    <div style="background-color: {card_bg}; border-left: 4px solid {border_accent}; border-radius: 4px; padding: 0.85rem 1rem; margin-bottom: 0.85rem; font-size: 0.92rem; color: #0f172a; line-height: 1.55;">
        <strong>Deterministic Explanation:</strong><br>
        {explanation}
    </div>

    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.65rem 0.95rem; margin-bottom: 0.85rem; font-size: 0.86rem;">
        <span style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b;">Business Rule Triggered</span><br>
        <strong style="color: #0f294a;">{rule}</strong>
    </div>

    <div style="margin-bottom: 0.85rem;">
        <div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #475569; margin-bottom: 0.4rem;">
            Supporting Metrics
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.5rem;">
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.5rem 0.7rem;">
                <div style="font-size: 0.68rem; color: #64748b; text-transform: uppercase;">6M Sales Qty</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #0f294a;">{m['6M Sales Qty']:,.0f}</div>
                <div style="font-size: 0.66rem; color: #94a3b8;">Wholesale units</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.5rem 0.7rem;">
                <div style="font-size: 0.68rem; color: #64748b; text-transform: uppercase;">Master Pack</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #0f294a;">{m['Master Pack']:,.0f}</div>
                <div style="font-size: 0.66rem; color: #94a3b8;">Commercial MOQ</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.5rem 0.7rem;">
                <div style="font-size: 0.68rem; color: #64748b; text-transform: uppercase;">Aged Qty</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #0f294a;">{m['Aged Qty']:,.0f}</div>
                <div style="font-size: 0.66rem; color: #94a3b8;">91+ day stock</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.5rem 0.7rem;">
                <div style="font-size: 0.68rem; color: #64748b; text-transform: uppercase;">Aged Value</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #2563eb;">₹{m['Aged Value']:,.0f}</div>
                <div style="font-size: 0.66rem; color: #94a3b8;">Capital tied</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.5rem 0.7rem;">
                <div style="font-size: 0.68rem; color: #64748b; text-transform: uppercase;">Avg Monthly Sales</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #0f294a;">{m['Avg Monthly Sales']:.1f}</div>
                <div style="font-size: 0.66rem; color: #94a3b8;">Units / month</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.5rem 0.7rem;">
                <div style="font-size: 0.68rem; color: #64748b; text-transform: uppercase;">Months to Clear</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #0f294a;">{mtc_disp}</div>
                <div style="font-size: 0.66rem; color: #94a3b8;">Clearance runway</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.5rem 0.7rem;">
                <div style="font-size: 0.68rem; color: #64748b; text-transform: uppercase;">Inventory Value</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #0f294a;">₹{m['Inventory Value']:,.0f}</div>
                <div style="font-size: 0.66rem; color: #94a3b8;">Total warehouse val</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.5rem 0.7rem;">
                <div style="font-size: 0.68rem; color: #64748b; text-transform: uppercase;">Risk Score</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: {r_color};">{m['Risk Score']} <span style="font-size: 0.68rem;">/ 100</span></div>
                <div style="font-size: 0.66rem; color: {r_color}; font-weight: 600;">{m['Risk Level']} Level</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.5rem 0.7rem;">
                <div style="font-size: 0.68rem; color: #64748b; text-transform: uppercase;">Risk Level</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: {r_color};">{m['Risk Level']}</div>
                <div style="font-size: 0.66rem; color: #94a3b8;">Vulnerability tier</div>
            </div>
        </div>
    </div>

    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid {pri_border}; border-radius: 6px; padding: 0.85rem 1.1rem; font-size: 0.88rem; line-height: 1.55;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem; flex-wrap: wrap; gap: 0.3rem;">
            <span style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b;">
                Deterministic Recommended Action Engine
            </span>
            <span style="font-size: 0.74rem; font-weight: 700; padding: 0.15rem 0.55rem; border-radius: 4px; {pri_badge_style}">
                {priority.upper()} PRIORITY
            </span>
        </div>
        <div style="font-size: 0.95rem; font-weight: 700; color: #0f294a; margin-bottom: 0.3rem;">
            {action}
        </div>
        <div style="font-size: 0.84rem; color: #334155;">
            <strong>Reason:</strong> {reason}
        </div>
    </div>

    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid {t_border}; border-radius: 6px; padding: 0.85rem 1.1rem; margin-top: 0.85rem; font-size: 0.88rem; line-height: 1.55;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem; flex-wrap: wrap; gap: 0.3rem;">
            <span style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #0369a1;">
                Commercial Decision Support: Case Classification vs. Sales Trend
            </span>
            <span style="font-size: 0.74rem; font-weight: 700; padding: 0.15rem 0.55rem; border-radius: 4px; {t_badge_style}">
                {sales_trend.upper()} TREND
            </span>
        </div>
        <div style="font-size: 0.95rem; font-weight: 700; color: #0f294a; margin-bottom: 0.3rem;">
            CASE CLASSIFICATION: <span style="color: {border_accent};">{cls}</span> &nbsp;&bull;&nbsp; SALES TREND: <span style="color: {t_border};">{sales_trend}</span>
        </div>
        <div style="font-size: 0.84rem; color: #334155; margin-bottom: 0.4rem;">
            <strong>Sales Trajectory Rationale:</strong> {trend_reason}
        </div>
        <div style="font-size: 0.78rem; color: #64748b; font-style: italic;">
            *Notice: Case Classification strictly enforces Rule R5 based on aged stock and clearing runway. Sales Trend reflects recent commercial momentum from Sales_Lines as an advisory metric and does not alter R1–R7 classifications.
        </div>
    </div>
    {priority_html}
</div>
"""
    st.markdown(_clean_html_block(html_card), unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # CHART 1: MONTHLY SALES TREND FOR SELECTED SKU
    # --------------------------------------------------------------------------
    st.markdown(f'<div style="font-size: 0.95rem; font-weight: 700; color: #0f294a; margin-top: 0.85rem; margin-bottom: 0.4rem;">1. Monthly Sales Trend for {sku}</div>', unsafe_allow_html=True)
    if sales_trends:
        pvt_qty = sales_trends.get("monthly_qty_df", pd.DataFrame())
        pvt_val = sales_trends.get("monthly_val_df", pd.DataFrame())
        ordered_m = sales_trends.get("ordered_months", [])

        if sku in pvt_qty.index and ordered_m:
            sku_qty = pvt_qty.loc[sku]
            sku_val = pvt_val.loc[sku] if sku in pvt_val.index else pd.Series(0, index=ordered_m)
            total_sales = float(sku_qty.sum())

            if total_sales == 0:
                st.info(f"⚪ No historical sales units were recorded for {sku} across the {len(ordered_m)} observation periods. No monthly sales trend curve to plot.")
            elif len(ordered_m) < 2:
                st.info(f"ℹ️ Only {len(ordered_m)} historical sales period is available for {sku}. Minimum 2 chronological months required to compute trend without fabricating data.")
            else:
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Bar(
                    x=ordered_m,
                    y=[sku_qty[m] for m in ordered_m],
                    name="Monthly Sales Qty",
                    marker_color="#2563eb",
                    text=[f"{sku_qty[m]:,.0f}" for m in ordered_m],
                    textposition="auto",
                    customdata=[sku_val.get(m, 0.0) for m in ordered_m],
                    hovertemplate="<b>%{x}</b><br>Sales Qty: %{y:,.0f} units<br>Sales Value: ₹%{customdata:,.0f}<extra></extra>",
                ))
                fig_trend.add_trace(go.Scatter(
                    x=ordered_m,
                    y=[sku_qty[m] for m in ordered_m],
                    mode="lines+markers",
                    name="Trajectory",
                    line=dict(color="#0f294a", width=2),
                    marker=dict(size=7, color="#0f294a"),
                    hoverinfo="skip",
                ))
                fig_trend.update_layout(
                    template="simple_white",
                    height=280,
                    margin=dict(l=10, r=10, t=25, b=25),
                    xaxis_title="Chronological Sales Month",
                    yaxis_title="Sales Quantity (Units)",
                    legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
                    font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI", size=11, color="#0f172a"),
                )
                st.plotly_chart(fig_trend, use_container_width=True)

                col_tr1, col_tr2, col_tr3, col_tr4 = st.columns(4)
                with col_tr1:
                    disp_lat = f"{latest_qty:,.0f} units" if (latest_qty is not None and pd.notna(latest_qty)) else "-"
                    st.metric(f"Latest Month ({latest_m})", disp_lat)
                with col_tr2:
                    disp_prev = f"{prev_qty:,.0f} units" if (prev_qty is not None and pd.notna(prev_qty)) else "-"
                    st.metric(f"Previous Month ({prev_m})", disp_prev)
                with col_tr3:
                    if growth_pct is not None and pd.notna(growth_pct):
                        st.metric("MoM Growth %", f"{growth_pct:+.1f}%", delta=f"{growth_pct:+.1f}%")
                    else:
                        st.metric("MoM Growth %", "-")
                with col_tr4:
                    st.metric("Avg Monthly Sales", f"{m['Avg Monthly Sales']:.1f} units")
        else:
            st.info(f"⚪ No historical sales records found for {sku} in Sales_Lines.")


# Navigation: 8 Primary Business Sections
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "Executive Action Center",
    "Item Analysis",
    "Sales Action Center",
    "Data Lineage / Audit",
    "Data Quality",
    "Settings",
    "Export",
    "AI Management Assistant",
])

# ==============================================================================
# TAB 1: EXECUTIVE ACTION CENTER
# ==============================================================================
with tab1:
    # Working Capital Impact Module (precomputed in run_analysis)
    wc = analysis.get("working_capital", calculate_working_capital_impact(items))
    wc_summary = wc["summary"]
    wc_by_class = wc["by_class"]
    wc_by_cat = wc["by_category"]
    wc_top10 = wc["top10_aged_skus"]

    # Portfolio Classification & Inventory Counts
    counts = items["Class"].value_counts()
    red_count = int(counts.get("Red List", 0))
    noaction_count = int(counts.get("No Action", 0))
    push_count = int(counts.get("Push", 0))
    total_skus = len(items)

    push_aged_value = float(wc_summary.get("push_aged_value", float(items.loc[items["Class"] == "Push", "Aged Value"].sum())))
    total_aged_value = float(wc_summary.get("aged_inventory_value", float(items["Aged Value"].sum())))
    total_inv_value = float(wc_summary.get("total_inventory_value", float(items["Inventory Value"].sum())))
    push_share = float(wc_summary.get("push_share_of_aged", (push_aged_value / total_aged_value * 100.0) if total_aged_value > 0 else 0.0))
    total_aged_qty = float(items["Aged Qty"].sum())
    total_stock_qty = float(items["Total Stock"].sum())

    # Operational Inventory Risk Tiers
    crit_count = int((items["Risk Level"] == "Critical").sum()) if "Risk Level" in items else 0
    high_count = int((items["Risk Level"] == "High").sum()) if "Risk Level" in items else 0
    med_count = int((items["Risk Level"] == "Medium").sum()) if "Risk Level" in items else 0
    low_count = int((items["Risk Level"] == "Low").sum()) if "Risk Level" in items else 0
    high_crit_skus = crit_count + high_count

    # Ranked Push Priority Queue
    ranked_push = analysis.get("ranked_push_table")
    if ranked_push is None:
        ranked_push = get_ranked_push_table(items)

    # Dead Stock Analysis (Items with 6M Sales Qty = 0; segregated analytical view)
    dead_stock_df = analysis.get("dead_stock")
    if dead_stock_df is None:
        dead_stock_df = identify_dead_stock(items, sales_df=analysis.get("clean_sales"))
    dead_summary = analysis.get("dead_stock_summary")
    if dead_summary is None:
        dead_summary = get_dead_stock_summary(
            dead_stock_df,
            total_inventory_value=wc_summary["total_inventory_value"],
            total_aged_value=wc_summary["aged_inventory_value"]
        )
    top_dead_stock_df = get_top_dead_stock_by_value(dead_stock_df, top_n=10)

    # Diagnostic Helpers for 30-Second Executive Assessment
    top1_sku = ranked_push.iloc[0]["SKU"] if not ranked_push.empty else "N/A"
    top1_score = int(ranked_push.iloc[0]["Priority Score"]) if not ranked_push.empty else 0
    top2_sku = ranked_push.iloc[1]["SKU"] if len(ranked_push) > 1 else "N/A"
    top2_score = int(ranked_push.iloc[1]["Priority Score"]) if len(ranked_push) > 1 else 0

    top_cat_row = wc_by_cat.iloc[0] if not wc_by_cat.empty else None
    top_exposed_cat = top_cat_row["Category"] if top_cat_row is not None else "N/A"
    top_exposed_cat_val = float(top_cat_row["Aged Value"]) if top_cat_row is not None else 0.0
    top_exposed_cat_share = (top_exposed_cat_val / total_aged_value * 100) if total_aged_value > 0 else 0.0

    # --------------------------------------------------------------------------
    # FIRST SCREEN: 30-SECOND EXECUTIVE DIAGNOSTIC ASSESSMENT
    # --------------------------------------------------------------------------
    st.markdown(_clean_html_block(f"""
    <div class="exec-brief-container">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.65rem; flex-wrap: wrap; gap: 0.5rem;">
            <div style="font-size: 0.88rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #0f294a;">
                Executive Action Center &bull; 30-Second Diagnostic Summary
            </div>
            <span style="font-size: 0.72rem; font-weight: 600; color: #0f294a; background: #e2e8f0; border: 1px solid #cbd5e1; padding: 0.2rem 0.55rem; border-radius: 4px;">
                Active Inventory Diagnostics
            </span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 0.65rem 1.25rem; font-size: 0.85rem; color: #1e293b; line-height: 1.55;">
            <div>1. <strong>Total Inventory:</strong> ₹{wc_summary['total_inventory_value']:,.0f} across {total_skus} active SKUs ({total_stock_qty:,.0f} units holding stock).</div>
            <div>2. <strong>Aged Inventory (Cash at Risk):</strong> ₹{wc_summary['aged_inventory_value']:,.0f} ({wc_summary['aged_inventory_pct']:.1f}% of inventory value) across {total_aged_qty:,.0f} aged units (91+ days).</div>
            <div>3. <strong>SKUs Requiring Action:</strong> {push_count + red_count} of {total_skus} SKUs need intervention ({push_count} Push + {red_count} Red List; {(((push_count + red_count)/total_skus*100) if total_skus > 0 else 0.0):.1f}% of catalog).</div>
            <div>4. <strong>Push Inventory Exposure:</strong> {push_count} Push SKUs holding ₹{wc_summary['push_inventory_value']:,.0f} inventory (₹{push_aged_value:,.0f} aged; {((push_aged_value/total_aged_value*100) if total_aged_value > 0 else 0.0):.1f}% of total aged capital).</div>
            <div>5. <strong>Most Urgent SKUs:</strong> <code>{top1_sku}</code> (Priority Score {top1_score}, Critical) and <code>{top2_sku}</code> (Priority Score {top2_score}, Critical).</div>
            <div>6. <strong>Most Exposed Category:</strong> <strong>{top_exposed_cat}</strong> (₹{top_exposed_cat_val:,.0f} aged capital; {top_exposed_cat_share:.1f}% of company aged stock).</div>
            <div>7. <strong>Dead Stock (Zero Demand):</strong> <strong>{dead_summary['kpi_label']}</strong> completely stagnant (6M Sales Qty = 0; ₹{dead_summary['dead_stock_aged_value']:,.0f} aged; {dead_summary['dead_stock_pct_of_total_inv']:.1f}% of catalog value; Red List under R5).</div>
            <div>8. <strong>Immediate Sales Focus:</strong> Target pre-qualified buyers in <strong>Top 10 Push Opportunities</strong> via Tab 3 (Sales Action Center).</div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # 8 EXECUTIVE KPI CARDS
    # --------------------------------------------------------------------------
    st.markdown(_clean_html_block(f"""
    <div class="kpi-grid">
        <div class="kpi-card exec-total">
            <div class="kpi-label">Total SKUs</div>
            <div class="kpi-number" style="color: #0f294a;">{total_skus}</div>
            <div class="kpi-desc">Active catalog items analyzed</div>
        </div>
        <div class="kpi-card push">
            <div class="kpi-label">Push SKUs</div>
            <div class="kpi-number" style="color: #2563eb;">{push_count}</div>
            <div class="kpi-desc">Actionable slow stock (Sales push)</div>
        </div>
        <div class="kpi-card redlist">
            <div class="kpi-label">Red List SKUs</div>
            <div class="kpi-number" style="color: #dc2626;">{red_count}</div>
            <div class="kpi-desc">6M sales &lt; 1 MP; write-off review</div>
        </div>
        <div class="kpi-card noaction">
            <div class="kpi-label">No Action SKUs</div>
            <div class="kpi-number" style="color: #059669;">{noaction_count}</div>
            <div class="kpi-desc">Healthy velocity or zero aged stock</div>
        </div>
        <div class="kpi-card exec-total">
            <div class="kpi-label">Total Inventory Value</div>
            <div class="kpi-number" style="color: #0f294a;">₹{wc_summary['total_inventory_value']:,.0f}</div>
            <div class="kpi-desc">Warehouse capital ({total_stock_qty:,.0f} units)</div>
        </div>
        <div class="kpi-card exec-aged">
            <div class="kpi-label">Aged Inventory Value</div>
            <div class="kpi-number" style="color: #b91c1c;">₹{wc_summary['aged_inventory_value']:,.0f}</div>
            <div class="kpi-desc">Cash at Risk ({wc_summary['aged_inventory_pct']:.1f}% of inventory)</div>
        </div>
        <div class="kpi-card value">
            <div class="kpi-label">Push Aged Value</div>
            <div class="kpi-number" style="color: #1d4ed8;">₹{push_aged_value:,.0f}</div>
            <div class="kpi-desc">{push_share:.1f}% of total active aged capital</div>
        </div>
        <div class="kpi-card exec-risk">
            <div class="kpi-label">High/Critical Risk SKUs</div>
            <div class="kpi-number" style="color: #ea580c;">{high_crit_skus} <span style="font-size: 0.85rem; font-weight: 500; color: #64748b;">SKUs</span></div>
            <div class="kpi-desc">{crit_count} Critical + {high_count} High risk tiers</div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SECTION 1: EXECUTIVE SUMMARY
    # --------------------------------------------------------------------------
    st.markdown(_clean_html_block("""
    <div class="exec-section-header">
        <div class="exec-section-title">SECTION 1: Executive Summary</div>
        <span class="exec-section-badge">Capital Allocation &amp; Scope</span>
    </div>
    """), unsafe_allow_html=True)

    # Cash at Risk Concept Banner
    st.markdown(_clean_html_block(f"""
    <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 5px solid #0f294a; border-radius: 6px; padding: 0.95rem 1.25rem; margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem;">
            <div>
                <div style="font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b;">
                    Executive Working Capital Metric &bull; Cash at Risk
                </div>
                <div style="font-size: 1.65rem; font-weight: 800; color: #0f294a; margin-top: 0.15rem;">
                    ₹{wc_summary['cash_at_risk']:,.0f} <span style="font-size: 0.92rem; font-weight: 600; color: #475569;">({wc_summary['aged_inventory_pct']:.1f}% of Total Inventory Value)</span>
                </div>
            </div>
            <span style="font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: #b45309; background: #fef3c7; border: 1px solid #fde68a; padding: 0.25rem 0.65rem; border-radius: 4px;">
                ⚠️ Trapped Working Capital
            </span>
        </div>
        <div style="font-size: 0.84rem; color: #334155; margin-top: 0.45rem; line-height: 1.5;">
            <strong>Cash at Risk Disclosure:</strong> Reflects <strong>inventory value tied up in aged stock (91+ days)</strong> across warehouse holdings. It quantifies tied-up working capital that requires proactive liquidation (Push) or scrap/write-off review (Red List), <em>not guaranteed cash recovery</em>.
        </div>
    </div>
    """), unsafe_allow_html=True)

    col_sec1_chart, col_sec1_tbl = st.columns([1.1, 0.9])

    with col_sec1_chart:
        fig_class = go.Figure()
        fig_class.add_trace(go.Bar(
            name="Total Inventory Value",
            x=wc_by_class["Class"],
            y=wc_by_class["Inventory Value"],
            marker_color="#2563eb",
            text=wc_by_class["Inventory Value"].apply(lambda v: f"₹{v:,.0f}"),
            textposition="auto",
        ))
        fig_class.add_trace(go.Bar(
            name="Aged Value (Cash at Risk)",
            x=wc_by_class["Class"],
            y=wc_by_class["Aged Value"],
            marker_color="#dc2626",
            text=wc_by_class["Aged Value"].apply(lambda v: f"₹{v:,.0f}"),
            textposition="auto",
        ))
        fig_class.update_layout(
            barmode="group",
            template="simple_white",
            height=320,
            margin=dict(l=10, r=10, t=25, b=25),
            yaxis_title="Inventory Value (₹)",
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
            font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI", size=11, color="#0f172a"),
        )
        st.plotly_chart(fig_class, use_container_width=True)

    with col_sec1_tbl:
        # Portfolio Summary Table
        summary_rows = [
            {
                "Classification": "Push",
                "SKUs": push_count,
                "Total Value": f"₹{wc_summary['push_inventory_value']:,.0f}",
                "Aged Value": f"₹{wc_summary['push_aged_value']:,.0f}",
                "Aged %": f"{(wc_summary['push_aged_value'] / wc_summary['push_inventory_value'] * 100):.1f}%" if wc_summary.get('push_inventory_value', 0) > 0 else "0.0%",
                "Operational Focus": "Targeted sales liquidation to qualified accounts"
            },
            {
                "Classification": "Red List",
                "SKUs": red_count,
                "Total Value": f"₹{wc_summary['red_list_inventory_value']:,.0f}",
                "Aged Value": f"₹{wc_summary['red_list_aged_value']:,.0f}",
                "Aged %": f"{(wc_summary['red_list_aged_value'] / wc_summary['red_list_inventory_value'] * 100):.1f}%" if wc_summary.get('red_list_inventory_value', 0) > 0 else "0.0%",
                "Operational Focus": "Halt replenishment; write-off / vendor return review"
            },
            {
                "Classification": "No Action",
                "SKUs": noaction_count,
                "Total Value": f"₹{wc_summary['no_action_inventory_value']:,.0f}",
                "Aged Value": "₹0",
                "Aged %": "0.0%",
                "Operational Focus": "Standard replenishment; regular velocity monitoring"
            },
            {
                "Classification": "Active Portfolio Total",
                "SKUs": total_skus,
                "Total Value": f"₹{wc_summary['total_inventory_value']:,.0f}",
                "Aged Value": f"₹{wc_summary['aged_inventory_value']:,.0f}",
                "Aged %": f"{wc_summary['aged_inventory_pct']:.1f}%",
                "Operational Focus": "Proactive slow-stock clearance & capital preservation"
            }
        ]
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        if len(analysis['inactive_stock']) > 0:
            st.caption(f"ℹ️ {len(analysis['inactive_stock'])} inactive items holding warehouse stock are isolated and tracked separately (Rule R4).")

    # --------------------------------------------------------------------------
    # SECTION 2: INVENTORY RISK
    # --------------------------------------------------------------------------
    st.markdown(_clean_html_block("""
    <div class="exec-section-header">
        <div class="exec-section-title">SECTION 2: Inventory Risk</div>
        <span class="exec-section-badge">Deterministic 0–100 Multi-Factor Risk Index</span>
    </div>
    """), unsafe_allow_html=True)

    st.caption("Multi-factor risk index evaluating aged stock %, clearance runway, sales velocity, commercial demand scale, and capital tied up. Complements R1-R7 slow stock classifications.")

    st.markdown(_clean_html_block(f"""
    <div class="metric-row" style="margin-bottom: 1.1rem;">
        <div class="metric-col" style="border-left: 4px solid #dc2626;">
            <div class="metric-col-label" style="color: #991b1b;">Critical Risk (80–100)</div>
            <div class="metric-col-val" style="color: #dc2626;">{crit_count} <span style="font-size: 0.85rem; font-weight: 500; color: #64748b;">SKUs</span></div>
            <div style="font-size: 0.78rem; color: #64748b; margin-top: 0.2rem;">Severe obsolescence / stagnant</div>
        </div>
        <div class="metric-col" style="border-left: 4px solid #ea580c;">
            <div class="metric-col-label" style="color: #c2410c;">High Risk (60–79)</div>
            <div class="metric-col-val" style="color: #ea580c;">{high_count} <span style="font-size: 0.85rem; font-weight: 500; color: #64748b;">SKUs</span></div>
            <div style="font-size: 0.78rem; color: #64748b; margin-top: 0.2rem;">Elevated aging or long runway</div>
        </div>
        <div class="metric-col" style="border-left: 4px solid #ca8a04;">
            <div class="metric-col-label" style="color: #a16207;">Medium Risk (30–59)</div>
            <div class="metric-col-val" style="color: #ca8a04;">{med_count} <span style="font-size: 0.85rem; font-weight: 500; color: #64748b;">SKUs</span></div>
            <div style="font-size: 0.78rem; color: #64748b; margin-top: 0.2rem;">Moderate slow-moving stock</div>
        </div>
        <div class="metric-col" style="border-left: 4px solid #16a34a;">
            <div class="metric-col-label" style="color: #166534;">Low Risk (0–29)</div>
            <div class="metric-col-val" style="color: #16a34a;">{low_count} <span style="font-size: 0.85rem; font-weight: 500; color: #64748b;">SKUs</span></div>
            <div style="font-size: 0.78rem; color: #64748b; margin-top: 0.2rem;">Healthy velocity or zero aged</div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # Dead Stock Diagnostic Alert (6M Sales Qty = 0)
    st.markdown(_clean_html_block(f"""
    <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-left: 4px solid #b91c1c; border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.5rem; margin-bottom: 0.85rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.4rem;">
            <div style="font-size: 0.82rem; font-weight: 700; color: #991b1b; text-transform: uppercase; letter-spacing: 0.04em;">
                Dead Stock Diagnostic (6M Sales Qty = 0)
            </div>
            <span style="font-size: 0.72rem; font-weight: 700; color: #991b1b; background: #fee2e2; border: 1px solid #fca5a5; padding: 0.15rem 0.5rem; border-radius: 4px;">
                Analytical Isolation &bull; Red List (Rule R5)
            </span>
        </div>
        <div style="font-size: 0.85rem; color: #7f1d1d; margin-top: 0.25rem; line-height: 1.45;">
            <strong>{dead_summary['kpi_label']}</strong> has recorded zero sales across the 6-month review period (₹{dead_summary['dead_stock_aged_value']:,.0f} aged; {dead_summary['dead_stock_total_units']:,.0f} units in stock). Completely stagnant items are strictly segregated from commercial Push items and classified as Red List under Rule R5. Review full operational liquidation details in <strong>Tab 2: Item Analysis</strong>.
        </div>
    </div>
    """), unsafe_allow_html=True)

    # Top High & Critical Risk Items Table
    high_crit_items = items[items["Risk Level"].isin(["Critical", "High"])].sort_values("Risk Score", ascending=False)
    if not high_crit_items.empty:
        risk_cols = ["SKU", "Item Name", "Category", "Class", "Risk Score", "Risk Level", "Months to Clear", "Aged Value", "Risk Explanation"]
        avail_risk_cols = [c for c in risk_cols if c in high_crit_items.columns]
        risk_display = high_crit_items[avail_risk_cols].copy()
        risk_display["Aged Value"] = risk_display["Aged Value"].apply(lambda v: f"₹{v:,.0f}")
        risk_display["Months to Clear"] = risk_display["Months to Clear"].round(1)
        st.dataframe(risk_display, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # SECTION 3: TOP 10 PUSH OPPORTUNITIES
    # --------------------------------------------------------------------------
    st.markdown(_clean_html_block("""
    <div class="exec-section-header">
        <div class="exec-section-title">SECTION 3: Top 10 Push Opportunities</div>
        <span class="exec-section-badge">Sales Prioritization Queue (#1 to #10)</span>
    </div>
    """), unsafe_allow_html=True)

    st.caption("Commercial liquidation queue ranking actionable Push slow-stock items by capital at risk, clearance runway, sales trend, turnover velocity, and operational risk.")

    top10_push_ranked = ranked_push.head(10).copy()
    if not top10_push_ranked.empty:
        def _get_target_count(s):
            tdf = targets.get(s)
            return len(tdf) if isinstance(tdf, pd.DataFrame) else 0

        def _get_top_target(s):
            tdf = targets.get(s)
            if isinstance(tdf, pd.DataFrame) and not tdf.empty and "CustomerName" in tdf.columns:
                return str(tdf.iloc[0]["CustomerName"])
            return "None qualified"

        top10_push_ranked["Target Accounts"] = top10_push_ranked["SKU"].apply(_get_target_count)
        top10_push_ranked["Top Target Account"] = top10_push_ranked["SKU"].apply(_get_top_target)

        push_cols_display = [
            "Rank", "SKU", "Description", "Category", "Aged Value",
            "Months to Clear", "Sales Trend", "Priority Score", "Priority Level",
            "Target Accounts", "Top Target Account", "Why Priority"
        ]
        avail_push_cols = [c for c in push_cols_display if c in top10_push_ranked.columns]
        display_push_df = top10_push_ranked[avail_push_cols].copy()
        if "Aged Value" in display_push_df.columns:
            display_push_df["Aged Value"] = display_push_df["Aged Value"].apply(lambda v: f"₹{v:,.0f}")
        if "Months to Clear" in display_push_df.columns:
            display_push_df["Months to Clear"] = display_push_df["Months to Clear"].apply(
                lambda m: "∞" if (pd.isna(m) or m == float("inf") or np.isinf(m)) else f"{float(m):.1f} m"
            )

        st.dataframe(display_push_df, use_container_width=True, hide_index=True)
        st.info("👉 **Where should sales teams focus?** Navigate to **Tab 3: Sales Action Center** to inspect the prioritized customer targets (Bucket 1, Bucket 2, Bucket 3) for each Push item.")

    # --------------------------------------------------------------------------
    # SECTION 4: TOP 10 CASH-AT-RISK SKUS
    # --------------------------------------------------------------------------
    st.markdown(_clean_html_block("""
    <div class="exec-section-header">
        <div class="exec-section-title">SECTION 4: Top 10 Cash-at-Risk SKUs</div>
        <span class="exec-section-badge">Whole-Portfolio Capital Concentration</span>
    </div>
    """), unsafe_allow_html=True)

    st.caption("Identifies the 10 catalog items holding the highest aged inventory value (91+ days) across both Push and Red List classifications.")

    fig_top10_all = px.bar(
        wc_top10.sort_values("Aged Value", ascending=True),
        x="Aged Value",
        y="SKU",
        orientation="h",
        hover_data=["Item Name", "Category", "Class", "Total Stock", "Inventory Value", "Aged Qty", "Months to Clear"],
        color="Class",
        color_discrete_map={
            "Push": "#2563eb",
            "No Action": "#059669",
            "Red List": "#dc2626"
        },
        text=wc_top10.sort_values("Aged Value", ascending=True)["Aged Value"].apply(lambda v: f"₹{v:,.0f}"),
    )
    fig_top10_all.update_traces(textposition="auto")
    fig_top10_all.update_layout(
        template="simple_white",
        height=330,
        margin=dict(l=10, r=20, t=25, b=30),
        xaxis_title="Aged Value (₹) — Cash at Risk",
        yaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5),
        font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI", size=11, color="#0f172a"),
    )
    st.plotly_chart(fig_top10_all, use_container_width=True)

    # Top 10 Cash at Risk Data Table
    top10_car = wc_top10.copy()
    top10_car.insert(0, "Rank", range(1, len(top10_car) + 1))
    if total_aged_value > 0 and "Aged Value" in top10_car.columns:
        top10_car["% of Total Aged Capital"] = (top10_car["Aged Value"] / total_aged_value * 100).apply(lambda p: f"{p:.1f}%")
    if "Aged Value" in top10_car.columns:
        top10_car["Aged Value"] = top10_car["Aged Value"].apply(lambda v: f"₹{v:,.0f}")
    if "Inventory Value" in top10_car.columns:
        top10_car["Inventory Value"] = top10_car["Inventory Value"].apply(lambda v: f"₹{v:,.0f}")
    if "Unit Cost (Rs)" in top10_car.columns:
        top10_car["Unit Cost (Rs)"] = top10_car["Unit Cost (Rs)"].apply(lambda c: f"₹{c:,.0f}")
    if "Months to Clear" in top10_car.columns:
        top10_car["Months to Clear"] = top10_car["Months to Clear"].apply(
            lambda m: "∞" if (m == float("inf") or np.isinf(m)) else (f"{float(m):.1f} m" if pd.notna(m) else "N/A")
        )

    top10_display_cols = [
        "Rank", "SKU", "Item Name", "Category", "Class", "Total Stock",
        "Aged Qty", "Unit Cost (Rs)", "Inventory Value", "Aged Value",
        "% of Total Aged Capital", "Recommended Action"
    ]
    avail_top10_display = [c for c in top10_display_cols if c in top10_car.columns]
    st.dataframe(top10_car[avail_top10_display], use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # SECTION 5: CATEGORY ANALYSIS
    # --------------------------------------------------------------------------
    st.markdown(_clean_html_block("""
    <div class="exec-section-header">
        <div class="exec-section-title">SECTION 5: Category Analysis</div>
        <span class="exec-section-badge">Portfolio Vulnerability by Product Line</span>
    </div>
    """), unsafe_allow_html=True)

    st.caption("Answers: Which categories are most exposed? Evaluates total inventory capital, aged inventory, and exposure concentration across product categories.")

    col_cat_c1, col_cat_c2 = st.columns([1, 1])

    with col_cat_c1:
        fig_cat = px.bar(
            wc_by_cat,
            x="Category",
            y="Aged Value",
            text=wc_by_cat["Aged Value"].apply(lambda v: f"₹{v:,.0f}"),
            color_discrete_sequence=["#0f294a"],
        )
        fig_cat.update_traces(textposition="auto")
        fig_cat.update_layout(
            template="simple_white",
            height=320,
            margin=dict(l=10, r=10, t=25, b=25),
            xaxis_title="",
            yaxis_title="Aged Value (₹)",
            font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI", size=11, color="#0f172a"),
        )
        st.plotly_chart(fig_cat, use_container_width=True)

    with col_cat_c2:
        cat_display = wc_by_cat.copy()
        cat_sku_counts = items.groupby("Category")["SKU"].count().to_dict()
        cat_push_counts = items[items["Class"] == "Push"].groupby("Category")["SKU"].count().to_dict()
        cat_display.insert(1, "Total SKUs", cat_display["Category"].map(cat_sku_counts))
        cat_display.insert(2, "Push SKUs", cat_display["Category"].map(cat_push_counts).fillna(0).astype(int))
        cat_display["Share of Total Aged Capital"] = (cat_display["Aged Value"] / total_aged_value * 100).apply(lambda p: f"{p:.1f}%") if total_aged_value > 0 else "0.0%"
        cat_display["Inventory Value"] = cat_display["Inventory Value"].apply(lambda v: f"₹{v:,.0f}")
        cat_display["Aged Value"] = cat_display["Aged Value"].apply(lambda v: f"₹{v:,.0f}")
        cat_display["Aged Share %"] = cat_display["Aged Share %"].apply(lambda p: f"{p:.1f}%")

        def _cat_exposure_tier(p_float):
            if p_float >= 28.0:
                return "High Exposure"
            elif p_float >= 20.0:
                return "Moderate"
            return "Low"

        cat_display["Vulnerability Level"] = wc_by_cat["Aged Share %"].apply(_cat_exposure_tier)
        st.dataframe(
            cat_display[["Category", "Total SKUs", "Push SKUs", "Inventory Value", "Aged Value", "Aged Share %", "Share of Total Aged Capital", "Vulnerability Level"]],
            use_container_width=True,
            hide_index=True
        )
        st.caption(f"📌 **Key Category Exposure:** <strong>{top_exposed_cat}</strong> holds the highest aged capital (₹{top_exposed_cat_val:,.0f}; {top_exposed_cat_share:.1f}% of total active aged inventory).")

    # --------------------------------------------------------------------------
    # SECTION 6: SALES TREND
    # --------------------------------------------------------------------------
    st.markdown(_clean_html_block("""
    <div class="exec-section-header">
        <div class="exec-section-title">SECTION 6: Sales Trend</div>
        <span class="exec-section-badge">Commercial Demand Momentum</span>
    </div>
    """), unsafe_allow_html=True)

    sales_trends = analysis.get("sales_trends", {})
    trend_dist = sales_trends.get("distribution", {})
    summary_df = sales_trends.get("summary_df", pd.DataFrame())

    # Decision-Support Distinction Callout
    st.markdown(_clean_html_block("""
    <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #0284c7; border-radius: 6px; padding: 0.85rem 1rem; margin-bottom: 1rem;">
        <div style="font-size: 0.88rem; color: #1e293b; line-height: 1.55;">
            &bull; <strong>CASE CLASSIFICATION (Rule R5):</strong> Strictly determines operational inventory status (<strong>Push</strong>, <strong>No Action</strong>, <strong>Red List</strong>) based on aged warehouse stock (91+ days) and Months to Clear.<br>
            &bull; <strong>SALES TREND:</strong> Evaluates recent month-over-month commercial momentum (<strong>Growing</strong>, <strong>Stable</strong>, <strong>Declining</strong>, <strong>No Sales</strong>, <strong>Insufficient Data</strong>) from <code>Sales_Lines</code> to assist sales reps in targeting receptive accounts.<br>
            <span style="font-size: 0.78rem; color: #64748b; font-style: italic;">
                *Sales Trend is strictly an advisory decision-support layer. It NEVER overrides, alters, or reclassifies items across Rules R1–R7.
            </span>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # Trend Summary KPI Cards
    st.markdown(_clean_html_block(f"""
    <div class="kpi-grid">
        <div class="kpi-card" style="border-top: 3px solid #16a34a; background-color: #f0fdf4;">
            <div class="kpi-label">Growing Demand</div>
            <div class="kpi-number" style="color: #15803d;">{trend_dist.get('Growing', 0)}</div>
            <div class="kpi-desc">MoM sales growth &gt; +5.0%</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #2563eb; background-color: #eff6ff;">
            <div class="kpi-label">Stable Velocity</div>
            <div class="kpi-number" style="color: #1d4ed8;">{trend_dist.get('Stable', 0)}</div>
            <div class="kpi-desc">MoM sales change within &plusmn;5.0%</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #ea580c; background-color: #fff7ed;">
            <div class="kpi-label">Declining Demand</div>
            <div class="kpi-number" style="color: #c2410c;">{trend_dist.get('Declining', 0)}</div>
            <div class="kpi-desc">MoM sales decline &lt; -5.0% or drop to 0</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #64748b; background-color: #f8fafc;">
            <div class="kpi-label">No Sales / Stagnant</div>
            <div class="kpi-number" style="color: #475569;">{trend_dist.get('No Sales', 0)}</div>
            <div class="kpi-desc">Zero historical sales units recorded</div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    top_declining = get_top_declining_push_items(summary_df, items, top_n=5)
    top_growing = get_top_growing_push_items(summary_df, items, top_n=5)

    col_chart2, col_chart3 = st.columns([1, 1])

    with col_chart2:
        st.markdown('<div class="content-box-title">Top Declining Push Items</div>', unsafe_allow_html=True)
        st.caption("Push items experiencing steep sales declines — requires urgent sales outreach before runout horizon elongates further.")
        if not top_declining.empty:
            fig_dec = px.bar(
                top_declining.sort_values("Sales Growth %", ascending=True),
                x="Sales Growth %",
                y="SKU",
                orientation="h",
                text=top_declining.sort_values("Sales Growth %", ascending=True)["Sales Growth %"].apply(lambda p: f"{p:.1f}%"),
                hover_data=["Item Name", "Category", "Previous Month Qty", "Latest Month Qty", "Aged Value"],
                color_discrete_sequence=["#ea580c"],
            )
            fig_dec.update_traces(textposition="auto")
            fig_dec.update_layout(
                template="simple_white",
                height=300,
                margin=dict(l=10, r=20, t=25, b=25),
                xaxis_title="Month-over-Month Sales Growth (%)",
                yaxis_title="",
                font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI", size=11, color="#0f172a"),
            )
            st.plotly_chart(fig_dec, use_container_width=True)

            dec_display = top_declining[["SKU", "Item Name", "Category", "Previous Month Qty", "Latest Month Qty", "Sales Growth %", "Aged Value"]].copy()
            dec_display["Sales Growth %"] = dec_display["Sales Growth %"].apply(lambda p: f"{p:.1f}%")
            dec_display["Aged Value"] = dec_display["Aged Value"].apply(lambda v: f"₹{v:,.0f}")
            st.dataframe(dec_display, use_container_width=True, hide_index=True)
        else:
            st.info("No declining Push items found.")

    with col_chart3:
        st.markdown('<div class="content-box-title">Top Growing Push Items</div>', unsafe_allow_html=True)
        st.caption("Push items with positive sales growth — prime candidates for cross-selling and clearance acceleration.")
        if not top_growing.empty:
            fig_grow = px.bar(
                top_growing.sort_values("Sales Growth %", ascending=True),
                x="Sales Growth %",
                y="SKU",
                orientation="h",
                text=top_growing.sort_values("Sales Growth %", ascending=True)["Sales Growth %"].apply(lambda p: f"+{p:.1f}%"),
                hover_data=["Item Name", "Category", "Previous Month Qty", "Latest Month Qty", "Aged Value"],
                color_discrete_sequence=["#16a34a"],
            )
            fig_grow.update_traces(textposition="auto")
            fig_grow.update_layout(
                template="simple_white",
                height=300,
                margin=dict(l=10, r=20, t=25, b=25),
                xaxis_title="Month-over-Month Sales Growth (%)",
                yaxis_title="",
                font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI", size=11, color="#0f172a"),
            )
            st.plotly_chart(fig_grow, use_container_width=True)

            grow_display = top_growing[["SKU", "Item Name", "Category", "Previous Month Qty", "Latest Month Qty", "Sales Growth %", "Aged Value"]].copy()
            grow_display["Sales Growth %"] = grow_display["Sales Growth %"].apply(lambda p: f"+{p:.1f}%")
            grow_display["Aged Value"] = grow_display["Aged Value"].apply(lambda v: f"₹{v:,.0f}")
            st.dataframe(grow_display, use_container_width=True, hide_index=True)
        else:
            st.info("No growing Push items found.")

    # --------------------------------------------------------------------------
    # SECTION 7: RECOMMENDED ACTIONS
    # --------------------------------------------------------------------------
    st.markdown(_clean_html_block("""
    <div class="exec-section-header">
        <div class="exec-section-title">SECTION 7: Recommended Actions</div>
        <span class="exec-section-badge">Operational Action Matrix &amp; Next Steps</span>
    </div>
    """), unsafe_allow_html=True)

    # Operational Mandate Cards
    col_act1, col_act2, col_act3 = st.columns(3)

    with col_act1:
        st.markdown(_clean_html_block(f"""
        <div style="background-color: #f0f7ff; border: 1px solid #bfdbfe; border-left: 4px solid #2563eb; border-radius: 6px; padding: 0.95rem 1.1rem; height: 100%;">
            <div style="font-weight: 700; color: #1e3a8a; font-size: 0.96rem; margin-bottom: 0.35rem;">
                🎯 Push Liquidation Mandate ({push_count} SKUs)
            </div>
            <div style="font-size: 0.85rem; color: #1e293b; line-height: 1.5; margin-bottom: 0.5rem;">
                Total Capital: <strong>₹{wc_summary['push_inventory_value']:,.0f}</strong><br>
                Aged Target: <strong>₹{push_aged_value:,.0f}</strong>
            </div>
            <div style="font-size: 0.82rem; color: #334155; line-height: 1.45;">
                <strong>Next Step:</strong> Mobilize sales reps to prioritize accounts in <strong>Bucket 1</strong> (Repeat Buyers) and <strong>Bucket 2</strong> (Similar Business) using Tab 3.
            </div>
        </div>
        """), unsafe_allow_html=True)

    with col_act2:
        st.markdown(_clean_html_block(f"""
        <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-left: 4px solid #dc2626; border-radius: 6px; padding: 0.95rem 1.1rem; height: 100%;">
            <div style="font-weight: 700; color: #991b1b; font-size: 0.96rem; margin-bottom: 0.35rem;">
                🛑 Red List Obsolescence ({red_count} SKUs)
            </div>
            <div style="font-size: 0.85rem; color: #1e293b; line-height: 1.5; margin-bottom: 0.5rem;">
                Total Capital: <strong>₹{wc_summary['red_list_inventory_value']:,.0f}</strong><br>
                Aged Target: <strong>₹{wc_summary['red_list_aged_value']:,.0f}</strong>
            </div>
            <div style="font-size: 0.82rem; color: #334155; line-height: 1.45;">
                <strong>Next Step:</strong> Immediately freeze replenishment orders; conduct formal scrap, vendor return, or write-off review (6M sales &lt; 1 Master Pack).
            </div>
        </div>
        """), unsafe_allow_html=True)

    with col_act3:
        st.markdown(_clean_html_block(f"""
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #059669; border-radius: 6px; padding: 0.95rem 1.1rem; height: 100%;">
            <div style="font-weight: 700; color: #065f46; font-size: 0.96rem; margin-bottom: 0.35rem;">
                ✅ No Action Monitoring ({noaction_count} SKUs)
            </div>
            <div style="font-size: 0.85rem; color: #1e293b; line-height: 1.5; margin-bottom: 0.5rem;">
                Total Capital: <strong>₹{wc_summary['no_action_inventory_value']:,.0f}</strong><br>
                Aged Target: <strong>₹0</strong> (Zero Aged Stock)
            </div>
            <div style="font-size: 0.82rem; color: #334155; line-height: 1.45;">
                <strong>Next Step:</strong> Maintain standard replenishment; inventory turnover is healthy (clearance runway &lt; 3.0 months).
            </div>
        </div>
        """), unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # CASE RESULTS SECTION (Evaluator Case Validation Checks)
    # --------------------------------------------------------------------------
    st.divider()

    actual_red = red_count
    actual_noaction = noaction_count
    actual_push = push_count
    actual_push_val = push_aged_value

    sku_class_map = items.set_index("SKU")["Class"].to_dict()
    c_1001 = sku_class_map.get("SKU1001", "N/A")
    c_1006 = sku_class_map.get("SKU1006", "N/A")
    c_1019 = sku_class_map.get("SKU1019", "N/A")
    c_1005 = sku_class_map.get("SKU1005", "N/A")

    t_1005 = targets.get("SKU1005", pd.DataFrame())
    top3_cust = []
    if isinstance(t_1005, pd.DataFrame) and not t_1005.empty and "CustomerName" in t_1005.columns:
        for _, row in t_1005.head(3).iterrows():
            top3_cust.append(str(row["CustomerName"]))
    while len(top3_cust) < 3:
        top3_cust.append("N/A")

    st.markdown(_clean_html_block("""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem; margin-top: 0.5rem;">
        <div style="font-size: 1.15rem; font-weight: 700; color: #0f294a;">Case Results</div>
        <span style="font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; color: #0369a1; background: #e0f2fe; border: 1px solid #bae6fd; padding: 0.2rem 0.6rem; border-radius: 4px;">
            Case validation checks
        </span>
    </div>
    <div style="font-size: 0.82rem; color: #64748b; margin-bottom: 0.85rem;">
        Validation feature for evaluator review. Displays dynamically calculated classification benchmarks, key SKU verifications, and prioritized customer targets for SKU1005.
    </div>
    """), unsafe_allow_html=True)

    col_case1, col_case2, col_case3 = st.columns(3)

    with col_case1:
        st.markdown(_clean_html_block(f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem 1rem; height: 100%;">
            <div style="font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 0.5rem;">
                Classification Benchmarks
            </div>
            <div style="font-size: 0.9rem; line-height: 1.8; color: #0f172a;">
                <div>&bull; <strong>Red List:</strong> <span style="font-weight: 700; color: #dc2626;">{actual_red}</span></div>
                <div>&bull; <strong>No Action:</strong> <span style="font-weight: 700; color: #059669;">{actual_noaction}</span></div>
                <div>&bull; <strong>Push:</strong> <span style="font-weight: 700; color: #2563eb;">{actual_push}</span></div>
                <div>&bull; <strong>Push Aged Value:</strong> <span style="font-weight: 700; color: #0f294a;">₹{actual_push_val:,.0f}</span></div>
            </div>
        </div>
        """), unsafe_allow_html=True)

    with col_case2:
        st.markdown(_clean_html_block(f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem 1rem; height: 100%;">
            <div style="font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 0.5rem;">
                Required SKU Checks
            </div>
            <div style="font-size: 0.9rem; line-height: 1.8; color: #0f172a;">
                <div>&bull; <strong>SKU1001</strong> &rarr; <span style="font-weight: 600; color: #059669;">{c_1001}</span></div>
                <div>&bull; <strong>SKU1006</strong> &rarr; <span style="font-weight: 600; color: #2563eb;">{c_1006}</span></div>
                <div>&bull; <strong>SKU1019</strong> &rarr; <span style="font-weight: 600; color: #2563eb;">{c_1019}</span></div>
                <div>&bull; <strong>SKU1005</strong> &rarr; <span style="font-weight: 600; color: #2563eb;">{c_1005}</span></div>
            </div>
        </div>
        """), unsafe_allow_html=True)

    with col_case3:
        st.markdown(_clean_html_block(f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem 1rem; height: 100%;">
            <div style="font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 0.5rem;">
                For SKU1005: First Three Target Customers
            </div>
            <div style="font-size: 0.9rem; line-height: 1.8; color: #0f172a;">
                <div>1. <strong>{top3_cust[0]}</strong></div>
                <div>2. <strong>{top3_cust[1]}</strong></div>
                <div>3. <strong>{top3_cust[2]}</strong></div>
            </div>
        </div>
        """), unsafe_allow_html=True)


# ==============================================================================
# TAB 2: ITEM ANALYSIS
# ==============================================================================
with tab2:
    st.markdown('<div class="content-box-title">Master Inventory Classification &amp; Aging</div>', unsafe_allow_html=True)
    st.caption("Filter, search, and analyze all active catalog items across aging buckets, operational velocity metrics, and deterministic risk scores.")

    # Filter Controls
    col_f1, col_f2, col_f3, col_f4, col_f5, col_f6, col_f7 = st.columns([1, 1, 1, 1.1, 1, 1.2, 1.2])
    all_classes = ["All"] + sorted(items["Class"].dropna().unique().tolist())
    all_risks = ["All", "Critical", "High", "Medium", "Low"]
    all_priorities = ["All", "Urgent", "High", "Medium", "Low"]
    all_trends = ["All", "Growing", "Stable", "Declining", "No Sales", "Insufficient Data"]
    all_cats = ["All"] + sorted(items["Category"].dropna().unique().tolist())

    f_class = col_f1.selectbox("Filter Class", all_classes)
    f_risk = col_f2.selectbox("Filter Risk Level", all_risks)
    f_prio = col_f3.selectbox("Filter Priority", all_priorities)
    f_trend = col_f4.selectbox("Filter Sales Trend", all_trends)
    f_cat = col_f5.selectbox("Filter Category", all_cats)
    s_sku = col_f6.text_input("Search SKU", placeholder="e.g. SKU1005")
    s_name = col_f7.text_input("Search Item Name", placeholder="e.g. Product 05")

    # Filter Application
    filtered = items.copy()
    if f_class != "All":
        filtered = filtered[filtered["Class"] == f_class]
    if f_risk != "All" and "Risk Level" in filtered.columns:
        filtered = filtered[filtered["Risk Level"] == f_risk]
    if f_prio != "All" and "Priority" in filtered.columns:
        filtered = filtered[filtered["Priority"] == f_prio]
    if f_trend != "All" and "Sales Trend" in filtered.columns:
        filtered = filtered[filtered["Sales Trend"] == f_trend]
    if f_cat != "All":
        filtered = filtered[filtered["Category"] == f_cat]
    if s_sku.strip():
        filtered = filtered[filtered["SKU"].str.contains(s_sku.strip().upper(), na=False)]
    if s_name.strip():
        filtered = filtered[filtered["Item Name"].str.lower().str.contains(s_name.strip().lower(), na=False)]

    st.markdown(f"**Showing {len(filtered)} of {len(items)} items**")

    # Display Table with clean formatting
    tbl_cols = [
        "SKU", "Item Name", "Category", "Class",
        "Sales Trend", "Sales Growth %", "Latest Month Sales", "Previous Month Sales",
        "Priority", "Recommended Action",
        "Risk Score", "Risk Level",
        "Master Pack Qty", "Unit Cost (Rs)", "Total Stock",
        "6M Sales Qty", "Avg Monthly Sales", "Months to Clear",
        "Aged Qty", "Aged Value", "Reason"
    ]
    avail_tbl_cols = [c for c in tbl_cols if c in filtered.columns]
    tbl_view = filtered[avail_tbl_cols].copy()

    if "Unit Cost (Rs)" in tbl_view.columns:
        tbl_view["Unit Cost (Rs)"] = tbl_view["Unit Cost (Rs)"].apply(lambda x: f"₹{x:,.0f}")
    if "Avg Monthly Sales" in tbl_view.columns:
        tbl_view["Avg Monthly Sales"] = tbl_view["Avg Monthly Sales"].round(1)
    if "Months to Clear" in tbl_view.columns:
        tbl_view["Months to Clear"] = tbl_view["Months to Clear"].apply(
            lambda m: "∞ (Non-clearing)" if m == float("inf") else f"{m:.2f}"
        )
    if "Aged Value" in tbl_view.columns:
        tbl_view["Aged Value"] = tbl_view["Aged Value"].apply(lambda v: f"₹{v:,.0f}")
    if "Sales Growth %" in tbl_view.columns:
        tbl_view["Sales Growth %"] = tbl_view["Sales Growth %"].apply(
            lambda p: f"{p:+.1f}%" if (pd.notna(p) and p is not None) else "-"
        )
    if "Latest Month Sales" in tbl_view.columns:
        tbl_view["Latest Month Sales"] = tbl_view["Latest Month Sales"].apply(
            lambda q: f"{q:,.0f}" if (pd.notna(q) and q is not None) else "-"
        )
    if "Previous Month Sales" in tbl_view.columns:
        tbl_view["Previous Month Sales"] = tbl_view["Previous Month Sales"].apply(
            lambda q: f"{q:,.0f}" if (pd.notna(q) and q is not None) else "-"
        )

    st.dataframe(tbl_view, use_container_width=True, hide_index=True)

    with st.expander("ℹ️ Transparent Inventory Risk Scoring Methodology (0–100)"):
        st.markdown("""
**Deterministic Scoring Architecture (0–100 Points):**

The Inventory Risk Score quantifies catalog vulnerability across 5 objective operational dimensions. The calculation never uses AI and does not override R1–R7 classifications:

1. **Aged Stock Percentage (0–25 pts):** Proportion of inventory aged 91+ days ($\ge 60\%$: 25 pts; $40\text{--}59\%$: 20 pts; $25\text{--}39\%$: 15 pts; $10\text{--}24\%$: 8 pts; $>0\%$: 4 pts; $0\%$: 0 pts).
2. **Months to Clear (0–25 pts):** Runway to clear stock at current monthly velocity (Infinite/stagnant: 25 pts; $\ge 12$m: 22 pts; $6\text{--}12$m: 18 pts; $3\text{--}6$m: 12 pts; $1.5\text{--}3$m: 5 pts; $<1.5$m: 0 pts).
3. **Sales Velocity (0–20 pts):** Monthly inventory turnover rate ($\le 0$ sales: 20 pts; $<10\%$ turnover: 16 pts; $<20\%$ turnover: 12 pts; $<33\%$ turnover: 6 pts; $\ge 33\%$: 0 pts).
4. **6M Demand Volume Scale (0–15 pts):** Wholesale commercial volume vs Master Pack ($0$ sales: 15 pts; $<1$ Master Pack: 12 pts; $<2$ Master Packs: 7 pts; $<5$ Master Packs: 3 pts; $\ge 5$ Master Packs: 0 pts).
5. **Aged Inventory Capital Value (0–15 pts):** Capital trapped in warehouse aged stock ($\ge ₹25\text{k}$: 15 pts; $₹15\text{k}\text{--}₹25\text{k}$: 12 pts; $₹7.5\text{k}\text{--}₹15\text{k}$: 8 pts; $₹2.5\text{k}\text{--}₹7.5\text{k}$: 4 pts; $>₹0$: 2 pts; $₹0$: 0 pts).

**Risk Level Tiers:**
- 🔴 **Critical (80–100):** Severe obsolescence, stagnant movement, or zero demand.
- 🟠 **High (60–79):** High proportion of aged stock, low sales velocity, and extended clearance runway.
- 🟡 **Medium (30–59):** Moderate slow-moving stock requiring targeted sales liquidation.
- 🟢 **Low (0–29):** Rapid stock clearance, healthy turnover, and minimal or zero aged inventory.
""")

    # --------------------------------------------------------------------------
    # DEAD STOCK ANALYSIS VIEW (6M Sales Qty = 0)
    # --------------------------------------------------------------------------
    st.divider()
    st.markdown('<div class="content-box-title">Dead Stock Analysis View (6M Sales Qty = 0)</div>', unsafe_allow_html=True)
    st.caption("Specialized analytical diagnostic identifying completely stagnant catalog items holding zero sales movement in the 6-month review period. Separated from normal slow-moving Push items.")

    # Operational Separation & Governance Callout Banner
    st.markdown(_clean_html_block("""
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 5px solid #dc2626; border-radius: 6px; padding: 0.95rem 1.25rem; margin-bottom: 1.15rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.35rem;">
            <div style="font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #991b1b;">
                Operational Separation &bull; Zero Demand Diagnostic (6M Sales Qty = 0)
            </div>
            <span style="font-size: 0.72rem; font-weight: 700; color: #991b1b; background: #fee2e2; border: 1px solid #fca5a5; padding: 0.2rem 0.55rem; border-radius: 4px;">
                Analytical Diagnostic &mdash; R1-R7 Invariant
            </span>
        </div>
        <div style="font-size: 0.86rem; color: #334155; line-height: 1.55;">
            <strong>Separation from Normal Push Items:</strong> Push items represent active slow-moving inventory with commercial sales velocity (> 0 sales, &ge; 3.0 months runway) prioritized for proactive sales outreach in Tab 3 (Sales Action Center). In contrast, <strong>Dead Stock</strong> isolates catalog items holding <strong>strictly zero sales</strong> (6M Sales Qty = 0) across the entire review period.<br>
            <span style="font-size: 0.80rem; color: #64748b; font-style: italic;">
                *Governance Notice: Dead Stock is an analytical diagnostic view, NOT a replacement for Red List classification. Under Rule R5, items with 6M sales &lt; 1 Master Pack remain officially classified as <strong>Red List</strong>.
            </span>
        </div>
    </div>
    """), unsafe_allow_html=True)

    tab2_dead_df = analysis.get("dead_stock")
    if tab2_dead_df is None:
        tab2_dead_df = identify_dead_stock(items, sales_df=analysis.get("clean_sales"))
    tab2_dead_summary = analysis.get("dead_stock_summary")
    if tab2_dead_summary is None:
        tot_inv_val = float(items["Inventory Value"].sum())
        tot_aged_val = float(items["Aged Value"].sum())
        tab2_dead_summary = get_dead_stock_summary(
            tab2_dead_df,
            total_inventory_value=tot_inv_val,
            total_aged_value=tot_aged_val
        )
    tab2_top_dead = get_top_dead_stock_by_value(tab2_dead_df, top_n=10)

    # Dead Stock KPI Cards
    st.markdown(_clean_html_block(f"""
    <div class="kpi-grid" style="margin-bottom: 1.25rem;">
        <div class="kpi-card" style="border-top: 3px solid #b91c1c; background-color: #fef2f2;">
            <div class="kpi-label">Dead Stock SKUs</div>
            <div class="kpi-number" style="color: #991b1b;">{tab2_dead_summary['dead_stock_count']}</div>
            <div class="kpi-desc">6M Sales Qty = 0 (Completely stagnant)</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #0f294a; background-color: #ffffff;">
            <div class="kpi-label">Dead Stock Inventory Value</div>
            <div class="kpi-number" style="color: #0f294a;">₹{tab2_dead_summary['dead_stock_inventory_value']:,.0f}</div>
            <div class="kpi-desc">Trapped warehouse inventory capital</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #dc2626; background-color: #ffffff;">
            <div class="kpi-label">Aged Value (Cash at Risk)</div>
            <div class="kpi-number" style="color: #dc2626;">₹{tab2_dead_summary['dead_stock_aged_value']:,.0f}</div>
            <div class="kpi-desc">{tab2_dead_summary['dead_stock_pct_of_aged_inv']:.1f}% of total aged inventory value</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #475569; background-color: #ffffff;">
            <div class="kpi-label">Warehouse Stock Units</div>
            <div class="kpi-number" style="color: #334155;">{tab2_dead_summary['dead_stock_total_units']:,.0f}</div>
            <div class="kpi-desc">{tab2_dead_summary['dead_stock_aged_units']:,.0f} units aged 91+ days</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #7c3aed; background-color: #ffffff;">
            <div class="kpi-label">Catalog Value Exposure</div>
            <div class="kpi-number" style="color: #6d28d9;">{tab2_dead_summary['dead_stock_pct_of_total_inv']:.1f}%</div>
            <div class="kpi-desc">Share of company inventory value</div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # Top Dead Stock by Inventory Value Table
    st.markdown('<div class="content-box-title">Top Dead Stock by Inventory Value</div>', unsafe_allow_html=True)
    st.caption("Ranked by total inventory value trapped in zero-demand stock. Displays all 10 required operational and diagnostic metrics.")

    if tab2_dead_df.empty:
        st.success("✅ No dead stock items detected. All active catalog items recorded sales during the 6-month review period.")
    else:
        req_dead_cols = [
            "SKU", "Description", "Category", "Total Stock", "Inventory Value",
            "Aged Qty", "Aged Value", "Last Available Sales Information",
            "Risk Score", "Recommended Action"
        ]
        dead_tbl_view = tab2_top_dead[[c for c in req_dead_cols if c in tab2_top_dead.columns]].copy()
        if "Total Stock" in dead_tbl_view.columns:
            dead_tbl_view["Total Stock"] = dead_tbl_view["Total Stock"].apply(lambda q: f"{q:,.0f}")
        if "Inventory Value" in dead_tbl_view.columns:
            dead_tbl_view["Inventory Value"] = dead_tbl_view["Inventory Value"].apply(lambda v: f"₹{v:,.0f}")
        if "Aged Qty" in dead_tbl_view.columns:
            dead_tbl_view["Aged Qty"] = dead_tbl_view["Aged Qty"].apply(lambda q: f"{q:,.0f}")
        if "Aged Value" in dead_tbl_view.columns:
            dead_tbl_view["Aged Value"] = dead_tbl_view["Aged Value"].apply(lambda v: f"₹{v:,.0f}")

        st.dataframe(dead_tbl_view, use_container_width=True, hide_index=True)

        col_ds_select, col_ds_dl = st.columns([2.5, 1.5])
        with col_ds_select:
            ds_lookup = tab2_dead_df.drop_duplicates(subset=["SKU"]).set_index("SKU") if not tab2_dead_df.empty else pd.DataFrame()
            dead_skus = list(ds_lookup.index)
            def _format_dead_sku(s):
                try:
                    desc = ds_lookup.loc[s, 'Description'] if (s in ds_lookup.index and 'Description' in ds_lookup.columns) else s
                    inv = ds_lookup.loc[s, 'Inventory Value'] if (s in ds_lookup.index and 'Inventory Value' in ds_lookup.columns) else 0
                    return f"{s} — {desc} (₹{inv:,.0f})"
                except Exception:
                    return str(s)
            selected_dead_sku = st.selectbox(
                "Select Dead Stock Item for Operational Diagnostic Detail",
                dead_skus,
                format_func=_format_dead_sku
            )

        with col_ds_dl:
            st.write("")
            st.write("")
            dead_excel = export_dead_stock_excel(tab2_dead_df)
            st.download_button(
                "📥 Export Dead Stock Analysis (.xlsx)",
                data=dead_excel,
                file_name="CompanyX_Dead_Stock_Analysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_dead_stock_tab2",
                use_container_width=True,
            )

        if selected_dead_sku:
            dead_row = tab2_dead_df[tab2_dead_df["SKU"] == selected_dead_sku].iloc[0]
            st.markdown(_clean_html_block(f"""
            <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #b91c1c; border-radius: 6px; padding: 0.95rem 1.25rem; margin-top: 0.75rem; margin-bottom: 1.15rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.5rem;">
                    <div>
                        <span style="font-size: 1.05rem; font-weight: 700; color: #0f294a;">{dead_row['SKU']}</span>
                        <span style="font-size: 0.92rem; color: #475569; margin-left: 0.4rem;">&mdash; {dead_row['Description']}</span>
                    </div>
                    <div style="display: flex; gap: 0.4rem; align-items: center;">
                        <span style="font-size: 0.72rem; font-weight: 700; color: #b91c1c; background: #fee2e2; border: 1px solid #fecaca; padding: 0.2rem 0.55rem; border-radius: 4px;">
                            Risk Score: {dead_row['Risk Score']} ({dead_row.get('Risk Level', 'Critical')})
                        </span>
                        <span style="font-size: 0.72rem; font-weight: 700; color: #991b1b; background: #fee2e2; border: 1px solid #fca5a5; padding: 0.2rem 0.55rem; border-radius: 4px;">
                            Rule R5: {dead_row['Class']}
                        </span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.65rem 1rem; font-size: 0.84rem; color: #334155; margin-bottom: 0.65rem;">
                    <div><strong>Category:</strong> {dead_row['Category']}</div>
                    <div><strong>Total Stock:</strong> {dead_row['Total Stock']:,.0f} units</div>
                    <div><strong>Inventory Value:</strong> ₹{dead_row['Inventory Value']:,.0f}</div>
                    <div><strong>Aged Qty (91+ d):</strong> {dead_row['Aged Qty']:,.0f} units</div>
                    <div><strong>Aged Value:</strong> ₹{dead_row['Aged Value']:,.0f}</div>
                    <div><strong>Unit Cost:</strong> ₹{dead_row.get('Unit Cost (Rs)', 0):,.0f}</div>
                </div>
                <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 4px; padding: 0.65rem 0.85rem; margin-bottom: 0.6rem; font-size: 0.83rem;">
                    <strong style="color: #0f294a;">Last Available Sales Information:</strong><br>
                    <span style="color: #64748b;">{dead_row['Last Available Sales Information']}</span>
                </div>
                <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-left: 3px solid #2563eb; border-radius: 4px; padding: 0.65rem 0.85rem; font-size: 0.84rem; color: #1e3a8a;">
                    <strong>Recommended Operational Action:</strong><br>
                    <span>{dead_row['Recommended Action']}</span>
                </div>
            </div>
            """), unsafe_allow_html=True)

    st.divider()
    st.markdown('<div class="content-box-title">SKU Classification Explainability Panel</div>', unsafe_allow_html=True)
    st.caption("Select any catalog item to inspect why it was assigned its classification, review the exact business rules triggered, and examine all 9 supporting operational metrics.")

    sku_lookup = items.drop_duplicates(subset=["SKU"]).set_index("SKU") if not items.empty else pd.DataFrame()
    sku_all_list = list(sku_lookup.index)

    col_expl_sku, _ = st.columns([2, 1])
    default_expl_idx = sku_all_list.index("SKU1006") if "SKU1006" in sku_all_list else 0
    def _format_expl_sku(s):
        try:
            name = sku_lookup.loc[s, 'Item Name'] if (s in sku_lookup.index and 'Item Name' in sku_lookup.columns) else s
            cls_val = sku_lookup.loc[s, 'Class'] if (s in sku_lookup.index and 'Class' in sku_lookup.columns) else 'Unknown'
            aged_val = sku_lookup.loc[s, 'Aged Value'] if (s in sku_lookup.index and 'Aged Value' in sku_lookup.columns) else 0.0
            return f"{s} — {name} [{cls_val}] (Aged Val: ₹{aged_val:,.0f})"
        except Exception:
            return str(s)
    selected_expl_sku = col_expl_sku.selectbox(
        "Select Catalog SKU to Inspect Classification Rationale",
        sku_all_list,
        index=default_expl_idx,
        format_func=_format_expl_sku
    )

    if selected_expl_sku:
        selected_item_data = sku_lookup.loc[selected_expl_sku]
        if isinstance(selected_item_data, pd.DataFrame):
            selected_item_data = selected_item_data.iloc[0]
        render_explainability_panel(selected_item_data, sales_trends=analysis.get("sales_trends", {}), sku_code=selected_expl_sku)

    # --------------------------------------------------------------------------
    # WHAT-IF SCENARIO SIMULATOR (SALES UPLIFT)
    # --------------------------------------------------------------------------
    st.divider()
    st.markdown('<div class="content-box-title">What-If Scenario Simulator (Sales Uplift)</div>', unsafe_allow_html=True)

    # Prominent Scenario Disclosure Banner
    st.markdown(_clean_html_block("""
    <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 5px solid #2563eb; border-radius: 6px; padding: 0.95rem 1.25rem; margin-bottom: 1.15rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.35rem;">
            <div style="font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #1e3a8a;">
                Exploratory Scenario Analysis &bull; Sales Uplift Simulation
            </div>
            <span style="font-size: 0.72rem; font-weight: 700; color: #b45309; background: #fef3c7; border: 1px solid #fde68a; padding: 0.2rem 0.55rem; border-radius: 4px;">
                ⚠️ Scenario Simulation &mdash; Not Actual Performance
            </span>
        </div>
        <div style="font-size: 0.86rem; color: #334155; line-height: 1.5;">
            Simulate the operational impact of sales uplifts (<strong>10%</strong>, <strong>25%</strong>, <strong>50%</strong>, or <strong>custom %</strong>) on inventory turnover, clearance runway, and operational classification.<br>
            <span style="font-size: 0.78rem; color: #64748b; font-style: italic;">
                *Strict Invariant: This simulation is 100% reversible, does not overwrite the source dataset, and never alters official Rules R1–R7 classifications.
            </span>
        </div>
    </div>
    """), unsafe_allow_html=True)

    col_sim_sku, col_sim_scenario = st.columns([1.5, 2.5])

    with col_sim_sku:
        sim_default_idx = sku_all_list.index(selected_expl_sku) if selected_expl_sku in sku_all_list else 0
        def _format_sim_sku(s):
            try:
                name = sku_lookup.loc[s, 'Item Name'] if (s in sku_lookup.index and 'Item Name' in sku_lookup.columns) else s
                cls_val = sku_lookup.loc[s, 'Class'] if (s in sku_lookup.index and 'Class' in sku_lookup.columns) else 'Unknown'
                return f"{s} — {name} [{cls_val}]"
            except Exception:
                return str(s)
        sim_sku = st.selectbox(
            "Select SKU to Simulate",
            sku_all_list,
            index=sim_default_idx,
            key="whatif_sim_sku",
            format_func=_format_sim_sku
        )

    with col_sim_scenario:
        scenario_preset = st.radio(
            "Select Uplift Scenario",
            ["10% sales uplift", "25% sales uplift", "50% sales uplift", "Custom sales uplift"],
            horizontal=True,
            key="whatif_scenario_preset",
        )

        if scenario_preset == "10% sales uplift":
            uplift_val = 10.0
        elif scenario_preset == "25% sales uplift":
            uplift_val = 25.0
        elif scenario_preset == "50% sales uplift":
            uplift_val = 50.0
        else:
            uplift_val = st.slider(
                "Specify Custom Sales Uplift (%)",
                min_value=-50.0,
                max_value=200.0,
                value=15.0,
                step=5.0,
                format="%+.0f%%",
                key="whatif_custom_slider",
            )

    # Compute deterministic simulation
    sim_item_raw = sku_lookup.loc[sim_sku]
    if isinstance(sim_item_raw, pd.DataFrame):
        sim_item_raw = sim_item_raw.iloc[0]

    sim_res = simulate_sku_sales_uplift(sim_item_raw, uplift_val)

    # Format helpers
    cur_mtc_str = "∞ (Non-clearing)" if (sim_res["current_months_to_clear"] == float("inf") or np.isinf(sim_res["current_months_to_clear"])) else f"{sim_res['current_months_to_clear']:.2f} m"
    sim_mtc_str = "∞ (Non-clearing)" if (sim_res["simulated_months_to_clear"] == float("inf") or np.isinf(sim_res["simulated_months_to_clear"])) else f"{sim_res['simulated_months_to_clear']:.2f} m"
    runway_saved_str = f"{sim_res['runway_reduction_months']:.1f} months saved" if not np.isinf(sim_res["runway_reduction_months"]) else "Accelerated from ∞"

    # Status badge styling
    badge_color_map = {
        "Push": ("#1d4ed8", "#eff6ff", "#bfdbfe"),
        "No Action": ("#15803d", "#f0fdf4", "#bbf7d0"),
        "Red List": ("#b91c1c", "#fef2f2", "#fecaca"),
    }
    cur_c, cur_bg, cur_bdr = badge_color_map.get(sim_res["current_classification"], ("#475569", "#f8fafc", "#e2e8f0"))
    sim_c, sim_bg, sim_bdr = badge_color_map.get(sim_res["simulated_operational_status"], ("#475569", "#f8fafc", "#e2e8f0"))

    # CURRENT vs SCENARIO Comparison Cards
    st.markdown(_clean_html_block(f"""
    <div style="font-size: 0.92rem; font-weight: 700; color: #0f294a; margin-top: 0.75rem; margin-bottom: 0.45rem; text-transform: uppercase; letter-spacing: 0.04em;">
        CURRENT vs SCENARIO ({uplift_val:+.0f}% Sales Uplift for {sim_sku})
    </div>
    <div class="metric-row">
        <div class="metric-col">
            <div class="metric-col-label">Avg Monthly Sales</div>
            <div style="display: flex; align-items: baseline; gap: 0.4rem; margin-top: 0.2rem;">
                <span style="font-size: 1.1rem; font-weight: 600; color: #64748b;">{sim_res['current_avg_monthly_sales']:.1f}</span>
                <span style="font-size: 0.85rem; color: #94a3b8;">&rarr;</span>
                <span style="font-size: 1.35rem; font-weight: 800; color: #059669;">{sim_res['simulated_avg_monthly_sales']:.1f}</span>
                <span style="font-size: 0.75rem; font-weight: 600; color: #059669;">({uplift_val:+.0f}%)</span>
            </div>
            <div style="font-size: 0.75rem; color: #64748b; margin-top: 0.15rem;">units / month pace</div>
        </div>
        <div class="metric-col">
            <div class="metric-col-label">Months to Clear (Runway)</div>
            <div style="display: flex; align-items: baseline; gap: 0.4rem; margin-top: 0.2rem;">
                <span style="font-size: 1.1rem; font-weight: 600; color: #64748b;">{cur_mtc_str}</span>
                <span style="font-size: 0.85rem; color: #94a3b8;">&rarr;</span>
                <span style="font-size: 1.35rem; font-weight: 800; color: #2563eb;">{sim_mtc_str}</span>
            </div>
            <div style="font-size: 0.75rem; color: #16a34a; margin-top: 0.15rem; font-weight: 600;">
                {sim_res['improvement_headline']}
            </div>
        </div>
        <div class="metric-col">
            <div class="metric-col-label">Operational Status</div>
            <div style="display: flex; align-items: center; gap: 0.45rem; margin-top: 0.25rem;">
                <span style="font-size: 0.78rem; font-weight: 700; color: {cur_c}; background: {cur_bg}; border: 1px solid {cur_bdr}; padding: 0.2rem 0.5rem; border-radius: 4px;">
                    {sim_res['current_classification']}
                </span>
                <span style="font-size: 0.85rem; color: #94a3b8;">&rarr;</span>
                <span style="font-size: 0.78rem; font-weight: 700; color: {sim_c}; background: {sim_bg}; border: 1px solid {sim_bdr}; padding: 0.2rem 0.5rem; border-radius: 4px;">
                    {sim_res['simulated_operational_status']}
                </span>
            </div>
            <div style="font-size: 0.74rem; color: #64748b; margin-top: 0.25rem;">
                {sim_res['status_note']}
            </div>
        </div>
        <div class="metric-col">
            <div class="metric-col-label">6-Month Demand Volume</div>
            <div style="display: flex; align-items: baseline; gap: 0.4rem; margin-top: 0.2rem;">
                <span style="font-size: 1.1rem; font-weight: 600; color: #64748b;">{sim_res['current_6m_sales_qty']:,.0f}</span>
                <span style="font-size: 0.85rem; color: #94a3b8;">&rarr;</span>
                <span style="font-size: 1.35rem; font-weight: 800; color: #0f294a;">{sim_res['simulated_6m_sales_qty']:,.0f}</span>
                <span style="font-size: 0.75rem; font-weight: 600; color: #059669;">(+{sim_res['additional_6m_units']:,.0f} u)</span>
            </div>
            <div style="font-size: 0.75rem; color: #64748b; margin-top: 0.15rem;">Master Pack: {sim_res['master_pack']:.0f} units</div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # Estimated Stock Clearance Improvement Callout
    st.markdown(_clean_html_block(f"""
    <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #16a34a; border-radius: 6px; padding: 0.85rem 1.15rem; margin-top: 0.85rem; margin-bottom: 1rem;">
        <div style="font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #166534;">
            Estimated Stock Clearance Improvement &bull; Operational Summary
        </div>
        <div style="font-size: 0.92rem; color: #14532d; font-weight: 600; margin-top: 0.25rem; line-height: 1.5;">
            {sim_res['clearance_summary']}
        </div>
        <div style="display: flex; gap: 1.5rem; flex-wrap: wrap; margin-top: 0.45rem; font-size: 0.82rem; color: #166534;">
            <div><strong>Clearance Pace:</strong> +{sim_res['additional_monthly_units']:.1f} units / month</div>
            <div><strong>Capital Liquidation Pace:</strong> +₹{sim_res['additional_monthly_capital']:,.0f} / month</div>
            <div><strong>Runway Shortening:</strong> {runway_saved_str} ({sim_res['runway_reduction_pct']:.1f}% faster)</div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # CHARTS: CURRENT vs SCENARIO
    # --------------------------------------------------------------------------
    col_chart_mtc, col_chart_dep = st.columns([1, 1.2])

    with col_chart_mtc:
        st.markdown('<div class="content-box-title">Clearance Runway (Months to Clear)</div>', unsafe_allow_html=True)
        st.caption("Compares current runway against scenario clearance runway. 3.0-month threshold indicates slow-stock cutoff.")

        cur_mtc_val = min(24.0, sim_res["current_months_to_clear"]) if not np.isinf(sim_res["current_months_to_clear"]) else 24.0
        sim_mtc_val = min(24.0, sim_res["simulated_months_to_clear"]) if not np.isinf(sim_res["simulated_months_to_clear"]) else 24.0

        fig_mtc = go.Figure()
        fig_mtc.add_trace(go.Bar(
            name="Current Runway",
            x=["Months to Clear"],
            y=[cur_mtc_val],
            marker_color="#64748b",
            text=[f"{sim_res['current_months_to_clear']:.2f} m" if not np.isinf(sim_res['current_months_to_clear']) else "∞"],
            textposition="auto",
        ))
        fig_mtc.add_trace(go.Bar(
            name=f"Scenario (+{uplift_val:.0f}%)",
            x=["Months to Clear"],
            y=[sim_mtc_val],
            marker_color="#2563eb",
            text=[f"{sim_res['simulated_months_to_clear']:.2f} m" if not np.isinf(sim_res['simulated_months_to_clear']) else "∞"],
            textposition="auto",
        ))

        # Add 3.0-month reference line
        fig_mtc.add_hline(
            y=3.0,
            line_dash="dash",
            line_color="#dc2626",
            annotation_text="3.0m Threshold (R5)",
            annotation_position="top left",
        )

        fig_mtc.update_layout(
            barmode="group",
            template="simple_white",
            height=280,
            margin=dict(l=10, r=10, t=25, b=25),
            yaxis_title="Months to Clear",
            legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
            font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI", size=11, color="#0f172a"),
        )
        st.plotly_chart(fig_mtc, use_container_width=True)

    with col_chart_dep:
        st.markdown('<div class="content-box-title">Projected Inventory Depletion Trajectory</div>', unsafe_allow_html=True)
        st.caption("Forecasts warehouse stock depletion over time under Current Pace vs Simulated Uplift Pace.")

        dep_df = pd.DataFrame(sim_res["depletion_schedule"])
        fig_dep = go.Figure()
        fig_dep.add_trace(go.Scatter(
            x=dep_df["Month"],
            y=dep_df["Current Pace Stock"],
            mode="lines+markers",
            name="Current Pace",
            line=dict(color="#64748b", width=2.5, dash="dot"),
        ))
        fig_dep.add_trace(go.Scatter(
            x=dep_df["Month"],
            y=dep_df["Simulated Pace Stock"],
            mode="lines+markers",
            name=f"Scenario Pace (+{uplift_val:.0f}%)",
            line=dict(color="#059669", width=3),
        ))

        fig_dep.update_layout(
            template="simple_white",
            height=280,
            margin=dict(l=10, r=10, t=25, b=25),
            xaxis_title="Timeline (Months)",
            yaxis_title="Warehouse Stock Units",
            legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
            font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI", size=11, color="#0f172a"),
        )
        st.plotly_chart(fig_dep, use_container_width=True)

    # Portfolio-Wide Scenario Impact Expander
    with st.expander(f"🌐 Portfolio-Wide Impact of {uplift_val:+.0f}% Sales Uplift across all Push Items", expanded=False):
        port_sim = simulate_portfolio_uplift(items, uplift_val)
        p_summary = port_sim["summary"]
        p_df = port_sim["simulated_items"]

        c_ps1, c_ps2, c_ps3, c_ps4 = st.columns(4)
        c_ps1.metric("Current Push SKUs", f"{p_summary['current_push_count']} SKUs")
        c_ps2.metric("Simulated Push SKUs", f"{p_summary['simulated_push_count']} SKUs")
        c_ps3.metric("Push SKUs Cleared to No Action", f"{p_summary['push_cleared_to_noaction']} SKUs", delta=f"-{p_summary['push_cleared_to_noaction']}")
        c_ps4.metric("Additional Monthly Capital Liquidated", f"₹{p_summary['total_additional_monthly_capital']:,.0f}/mo")

        # Show table of Push items that benefit
        push_benefits = p_df[p_df["Current Class"] == "Push"].copy()
        push_benefits["Current MTC"] = push_benefits["Current MTC"].round(2)
        push_benefits["Simulated MTC"] = push_benefits["Simulated MTC"].round(2)
        push_benefits["Runway Saved (m)"] = push_benefits["Runway Saved (m)"].round(2)
        push_benefits["Additional Monthly Capital"] = push_benefits["Additional Monthly Capital"].apply(lambda v: f"₹{v:,.0f}")
        push_benefits["Aged Value"] = push_benefits["Aged Value"].apply(lambda v: f"₹{v:,.0f}")

        st.dataframe(
            push_benefits[["SKU", "Item Name", "Category", "Current Class", "Simulated Status", "Current MTC", "Simulated MTC", "Runway Saved (m)", "Additional Monthly Capital", "Aged Value"]],
            use_container_width=True,
            hide_index=True,
        )



# ==============================================================================
# TAB 3: SALES ACTION CENTER
# ==============================================================================
with tab3:
    ranked_push = analysis.get("ranked_push_table")
    if ranked_push is None or ranked_push.empty:
        ranked_push = get_ranked_push_table(items, sales_trends=analysis.get("sales_trends"))

    # Consolidated Cross-Portfolio Sales Action Table (reused from precomputed session state)
    sales_action_raw = r.get("sales_action_table")
    if sales_action_raw is None or sales_action_raw.empty:
        sales_action_raw = build_sales_action_table(
            items, targets, sales_trends=analysis.get("sales_trends")
        )
        r["sales_action_table"] = sales_action_raw

    # 1. Mission Callout Banner: "Who should the salesperson call today and what should they sell?"
    st.markdown(_clean_html_block("""
    <div style="background-color: #f0f7ff; border: 1px solid #bfdbfe; border-left: 5px solid #2563eb; border-radius: 6px; padding: 0.95rem 1.25rem; margin-bottom: 1.15rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.35rem;">
            <div style="font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #1e3a8a;">
                Dedicated Sales Action Center &bull; Daily Outbound Priority Queue
            </div>
            <span style="font-size: 0.72rem; font-weight: 600; color: #1e3a8a; background: #dbeafe; border: 1px solid #bfdbfe; padding: 0.2rem 0.55rem; border-radius: 4px;">
                Commercial Execution Matrix
            </span>
        </div>
        <div style="font-size: 1.25rem; font-weight: 800; color: #0f294a; line-height: 1.3;">
            "Who should the salesperson call today and what should they sell?"
        </div>
        <div style="font-size: 0.86rem; color: #334155; margin-top: 0.35rem; line-height: 1.5;">
            Actionable slow-stock liquidation ledger matching high-spend commercial accounts (&gt; ₹100,000 spend) to prioritized Push slow-stock items. Filter by SKU, Category, Priority, Risk Level, Bucket, Industry, or Customer ID, sort by Priority Score, and review clear action recommendations.
        </div>
    </div>
    """), unsafe_allow_html=True)

    if sales_action_raw.empty:
        st.info("No actionable Push items or customer targets were identified in this review cycle. All catalog items are currently classified as either No Action or Red List.")
    else:
        tot_opps = len(sales_action_raw)
        tot_push_skus = len(sales_action_raw["SKU"].unique())
        tot_push_aged = float(sales_action_raw.drop_duplicates("SKU")["Aged Value"].sum())
        b1_opps = int((sales_action_raw["Bucket Number"] == 1).sum())
        b2_opps = int((sales_action_raw["Bucket Number"] == 2).sum())
        b3_opps = int((sales_action_raw["Bucket Number"] == 3).sum())

        st.markdown(_clean_html_block(f"""
        <div class="metric-row" style="margin-bottom: 1.15rem;">
            <div class="metric-col">
                <div class="metric-col-label">Total Call Opportunities</div>
                <div class="metric-col-val" style="color: #0f294a;">{tot_opps}</div>
                <div style="font-size: 0.78rem; color: #64748b;">Pre-qualified customer-SKU pairs</div>
            </div>
            <div class="metric-col">
                <div class="metric-col-label">Actionable Push SKUs</div>
                <div class="metric-col-val" style="color: #2563eb;">{tot_push_skus}</div>
                <div style="font-size: 0.78rem; color: #64748b;">Active items requiring sales push</div>
            </div>
            <div class="metric-col">
                <div class="metric-col-label">Push Aged Capital</div>
                <div class="metric-col-val" style="color: #b91c1c;">₹{tot_push_aged:,.0f}</div>
                <div style="font-size: 0.78rem; color: #64748b;">Tied-up aged inventory to liquidate</div>
            </div>
            <div class="metric-col">
                <div class="metric-col-label">Bucket 1 (Repeat Buyers)</div>
                <div class="metric-col-val" style="color: #1e3a8a;">{b1_opps}</div>
                <div style="font-size: 0.78rem; color: #64748b;">Highest conversion probability</div>
            </div>
            <div class="metric-col">
                <div class="metric-col-label">Bucket 2 (Similar Business)</div>
                <div class="metric-col-val" style="color: #2563eb;">{b2_opps}</div>
                <div style="font-size: 0.78rem; color: #64748b;">Sector-matched eligible accounts</div>
            </div>
            <div class="metric-col">
                <div class="metric-col-label">Bucket 3 (Same Category)</div>
                <div class="metric-col-val" style="color: #0369a1;">{b3_opps}</div>
                <div style="font-size: 0.78rem; color: #64748b;">Category cross-sell targets</div>
            </div>
        </div>
        """), unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # 7 FILTERS AND SORTING CONTROLS
        # ----------------------------------------------------------------------
        st.markdown('<div class="content-box-title">Filters &amp; Prioritization Controls</div>', unsafe_allow_html=True)
        st.caption("Apply filters across product attributes and customer segments. Sort by Priority Score to concentrate on the most urgent liquidation opportunities.")

        fcol1, fcol2, fcol3, fcol4 = st.columns(4)
        unique_skus = ["All SKUs"] + sorted(sales_action_raw["SKU"].unique().tolist())
        selected_filter_sku = fcol1.selectbox("Filter SKU", unique_skus, index=0, key="sa_filter_sku")

        unique_cats = ["All Categories"] + sorted(sales_action_raw["Category"].unique().tolist())
        selected_filter_cat = fcol2.selectbox("Filter Category", unique_cats, index=0, key="sa_filter_cat")

        priority_opts = ["All Priorities", "Critical", "High", "Medium", "Low"]
        selected_filter_pri = fcol3.selectbox("Filter Priority", priority_opts, index=0, key="sa_filter_pri")

        risk_opts = ["All Risk Levels", "Critical", "High", "Medium", "Low"]
        selected_filter_risk = fcol4.selectbox("Filter Risk Level", risk_opts, index=0, key="sa_filter_risk")

        fcol5, fcol6, fcol7, fcol8 = st.columns(4)
        bucket_opts = [
            "All Buckets",
            "Bucket 1 (Bought Before)",
            "Bucket 2 (Similar Business)",
            "Bucket 3 (Same Category)"
        ]
        selected_filter_bucket = fcol5.selectbox("Filter Customer Bucket", bucket_opts, index=0, key="sa_filter_bucket")

        all_ind = sorted([str(i) for i in sales_action_raw["Customer Industry"].unique() if str(i) not in ["Unassigned", "nan", "None", ""]])
        ind_opts = ["All Industries"] + all_ind + (["Unassigned"] if "Unassigned" in sales_action_raw["Customer Industry"].values else [])
        selected_filter_ind = fcol6.selectbox("Filter Industry", ind_opts, index=0, key="sa_filter_ind")

        cust_id_map = sales_action_raw.drop_duplicates("Customer ID").set_index("Customer ID")["Customer Name"].to_dict()
        cust_choices = ["All Customers"] + [f"{cid} — {cust_id_map.get(cid, cid)}" for cid in sorted(cust_id_map.keys())]
        selected_filter_cust_label = fcol7.selectbox("Filter Customer ID", cust_choices, index=0, key="sa_filter_cust")
        selected_filter_cust = selected_filter_cust_label.split(" — ")[0] if selected_filter_cust_label != "All Customers" else None

        sort_options = [
            "Priority Score (High to Low)",
            "Opportunity Score (High to Low)",
            "Aged Value (High to Low)",
            "6M Purchase Value (High to Low)",
            "Bucket (Bucket 1 → 2 → 3)",
            "Months to Clear (High to Low)",
        ]
        selected_sort = fcol8.selectbox("Sort Table By", sort_options, index=0, key="sa_sort_by")

        # Apply 7 filters
        filtered_action_df = filter_sales_action_table(
            sales_action_raw,
            sku=selected_filter_sku,
            category=selected_filter_cat,
            priority=selected_filter_pri,
            risk_level=selected_filter_risk,
            customer_bucket=selected_filter_bucket,
            industry=selected_filter_ind,
            customer_id=selected_filter_cust,
        )

        # Apply sorting
        sorted_action_df = sort_sales_action_table(
            filtered_action_df,
            sort_by=selected_sort,
            ascending=False,
        )

        st.markdown("<div style='margin-top: 0.65rem;'></div>", unsafe_allow_html=True)

        # Action Summary Bar & Export Sales Action List Button
        bar_col1, bar_col2 = st.columns([2.6, 1.4])
        with bar_col1:
            st.markdown(_clean_html_block(f"""
            <div style="font-size: 0.92rem; color: #1e293b; padding-top: 0.45rem;">
                Showing <strong>{len(sorted_action_df)}</strong> of <strong>{tot_opps}</strong> actionable call opportunities matching active filters.
            </div>
            """), unsafe_allow_html=True)

        with bar_col2:
            sa_cache_key = f"sa_excel_{len(sorted_action_df)}_{hash(tuple(sorted_action_df['Customer ID'].values[:10])) if not sorted_action_df.empty else 0}"
            if st.session_state.get("sa_excel_key") != sa_cache_key or "sa_excel_data" not in st.session_state:
                st.session_state["sa_excel_data"] = export_sales_action_excel(sorted_action_df)
                st.session_state["sa_excel_key"] = sa_cache_key
            excel_data = st.session_state["sa_excel_data"]
            st.download_button(
                label="📥 Export Sales Action List",
                data=excel_data,
                file_name=f"CompanyX_Sales_Action_List_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_export_sales_action_list",
                type="primary",
                use_container_width=True,
            )

        # ----------------------------------------------------------------------
        # SALES ACTION TABLE
        # ----------------------------------------------------------------------
        if sorted_action_df.empty:
            st.warning("⚠️ No customer-SKU opportunities match the selected filter criteria. Adjust or reset your filters above.")
        else:
            table_display_cols = [
                "Priority",
                "SKU",
                "Item Description",
                "Customer ID",
                "Customer Industry",
                "Bucket",
                "6M Purchase Value",
                "Opportunity Score",
                "Aged Value",
                "Months to Clear",
                "Recommended Action",
                "Reason",
            ]
            action_table_view = sorted_action_df[table_display_cols].copy()

            st.dataframe(
                action_table_view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Priority": st.column_config.TextColumn("Priority", width="small", help="SKU Liquidation Priority Tier (sorted by Priority Score)"),
                    "SKU": st.column_config.TextColumn("SKU", width="small"),
                    "Item Description": st.column_config.TextColumn("Item Description", width="medium"),
                    "Customer ID": st.column_config.TextColumn("Customer ID", width="small"),
                    "Customer Industry": st.column_config.TextColumn("Customer Industry", width="medium"),
                    "Bucket": st.column_config.NumberColumn("Bucket", format="Bucket %d", width="small"),
                    "6M Purchase Value": st.column_config.NumberColumn("6M Purchase Value", format="₹%,.0f"),
                    "Opportunity Score": st.column_config.NumberColumn("Opportunity Score", format="%d / 100"),
                    "Aged Value": st.column_config.NumberColumn("Aged Value", format="₹%,.0f"),
                    "Months to Clear": st.column_config.NumberColumn("Months to Clear", format="%.1f m"),
                    "Recommended Action": st.column_config.TextColumn("Recommended Action", width="large"),
                    "Reason": st.column_config.TextColumn("Reason", width="medium"),
                }
            )

        st.divider()

    st.markdown('<div class="content-box-title">Ranked Push SKU Sales Prioritization Table</div>', unsafe_allow_html=True)
    st.caption("Deterministic 0–100 Sales Priority Score ranking which Push items commercial reps should work on first based on aged capital, months to clear, sales trend, velocity, and inventory risk.")

    if ranked_push.empty:
        st.info("No Push items were identified in this review cycle. Proactive customer targeting is only performed for slow-moving items requiring sales liquidation (Class == 'Push'). All catalog items are currently classified as either No Action or Red List.")
    else:
        # Display the Ranked Push SKU Table matching exact specifications
        display_ranked = ranked_push.copy()
        if "Aged Value" in display_ranked.columns:
            display_ranked["Aged Value"] = display_ranked["Aged Value"].apply(lambda v: f"₹{v:,.0f}")
        if "Months to Clear" in display_ranked.columns:
            display_ranked["Months to Clear"] = display_ranked["Months to Clear"].apply(
                lambda m: "∞" if (m == float("inf") or np.isinf(m)) else f"{m:.2f}"
            )
        if "Priority Score" in display_ranked.columns:
            display_ranked["Priority Score"] = display_ranked["Priority Score"].apply(lambda s: f"{s} / 100")

        spec_cols = [
            "Rank", "SKU", "Description", "Category",
            "Aged Value", "Months to Clear", "Sales Trend",
            "Risk Score", "Priority Score", "Priority Level", "Why Priority", "Recommended Action"
        ]
        avail_spec_cols = [c for c in spec_cols if c in display_ranked.columns]
        st.dataframe(display_ranked[avail_spec_cols], use_container_width=True, hide_index=True)

        st.divider()
        st.markdown('<div class="content-box-title">Targeted Account Recommendations &amp; Call Lists</div>', unsafe_allow_html=True)
        st.caption("Prioritized call lists based on historical purchases (Bucket 1), industry affinity (Bucket 2), and category purchases (Bucket 3).")

        ranked_push_dedup = ranked_push.drop_duplicates(subset=["SKU"])
        push_skus = ranked_push_dedup["SKU"].tolist()
        push_lookup = items.drop_duplicates(subset=["SKU"]).set_index("SKU") if not items.empty else pd.DataFrame()

        def _format_push_sku_option(s):
            try:
                row = push_lookup.loc[s]
                rank = int(row['Priority Rank']) if ('Priority Rank' in row and pd.notna(row['Priority Rank'])) else 1
                name = str(row.get('Item Name', s))
                score = int(row['Priority Score']) if ('Priority Score' in row and pd.notna(row['Priority Score'])) else 0
                lvl = str(row.get('Priority Level', 'Medium'))
                aged = float(row['Aged Value']) if ('Aged Value' in row and pd.notna(row['Aged Value'])) else 0.0
                return f"Rank #{rank}: {s} — {name} [{score}/100 {lvl}] (Aged: ₹{aged:,.0f})"
            except Exception:
                return str(s)

        selected_sku = st.selectbox(
            "Select Push SKU to Inspect Customer Call Lists",
            push_skus,
            index=0,
            format_func=_format_push_sku_option
        )

        item_row = push_lookup.loc[selected_sku] if selected_sku in push_lookup.index else ranked_push_dedup.iloc[0]
        sku_risk_score = int(item_row["Risk Score"]) if ("Risk Score" in item_row and pd.notna(item_row["Risk Score"])) else 0
        sku_risk_lvl = str(item_row.get("Risk Level", "Medium")) if "Risk Level" in item_row else "Medium"
        sku_risk_expl = str(item_row.get("Risk Explanation", "")) if "Risk Explanation" in item_row else ""
        sku_p_score = int(item_row["Priority Score"]) if ("Priority Score" in item_row and pd.notna(item_row["Priority Score"])) else 0
        sku_p_lvl = str(item_row.get("Priority Level", "Medium")) if "Priority Level" in item_row else "Medium"
        sku_p_rank = int(item_row["Priority Rank"]) if ("Priority Rank" in item_row and pd.notna(item_row["Priority Rank"])) else 1
        sku_why_priority = str(item_row.get("Why Priority", "")) if "Why Priority" in item_row else ""

        risk_color_map = {
            "Critical": "#dc2626",
            "High": "#ea580c",
            "Medium": "#ca8a04",
            "Low": "#16a34a"
        }
        badge_color = risk_color_map.get(sku_risk_lvl, "#ca8a04")

        pri_color_map = {
            "Critical": "#dc2626",
            "High": "#7c3aed",
            "Medium": "#2563eb",
            "Low": "#16a34a"
        }
        p_badge_color = pri_color_map.get(sku_p_lvl, "#7c3aed")

        mtc_raw_val = item_row.get("Months to Clear")
        if mtc_raw_val == float("inf") or np.isinf(mtc_raw_val):
            sku_mtc_display = "∞ (Cannot clear)"
        else:
            sku_mtc_display = f"{float(mtc_raw_val):.2f} mths"

        # Item Summary Card with Risk Score and Sales Priority Score
        st.markdown(_clean_html_block(f"""
<div class="metric-row">
    <div class="metric-col">
        <div class="metric-col-label">Selected SKU</div>
        <div class="metric-col-val">{selected_sku}</div>
        <div style="font-size: 0.8rem; color: #475569;">{item_row['Item Name']}</div>
    </div>
    <div class="metric-col">
        <div class="metric-col-label">Aged Value</div>
        <div class="metric-col-val" style="color: #2563eb;">₹{item_row['Aged Value']:,.0f}</div>
        <div style="font-size: 0.8rem; color: #64748b;">Unit Cost: ₹{item_row['Unit Cost (Rs)']}</div>
    </div>
    <div class="metric-col">
        <div class="metric-col-label">Months to Clear</div>
        <div class="metric-col-val">{sku_mtc_display}</div>
        <div style="font-size: 0.8rem; color: #64748b;">Total Stock: {item_row['Total Stock']:,.0f}</div>
    </div>
    <div class="metric-col">
        <div class="metric-col-label">Sales Trend</div>
        <div class="metric-col-val" style="color: #0f294a;">{item_row.get('Sales Trend', 'Stable')}</div>
        <div style="font-size: 0.8rem; color: #64748b;">Growth: {item_row.get('Sales Growth %', 0):+.1f}%</div>
    </div>
    <div class="metric-col" style="border-left: 4px solid {badge_color};">
        <div class="metric-col-label" style="color: {badge_color};">Risk Assessment</div>
        <div class="metric-col-val" style="color: {badge_color};">{sku_risk_score} <span style="font-size: 0.85rem; font-weight: 600;">/ 100</span></div>
        <div style="font-size: 0.8rem; font-weight: 600; color: {badge_color};">{sku_risk_lvl} Risk</div>
    </div>
    <div class="metric-col" style="border-left: 4px solid {p_badge_color};">
        <div class="metric-col-label" style="color: {p_badge_color};">Sales Priority</div>
        <div class="metric-col-val" style="color: {p_badge_color};">{sku_p_score} <span style="font-size: 0.85rem; font-weight: 600;">/ 100</span></div>
        <div style="font-size: 0.8rem; font-weight: 600; color: {p_badge_color};">Rank #{sku_p_rank} &bull; {sku_p_lvl}</div>
    </div>
</div>
<div style="background-color: #f5f3ff; border: 1px solid #ddd6fe; border-left: 4px solid {p_badge_color}; padding: 0.65rem 1rem; border-radius: 4px; margin-bottom: 0.75rem; font-size: 0.88rem; color: #1e1b4b;">
    <strong>Why Priority?</strong> {sku_why_priority}
</div>
<div style="background-color: #f8fafc; border-left: 4px solid {badge_color}; padding: 0.55rem 1rem; border-radius: 4px; margin-bottom: 1.15rem; font-size: 0.86rem; color: #1e293b;">
    <strong>Risk Driver Insight:</strong> {sku_risk_expl}
</div>
"""), unsafe_allow_html=True)

        with st.expander("🔍 WHY THIS ITEM IS CLASSIFIED THIS WAY (Explainability Panel)", expanded=True):
            render_explainability_panel(item_row, sku_code=selected_sku)

        target_df = targets.get(selected_sku, pd.DataFrame()).copy()

        if target_df.empty:
            st.info(
                f"No eligible customer accounts qualify for {selected_sku}. "
                "Rule R6 requires accounts to have total 6-month purchases exceeding ₹100,000 "
                "to qualify for outbound push campaigns across Buckets 1, 2, or 3."
            )
        else:
            b1_count = int((target_df["Bucket"] == 1).sum()) if "Bucket" in target_df.columns else 0
            b2_count = int((target_df["Bucket"] == 2).sum()) if "Bucket" in target_df.columns else 0
            b3_count = int((target_df["Bucket"] == 3).sum()) if "Bucket" in target_df.columns else 0

            st.markdown(_clean_html_block(f"""
<div style="font-size: 0.85rem; color: #475569; margin-bottom: 0.75rem;">
<strong>{len(target_df)} target account(s) found:</strong> &nbsp;
<span style="color: #1e3a8a; font-weight: 600;">{b1_count} in Bucket 1 (Bought Before)</span> &bull; 
<span style="color: #2563eb; font-weight: 600;">{b2_count} in Bucket 2 (Similar Business)</span> &bull; 
<span style="color: #0369a1; font-weight: 600;">{b3_count} in Bucket 3 (Same Category)</span>
</div>
"""), unsafe_allow_html=True)

            col_mode, col_info = st.columns([1.6, 2.4])
            display_mode = col_mode.radio(
                "Display Format",
                ["Responsive (Auto)", "Desktop Table", "Mobile Action Cards"],
                horizontal=True,
                help="Responsive (Auto) renders full table on desktop screens and automatically switches to compact cards on mobile screen widths (≤ 768px)."
            )

            def _build_desktop_table_html(df):
                rows_html = []
                for _, row in df.iterrows():
                    b_num = int(row["Bucket"])
                    b_badge = f"bucket-badge-{b_num}"
                    bucket_str = row['Bucket Name'] if row['Bucket Name'].startswith("Bucket") else f"Bucket {row['Bucket Name']}"
                    opp_score = int(row.get("Opportunity Score", 0))
                    opp_level = str(row.get("Opportunity Level", "Developing"))
                    if opp_score >= 80:
                        opp_color = "#059669"
                        opp_bg = "#ecfdf5"
                        opp_bdr = "#a7f3d0"
                    elif opp_score >= 60:
                        opp_color = "#2563eb"
                        opp_bg = "#eff6ff"
                        opp_bdr = "#bfdbfe"
                    elif opp_score >= 40:
                        opp_color = "#d97706"
                        opp_bg = "#fffbeb"
                        opp_bdr = "#fde68a"
                    else:
                        opp_color = "#64748b"
                        opp_bg = "#f8fafc"
                        opp_bdr = "#e2e8f0"

                    evidence = str(row.get("Relevant Purchase Evidence", ""))
                    reason = str(row.get("Reason", ""))

                    rows_html.append(f"""
<tr>
<td style="text-align: center;"><span class="priority-pill">Priority {row['Priority']}</span></td>
<td>
<strong>{row['CustomerName']}</strong><br>
<code style="font-size: 0.78rem;">{row['CustomerID']}</code>
</td>
<td><span class="bucket-badge {b_badge}">{bucket_str}</span></td>
<td style="text-align: center;">
<span style="display: inline-block; padding: 0.2rem 0.5rem; background: {opp_bg}; color: {opp_color}; border: 1px solid {opp_bdr}; border-radius: 4px; font-weight: 700; font-size: 0.8rem; white-space: nowrap;">
{opp_score} / 100
</span><br>
<span style="font-size: 0.72rem; color: {opp_color}; font-weight: 600;">{opp_level}</span>
</td>
<td style="text-align: right; font-weight: 700; color: #1e3a8a; white-space: nowrap;">₹{row['6M Purchase Value']:,.0f}</td>
<td>
<div>{row['Industry'] or 'Unassigned'}</div>
<div style="font-size: 0.74rem; color: #64748b;">{row['Area'] or 'Standard'}</div>
</td>
<td style="font-size: 0.82rem; color: #334155; line-height: 1.35; max-width: 280px;">
{evidence}
</td>
<td style="font-size: 0.82rem; color: #475569; line-height: 1.35; max-width: 260px; font-style: italic;">
{reason}
</td>
</tr>
""")
                table_html = f"""
<div style="overflow-x: auto; width: 100%;">
<table class="styled-action-table">
<thead>
<tr>
<th style="text-align: center; width: 85px;">Priority</th>
<th style="width: 140px;">Customer</th>
<th style="width: 130px;">Bucket</th>
<th style="text-align: center; width: 110px;">Opportunity</th>
<th style="text-align: right; width: 125px;">6M Spend</th>
<th style="width: 110px;">Industry / Area</th>
<th style="width: 280px;">Relevant Purchase Evidence</th>
<th style="width: 260px;">Why This Customer?</th>
</tr>
</thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</div>
"""
                return _clean_html_block(table_html)

            def _build_mobile_cards_html(df):
                cards_html = []
                for _, row in df.iterrows():
                    b_num = int(row["Bucket"])
                    pill_class = f"mobile-bucket-{b_num}-pill"
                    bucket_str = row['Bucket Name'] if row['Bucket Name'].startswith("Bucket") else f"Bucket {row['Bucket Name']}"
                    opp_score = int(row.get("Opportunity Score", 0))
                    opp_level = str(row.get("Opportunity Level", "Developing"))
                    if opp_score >= 80:
                        opp_color = "#059669"
                        opp_bg = "#ecfdf5"
                        opp_bdr = "#a7f3d0"
                    elif opp_score >= 60:
                        opp_color = "#2563eb"
                        opp_bg = "#eff6ff"
                        opp_bdr = "#bfdbfe"
                    elif opp_score >= 40:
                        opp_color = "#d97706"
                        opp_bg = "#fffbeb"
                        opp_bdr = "#fde68a"
                    else:
                        opp_color = "#64748b"
                        opp_bg = "#f8fafc"
                        opp_bdr = "#e2e8f0"

                    evidence = str(row.get("Relevant Purchase Evidence", ""))
                    reason = str(row.get("Reason", ""))

                    cards_html.append(f"""
<div class="mobile-action-card bucket-{b_num}">
<div class="mobile-card-top">
<span class="mobile-priority-badge">Priority {row['Priority']}</span>
<span style="font-size: 0.74rem; font-weight: 700; background: {opp_bg}; color: {opp_color}; border: 1px solid {opp_bdr}; padding: 0.15rem 0.5rem; border-radius: 4px;">
Opp Score: {opp_score}/100 &bull; {opp_level}
</span>
<span class="mobile-bucket-title {pill_class}">{bucket_str}</span>
</div>
<div class="mobile-customer-name">
{row['CustomerName']}
<span class="mobile-customer-id">({row['CustomerID']})</span>
</div>
<div class="mobile-card-details">
<div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem;">
<span><strong>Industry:</strong> {row['Industry'] or 'Unassigned'}</span>
<span><strong>Area:</strong> {row['Area'] or 'Standard'}</span>
</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.35rem; padding-top: 0.35rem; border-top: 1px dashed #e2e8f0;">
<span style="font-weight: 600; color: #475569;">6M Purchase Value:</span>
<span class="mobile-spend-value">₹{row['6M Purchase Value']:,.0f}</span>
</div>
<div style="margin-top: 0.45rem; padding-top: 0.45rem; border-top: 1px solid #f1f5f9; font-size: 0.78rem;">
<div style="color: #1e3a8a; margin-bottom: 0.25rem;">
<strong>Evidence:</strong> {evidence}
</div>
<div style="color: #475569; font-style: italic;">
<strong>Why this customer:</strong> {reason}
</div>
</div>
</div>
</div>
""")
                cards_wrapper = f"""
<div class="mobile-cards-wrapper">
{''.join(cards_html)}
</div>
"""
                return _clean_html_block(cards_wrapper)

            if display_mode == "Responsive (Auto)":
                st.caption("Auto-adapts layout: renders full data table on desktop and compact action cards on mobile devices (width ≤ 768px).")
                responsive_html = f"""
<div class="sales-desktop-container">
{_build_desktop_table_html(target_df)}
</div>
<div class="sales-mobile-container">
{_build_mobile_cards_html(target_df)}
</div>
"""
                st.markdown(_clean_html_block(responsive_html), unsafe_allow_html=True)
            elif display_mode == "Desktop Table":
                st.caption("Displaying full customer table for desktop view.")
                st.markdown(_clean_html_block(_build_desktop_table_html(target_df)), unsafe_allow_html=True)
            else:
                st.caption("Displaying mobile-optimized compact action cards (no horizontal scrolling required).")
                st.markdown(_clean_html_block(_build_mobile_cards_html(target_df)), unsafe_allow_html=True)

            # ------------------------------------------------------------------
            # OPTIONAL AI SALES MESSAGE GENERATOR
            # ------------------------------------------------------------------
            st.divider()
            st.markdown('<div class="content-box-title">AI Sales Message Generator (Optional)</div>', unsafe_allow_html=True)
            st.caption(
                "Generate grounded, draft sales communications based strictly on 8 controlled application parameters: "
                "SKU, Customer, Customer Industry, Purchase History, Bucket, Aged Inventory, Recommended Action, and Relevant Sales Evidence. "
                "AI is constrained from inventing prices, discounts, quantities, delivery dates, product specs, or customer needs."
            )

            # Customer selection for communication suite
            cust_choices = [
                f"{row['CustomerID']} — {row['CustomerName']} (Priority {row['Priority']}, Bucket {row['Bucket']})"
                for _, row in target_df.iterrows()
            ]
            cust_map = {
                f"{row['CustomerID']} — {row['CustomerName']} (Priority {row['Priority']}, Bucket {row['Bucket']})": row
                for _, row in target_df.iterrows()
            }

            sel_cust_label = st.selectbox(
                "Select Target Account to Generate Draft Sales Communication",
                cust_choices,
                key="ai_sales_suite_cust_select",
            )
            sel_cust_row = cust_map[sel_cust_label]

            # Extract the 8 selected grounding fields
            ctx_sku = f"{selected_sku} — {item_row['Item Name']}"
            ctx_customer = f"{sel_cust_row['CustomerID']} — {sel_cust_row['CustomerName']}"
            ctx_industry = str(sel_cust_row.get("Industry", "Unassigned"))
            if ctx_industry in ["", "nan", "None", "NA"]:
                ctx_industry = "Unassigned"
            ctx_spend = float(sel_cust_row.get("6M Purchase Value", 0.0))
            ctx_purchase_history = f"₹{ctx_spend:,.0f} across 6 months"
            ctx_bucket = int(sel_cust_row["Bucket"])
            ctx_bucket_desc = f"Bucket {ctx_bucket} ({sel_cust_row.get('Bucket Name', 'Qualified Target')})"
            ctx_aged_val = float(item_row.get("Aged Value", 0.0))
            ctx_aged_inventory = f"₹{ctx_aged_val:,.0f} (91+ days aged stock)"
            ctx_action = str(sel_cust_row.get("Recommended Action", ""))
            if not ctx_action:
                ctx_action = f"Contact {sel_cust_row['CustomerName']} and promote {selected_sku}."
            ctx_evidence = str(sel_cust_row.get("Evidence", sel_cust_row.get("Relevant Purchase Evidence", "")))
            if not ctx_evidence:
                ctx_evidence = f"Account spend of ₹{ctx_spend:,.0f} qualifies for {ctx_bucket_desc}."

            # Executive Context Card showing the 8 selected parameters
            st.markdown(_clean_html_block(f"""
            <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #1e3a8a; border-radius: 6px; padding: 0.9rem 1.15rem; margin: 0.75rem 0 1rem 0;">
                <div style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #1e3a8a; margin-bottom: 0.5rem;">
                    Selected Context Parameters (Strict Grounding Source)
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 0.45rem 1rem; font-size: 0.82rem; color: #1e293b;">
                    <div><span style="color: #64748b;">1. SKU:</span> <strong>{ctx_sku}</strong></div>
                    <div><span style="color: #64748b;">2. Customer:</span> <strong>{ctx_customer}</strong></div>
                    <div><span style="color: #64748b;">3. Customer Industry:</span> <strong>{ctx_industry}</strong></div>
                    <div><span style="color: #64748b;">4. Purchase History:</span> <strong>{ctx_purchase_history}</strong></div>
                    <div><span style="color: #64748b;">5. Bucket:</span> <strong>{ctx_bucket_desc}</strong></div>
                    <div><span style="color: #64748b;">6. Aged Inventory:</span> <strong>{ctx_aged_inventory}</strong></div>
                    <div style="grid-column: 1 / -1;"><span style="color: #64748b;">7. Recommended Action:</span> <strong>{ctx_action}</strong></div>
                    <div style="grid-column: 1 / -1;"><span style="color: #64748b;">8. Relevant Sales Evidence:</span> <em>{ctx_evidence}</em></div>
                </div>
            </div>
            """), unsafe_allow_html=True)

            btn_col1, btn_col2 = st.columns([2, 1])
            with btn_col1:
                btn_draft_suite = st.button(
                    "⚡ Generate AI Sales Communication Suite",
                    type="primary",
                    use_container_width=True,
                    key="btn_generate_sales_suite",
                )
            with btn_col2:
                btn_reset = st.button("🔄 Reset Draft", use_container_width=True, key="btn_reset_sales_suite")
                if btn_reset:
                    st.session_state.pop("sales_suite_draft", None)
                    st.session_state.pop("sales_suite_for", None)

            suite_key = f"{selected_sku}_{sel_cust_row['CustomerID']}"

            if btn_draft_suite:
                with st.spinner("Drafting WhatsApp message, professional email, and sales call talking points..."):
                    suite_res = generate_sales_communication_suite(
                        sku=ctx_sku,
                        customer=str(sel_cust_row["CustomerName"]),
                        customer_industry=ctx_industry,
                        purchase_history=ctx_purchase_history,
                        bucket=ctx_bucket,
                        aged_inventory=ctx_aged_inventory,
                        recommended_action=ctx_action,
                        relevant_sales_evidence=ctx_evidence,
                        api_key=st.session_state.get("ai_key_input"),
                    )
                st.session_state["sales_suite_draft"] = suite_res
                st.session_state["sales_suite_for"] = suite_key

            if st.session_state.get("sales_suite_draft") and st.session_state.get("sales_suite_for") == suite_key:
                suite_res = st.session_state["sales_suite_draft"]

                # Prominent Labels & Review Warning (Mandatory Requirement)
                st.markdown(_clean_html_block(f"""
                <div style="background-color: #fffbeb; border: 1px solid #fde68a; border-left: 5px solid #d97706; border-radius: 6px; padding: 0.85rem 1.15rem; margin-top: 0.75rem; margin-bottom: 0.95rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.25rem;">
                        <span style="background: #fef3c7; color: #92400e; font-weight: 800; padding: 0.2rem 0.65rem; border-radius: 4px; border: 1px solid #fde68a; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em;">
                            {suite_res['label']}
                        </span>
                        <span style="font-size: 0.74rem; color: #475569; background: #ffffff; border: 1px solid #cbd5e1; padding: 0.15rem 0.55rem; border-radius: 4px;">
                            Engine: {suite_res['source']}
                        </span>
                    </div>
                    <div style="font-size: 0.92rem; font-weight: 700; color: #b45309; margin-top: 0.25rem;">
                        ⚠️ {suite_res['review_warning']}
                    </div>
                    <div style="font-size: 0.78rem; color: #78350f; margin-top: 0.15rem;">
                        This communication draft was synthesized strictly from the 8 verified data fields. The salesperson must review commercial alignment prior to sending.
                    </div>
                </div>
                """), unsafe_allow_html=True)

                # 3 Required Formats in Clean Sub-tabs
                tab_wa, tab_email, tab_call = st.tabs([
                    "💬 1. Short WhatsApp Message",
                    "✉️ 2. Professional Email",
                    "📞 3. Sales Call Talking Points",
                ])

                with tab_wa:
                    st.caption("Short, friendly WhatsApp-style message inviting a brief conversation. Zero invented discounts, prices, or delivery deadlines.")
                    st.text_area(
                        "WhatsApp Message Draft (Copy & Dispatch via WhatsApp / SMS)",
                        value=suite_res["whatsapp_message"],
                        height=140,
                        key="suite_wa_text_area",
                        help="Review, customize greeting if needed, and dispatch via enterprise WhatsApp client."
                    )
                    st.caption(f"📏 Message length: {len(suite_res['whatsapp_message'])} characters")

                with tab_email:
                    st.caption("Formal commercial email for procurement officers. References account relationship, warehouse allocation status, and recommends a call.")
                    st.text_input(
                        "Email Subject Line",
                        value=suite_res["email_subject"],
                        key="suite_email_subject_input",
                        help="Subject line summarizing allocation and SKU context."
                    )
                    st.text_area(
                        "Email Body Draft (Copy & Dispatch via Outlook / Gmail)",
                        value=suite_res["email_body"],
                        height=260,
                        key="suite_email_body_area",
                        help="Professional email body grounded in verified facts."
                    )
                    st.caption("Copy-ready text: Account executives may review, adjust commercial terms if needed, and dispatch via enterprise mail.")

                with tab_call:
                    st.caption("Actionable talking points for outbound telephone calls. Guides rep on relationship facts, stock readiness, and sales objectives.")
                    st.markdown(suite_res["talking_points_formatted"])
                    with st.expander("📋 Copy Plaintext Talking Points", expanded=False):
                        st.text_area(
                            "Plaintext Call Notes",
                            value="\n".join(f"{i+1}. {pt}" for i, pt in enumerate(suite_res["talking_points"])),
                            height=150,
                            key="suite_tp_raw_area"
                        )

            # AI Usage Note (Mandatory requirement)
            st.markdown(_clean_html_block("""
            <div style="font-size: 0.8rem; color: #64748b; background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 3px solid #64748b; padding: 0.65rem 0.95rem; border-radius: 4px; margin-top: 1rem;">
                <strong>AI Usage Note:</strong> AI is used strictly and exclusively for communication drafting and outreach messaging. All inventory calculations, item classifications (Red List / No Action / Push), customer eligibility checks (> ₹100k spend), bucket assignments (Buckets 1, 2, 3), and priority rankings are computed strictly by deterministic Python/Pandas logic (Rules R1–R7) and are never determined or influenced by AI.
            </div>
            """), unsafe_allow_html=True)

            # ------------------------------------------------------------------
            # SALES OUTREACH & EXECUTION TRACKER (Item 26)
            # ------------------------------------------------------------------
            st.divider()
            st.markdown('<div class="content-box-title">📞 Commercial Outreach &amp; Sales Execution Tracker</div>', unsafe_allow_html=True)
            st.caption(
                "Operational execution log for sales reps to record outreach status, track buyer commitments, "
                "log liquidation discussions, and monitor working capital recovered in real time."
            )

            if "sales_tracker_state" not in st.session_state:
                st.session_state["sales_tracker_state"] = {}

            tracker_df = init_sales_tracker(sales_action_raw, st.session_state["sales_tracker_state"])
            tracker_kpis = calculate_sales_tracker_kpis(tracker_df)

            st.markdown(_clean_html_block(f"""
            <div class="metric-row" style="margin-bottom: 1.15rem;">
                <div class="metric-col">
                    <div class="metric-col-label">Total Outreach Leads</div>
                    <div class="metric-col-val" style="color: #0f294a;">{tracker_kpis['total_leads']}</div>
                    <div style="font-size: 0.78rem; color: #64748b;">Qualified targets tracked</div>
                </div>
                <div class="metric-col">
                    <div class="metric-col-label">Contacted / Engaged</div>
                    <div class="metric-col-val" style="color: #2563eb;">{tracker_kpis['contacted_count']}</div>
                    <div style="font-size: 0.78rem; color: #64748b;">{tracker_kpis['pending_count']} pending initial call</div>
                </div>
                <div class="metric-col">
                    <div class="metric-col-label">In Discussion / Follow-Up</div>
                    <div class="metric-col-val" style="color: #d97706;">{tracker_kpis['in_discussion_count']}</div>
                    <div style="font-size: 0.78rem; color: #64748b;">Active commercial talks</div>
                </div>
                <div class="metric-col">
                    <div class="metric-col-label">Orders Placed (Liquidated)</div>
                    <div class="metric-col-val" style="color: #16a34a;">{tracker_kpis['orders_placed_count']}</div>
                    <div style="font-size: 0.78rem; color: #64748b;">Conversion: {tracker_kpis['conversion_rate_pct']:.1f}%</div>
                </div>
                <div class="metric-col">
                    <div class="metric-col-label">Capital Liquidated</div>
                    <div class="metric-col-val" style="color: #16a34a;">₹{tracker_kpis['liquidated_value']:,.0f}</div>
                    <div style="font-size: 0.78rem; color: #64748b;">{tracker_kpis['liquidated_units']:,} units liquidated</div>
                </div>
            </div>
            """), unsafe_allow_html=True)

            with st.expander("📝 Log / Update Call Disposition", expanded=False):
                with st.form("tracker_call_log_form"):
                    lead_options = [
                        f"{r['SKU']} | {r['Customer Name']} ({r['Customer ID']}) — Bucket {r['Bucket']}"
                        for _, r in tracker_df.iterrows()
                    ]
                    lead_id_map = {
                        f"{r['SKU']} | {r['Customer Name']} ({r['Customer ID']}) — Bucket {r['Bucket']}": (r['SKU'], r['Customer ID'], r['Lead ID'])
                        for _, r in tracker_df.iterrows()
                    }
                    if lead_options:
                        sel_lead_label = st.selectbox("Select Target Lead to Update", lead_options)
                        sel_sku, sel_cid, sel_lid = lead_id_map[sel_lead_label]

                        curr_row = tracker_df[tracker_df["Lead ID"] == sel_lid].iloc[0]
                        curr_status = curr_row["Call Status"]
                        status_idx = TRACKER_STATUS_OPTIONS.index(curr_status) if curr_status in TRACKER_STATUS_OPTIONS else 0

                        c_log1, c_log2, c_log3 = st.columns(3)
                        new_status = c_log1.selectbox("Call Status", TRACKER_STATUS_OPTIONS, index=status_idx)
                        new_units = c_log2.number_input("Units Committed", min_value=0, value=int(curr_row["Units Committed"]), step=1)
                        new_value = c_log3.number_input("Value Realized (₹)", min_value=0.0, value=float(curr_row["Value Realized (Rs)"]), step=500.0)

                        new_notes = st.text_input("Sales Notes / Feedback", value=str(curr_row["Sales Rep Notes"]), placeholder="e.g., Client agreed to purchase 20 units at standard price, delivery next Monday.")

                        submitted = st.form_submit_button("💾 Save Call Log Entry", type="primary")
                        if submitted:
                            st.session_state["sales_tracker_state"][sel_lid] = {
                                "Call Status": new_status,
                                "Last Contact Date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                                "Units Committed": new_units,
                                "Value Realized (Rs)": new_value,
                                "Sales Rep Notes": new_notes,
                            }
                            st.success(f"Updated call status for {sel_lead_label} to '{new_status}'!")
                            st.rerun()

            t_col1, t_col2 = st.columns([2.5, 1.5])
            with t_col1:
                tracker_status_filter = st.selectbox(
                    "Filter Tracker by Status",
                    ["All Statuses"] + TRACKER_STATUS_OPTIONS,
                    index=0,
                    key="tracker_view_filter"
                )
            with t_col2:
                tracker_excel_bytes = export_sales_tracker_excel(tracker_df)
                st.download_button(
                    label="📥 Export Sales Tracker (Excel)",
                    data=tracker_excel_bytes,
                    file_name=f"CompanyX_Sales_Tracker_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="btn_download_sales_tracker",
                    type="secondary",
                    use_container_width=True,
                )

            view_tracker_df = tracker_df.copy()
            if tracker_status_filter != "All Statuses":
                view_tracker_df = view_tracker_df[view_tracker_df["Call Status"] == tracker_status_filter]

            tracker_display_cols = [
                "Call Status", "SKU", "Item Description", "Customer Name", "Customer ID",
                "Bucket", "Opportunity Score", "6M Purchase Value", "Units Committed",
                "Value Realized (Rs)", "Last Contact Date", "Sales Rep Notes"
            ]
            st.dataframe(
                view_tracker_df[tracker_display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Call Status": st.column_config.TextColumn("Call Status", width="medium"),
                    "SKU": st.column_config.TextColumn("SKU", width="small"),
                    "Item Description": st.column_config.TextColumn("Item Description", width="medium"),
                    "Customer Name": st.column_config.TextColumn("Customer Name", width="medium"),
                    "Customer ID": st.column_config.TextColumn("Customer ID", width="small"),
                    "Bucket": st.column_config.NumberColumn("Bucket", format="Bucket %d", width="small"),
                    "Opportunity Score": st.column_config.NumberColumn("Opportunity Score", format="%d/100", width="small"),
                    "6M Purchase Value": st.column_config.NumberColumn("6M Spend", format="₹%,.0f", width="small"),
                    "Units Committed": st.column_config.NumberColumn("Units", format="%d", width="small"),
                    "Value Realized (Rs)": st.column_config.NumberColumn("Liquidated Value", format="₹%,.0f", width="small"),
                    "Last Contact Date": st.column_config.TextColumn("Date", width="small"),
                    "Sales Rep Notes": st.column_config.TextColumn("Notes", width="large"),
                }
            )


# ==============================================================================
# TAB 4: DATA LINEAGE / AUDIT
# ==============================================================================
with tab4:
    lineage_data = r.get("lineage_data")
    if lineage_data is None:
        lineage_data = build_data_lineage(r["raw"], validation, analysis, targets)
        r["lineage_data"] = lineage_data
    lineage_stages = lineage_data["stages"]
    lineage_summary = lineage_data["summary"]
    lineage_matrix_df = lineage_data["matrix_df"]

    st.markdown('<div class="content-box-title">End-to-End Data Lineage &amp; Transformation Audit</div>', unsafe_allow_html=True)
    st.caption("Complete operational visibility showing exactly how raw input records are validated, cleansed, consolidated, classified, and synthesized into the final sales calling ledger.")

    # 1. Auditor & Governance Assurance Callout
    st.markdown(_clean_html_block("""
    <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 5px solid #0f294a; border-radius: 6px; padding: 0.95rem 1.25rem; margin-bottom: 1.15rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.35rem;">
            <div style="font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #0f294a;">
                Deterministic Pipeline Audit &bull; Complete Transformation Traceability
            </div>
            <span style="font-size: 0.72rem; font-weight: 700; color: #0369a1; background: #e0f2fe; border: 1px solid #bae6fd; padding: 0.2rem 0.55rem; border-radius: 4px;">
                12-Stage Deterministic Flow &mdash; Rules R1–R7 Invariant
            </span>
        </div>
        <div style="font-size: 0.86rem; color: #334155; line-height: 1.55;">
            <strong>Data Lineage Guarantee:</strong> Every operational output in this system is computed strictly through deterministic business logic (Rules R1–R7) with zero artificial intelligence or black-box overrides. This page provides full auditability of all 12 transformation stages, documenting record counts, data hygiene purges, pack consolidations, customer eligibility filters, risk scoring, and sales queue prioritization.
        </div>
    </div>
    """), unsafe_allow_html=True)

    # 2. Executive Audit Metric Cards
    st.markdown(_clean_html_block(f"""
    <div class="kpi-grid" style="margin-bottom: 1.35rem;">
        <div class="kpi-card" style="border-top: 3px solid #0f294a; background-color: #ffffff;">
            <div class="kpi-label">Raw Records Ingested</div>
            <div class="kpi-number" style="color: #0f294a;">{lineage_summary['total_raw_records']:,}</div>
            <div class="kpi-desc">Across 4 raw source sheets</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #059669; background-color: #ffffff;">
            <div class="kpi-label">Clean Operational Records</div>
            <div class="kpi-number" style="color: #059669;">{lineage_summary['clean_records']:,}</div>
            <div class="kpi-desc">{lineage_summary['duplicates_purged']} duplicate sales purged</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #2563eb; background-color: #ffffff;">
            <div class="kpi-label">Active Catalog Items</div>
            <div class="kpi-number" style="color: #2563eb;">{lineage_summary['active_catalog_skus']}</div>
            <div class="kpi-desc">{lineage_summary['pack_switches']} pack switches consolidated (R3)</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #b91c1c; background-color: #ffffff;">
            <div class="kpi-label">Excluded Inactive Items</div>
            <div class="kpi-number" style="color: #b91c1c;">{lineage_summary['inactive_items_excluded']}</div>
            <div class="kpi-desc">1 SKU holds stock; tracked under R4</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #d97706; background-color: #ffffff;">
            <div class="kpi-label">Eligible Accounts (&gt; ₹100k)</div>
            <div class="kpi-number" style="color: #d97706;">{lineage_summary['eligible_customers']}</div>
            <div class="kpi-desc">{lineage_summary['ineligible_customers']} accounts below ₹100k spend (R6)</div>
        </div>
        <div class="kpi-card" style="border-top: 3px solid #7c3aed; background-color: #ffffff;">
            <div class="kpi-label">Sales Action Calls</div>
            <div class="kpi-number" style="color: #6d28d9;">{lineage_summary['total_sales_recommendations']}</div>
            <div class="kpi-desc">Pre-screened calling opportunities</div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # 3. Simple Professional Visual Flow (Vertical Flowchart of all 12 stages)
    st.markdown('<div class="content-box-title">Deterministic Transformation Pipeline (12-Stage Visual Flow)</div>', unsafe_allow_html=True)
    st.caption("Sequential pipeline depicting data movement, volume changes, governance filters, and material adjustments from raw input ingestion to outbound calling ledger.")

    flow_cards_html = []
    for idx, s in enumerate(lineage_stages):
        stage_num = s["id"]
        stage_name = s["name"]
        stage_sub = s["subtitle"]
        icon = s["icon"]
        rec_summary = s["records_summary"]
        exc_count = s["excluded_records_count"]
        exc_str = f"<span style='color: #dc2626; font-weight: 700;'>{exc_count:,} excluded</span>" if exc_count > 0 else "<span style='color: #16a34a; font-weight: 600;'>0 excluded</span>"
        
        accent_color = "#2563eb" if stage_num in [1, 2, 3] else ("#0284c7" if stage_num in [4, 5, 6] else ("#4f46e5" if stage_num in [7, 8, 9] else "#0f294a"))

        card_html = f"""
        <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-left: 5px solid {accent_color}; border-radius: 8px; padding: 0.85rem 1.15rem; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
            <div style="display: flex; align-items: center; gap: 0.85rem;">
                <div style="width: 38px; height: 38px; border-radius: 50%; background: #f1f5f9; display: flex; align-items: center; justify-content: center; font-size: 1.15rem;">
                    {icon}
                </div>
                <div>
                    <div style="display: flex; align-items: baseline; gap: 0.45rem;">
                        <span style="font-size: 0.72rem; font-weight: 800; color: {accent_color}; text-transform: uppercase; letter-spacing: 0.05em;">Stage {stage_num}</span>
                        <strong style="font-size: 1.02rem; color: #0f294a;">{stage_name}</strong>
                    </div>
                    <div style="font-size: 0.82rem; color: #475569;">{stage_sub}</div>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;">
                <div style="text-align: right;">
                    <div style="font-size: 0.76rem; color: #64748b; text-transform: uppercase; font-weight: 600;">Record Volume</div>
                    <div style="font-size: 0.90rem; font-weight: 700; color: #0f294a;">{rec_summary}</div>
                </div>
                <div style="text-align: right; min-width: 110px;">
                    <div style="font-size: 0.76rem; color: #64748b; text-transform: uppercase; font-weight: 600;">Exclusions</div>
                    <div style="font-size: 0.88rem;">{exc_str}</div>
                </div>
            </div>
        </div>
        """
        flow_cards_html.append(card_html)
        if idx < len(lineage_stages) - 1:
            arrow_html = """
            <div style="display: flex; justify-content: center; align-items: center; color: #94a3b8; font-size: 1.25rem; font-weight: 800; margin: 0.15rem 0;">
                &darr;
            </div>
            """
            flow_cards_html.append(arrow_html)

    st.markdown(_clean_html_block(f"""
    <div style="max-width: 980px; margin: 0 auto 1.5rem auto;">
        {''.join(flow_cards_html)}
    </div>
    """), unsafe_allow_html=True)

    # 4. Interactive Stage-by-Stage Operational Deep Dive
    st.divider()
    st.markdown('<div class="content-box-title">Stage Inspector: Deep-Dive Operational Diagnostics</div>', unsafe_allow_html=True)
    st.caption("Select any of the 12 pipeline stages to inspect the exact record counts, transformations, warnings, and business exclusion reasons.")

    col_sel_stg, col_stg_dl = st.columns([2.5, 1.5])
    with col_sel_stg:
        stage_options = [f"{s['id']}. {s['name']} — {s['subtitle']}" for s in lineage_stages]
        selected_stg_idx = st.selectbox(
            "Select Pipeline Stage to Inspect",
            range(len(stage_options)),
            format_func=lambda i: stage_options[i],
            key="lineage_stage_select",
        )
    with col_stg_dl:
        st.write("")
        st.write("")
        lineage_excel = export_data_lineage_excel(lineage_data)
        st.download_button(
            "📥 Export Data Lineage Report (.xlsx)",
            data=lineage_excel,
            file_name="CompanyX_Data_Lineage_Audit.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_lineage_excel",
            use_container_width=True,
        )

    selected_stage = lineage_stages[selected_stg_idx]

    # Pre-build HTML lists without backslashes for f-string compatibility
    breakdown_items_html = "".join([f"<li><strong>{k}:</strong> {v}</li>" for k, v in selected_stage["record_breakdown"].items()])
    trans_items_html = "".join([f"<li style='margin-bottom: 0.3rem;'>{t}</li>" for t in selected_stage["transformations"]])
    warn_items_html = "".join([f"<li style='margin-bottom: 0.3rem;'>{w}</li>" for w in selected_stage["warnings"]])

    # Render selected stage detail box
    st.markdown(_clean_html_block(f"""
    <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 5px solid #2563eb; border-radius: 8px; padding: 1.15rem 1.35rem; margin-top: 0.5rem; margin-bottom: 1.5rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span style="font-size: 1.4rem;">{selected_stage['icon']}</span>
                <div>
                    <div style="font-size: 1.15rem; font-weight: 800; color: #0f294a;">
                        Stage {selected_stage['id']}: {selected_stage['name']}
                    </div>
                    <div style="font-size: 0.85rem; color: #64748b;">
                        {selected_stage['subtitle']}
                    </div>
                </div>
            </div>
            <span style="font-size: 0.74rem; font-weight: 700; color: #1e3a8a; background: #dbeafe; border: 1px solid #bfdbfe; padding: 0.25rem 0.65rem; border-radius: 4px;">
                Input: {selected_stage['records_in']:,} &rarr; Output: {selected_stage['records_out']:,}
            </span>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-top: 0.85rem;">
            <!-- Column 1: Record Counts & Breakdown -->
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem 1rem;">
                <div style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; color: #0f294a; margin-bottom: 0.45rem;">
                    1. Number of Records
                </div>
                <div style="font-size: 1.1rem; font-weight: 800; color: #1e293b; margin-bottom: 0.35rem;">
                    {selected_stage['records_summary']}
                </div>
                <div style="font-size: 0.82rem; color: #475569; line-height: 1.5;">
                    <strong>Inputs Received:</strong> {selected_stage['records_in']:,} records<br>
                    <strong>Outputs Produced:</strong> {selected_stage['records_out']:,} records<br>
                    <strong>Detailed Breakdown:</strong>
                    <ul style="margin: 0.25rem 0 0 1.15rem; padding: 0;">
                        {breakdown_items_html}
                    </ul>
                </div>
            </div>

            <!-- Column 2: Important Transformations -->
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem 1rem;">
                <div style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; color: #059669; margin-bottom: 0.45rem;">
                    2. Important Transformations
                </div>
                <ul style="margin: 0; padding-left: 1.15rem; font-size: 0.82rem; color: #334155; line-height: 1.5;">
                    {trans_items_html}
                </ul>
            </div>

            <!-- Column 3: Warnings & Adjustments -->
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem 1rem;">
                <div style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; color: #d97706; margin-bottom: 0.45rem;">
                    3. Warnings &amp; Disclosures
                </div>
                <ul style="margin: 0; padding-left: 1.15rem; font-size: 0.82rem; color: #334155; line-height: 1.5;">
                    {warn_items_html}
                </ul>
            </div>

            <!-- Column 4: Excluded Records & Reason -->
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem 1rem;">
                <div style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; color: #dc2626; margin-bottom: 0.45rem;">
                    4. Excluded Records &amp; Reason
                </div>
                <div style="font-size: 0.84rem; color: #b91c1c; font-weight: 700; margin-bottom: 0.35rem;">
                    {selected_stage['excluded_records_count']} record(s) excluded: {selected_stage['excluded_records_detail']}
                </div>
                <div style="font-size: 0.82rem; color: #475569; line-height: 1.45; background: #fef2f2; border: 1px solid #fecaca; border-radius: 4px; padding: 0.5rem 0.65rem;">
                    <strong style="color: #991b1b;">Reason for Exclusion:</strong><br>
                    {selected_stage['exclusion_reason']}
                </div>
            </div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # 5. Consolidated 12-Stage Lineage Matrix Table
    st.divider()
    st.markdown('<div class="content-box-title">Consolidated 12-Stage Lineage Matrix Table</div>', unsafe_allow_html=True)
    st.caption("Complete reference matrix documenting inputs, outputs, exclusions, transformations, warnings, and governance reasons for all 12 stages.")

    tbl_display = lineage_matrix_df[[
        "Stage #", "Pipeline Stage", "Subtitle", "Records In", "Records Out",
        "Excluded Records", "Excluded Detail", "Exclusion Reason", "Key Transformations", "Warnings"
    ]].copy()
    st.dataframe(tbl_display, use_container_width=True, hide_index=True)


# ==============================================================================
# TAB 5: DATA QUALITY
# ==============================================================================
with tab5:
    st.markdown('<div class="content-box-title">Data Quality Audit &amp; Material Adjustment Log</div>', unsafe_allow_html=True)
    st.caption("Comprehensive data health diagnostics, governance handling rules, and referential integrity audit.")

    # Prominent Governance & Auditor Notice
    st.markdown(_clean_html_block("""
<div class="dq-notice-banner">
    <strong>Auditor Governance Note:</strong><br>
    Data quality issues do not automatically mean the analysis is unusable. The tool applies defined handling rules and makes every material adjustment visible.
</div>
"""), unsafe_allow_html=True)

    with st.expander("📋 Case Input Schema Conformance Register (Rules R1–R2 Source of Truth)", expanded=False):
        st.caption("Verifies that all four ingested worksheets strictly conform to the expected Company X Case Schema.")
        raw_tables = r["raw"]
        sheet_names = ["Item_Master", "Stock_Aging", "Sales_Lines", "Customers"]
        schema_rows = []
        for s_idx, s_name in enumerate(sheet_names):
            df_curr = raw_tables[s_idx]
            exp_cols = EXPECTED_COLUMNS[s_name]
            det_cols = list(df_curr.columns)
            miss_cols = [c for c in exp_cols if c not in det_cols]
            extra_cols = [c for c in det_cols if c not in exp_cols]
            schema_rows.append({
                "Worksheet": s_name,
                "Conformance Status": "✅ 100% Conforming" if not miss_cols else f"❌ {len(miss_cols)} Missing",
                "Required Columns": len(exp_cols),
                "Detected Columns": len(det_cols),
                "Missing Columns": ", ".join(miss_cols) if miss_cols else "None",
                "Non-Standard Columns": ", ".join(extra_cols) if extra_cols else "None",
            })
        st.dataframe(pd.DataFrame(schema_rows), use_container_width=True, hide_index=True)

    issues_list = validation.get("issues", [])
    raw_customers = r["raw"][3]
    missing_ind_mask = raw_customers["Industry"].isna() | raw_customers["Industry"].astype(str).str.strip().isin(["", "nan", "None", "NA", "<NA>"])
    missing_ind_count = int(missing_ind_mask.sum())

    dq_score = validation.get("data_quality_score", 100)
    score_color = "#16a34a" if dq_score >= 85 else ("#d97706" if dq_score >= 70 else "#dc2626")
    score_grade = "Grade A (Clean & Validated)" if dq_score >= 85 else ("Grade B (Acceptable Disclosures)" if dq_score >= 70 else "Grade C (Material Anomalies)")
    n_err = sum(1 for i in issues_list if i.get("Severity") == "ERROR")
    n_warn = sum(1 for i in issues_list if i.get("Severity") == "WARNING")
    n_info = sum(1 for i in issues_list if i.get("Severity") == "INFO")

    # Executive Summary Metrics & Data Quality Score
    st.markdown(_clean_html_block(f"""
<div class="metric-row">
    <div class="metric-col" style="flex: 1.2; border-right: 2px solid #e2e8f0; padding-right: 1.25rem;">
        <div class="metric-col-label">Data Quality Score</div>
        <div class="metric-col-val" style="color: {score_color}; font-size: 1.8rem;">
            {dq_score} <span style="font-size: 1rem; color: #64748b; font-weight: 500;">/ 100</span>
        </div>
        <div style="font-size: 0.8rem; font-weight: 600; color: {score_color}; margin-top: 0.15rem;">
            {score_grade}
        </div>
    </div>
    <div class="metric-col">
        <div class="metric-col-label">Severity Breakdown</div>
        <div style="font-size: 0.92rem; line-height: 1.6; margin-top: 0.25rem;">
            <span style="color: #dc2626; font-weight: 700;">🔴 {n_err} Errors</span> &nbsp;&bull;&nbsp;
            <span style="color: #d97706; font-weight: 700;">🟡 {n_warn} Warnings</span> &nbsp;&bull;&nbsp;
            <span style="color: #2563eb; font-weight: 700;">🔵 {n_info} Info</span>
        </div>
        <div style="font-size: 0.78rem; color: #64748b; margin-top: 0.15rem;">{len(issues_list)} total audit disclosures logged</div>
    </div>
    <div class="metric-col">
        <div class="metric-col-label">Duplicate Sales Lines</div>
        <div class="metric-col-val">{validation.get('duplicate_sales_rows', 0)}</div>
        <div style="font-size: 0.8rem; color: #64748b;">Deduplicated before velocity</div>
    </div>
    <div class="metric-col">
        <div class="metric-col-label">Missing Industry Accounts</div>
        <div class="metric-col-val">{missing_ind_count}</div>
        <div style="font-size: 0.8rem; color: #64748b;">Ineligible for Bucket 2</div>
    </div>
    <div class="metric-col">
        <div class="metric-col-label">Pack Switches Applied</div>
        <div class="metric-col-val">{len(analysis['switch_map'])}</div>
        <div style="font-size: 0.8rem; color: #64748b;">Rule R3 consolidations</div>
    </div>
    <div class="metric-col">
        <div class="metric-col-label">Inactive SKUs with Stock</div>
        <div class="metric-col-val">{len(analysis['inactive_stock'])}</div>
        <div style="font-size: 0.8rem; color: #64748b;">Rule R4 tracked inventory</div>
    </div>
</div>
"""), unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # MASTER AUDIT REGISTER: All Detected Issues with Structured Columns
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">Master Audit Register (All Detected Issues)</div>', unsafe_allow_html=True)
    st.caption("Every detected anomaly is detailed with its severity level, issue type, sheet, column, affected record count, system handling rule, and recommended source fix.")

    if issues_list:
        col_f_sev, col_f_search = st.columns([1.5, 2.5])
        sev_filter = col_f_sev.selectbox("Filter by Severity", ["All", "ERROR", "WARNING", "INFO"], key="dq_sev_filter")
        kw_filter = col_f_search.text_input("Filter by Keyword", placeholder="Search issue, sheet, or column...", key="dq_kw_filter")

        filtered_issues = issues_list
        if sev_filter != "All":
            filtered_issues = [i for i in filtered_issues if i.get("Severity") == sev_filter]
        if kw_filter.strip():
            kw = kw_filter.strip().lower()
            filtered_issues = [
                i for i in filtered_issues
                if kw in i.get("Problem", "").lower()
                or kw in i.get("Description", "").lower()
                or kw in i.get("Issue Type", "").lower()
                or kw in i.get("Sheet", "").lower()
                or kw in i.get("Column", "").lower()
            ]

        df_all_issues = pd.DataFrame([
            {
                "Severity": str(iss.get("Severity", "WARNING")),
                "Issue Type": str(iss.get("Issue Type", "Data Hygiene")),
                "Sheet": str(iss.get("Sheet", "All")),
                "Column": str(iss.get("Column", "N/A")),
                "Problem": str(iss.get("Problem", "")),
                "Number of affected records": int(iss.get("Count", 0)),
                "What the tool did": str(iss.get("Tool Handling", "")),
                "Recommended source-level fix": str(iss.get("Recommended Source Fix", "")),
            }
            for iss in filtered_issues
        ])
        st.dataframe(df_all_issues, use_container_width=True, hide_index=True)
    else:
        st.success("No validation anomalies detected. All input files conform to required schema and domain constraints.")

    # --------------------------------------------------------------------------
    # SECTION A: Formatting issues
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">A. Formatting Issues</div>', unsafe_allow_html=True)
    fmt_issues = [
        iss for iss in issues_list
        if any(term in iss.get("Problem", "").lower() for term in ["formatting", "inconsistenc", "whitespace", "case"])
    ]
    if fmt_issues:
        df_fmt = pd.DataFrame([
            {
                "Problem": str(iss.get("Problem", "")),
                "Number of affected records": int(iss.get("Count", 0)),
                "What the tool did": str(iss.get("Tool Handling", "")),
                "Recommended source-level fix": str(iss.get("Recommended Source Fix", "")),
            }
            for iss in fmt_issues
        ])
        st.dataframe(df_fmt, use_container_width=True, hide_index=True)
        st.caption("Operational Handling: Identifiers with inconsistent casing or extraneous whitespace were normalized (trimmed and uppercase) during ingestion to prevent false lookup failures across master and transactional records.")
    else:
        st.markdown('<div class="dq-badge-clean">✓ No formatting inconsistencies detected. All SKUs and Customer IDs conform to uppercase trimmed standards.</div>', unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SECTION B: Duplicate records
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">B. Duplicate Records</div>', unsafe_allow_html=True)
    dup_issues = [
        iss for iss in issues_list
        if "duplicate" in iss.get("Problem", "").lower()
    ]
    if dup_issues:
        df_dup = pd.DataFrame([
            {
                "Problem": str(iss.get("Problem", "")),
                "Number of affected records": int(iss.get("Count", 0)),
                "What the tool did": str(iss.get("Tool Handling", "")),
                "Recommended source-level fix": str(iss.get("Recommended Source Fix", "")),
            }
            for iss in dup_issues
        ])
        st.dataframe(df_dup, use_container_width=True, hide_index=True)
        st.caption("Operational Handling: Exact duplicate transaction rows in Sales Lines were deduplicated prior to aggregation. If left unhandled, duplicate sales would artificially inflate 6-month sales velocity, improperly decreasing Months to Clear and distorting item classifications.")
    else:
        st.markdown('<div class="dq-badge-clean">✓ No duplicate transaction records detected in Sales Lines or Master tables.</div>', unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SECTION C: Missing master-data relationships
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">C. Missing Master-Data Relationships</div>', unsafe_allow_html=True)
    rel_issues = [
        iss for iss in issues_list
        if any(term in iss.get("Problem", "").lower() for term in ["not found in", "orphan", "referential", "unmatched"])
    ]
    if rel_issues:
        df_rel = pd.DataFrame([
            {
                "Problem": str(iss.get("Problem", "")),
                "Number of affected records": int(iss.get("Count", 0)),
                "What the tool did": str(iss.get("Tool Handling", "")),
                "Recommended source-level fix": str(iss.get("Recommended Source Fix", "")),
            }
            for iss in rel_issues
        ])
        st.dataframe(df_rel, use_container_width=True, hide_index=True)
    else:
        st.markdown(_clean_html_block("""
<div class="dq-badge-clean">
    ✓ Complete Referential Integrity Verified:
    <ul style="margin: 0.35rem 0 0 1.25rem; padding: 0;">
        <li>100% of transactional Sales SKUs map to valid Item Master records.</li>
        <li>100% of Sales Customer IDs map to valid Customer Master records.</li>
        <li>100% of warehouse Stock Aging SKUs map to valid Item Master records.</li>
    </ul>
</div>
"""), unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SECTION D: Missing Industry
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">D. Missing Industry (Customer Master)</div>', unsafe_allow_html=True)
    ind_issues = [
        iss for iss in issues_list
        if "industry" in iss.get("Problem", "").lower()
    ]
    if ind_issues:
        df_ind = pd.DataFrame([
            {
                "Problem": str(iss.get("Problem", "")),
                "Number of affected records": int(iss.get("Count", 0)),
                "What the tool did": str(iss.get("Tool Handling", "")),
                "Recommended source-level fix": str(iss.get("Recommended Source Fix", "")),
            }
            for iss in ind_issues
        ])
        st.dataframe(df_ind, use_container_width=True, hide_index=True)
        st.caption("Rule R6 Governance Impact: Under Rule R6, Bucket 2 customer targeting relies on industry affinity (matching customers whose Industry corresponds to previous buyers of the Push item). Customers with missing Industry are strictly barred from entering Bucket 2. However, they remain fully eligible for Bucket 1 (historical buyers) and Bucket 3 (same category buyers) if their 6-month spend exceeds ₹100,000.")

        # Show affected customer record(s)
        missing_customers = raw_customers[missing_ind_mask][["CustomerID", "CustomerName", "Area"]].copy()
        missing_customers["Industry Status"] = "Missing (Ineligible for Bucket 2)"
        st.markdown("**Customer Accounts with Missing Industry:**")
        st.dataframe(missing_customers, use_container_width=True, hide_index=True)
    else:
        st.markdown('<div class="dq-badge-clean">✓ All customer accounts have an assigned Industry. Complete Bucket 2 affinity targeting enabled.</div>', unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SECTION E: Pack-size SWITCH mappings (Rule R3)
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">E. Pack-Size SWITCH Mappings (Rule R3 Consolidation)</div>', unsafe_allow_html=True)
    st.caption("Under Rule R3, when Alternate Flag = SWITCH, the historical sales and warehouse stock of the old item are consolidated under the new item's SKU. The old SKU does not remain as an independent analytical item. Note: Only Alternate Flag = SWITCH triggers consolidation; the mere presence of an alternate item name does not trigger consolidation.")

    switches_df = analysis["switch_map_df"]
    if switches_df.empty:
        st.info("No pack-size switch relationships detected.")
    else:
        st.dataframe(switches_df, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # SECTION F: Inactive items with stock (Rule R4)
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">F. Inactive Items with Stock (Rule R4 Warehouse Audit)</div>', unsafe_allow_html=True)
    st.caption("Under Rule R4, inactive catalog items are excluded from the main classification so sales reps do not pitch discontinued lines. However, inactive items that still hold physical warehouse inventory are separately tracked and reported so physical capital is never silently lost.")

    inactive_stock = analysis["inactive_stock"]
    if inactive_stock.empty:
        st.success("No inactive catalog items currently hold stock in the warehouse.")
    else:
        st.warning(f"⚠️ {len(inactive_stock)} inactive item(s) currently hold physical stock in warehouse inventory:")
        st.dataframe(inactive_stock, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # ANALYSIS AUDIT SECTION (Management & Evaluator Traceability)
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">Analysis Audit (End-to-End Transformation Traceability)</div>', unsafe_allow_html=True)
    st.caption("Step-by-step pipeline audit trail documenting record transformation counts, governance adjustments, and classification lineage for management and case evaluation.")

    audit_data = r.get("audit_trail") or build_audit_trail(r["raw"], validation, analysis, targets)
    audit_table = audit_data["table"][["Step", "Stage", "Audit Metric", "Formatted Value", "Operational Detail"]].copy()
    audit_table.columns = ["Step", "Transformation Stage", "Audit Metric", "Volume / Count", "Operational Context & Rule Reference"]
    st.dataframe(audit_table, use_container_width=True, hide_index=True)


# ==============================================================================
# TAB 6: SETTINGS (Configurable Parameters & Case Rules)
# ==============================================================================
with tab6:
    st.markdown('<div class="content-box-title">System Settings & Configurable Parameters</div>', unsafe_allow_html=True)
    st.caption("Centralized configuration control for all business thresholds, classification triggers, and qualification cutoffs. Default values match the Company X Case Study requirements exactly.")

    current_cfg = st.session_state.get("config", r.get("config", get_default_config()))

    # Mode Indicator Banner
    if current_cfg.is_default():
        st.markdown(_clean_html_block("""
        <div style="background-color: #f0fdf4; border: 1px solid #86efac; border-left: 5px solid #16a34a; border-radius: 6px; padding: 0.95rem 1.15rem; margin-bottom: 1.25rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                <div>
                    <span style="background-color: #dcfce7; color: #15803d; font-weight: 800; font-size: 0.8rem; padding: 3px 9px; border-radius: 4px; border: 1px solid #86efac; letter-spacing: 0.05em;">
                        CASE DEFAULT SETTINGS
                    </span>
                    <span style="font-weight: 700; color: #166534; font-size: 0.95rem; margin-left: 0.5rem;">
                        Official Benchmark Case Rules Active
                    </span>
                    <div style="color: #14532d; font-size: 0.84rem; margin-top: 0.35rem; line-height: 1.45;">
                        All calculations strictly follow official MBA Case Study specifications: Red List (&lt; 1 Master Pack), No Action (Months to Clear &lt; 3), Customer Eligibility (&gt; ₹100,000 6M spend), and Aged Stock (91+ days).
                    </div>
                </div>
            </div>
        </div>
        """), unsafe_allow_html=True)
    else:
        diffs = current_cfg.diff_from_defaults()
        diff_rows = "".join([
            f"<tr><td style='padding: 6px 12px; font-weight: 600; border-bottom: 1px solid #fef3c7;'>{d['parameter']}</td>"
            f"<td style='padding: 6px 12px; color: #64748b; border-bottom: 1px solid #fef3c7;'>{d['default_value']}</td>"
            f"<td style='padding: 6px 12px; color: #b45309; font-weight: 700; border-bottom: 1px solid #fef3c7;'>{d['custom_value']}</td></tr>"
            for d in diffs
        ])
        st.markdown(_clean_html_block(f"""
        <div style="background-color: #fffbeb; border: 1px solid #fde68a; border-left: 5px solid #d97706; border-radius: 6px; padding: 0.95rem 1.15rem; margin-bottom: 1.25rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                <div>
                    <span style="background-color: #fef3c7; color: #b45309; font-weight: 800; font-size: 0.8rem; padding: 3px 9px; border-radius: 4px; border: 1px solid #fcd34d; letter-spacing: 0.05em;">
                        CUSTOM SETTINGS
                    </span>
                    <span style="font-weight: 700; color: #92400e; font-size: 0.95rem; margin-left: 0.5rem;">
                        Custom Operational Parameters Active ({len(diffs)} parameter{'s' if len(diffs) > 1 else ''} modified)
                    </span>
                    <div style="color: #78350f; font-size: 0.84rem; margin-top: 0.35rem; line-height: 1.45;">
                        Derived inventory classifications and sales targets are recalculated under custom criteria. The underlying raw data remains completely immutable.
                    </div>
                </div>
            </div>
            <div style="margin-top: 0.75rem;">
                <table style="width: 100%; border-collapse: collapse; background: #ffffff; border: 1px solid #fef3c7; border-radius: 6px; overflow: hidden; font-size: 0.84rem;">
                    <thead>
                        <tr style="background: #fef3c7; text-align: left; font-size: 0.76rem; text-transform: uppercase; color: #92400e; letter-spacing: 0.04em;">
                            <th style="padding: 6px 12px;">Parameter</th>
                            <th style="padding: 6px 12px;">Case Default Setting</th>
                            <th style="padding: 6px 12px;">Active Custom Setting</th>
                        </tr>
                    </thead>
                    <tbody>
                        {diff_rows}
                    </tbody>
                </table>
            </div>
        </div>
        """), unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SUBSECTION 1: CURRENT CASE RULES
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">Current Case Rules (Rules R1–R7)</div>', unsafe_allow_html=True)
    st.caption("Official governance and operational decision rules established in the Company X Case Study. Default configurable parameters are calibrated to enforce these rules.")

    rules_data = get_current_case_rules()
    rules_table = pd.DataFrame(rules_data)
    st.dataframe(rules_table, use_container_width=True, hide_index=True)

    st.divider()

    # --------------------------------------------------------------------------
    # SUBSECTION 2: CONFIGURABLE PARAMETERS
    # --------------------------------------------------------------------------
    st.markdown('<div class="dq-section-header">Configurable Parameters</div>', unsafe_allow_html=True)
    st.caption("Adjust operational parameters to test alternative inventory and commercial policies. Click **Apply Settings** to re-evaluate the analysis across all dashboard tabs without mutating raw data.")

    with st.form("settings_form"):
        col_s1, col_s2 = st.columns(2, gap="large")

        with col_s1:
            st.markdown("#### 1. Catalog & Inventory Classification")
            st.caption("Governs the R5 Slow Stock Decision Engine (Red List, No Action, Push).")

            input_mp_mult = st.number_input(
                "Red List Sales Threshold (Master Pack Multiplier)",
                min_value=0.1,
                max_value=10.0,
                value=float(current_cfg.red_list_mp_multiplier),
                step=0.1,
                format="%.1f",
                help="Default: 1.0x Master Pack. If 6M Sales Qty < Multiplier × Master Pack Qty, the item is classified as Red List."
            )
            st.caption("🏷️ **Case Default:** `6M Sales Qty < 1 Master Pack` (Multiplier: 1.0x)")

            input_mtc_thresh = st.number_input(
                "Months-to-Clear Threshold (Runway Cutoff in Months)",
                min_value=0.5,
                max_value=36.0,
                value=float(current_cfg.months_to_clear_threshold),
                step=0.5,
                format="%.1f",
                help="Default: 3.0 months. If Aged Qty = 0 OR Months to Clear < Threshold, the item is classified as No Action."
            )
            st.caption("⏱️ **Case Default:** `Months to Clear < 3.0`")

            aging_options = [91, 61, 31]
            aging_labels = {
                91: "91+ days (Case Default — Qty 91-180 days + Qty 180+ days)",
                61: "61+ days (Includes Qty 61-90 days, 91-180 days, 180+ days)",
                31: "31+ days (Includes Qty 31-60 days, 61-90 days, 91-180 days, 180+ days)",
            }
            cur_aging_idx = aging_options.index(current_cfg.aging_days_threshold) if current_cfg.aging_days_threshold in aging_options else 0
            selected_aging = st.selectbox(
                "Aging Threshold (Aged Stock Cutoff)",
                options=aging_options,
                index=cur_aging_idx,
                format_func=lambda x: aging_labels.get(x, f"{x}+ days"),
                help="Default: 91+ days. Defines physical stock aging buckets considered aged."
            )
            st.caption("📅 **Case Default:** `91+ days`")

            st.markdown("#### 2. Commercial Customer Qualification")
            st.caption("Governs the R6 Customer Targeting Eligibility threshold.")

            input_spend = st.number_input(
                "Customer Eligibility 6M Spend Threshold (₹)",
                min_value=5000.0,
                max_value=2000000.0,
                value=float(current_cfg.customer_eligibility_spend),
                step=10000.0,
                format="%.0f",
                help="Default: ₹100,000. Customers with 6-month purchase turnover > Threshold qualify for sales outreach."
            )
            st.caption("💼 **Case Default:** `6M Purchase Value > ₹100,000`")

        with col_s2:
            st.markdown("#### 3. Operational Inventory Risk Thresholds (0-100 Score)")
            st.caption("Defines risk level classification tiers for warehouse items.")

            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                input_risk_crit = st.number_input("Critical Risk ≥", min_value=50, max_value=95, value=int(current_cfg.risk_critical_threshold), step=5)
            with col_r2:
                input_risk_high = st.number_input("High Risk ≥", min_value=30, max_value=85, value=int(current_cfg.risk_high_threshold), step=5)
            with col_r3:
                input_risk_med = st.number_input("Medium Risk ≥", min_value=10, max_value=60, value=int(current_cfg.risk_medium_threshold), step=5)
            st.caption("⚠️ **Case Defaults:** Critical ≥ 80, High ≥ 60, Medium ≥ 30, Low < 30")

            st.markdown("#### 4. Sales Priority Thresholds (0-100 Score)")
            st.caption("Defines priority tiers for commercial sales calling queues on Push items.")

            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                input_prio_crit = st.number_input("Critical Priority ≥", min_value=50, max_value=95, value=int(current_cfg.priority_critical_threshold), step=5)
            with col_p2:
                input_prio_high = st.number_input("High Priority ≥", min_value=30, max_value=85, value=int(current_cfg.priority_high_threshold), step=5)
            with col_p3:
                input_prio_med = st.number_input("Medium Priority ≥", min_value=10, max_value=60, value=int(current_cfg.priority_medium_threshold), step=5)
            st.caption("🎯 **Case Defaults:** Critical ≥ 80, High ≥ 60, Medium ≥ 30, Low < 30")

            st.markdown(_clean_html_block("""
            <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 0.85rem; margin-top: 1rem; font-size: 0.82rem; color: #475569; line-height: 1.5;">
                🛡️ <strong>Data Integrity & Reversibility Guarantee:</strong><br>
                Modifying parameters recalculates classifications on the in-memory analysis pipeline. 
                The raw transactional data and original workbook files are <strong>never overwritten or corrupted</strong>. 
                You can return to the exact case benchmark results at any time using the reset button.
            </div>
            """), unsafe_allow_html=True)

        col_b1, col_b2, col_b3 = st.columns([1.5, 1.5, 3])
        with col_b1:
            submit_custom = st.form_submit_button("💾 Apply Settings", type="primary", use_container_width=True)
        with col_b2:
            reset_defaults = st.form_submit_button("↺ Reset to Case Defaults", use_container_width=True)

    if submit_custom:
        new_config = CaseConfig(
            red_list_mp_multiplier=float(input_mp_mult),
            months_to_clear_threshold=float(input_mtc_thresh),
            customer_eligibility_spend=float(input_spend),
            aging_days_threshold=int(selected_aging),
            risk_critical_threshold=int(input_risk_crit),
            risk_high_threshold=int(input_risk_high),
            risk_medium_threshold=int(input_risk_med),
            priority_critical_threshold=int(input_prio_crit),
            priority_high_threshold=int(input_prio_high),
            priority_medium_threshold=int(input_prio_med),
        )
        apply_config_and_rerun(new_config)

    if reset_defaults:
        apply_config_and_rerun(get_default_config())

    # --------------------------------------------------------------------------
    # SUBSECTION 3: IMPACT COMPARISON (BENCHMARK vs ACTIVE)
    # --------------------------------------------------------------------------
    st.divider()
    st.markdown('<div class="dq-section-header">Operational Impact: Case Benchmark vs Active Settings</div>', unsafe_allow_html=True)
    st.caption("Compare core operational counts under official case requirements versus your active settings.")

    # Calculate metrics under active settings
    act_push = int((items["Class"] == "Push").sum()) if "Class" in items.columns else 0
    act_noaction = int((items["Class"] == "No Action").sum()) if "Class" in items.columns else 0
    act_redlist = int((items["Class"] == "Red List").sum()) if "Class" in items.columns else 0
    act_push_aged = float(items.loc[items["Class"] == "Push", "Aged Value"].sum()) if ("Aged Value" in items.columns and "Class" in items.columns) else 0.0
    act_elig_cust = len({
        cid for df in targets.values()
        if isinstance(df, pd.DataFrame) and not df.empty and "CustomerID" in df.columns
        for cid in df["CustomerID"].dropna()
    }) if targets else 0

    comparison_data = [
        {
            "Metric": "Push SKUs (Sales Push Action)",
            "Case Benchmark Default": "18 SKUs",
            "Active Configuration": f"{act_push} SKUs",
            "Variance": f"{act_push - 18:+d} SKUs" if act_push != 18 else "0 (Benchmark)",
        },
        {
            "Metric": "No Action SKUs (Organically Clearing)",
            "Case Benchmark Default": "13 SKUs",
            "Active Configuration": f"{act_noaction} SKUs",
            "Variance": f"{act_noaction - 13:+d} SKUs" if act_noaction != 13 else "0 (Benchmark)",
        },
        {
            "Metric": "Red List SKUs (Viability Review)",
            "Case Benchmark Default": "7 SKUs",
            "Active Configuration": f"{act_redlist} SKUs",
            "Variance": f"{act_redlist - 7:+d} SKUs" if act_redlist != 7 else "0 (Benchmark)",
        },
        {
            "Metric": "Push Aged Inventory Value",
            "Case Benchmark Default": "₹163,841",
            "Active Configuration": f"₹{act_push_aged:,.0f}",
            "Variance": f"₹{act_push_aged - 163841:+,.0f}" if abs(act_push_aged - 163841) > 1 else "₹0 (Benchmark)",
        },
        {
            "Metric": "Eligible Customer Accounts",
            "Case Benchmark Default": "14 accounts (> ₹100k spend)",
            "Active Configuration": f"{act_elig_cust} accounts",
            "Variance": f"{act_elig_cust - 14:+d} accounts" if act_elig_cust != 14 else "0 (Benchmark)",
        },
    ]
    st.dataframe(pd.DataFrame(comparison_data), use_container_width=True, hide_index=True)


# ==============================================================================
# TAB 7: EXPORT
# ==============================================================================
with tab7:
    st.markdown('<div class="content-box-title">Executive Excel Report Generation</div>', unsafe_allow_html=True)
    st.caption("Generate and download the complete multi-sheet Excel report containing all executive summaries, classification tables, customer targets, and data quality logs.")

    st.markdown(_clean_html_block("""
<div class="summary-card" style="margin-bottom: 1rem;">
    <div style="font-weight: 700; color: #0f294a; margin-bottom: 0.65rem; font-size: 0.95rem;">
        📊 Presentation-Grade Multi-Sheet Workbook Structure (12 Business Sections):
    </div>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; font-size: 0.86rem; color: #334155; line-height: 1.5;">
        <div>
            <div><strong>1. Executive Summary:</strong> Core portfolio KPIs, cash at risk, Push aged share, and active governance mode.</div>
            <div><strong>2. SKU Analysis:</strong> Complete catalog of active SKUs with R1–R7 classifications, risk, and priority.</div>
            <div><strong>3. Push Items:</strong> Prioritized commercial push items ranked by 0–100 Sales Priority Score.</div>
            <div><strong>4. Red List:</strong> Stagnant SKUs with sales &lt; 1 Master Pack; liquidation actions and pack ratios.</div>
            <div><strong>5. No Action:</strong> Rapid runway (&lt; 3.0m) and zero aged stock monitoring register.</div>
            <div><strong>6. Customer Targets:</strong> Pre-qualified sales call lists sorted by Bucket and Customer Opportunity Score.</div>
        </div>
        <div>
            <div><strong>7. Sales Action List:</strong> Unified sales dispatch queue with deterministic call recommendations.</div>
            <div><strong>8. Risk Analysis:</strong> 5-dimension risk score breakdown (Aged %, MTC, Velocity, Volume, Value).</div>
            <div><strong>9. Working Capital:</strong> Capital trapped by slow stock class, category exposure, and Top 10 SKUs.</div>
            <div><strong>10. Dead Stock:</strong> Dedicated ledger for items with 0 sales in 6 months requiring scrap/salvage.</div>
            <div><strong>11. Data Quality:</strong> Ingestion issue log, Rule R4 inactive stock isolation, and R3 pack switches.</div>
            <div><strong>12. Assumptions &amp; Rules:</strong> Full documentation of Rules R1–R7, defaults, and governance policies.</div>
        </div>
    </div>
    <div style="margin-top: 0.75rem; padding-top: 0.5rem; border-top: 1px solid #e2e8f0; font-size: 0.8rem; color: #64748b;">
        ⚡ <em>All sheets include corporate styling, frozen header panes, auto-filters, Indian Rupee currency formatting, dynamic conditional formatting, and auto-fitted columns. Zero calculations altered.</em>
    </div>
</div>
"""), unsafe_allow_html=True)

    if "excel_report_bytes" not in r or r["excel_report_bytes"] is None:
        st.info("💡 Click the button below to generate the comprehensive 12-sheet Excel review workbook.")
        if st.button("📊 Generate Complete Excel Report (.xlsx)", type="primary", key="btn_gen_12_sheet", use_container_width=True):
            with st.spinner("Generating presentation-grade 12-sheet Excel report..."):
                r["excel_report_bytes"] = create_excel_report(
                    items=items,
                    targets=targets,
                    validation=validation,
                    inactive_stock=analysis.get("inactive_stock"),
                    switches=analysis.get("switch_map_df"),
                    analysis=analysis,
                    sales_lines=analysis.get("clean_sales"),
                    config=active_cfg,
                    audit_trail=r.get("audit_trail"),
                )
                st.rerun()
    else:
        excel_bytes = r["excel_report_bytes"]
        st.download_button(
            "⬇️ Download Complete Excel Report (.xlsx)",
            data=excel_bytes,
            file_name="CompanyX_Slow_Stock_Review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )

    st.divider()
    st.markdown('<div class="content-box-title">Dead Stock Analysis Report (.xlsx)</div>', unsafe_allow_html=True)
    st.caption("Export dedicated dead stock ledger (items with 6M Sales Qty = 0) containing inventory value, aged value, risk score, last available sales information, and deterministic recommended actions.")

    dead_df_tab5 = analysis.get("dead_stock")
    if dead_df_tab5 is None:
        dead_df_tab5 = identify_dead_stock(items, sales_df=analysis.get("clean_sales"))
    dead_bytes_tab5 = export_dead_stock_excel(dead_df_tab5)
    st.download_button(
        "⬇️ Download Dead Stock Analysis (.xlsx)",
        data=dead_bytes_tab5,
        file_name="CompanyX_Dead_Stock_Analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_dead_stock_tab5",
        use_container_width=True,
    )


# ==============================================================================
# TAB 8: AI MANAGEMENT ASSISTANT
# ==============================================================================
with tab8:
    st.markdown('<div class="content-box-title">Executive AI Management Assistant</div>', unsafe_allow_html=True)
    st.caption("Interactive natural language query and operational interpretation layer operating strictly over pre-calculated analytical outputs.")

    # Mandatory Governance Disclaimer Box
    st.markdown(_clean_html_block(f"""
<div style="background: #f8fafc; border-left: 4px solid #2563eb; padding: 0.9rem 1.15rem; border-radius: 6px; margin-bottom: 1.25rem;">
    <div style="font-weight: 700; color: #1e3a8a; font-size: 0.92rem; margin-bottom: 0.35rem;">
        🛡️ Governance &amp; Interpretation Layer Disclaimer
    </div>
    <div style="color: #334155; font-size: 0.85rem; line-height: 1.55;">
        <strong>The AI Management Assistant is strictly an interpretation, explanation, and query interface.</strong><br>
        • The AI must <strong>NOT</strong> calculate financial metrics.<br>
        • The AI must <strong>NOT</strong> classify SKUs.<br>
        • The AI must <strong>NOT</strong> determine Rules R1–R7.<br>
        All figures, classifications, risk scores, priority rankings, and customer buckets originate exclusively from the deterministic calculation engine. The assistant references actual calculated figures and never invents or estimates numbers. If information is unavailable, it reports <em>"Insufficient data available."</em>
    </div>
</div>
"""), unsafe_allow_html=True)

    # Build structured management context
    management_ctx = build_management_structured_context(
        items=items,
        targets=targets,
        working_capital=analysis.get("working_capital"),
        dead_stock=analysis.get("dead_stock"),
        config=active_cfg,
        sales_trends=analysis.get("sales_trends"),
        sales_df=analysis.get("clean_sales"),
    )

    st.markdown("##### 💡 Suggested Executive Questions")
    st.caption("Click any canonical question to view an immediate, grounded executive interpretation referencing exact figures:")

    c_q1, c_q2, c_q3, c_q4, c_q5 = st.columns(5)
    selected_prompt = None

    with c_q1:
        if st.button("🎯 Which 5 items to prioritize?", key="btn_q1", use_container_width=True):
            selected_prompt = "Which five items should we prioritize?"
    with c_q2:
        if st.button("🔍 Why is SKU1006 important?", key="btn_q2", use_container_width=True):
            selected_prompt = "Why is SKU1006 important?"
    with c_q3:
        if st.button("📊 Highest aged categories?", key="btn_q3", use_container_width=True):
            selected_prompt = "Which categories have the highest aged inventory?"
    with c_q4:
        if st.button("⚠️ Working capital risks?", key="btn_q4", use_container_width=True):
            selected_prompt = "What are the biggest working capital risks?"
    with c_q5:
        if st.button("📞 Who should sales contact?", key="btn_q5", use_container_width=True):
            selected_prompt = "Which customers should sales contact?"

    # Query Input (persisted in session state)
    if "ai_mgmt_query" not in st.session_state:
        st.session_state["ai_mgmt_query"] = "Which five items should we prioritize?"

    if selected_prompt:
        st.session_state["ai_mgmt_query"] = selected_prompt

    user_query = st.text_input(
        "Ask a management inquiry (e.g. SKU question, category exposure, prioritization, working capital):",
        value=st.session_state.get("ai_mgmt_query", "Which five items should we prioritize?"),
        key="input_ai_query",
    )

    col_btn, col_empty = st.columns([1, 4])
    with col_btn:
        run_query = st.button("⚡ Run Inquiry", type="primary", use_container_width=True)

    active_inquiry = user_query if (run_query or selected_prompt or user_query) else st.session_state.get("ai_mgmt_query")

    if active_inquiry:
        st.markdown("---")
        with st.spinner("Interpreting pre-calculated outputs..."):
            response = interpret_management_query(active_inquiry, management_ctx)

        st.markdown(f"#### 📋 Executive Interpretation: *\"{active_inquiry}\"*")

        # Display response text in professional box
        st.markdown(_clean_html_block(f"""
<div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
    {response["answer"].replace(chr(10), '<br>')}
</div>
"""), unsafe_allow_html=True)

        # Referenced Metrics Table
        if response.get("referenced_metrics"):
            with st.expander("📌 Verified Calculated Figures Referenced in Answer", expanded=True):
                ref_dict = response["referenced_metrics"]
                if isinstance(ref_dict, dict):
                    first_val = next(iter(ref_dict.values())) if ref_dict else None
                    if isinstance(first_val, dict):
                        ref_df = pd.DataFrame.from_dict(ref_dict, orient="index")
                        st.dataframe(ref_df, use_container_width=True)
                    else:
                        ref_df = pd.DataFrame([{"Metric": k, "Value": str(v)} for k, v in ref_dict.items()])
                        st.dataframe(ref_df, use_container_width=True, hide_index=True)

        st.caption(f"🔒 *{response['disclaimer']}*")

    st.divider()
    with st.expander("🔍 Inspect Structured Context Provided to AI (JSON Engine Payload)", expanded=False):
        st.caption("Complete verified dictionary provided to the interpretation layer. The AI has zero access to raw unvalidated data or calculation formulas.")
        st.json({
            "kpis": management_ctx["kpis"],
            "top_5_push_items": management_ctx["top_push_items"][:5],
            "categories": management_ctx["categories"],
            "top_cash_at_risk": management_ctx["top_cash_at_risk"][:5],
            "top_customer_opportunities": management_ctx["customer_opportunities"][:5],
            "dead_stock": management_ctx["dead_stock"],
            "governance_disclaimer": management_ctx["disclaimer"],
        })


