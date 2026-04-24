### Recommended release + migration workflow

## A) Build a virgin release
```bash
cd /Users/mtgardn/Projects/Software/Python/BudgetPal
PACKAGED_CONFIG_SRC=/Users/mtgardn/Projects/Software/Python/BudgetPal/config/budgetpal_config.example.json \
./scripts/app_release_macos.sh v1.2.0
```

## B) Install new release (same machine) and keep existing data/settings
Just replace the app bundle.  
BudgetPal runtime state remains in:

`~/Library/Application Support/BudgetPal`

So your DB/settings persist automatically.

## C) Install as truly fresh on your machine (for testing)
Before first launch of the new app:
```bash
mv ~/Library/Application\ Support/BudgetPal ~/Library/Application\ Support/BudgetPal.backup.$(date +%Y%m%d_%H%M%S)
```
Then launch app -> it starts virgin.

## D) Migrate old settings/data into a new release or new machine
With BudgetPal closed:

1. Copy old folder:
   - `~/Library/Application Support/BudgetPal/config/budgetpal_config.json`
   - `~/Library/Application Support/BudgetPal/database/budgetpal.sqlite`
2. Place them into the same location on target machine.
3. Launch BudgetPal.
4. If paths differ (SubTracker path, backup dir), update in Settings once.
