Great question. Here’s the clean workflow for each case with your current v2 contract (`subscriptions.budgetpal_category_id` is authoritative).

**Rule of thumb**
1. Make category change in **BudgetPal** first.
2. Export BudgetPal categories.
3. Import that export into **SubTracker** (`budgetpal_categories`).
4. Refresh subscriptions in BudgetPal.

**1) Add a new category and sync**
1. In BudgetPal: `Settings -> Definitions`, add/save the new category (use `Expense` type if it will be used by SubTracker subscriptions).
2. In BudgetPal: export categories CSV.
3. In SubTracker: import that CSV into `budgetpal_categories` (upsert by `budgetpal_category_id`).
4. In SubTracker: assign that category to any relevant subscriptions.
5. In BudgetPal: `Bills -> Refresh Subscriptions`, then `Refresh Bills`.
6. Confirm no category mapping warning appears.

**2) Rename an existing category and sync**
1. In BudgetPal: rename the category (same row/id, new name).
2. Export categories CSV from BudgetPal.
3. Import into SubTracker `budgetpal_categories`.
4. No subscription remap is needed if IDs were preserved.
5. In BudgetPal: `Refresh Subscriptions` and `Refresh Bills`.
6. Verify renamed category appears correctly in Bills.

**3) Delete a category and sync**
1. In BudgetPal: reassign every reference off that category first (transactions, bill definitions/instances, income definitions/instances, budget allocations).
2. Delete the category in BudgetPal.
3. Export categories CSV.
4. Import into SubTracker `budgetpal_categories`.
5. In SubTracker: reassign any subscriptions still using the deleted category ID to a valid ID.
6. In BudgetPal: `Refresh Subscriptions` and `Refresh Bills`.
7. Confirm no fallback-to-`Uncategorized` warning.

If you want, I can also give you a single validation query you can run after each sync to confirm there are zero ID mismatches before you refresh in BudgetPal.