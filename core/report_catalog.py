from __future__ import annotations

REPORT_TYPE_DEFINITIONS: list[dict[str, object]] = [
    {
        "engine_key": "tax_preparation",
        "type_label": "Tax Preparation Report",
        "default_display_name": "Tax Preparation Report",
        "default_description": (
            "Annual taxable income and tax-deductible expense summaries grouped by category."
        ),
        "sort_order": 10,
        "supports_month": False,
        "supports_annual": True,
        "period_mode": "year",
    },
    {
        "engine_key": "dashboard_monthly",
        "type_label": "Dashboard Report",
        "default_display_name": "Dashboard Report",
        "default_description": (
            "Monthly dashboard snapshot: expense/income budget allocation details and account status."
        ),
        "sort_order": 20,
        "supports_month": True,
        "supports_annual": False,
        "period_mode": "month",
    },
    {
        "engine_key": "annual_account_status",
        "type_label": "Annual Account Status Report",
        "default_display_name": "Annual Account Status Report",
        "default_description": (
            "Yearly account status summary by account with beginning, activity (withdrawals/deposits), and ending totals."
        ),
        "sort_order": 30,
        "supports_month": False,
        "supports_annual": True,
        "period_mode": "year",
    },
]


def report_type_lookup() -> dict[str, dict[str, object]]:
    return {str(row["engine_key"]): row for row in REPORT_TYPE_DEFINITIONS}


def report_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in REPORT_TYPE_DEFINITIONS:
        rows.append(
            {
                "engine_key": str(row["engine_key"]),
                "display_name": str(row["default_display_name"]),
                "description": str(row["default_description"]),
            }
        )
    return rows
