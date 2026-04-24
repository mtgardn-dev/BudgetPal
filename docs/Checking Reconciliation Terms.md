Here’s exactly how each value is computed on **Accounts > Checking > Checking Reconciliation**:

- **Pending Deposits**
  - Sum of all **uncleared** checking transactions in the table where `amount_cents > 0`.

- **Pending Withdrawals**
  - Sum of absolute value of all **uncleared** checking transactions where `amount_cents < 0`.

- **Net Pending**
  - `Pending Deposits - Pending Withdrawals`.

- **Cleared Register Balance**
  - Start with the tab’s computed **Ending Balance** (running balance after all listed rows),
  - then remove uncleared effect:
  - `Cleared Register Balance = Ending Balance - Net Pending`.

- **Adjusted Statement Balance**
  - Only shown if statement ending balance is entered.
  - `Adjusted Statement Balance = Statement Ending Balance + Net Pending`.
  - If statement ending is blank, shows `N/A`.

- **Difference**
  - `Difference = Adjusted Statement Balance - Ending Balance`.
  - If no statement ending entered, shows `N/A`.

- **Status**
  - If no statement entered: `Statement balance not entered`
  - If difference is zero: `Balanced`
  - Otherwise: `Out of balance`

A key identity in this implementation:
- Because of the formulas above, when statement balance exists:
  - `Difference = Statement Ending Balance - Cleared Register Balance`

So this is reconciling the **statement ending** directly against the **cleared register balance**, with pending items tracked explicitly.