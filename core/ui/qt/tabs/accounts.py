from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.ui.qt.models.balance_checking_model import BalanceCheckingTableModel


class AccountLedgerPane(QWidget):
    beginning_balance_save_requested = Signal(int, str)
    statement_save_requested = Signal(int, str, str)
    txn_cleared_toggled = Signal(int, bool)
    txn_note_edited = Signal(int, str)
    sort_changed = Signal(int, str)
    select_all_requested = Signal(int)
    clear_all_requested = Signal(int)

    def __init__(self, account_row: dict) -> None:
        super().__init__()
        self.account_id = int(account_row["account_id"])
        self.account_name = str(account_row.get("name") or "").strip()
        self.account_type = str(account_row.get("account_type") or "").strip().lower()
        self.institution_name = str(account_row.get("institution_name") or "").strip()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        balance_row = QHBoxLayout()
        balance_row.setContentsMargins(0, 0, 0, 0)
        balance_row.setSpacing(8)
        balance_row.addWidget(QLabel("Beginning Balance"), alignment=Qt.AlignLeft)
        self.beginning_balance_input = QLineEdit()
        self.beginning_balance_input.setPlaceholderText("0.00")
        self.beginning_balance_input.setFixedWidth(140)
        balance_row.addWidget(self.beginning_balance_input, alignment=Qt.AlignLeft)
        self.save_beginning_balance_button = QPushButton("Save")
        balance_row.addWidget(self.save_beginning_balance_button, alignment=Qt.AlignLeft)
        balance_row.addSpacing(12)
        balance_row.addWidget(QLabel("Ending Balance"), alignment=Qt.AlignLeft)
        self.ending_balance_value = QLabel("$0.00")
        self.ending_balance_value.setStyleSheet("font-weight: 600;")
        balance_row.addWidget(self.ending_balance_value, alignment=Qt.AlignLeft)
        balance_row.addStretch(1)
        root.addLayout(balance_row)

        self.reconciliation_frame = QFrame()
        self.reconciliation_frame.setFrameShape(QFrame.StyledPanel)
        recon_layout = QVBoxLayout(self.reconciliation_frame)
        recon_layout.setContentsMargins(10, 8, 10, 8)
        recon_layout.setSpacing(6)
        recon_layout.addWidget(QLabel("Checking Reconciliation"), alignment=Qt.AlignLeft)

        recon_input_row = QHBoxLayout()
        recon_input_row.setContentsMargins(0, 0, 0, 0)
        recon_input_row.setSpacing(8)
        recon_input_row.addWidget(QLabel("Statement Ending"), alignment=Qt.AlignLeft)
        self.statement_ending_input = QLineEdit()
        self.statement_ending_input.setPlaceholderText("0.00")
        self.statement_ending_input.setFixedWidth(130)
        recon_input_row.addWidget(self.statement_ending_input, alignment=Qt.AlignLeft)
        recon_input_row.addWidget(QLabel("Statement Date"), alignment=Qt.AlignLeft)
        self.statement_date_input = QLineEdit()
        self.statement_date_input.setPlaceholderText("YYYY-MM-DD")
        self.statement_date_input.setFixedWidth(130)
        recon_input_row.addWidget(self.statement_date_input, alignment=Qt.AlignLeft)
        self.save_statement_button = QPushButton("Save Statement")
        recon_input_row.addWidget(self.save_statement_button, alignment=Qt.AlignLeft)
        recon_input_row.addStretch(1)
        recon_layout.addLayout(recon_input_row)

        recon_metrics = QFormLayout()
        recon_metrics.setContentsMargins(0, 0, 0, 0)
        recon_metrics.setHorizontalSpacing(12)
        recon_metrics.setVerticalSpacing(4)
        recon_metrics.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        recon_metrics.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.pending_deposits_value = QLabel("$0.00")
        recon_metrics.addRow("Pending Deposits", self.pending_deposits_value)
        self.pending_withdrawals_value = QLabel("$0.00")
        recon_metrics.addRow("Pending Withdrawals", self.pending_withdrawals_value)
        self.net_pending_value = QLabel("$0.00")
        recon_metrics.addRow("Net Pending", self.net_pending_value)
        self.cleared_register_value = QLabel("$0.00")
        recon_metrics.addRow("Cleared Register Balance", self.cleared_register_value)
        self.adjusted_statement_value = QLabel("N/A")
        recon_metrics.addRow("Adjusted Statement Balance", self.adjusted_statement_value)
        self.reconciliation_diff_value = QLabel("N/A")
        recon_metrics.addRow("Difference", self.reconciliation_diff_value)
        self.reconciliation_status_value = QLabel("")
        self.reconciliation_status_value.setStyleSheet("font-weight: 600;")
        recon_metrics.addRow("Status", self.reconciliation_status_value)
        recon_layout.addLayout(recon_metrics)

        self.reconciliation_frame.setVisible(self.account_type == "checking")
        root.addWidget(self.reconciliation_frame)

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.setSpacing(8)
        frame_layout.addWidget(QLabel("Account Activity"), alignment=Qt.AlignLeft)

        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(8)
        controls_row.addWidget(QLabel("Sort by"), alignment=Qt.AlignLeft)
        self.sort_by_combo = QComboBox()
        self.sort_by_combo.addItem("Date", "date")
        self.sort_by_combo.addItem("Type", "type")
        self.sort_by_combo.addItem("Transaction ID", "txn_id")
        self.sort_by_combo.setCurrentIndex(0)
        self.sort_by_combo.setFixedWidth(120)
        controls_row.addWidget(self.sort_by_combo, alignment=Qt.AlignLeft)
        controls_row.addStretch(1)
        self.select_all_button = QPushButton("Select All")
        self.clear_all_button = QPushButton("Clear All")
        controls_row.addWidget(self.select_all_button, alignment=Qt.AlignRight)
        controls_row.addWidget(self.clear_all_button, alignment=Qt.AlignRight)
        frame_layout.addLayout(controls_row)

        self.table = QTableView()
        self.model = BalanceCheckingTableModel([])
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(
            QTableView.DoubleClicked | QTableView.EditKeyPressed
        )
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setMinimumHeight(380)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 92)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 74)
        frame_layout.addWidget(self.table, 1)
        root.addWidget(frame, 1)

        self.save_beginning_balance_button.clicked.connect(
            self._emit_beginning_balance_save
        )
        self.save_statement_button.clicked.connect(
            self._emit_statement_save
        )
        self.beginning_balance_input.editingFinished.connect(
            self._emit_beginning_balance_save
        )
        self.model.txn_cleared_toggled.connect(self._emit_txn_cleared_toggled)
        self.model.txn_note_edited.connect(self._emit_txn_note_edited)
        self.sort_by_combo.currentIndexChanged.connect(self._emit_sort_changed)
        self.select_all_button.clicked.connect(
            lambda: self.select_all_requested.emit(int(self.account_id))
        )
        self.clear_all_button.clicked.connect(
            lambda: self.clear_all_requested.emit(int(self.account_id))
        )
        self.table.clicked.connect(self._on_table_clicked)

    def _on_table_clicked(self, index) -> None:
        if not index.isValid() or index.column() != 6:
            return
        row = self.model.row_dict(index.row()) or {}
        txn_id = int(row.get("txn_id") or 0)
        if txn_id <= 0:
            return
        current = bool(row.get("is_cleared"))
        target = Qt.Unchecked if current else Qt.Checked
        self.model.setData(index, target, Qt.CheckStateRole)

    def _emit_beginning_balance_save(self) -> None:
        self.beginning_balance_save_requested.emit(
            int(self.account_id), self.beginning_balance_input.text()
        )

    def _emit_statement_save(self) -> None:
        self.statement_save_requested.emit(
            int(self.account_id),
            self.statement_ending_input.text(),
            self.statement_date_input.text(),
        )

    def _emit_sort_changed(self) -> None:
        self.sort_changed.emit(int(self.account_id), self.sort_key())

    def _emit_txn_cleared_toggled(self, txn_id: int, is_cleared: bool) -> None:
        self.txn_cleared_toggled.emit(int(txn_id), bool(is_cleared))

    def _emit_txn_note_edited(self, txn_id: int, note_text: str) -> None:
        self.txn_note_edited.emit(int(txn_id), str(note_text or ""))

    def sort_key(self) -> str:
        return str(self.sort_by_combo.currentData() or "date").strip().lower()

    def set_statement_fields(self, statement_balance_text: str, statement_date_text: str) -> None:
        self.statement_ending_input.blockSignals(True)
        self.statement_date_input.blockSignals(True)
        self.statement_ending_input.setText(str(statement_balance_text or ""))
        self.statement_date_input.setText(str(statement_date_text or ""))
        self.statement_ending_input.blockSignals(False)
        self.statement_date_input.blockSignals(False)

    def set_reconciliation_values(
        self,
        *,
        pending_deposits_display: str,
        pending_withdrawals_display: str,
        net_pending_display: str,
        cleared_register_display: str,
        adjusted_statement_display: str,
        difference_display: str,
        status_text: str,
        status_ok: bool | None,
    ) -> None:
        self.pending_deposits_value.setText(str(pending_deposits_display or "$0.00"))
        self.pending_withdrawals_value.setText(str(pending_withdrawals_display or "$0.00"))
        self.net_pending_value.setText(str(net_pending_display or "$0.00"))
        self.cleared_register_value.setText(str(cleared_register_display or "$0.00"))
        self.adjusted_statement_value.setText(str(adjusted_statement_display or "N/A"))
        self.reconciliation_diff_value.setText(str(difference_display or "N/A"))
        self.reconciliation_status_value.setText(str(status_text or ""))
        if status_ok is True:
            self.reconciliation_status_value.setStyleSheet("font-weight: 600; color: #0F766E;")
        elif status_ok is False:
            self.reconciliation_status_value.setStyleSheet("font-weight: 600; color: #B91C1C;")
        else:
            self.reconciliation_status_value.setStyleSheet("font-weight: 600;")


class AccountsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._panes_by_account_id: dict[int, AccountLedgerPane] = {}
        self._account_rows_by_id: dict[int, dict] = {}
        self._preferred_account_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)
        header_row.addWidget(QLabel("Year/Month"), alignment=Qt.AlignLeft)
        self.month_filter = QComboBox()
        self.month_filter.setMinimumWidth(130)
        header_row.addWidget(self.month_filter, alignment=Qt.AlignLeft)
        header_row.addSpacing(12)
        self.view_heading = QLabel("Accounts")
        self.view_heading.setStyleSheet("font-weight: 600;")
        header_row.addWidget(self.view_heading, alignment=Qt.AlignLeft)
        header_row.addStretch(1)
        root.addLayout(header_row)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(8)

        self.details_group = QGroupBox("Account Details")
        details_layout = QVBoxLayout(self.details_group)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(8)
        details_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        details_form = QFormLayout()
        details_form.setContentsMargins(0, 0, 0, 0)
        details_form.setHorizontalSpacing(10)
        details_form.setVerticalSpacing(8)
        details_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        details_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.details_institution = QLineEdit()
        self.details_institution.setReadOnly(True)
        self.details_institution.setMinimumWidth(320)
        details_form.addRow("Institution", self.details_institution)
        self.details_name = QLineEdit()
        self.details_name.setReadOnly(True)
        self.details_name.setMinimumWidth(320)
        details_form.addRow("Account Alias", self.details_name)
        self.details_type = QLineEdit()
        self.details_type.setReadOnly(True)
        self.details_type.setMinimumWidth(320)
        details_form.addRow("Account Class", self.details_type)
        self.details_account_number = QLineEdit()
        self.details_account_number.setReadOnly(True)
        self.details_account_number.setMinimumWidth(320)
        details_form.addRow("Account Number", self.details_account_number)
        self.details_cd_start_date = QLineEdit()
        self.details_cd_start_date.setReadOnly(True)
        self.details_cd_start_date.setMinimumWidth(320)
        details_form.addRow("CD Start Date", self.details_cd_start_date)
        self.details_cd_interval = QLineEdit()
        self.details_cd_interval.setReadOnly(True)
        self.details_cd_interval.setMinimumWidth(320)
        details_form.addRow("CD Interval", self.details_cd_interval)
        self.details_cd_interest_rate = QLineEdit()
        self.details_cd_interest_rate.setReadOnly(True)
        self.details_cd_interest_rate.setMinimumWidth(320)
        details_form.addRow("CD Interest Rate", self.details_cd_interest_rate)
        self.details_notes = QLineEdit()
        self.details_notes.setReadOnly(True)
        self.details_notes.setMinimumWidth(320)
        details_form.addRow("Notes", self.details_notes)
        self.details_external = QCheckBox("External Account")
        self.details_external.setEnabled(False)
        details_form.addRow("", self.details_external)

        details_layout.addLayout(details_form)
        details_layout.addStretch(1)
        self.details_group.setMinimumWidth(480)
        self.details_group.setMaximumWidth(580)
        content_row.addWidget(self.details_group, 0)

        self.account_tabs = QTabWidget()
        self.account_tabs.currentChanged.connect(self._remember_current_account_id)
        content_row.addWidget(self.account_tabs, 1)
        root.addLayout(content_row, 1)

    def sync_accounts(self, account_rows: list[dict]) -> list[AccountLedgerPane]:
        self._account_rows_by_id = {
            int(row["account_id"]): dict(row) for row in account_rows
        }
        existing_ids = set(self._panes_by_account_id.keys())
        target_ids = set(self._account_rows_by_id.keys())
        created: list[AccountLedgerPane] = []

        for account_id in existing_ids - target_ids:
            pane = self._panes_by_account_id.pop(account_id)
            idx = self.account_tabs.indexOf(pane)
            if idx >= 0:
                self.account_tabs.removeTab(idx)
            pane.deleteLater()

        current_pane = self.account_tabs.currentWidget()
        current_account_id = getattr(current_pane, "account_id", None)
        target_account_id = (
            int(self._preferred_account_id)
            if self._preferred_account_id is not None
            else (int(current_account_id) if current_account_id is not None else None)
        )

        for account_id, row in self._account_rows_by_id.items():
            pane = self._panes_by_account_id.get(account_id)
            if pane is None:
                pane = AccountLedgerPane(row)
                self._panes_by_account_id[account_id] = pane
                title = str(row.get("name") or f"Account {account_id}")
                self.account_tabs.addTab(pane, title)
                created.append(pane)
            else:
                idx = self.account_tabs.indexOf(pane)
                if idx >= 0:
                    self.account_tabs.setTabText(
                        idx, str(row.get("name") or f"Account {account_id}")
                    )

        if self.account_tabs.count() == 0:
            self.set_account_details(None)
            return created

        if target_account_id is not None:
            target = self.pane_for_account_id(int(target_account_id))
            if target is not None:
                idx = self.account_tabs.indexOf(target)
                if idx >= 0:
                    self.account_tabs.setCurrentIndex(idx)
                    self._preferred_account_id = int(target_account_id)
                    return created

        if self.account_tabs.currentIndex() < 0:
            self.account_tabs.setCurrentIndex(0)
        current = self.current_pane()
        self._preferred_account_id = int(current.account_id) if current is not None else None
        return created

    def _remember_current_account_id(self, index: int) -> None:
        if index < 0:
            self._preferred_account_id = None
            return
        pane = self.account_tabs.widget(index)
        if isinstance(pane, AccountLedgerPane):
            self._preferred_account_id = int(pane.account_id)

    def pane_for_account_id(self, account_id: int) -> AccountLedgerPane | None:
        return self._panes_by_account_id.get(int(account_id))

    def account_row_by_id(self, account_id: int) -> dict | None:
        row = self._account_rows_by_id.get(int(account_id))
        return dict(row) if row else None

    def current_pane(self) -> AccountLedgerPane | None:
        widget = self.account_tabs.currentWidget()
        if isinstance(widget, AccountLedgerPane):
            return widget
        return None

    def panes(self) -> list[AccountLedgerPane]:
        return list(self._panes_by_account_id.values())

    def set_account_details(self, row: dict | None) -> None:
        if row is None:
            self.details_institution.clear()
            self.details_name.clear()
            self.details_type.clear()
            self.details_account_number.clear()
            self.details_cd_start_date.clear()
            self.details_cd_interval.clear()
            self.details_cd_interest_rate.clear()
            self.details_notes.clear()
            self.details_external.setChecked(False)
            return

        self.details_institution.setText(str(row.get("institution_name") or ""))
        self.details_name.setText(str(row.get("name") or ""))
        self.details_type.setText(str(row.get("account_type") or ""))
        self.details_account_number.setText(str(row.get("account_number") or ""))
        self.details_cd_start_date.setText(str(row.get("cd_start_date") or ""))
        interval = (
            ""
            if row.get("cd_interval_count") in (None, "")
            else f"{row.get('cd_interval_count')} {str(row.get('cd_interval_unit') or '').strip()}"
        )
        self.details_cd_interval.setText(interval.strip())
        rate_bps = row.get("cd_interest_rate_bps")
        if rate_bps in (None, ""):
            self.details_cd_interest_rate.clear()
        else:
            try:
                self.details_cd_interest_rate.setText(f"{int(rate_bps) / 100:.2f}%")
            except (TypeError, ValueError):
                self.details_cd_interest_rate.setText(str(rate_bps))
        self.details_notes.setText(str(row.get("notes") or ""))
        self.details_external.setChecked(bool(row.get("is_external")))
