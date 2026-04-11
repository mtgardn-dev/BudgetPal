from __future__ import annotations

from core.persistence.db import BudgetPalDatabase
from core.persistence.repositories.categories_repo import CategoriesRepository


def test_upsert_is_case_insensitive_for_category_name(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    repo = CategoriesRepository(db)

    category_id_1 = repo.upsert("Health/medical", is_income=False)
    category_id_2 = repo.upsert("Health/Medical", is_income=False)

    assert category_id_1 == category_id_2
    rows = repo.find_case_variants("health/medical")
    assert len(rows) == 1


def test_merge_category_into_repoints_foreign_keys_and_merges_budget_rows(tmp_path) -> None:
    db = BudgetPalDatabase(tmp_path / "budgetpal.db")
    repo = CategoriesRepository(db)

    with db.connection() as conn:
        conn.execute("INSERT INTO categories(name, is_income, is_active) VALUES ('Health/medical', 0, 1)")
        conn.execute("INSERT INTO categories(name, is_income, is_active) VALUES ('Health/Medical', 0, 1)")
        source_id = int(
            conn.execute(
                "SELECT category_id FROM categories WHERE name = 'Health/medical'"
            ).fetchone()["category_id"]
        )
        target_id = int(
            conn.execute(
                "SELECT category_id FROM categories WHERE name = 'Health/Medical'"
            ).fetchone()["category_id"]
        )

        month_id = int(
            conn.execute(
                "INSERT INTO budget_months(year, month, starting_balance_cents) VALUES (2026, 4, 0)"
            ).lastrowid
        )
        conn.execute(
            """
            INSERT INTO budget_lines(budget_month_id, category_id, planned_cents, note)
            VALUES (?, ?, 1000, 'left')
            """,
            (month_id, source_id),
        )
        conn.execute(
            """
            INSERT INTO budget_lines(budget_month_id, category_id, planned_cents, note)
            VALUES (?, ?, 2000, 'right')
            """,
            (month_id, target_id),
        )

        conn.execute(
            """
            INSERT INTO budget_category_definitions(category_id, default_amount_cents, note, is_active)
            VALUES (?, 1100, 'src', 1)
            """,
            (source_id,),
        )
        conn.execute(
            """
            INSERT INTO budget_category_definitions(category_id, default_amount_cents, note, is_active)
            VALUES (?, 2200, 'dst', 1)
            """,
            (target_id,),
        )

        conn.execute(
            """
            INSERT INTO transactions(
                txn_date, amount_cents, txn_type, payee, description, category_id, account_id
            )
            VALUES ('2026-04-10', -1234, 'expense', 'Vendor', 'Desc', ?, 1)
            """,
            (source_id,),
        )

    deleted = repo.merge_category_into(source_id, target_id)
    assert deleted == 1

    with db.connection() as conn:
        categories = conn.execute(
            """
            SELECT category_id, name
            FROM categories
            WHERE lower(name) = lower('Health/medical')
            ORDER BY category_id
            """
        ).fetchall()
        assert len(categories) == 1
        assert int(categories[0]["category_id"]) == target_id

        txn_category = conn.execute(
            "SELECT category_id FROM transactions LIMIT 1"
        ).fetchone()
        assert int(txn_category["category_id"]) == target_id

        budget_line = conn.execute(
            """
            SELECT category_id, planned_cents, note
            FROM budget_lines
            WHERE budget_month_id = ?
            """,
            (month_id,),
        ).fetchall()
        assert len(budget_line) == 1
        assert int(budget_line[0]["category_id"]) == target_id
        assert int(budget_line[0]["planned_cents"]) == 3000
        assert str(budget_line[0]["note"]) == "right; left"

        definition = conn.execute(
            """
            SELECT category_id, default_amount_cents, note
            FROM budget_category_definitions
            """
        ).fetchall()
        assert len(definition) == 1
        assert int(definition[0]["category_id"]) == target_id
        assert int(definition[0]["default_amount_cents"]) == 3300
        assert str(definition[0]["note"]) == "dst; src"
