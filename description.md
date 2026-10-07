# PLC Monitor — Project Description & QA Report

> **HISTORICAL DOCUMENT** — snapshot from 2026-07-21; architecture/directory claims have since changed.
> Current development status lives in `STATUS.md`.

> **Version:** 1.0.0
> **Stack:** Python 3.10+, PyQt6, pymodbus, SQLite, bcrypt, openpyxl, reportlab
> **Last Updated:** 2026-07-21

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Directory Structure](#3-directory-structure)
4. [Database Schema](#4-database-schema)
5. [User Flow](#5-user-flow)
6. [Technical Details](#6-technical-details)
7. [QA Report — Bug Inventory](#7-qa-report--bug-inventory)
8. [Test Suite Status](#8-test-suite-status)
9. [Current Standing & Next Steps](#9-current-standing--next-steps)

---

## 1. Project Overview

**PLC Monitor** is a desktop application for real-time monitoring, testing, and data logging of industrial Programmable Logic Controllers (PLCs) on factory floors. It is designed for **switch testing stations** — production lines where electrical switches or modules are tested for pass/fail quality before shipping.

### Core Capabilities

- **Real-time PLC monitoring** via Modbus TCP and Modbus RTU (serial RS-485/RS-232)
- **Multi-brand support:** Mitsubishi FX/iQ-F series, Delta DVP/AS series, and generic Modbus devices
- **Configurable model system:** Users define "models" (product types), each mapping a unique set of PLC registers to test parameters
- **Automated PASS/FAIL evaluation** against configurable limits per model
- **Manual test mode** for direct coil/register control
- **Production session tracking** with operator attribution, batch counting, and comment logs
- **Report generation** in Excel (shift reports) and PDF (test certificates)
- **Role-based access control:** ADMIN, SUPERVISOR, OPERATOR roles with different permissions
- **Dark/Light theme support**

### Target Users

- Factory floor operators running switch/module test stations
- Quality supervisors reviewing test results and generating reports
- System administrators configuring PLC registers, models, and test parameters

### Hardware Context

The application communicates with PLCs (typically Mitsubishi FX3U/FX5U or Delta DVP series) over Modbus. The PLC reads physical sensor values (current, voltage, resistance) from the switch being tested and writes pass/fail results to registers. The application polls these registers in real-time, displays the data, evaluates pass/fail, and logs everything to SQLite.

---

## 2. Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                      UI Layer (PyQt6)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ MainWindow│ │ TestPage │ │ConfigPage│ │ReportsPage │  │
│  │ (Router)  │ │(Dashboard│ │ (Admin)  │ │ (Export)   │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘  │
├─────────────────────────────────────────────────────────┤
│                    Logic Layer                           │
│  ┌──────────────────┐  ┌───────────────────┐            │
│  │ SessionController │  │PassFailEvaluator  │            │
│  │ (Test Lifecycle)  │  │(PASS/FAIL Logic)  │            │
│  └──────────────────┘  └───────────────────┘            │
├─────────────────────────────────────────────────────────┤
│                    PLC Layer                              │
│  ┌────────────────┐ ┌──────────────┐ ┌───────────────┐  │
│  │ConnectionManager│ │ WriteManager │ │ ConnectionTest│  │
│  │(Polling Thread) │ │(Audit Write) │ │   (Background)│  │
│  └────────────────┘ └──────────────┘ └───────────────┘  │
│  ┌──────────────────────────────────────────────────┐   │
│  │  PLCDriverFactory → MitsubishiDriver/TCP/RTU     │   │
│  │                  → DeltaDriver/TCP/RTU           │   │
│  └──────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│                  Data Layer (SQLite)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ UserRepo │ │ModelRepo │ │SessionRepo│ │PLCProfile│   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │Register  │ │ModelMap  │ │ReportRepo│ │MessageReg│   │
│  │Library   │ │  Repo    │ │          │ │   Repo   │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Design Patterns

| Pattern | Implementation |
|---------|---------------|
| **Singleton** | `Database`, `AppState` — double-checked locking with `threading.Lock` |
| **Repository** | 14 repository classes, each wrapping one SQLite table |
| **Factory** | `PLCDriverFactory.create(profile)` dispatches to the correct driver subclass |
| **Observer** | PyQt6 signals (`pyqtSignal`) for PLC events, readings, state changes |
| **Strategy** | Driver inheritance chain (MitsubishiDriver, DeltaDriver) for brand-specific address translation |
| **Thread-local** | `Database.get_connection()` returns per-thread SQLite connections |
| **God Object** | `AppState` singleton holds all repos, PLC state, user session, and caches |

### Key Architectural Decisions

1. **No hardcoded register addresses.** All register addresses, model definitions, and PLC parameters live exclusively in the SQLite database. The schema is designed as "Schema v4.0 — zero hardcoded addresses."

2. **Driver inheritance chain (MRO):** `DeltaRTUDriver → DeltaDriver → MitsubishiRTUDriver → MitsubishiDriver → PLCDriver`. Transport (TCP vs RTU) and address translation (Mitsubishi vs Delta) are composed via multiple inheritance.

3. **Background polling thread.** `ConnectionManager` extends `QThread` and runs a continuous poll loop, reading all configured registers and emitting Qt signals to update the UI.

4. **Thread-local SQLite connections.** Each thread (main UI, PLC polling, report generation) gets its own `sqlite3.Connection` via `threading.local()`, with WAL mode for concurrent reads.

5. **All writes go through `PLCWriteManager`.** Every PLC write is logged to `plc_write_log` with operator ID, timestamp, and reason for auditability.

---

## 3. Directory Structure

```
plc_monitor/
├── main.py                          # Application entry point
├── schema.sql                       # SQLite schema (14 tables + indexes)
├── config.json                      # Legacy config (NOT used by main.py — dead file)
├── requirements.txt                 # Python dependencies
├── pyproject.toml                   # pyright config only (no pytest config)
├── conftest.py                      # Test root path setup only
├── plc_monitor.db                   # Runtime SQLite database
│
├── src/
│   ├── db/                          # Database Layer (16 files)
│   │   ├── database.py              # Thread-safe singleton DB manager (WAL mode)
│   │   ├── seed.py                  # Initial data seeding (bcrypt passwords)
│   │   ├── user_repo.py             # User authentication (bcrypt.checkpw)
│   │   ├── plc_profile_repo.py      # PLC connection settings (single row, id=1)
│   │   ├── register_library_repo.py # Register definitions (address, type, scale)
│   │   ├── model_repo.py            # Product models (name, description)
│   │   ├── model_map_repo.py        # Register-to-model mappings
│   │   ├── control_repo.py          # Write operations (start, stop, reset)
│   │   ├── io_list_repo.py          # I/O monitoring list
│   │   ├── message_repo.py          # Status message register mapping
│   │   ├── session_repo.py          # Test sessions + results
│   │   ├── report_repo.py           # Aggregated report queries
│   │   ├── app_config_repo.py       # Theme, first_run flag
│   │   └── parameter_repo.py        # Model parameter validation
│   │
│   ├── plc/                         # PLC Communication Layer (13 files)
│   │   ├── base_driver.py           # Abstract PLCDriver + PLCReadResult/PLCWriteResult
│   │   ├── mitsubishi_driver.py     # Mitsubishi Modbus TCP
│   │   ├── mitsubishi_rtu_driver.py # Mitsubishi Modbus RTU (serial)
│   │   ├── delta_driver.py          # Delta Modbus TCP (address offsets)
│   │   ├── delta_rtu_driver.py      # Delta Modbus RTU (serial)
│   │   ├── driver_factory.py        # Factory with instance caching
│   │   ├── connection_manager.py    # QThread polling loop
│   │   ├── connection_tester.py     # Background connection test
│   │   ├── data_model.py            # PLCDataModel, RegisterReading, PLCStatus
│   │   ├── write_manager.py         # Audit-logged PLC writes
│   │   └── model_push_worker.py     # Push model config to PLC
│   │
│   ├── logic/                       # Business Logic (2 files)
│   │   ├── session_controller.py    # Test session lifecycle
│   │   └── pass_fail_evaluator.py   # PASS/FAIL evaluation engine
│   │
│   ├── ui/                          # User Interface (18+ files)
│   │   ├── main_window.py           # Main container, page routing, PLC lifecycle
│   │   ├── app_state.py             # Global singleton state
│   │   ├── theme_manager.py         # Dark/Light theme loading
│   │   ├── login_overlay.py         # Authentication overlay (current)
│   │   ├── login_window.py          # Legacy login window (older entry point)
│   │   ├── login_screen.py          # Legacy login screen
│   │   ├── pages/                   # Main content pages (8 files)
│   │   │   ├── setup_wizard_page.py # First-run PLC configuration
│   │   │   ├── model_page.py        # Model selection dashboard
│   │   │   ├── test_page.py         # Live testing dashboard (cards, controls)
│   │   │   ├── manual_page.py       # Manual coil/register control
│   │   │   ├── config_page.py       # Admin config hub (7 tabs, 1672 lines)
│   │   │   ├── io_list_page.py      # I/O status monitoring
│   │   │   ├── reports_page.py      # Session history + export
│   │   │   └── settings_page.py     # User management + theme
│   │   ├── components/              # Reusable UI components (22 files)
│   │   │   ├── sidebar.py           # Navigation sidebar
│   │   │   ├── top_bar.py           # Status header
│   │   │   ├── status_bar.py        # Bottom status bar
│   │   │   ├── param_card.py        # Dashboard parameter card
│   │   │   ├── module_card.py       # Module status card
│   │   │   ├── counter_panel.py     # Production counters
│   │   │   ├── manual_grid.py       # Manual test grid
│   │   │   ├── test_grid.py         # Test section grid
│   │   │   ├── model_manager.py     # Model CRUD panel
│   │   │   ├── message_bar.py       # Status message bar
│   │   │   ├── plc_config_panel.py  # Connection status panel
│   │   │   ├── plc_block_editor.py  # PLC block register editor
│   │   │   ├── nav_bar.py           # Legacy navigation
│   │   │   ├── param_editor.py      # STUB (empty class)
│   │   │   ├── register_mapper.py   # STUB (empty class)
│   │   │   ├── limits_editor.py     # STUB (empty class)
│   │   │   ├── data_grid.py         # STUB (docstring only)
│   │   │   ├── indicator.py         # STUB (docstring only)
│   │   │   ├── plc_live_panel.py    # STUB (empty class)
│   │   │   ├── write_log_panel.py   # STUB (empty class)
│   │   │   └── plc_tag_editor.py    # Dead code (wrong imports)
│   │   └── dialogs/                 # Modal dialogs (8 files)
│   │       ├── confirm_dialog.py    # Confirmation prompt
│   │       ├── register_picker.py   # Register selection dialog
│   │       ├── password_utility.py  # Password change dialog
│   │       ├── comments_dialog.py   # Session comments
│   │       ├── reports_dialog.py    # Report search + export
│   │       ├── plc_profile_dialog.py # PLC profile editor
│   │       ├── model_dialog.py      # STUB (empty class)
│   │       └── password_dialog.py   # STUB (empty class)
│   │
│   ├── reports/                     # Report Generation (6 files)
│   │   ├── excel_generator.py       # Excel shift reports
│   │   ├── excel_exporter.py        # Excel export wrapper
│   │   ├── pdf_generator.py         # PDF test certificates
│   │   ├── pdf_exporter.py          # PDF export wrapper
│   │   └── report_worker.py         # Background report generation
│   │
│   └── utils/                       # Utilities (4 files)
│       ├── constants.py             # All app constants (356 lines)
│       ├── validators.py            # IP/port validation, address conversion
│       ├── exporters.py             # Legacy export utilities
│       └── config_manager.py        # Legacy config.json reader (unused)
│
├── tests/                           # Test Suite (17 test files + 1 mock server)
│   ├── test_db.py                   # Database layer tests (best coverage)
│   ├── test_plc_driver.py           # PLC driver unit tests
│   ├── test_exporters.py            # Excel/PDF generation tests
│   ├── test_login_ui.py             # Login window UI tests
│   ├── test_main_window.py          # Main window navigation tests (BROKEN — stale attrs)
│   ├── test_manual_window.py        # Manual grid tests
│   ├── test_settings_window.py      # Settings tests (BROKEN — tests stubs)
│   ├── test_pass_fail.py            # EMPTY placeholder
│   ├── mock_plc_server.py           # Modbus TCP mock server
│   ├── test_connection_live.py      # Standalone script (not pytest)
│   ├── test_dashboard_live.py       # Standalone script (not pytest)
│   ├── test_full_flow.py            # Standalone script (not pytest)
│   ├── test_full_visual.py          # Standalone script (not pytest)
│   ├── test_integration_smoke.py    # Standalone script (not pytest)
│   ├── test_login_visual.py         # Standalone script (BROKEN imports)
│   ├── test_settings_visual.py      # Standalone script (not pytest)
│   ├── test_step4_visual.py         # Standalone script (not pytest)
│   └── test_final_checklist.py      # Standalone script (not pytest)
│
├── migrations/                      # Schema migrations
│   ├── 001_serial_settings.sql
│   ├── 002_add_message_register_id.sql
│   └── 003_fix_register_fk_cascades.sql
│
├── logs/                            # Runtime logs (rotating, 5MB x 3)
├── reports/                         # Generated reports output
├── assets/                          # Static assets
├── image/                           # Images
└── scratch/                         # Debug scripts
```

---

## 4. Database Schema

The database uses SQLite with WAL mode. Schema version 4.3 with 15 tables:

| Table | Purpose | Key Design |
|-------|---------|------------|
| `users` | Authentication | Username + bcrypt password hash + role (ADMIN/OPERATOR/SUPERVISOR) |
| `plc_profile` | PLC connection config | Single row (id=1). Brand, protocol, TCP/RTU settings, timing |
| `register_library` | Register definitions | Single source of truth for ALL registers. Address, type, data type, scale factor |
| `models` | Product models | User-defined model names (e.g., "SW-0256A") |
| `model_register_map` | Register-to-model links | Links registers to models with roles (MEASURED, RESULT, LIMIT_MIN, etc.) |
| `control_registers` | Write operations | Button-triggered writes (START_TEST, RESET_BATCH, etc.) |
| `io_list_config` | I/O monitoring | Live status points for I/O page |
| `register_blocks` | Bulk address ranges | Contiguous ranges (start + count + type). Polled in batches, written with FC16/FC0F + verify |
| `message_register` | Status messages | Maps register values to status bar messages |
| `test_sessions` | Test run records | Model, operator, timestamps, ok/ng/batch counts |
| `test_results` | Measurement snapshots | Per-register measurements for each session |
| `plc_write_log` | Audit trail | Every PLC write logged with operator, timestamp, reason; optional `block_id` for block writes (FK → register_blocks, ON DELETE SET NULL) |
| `session_comments` | Operator notes | Free-text notes attached to sessions |
| `app_config` | App settings | Theme, first_run flag, poll interval |
| `db_migrations` | Schema versioning | Tracks applied migrations |

### Key Schema Design Decisions

- **Zero hardcoded addresses:** All register addresses live in `register_library`, not in code. The address formulas (Mitsubishi vs Delta) are applied at runtime by `validators.compute_modbus_address()`. Register blocks follow the same rule: the address range is user-selected (start + count + register type), never brand-fixed.
- **Register roles:** Each register in a model has a functional role (MEASURED, RESULT, LIMIT_MIN, LIMIT_MAX, STATUS, COUNTER, TIMER, CUSTOM). This drives the dashboard layout and PASS/FAIL logic.
- **Separation of concerns:** `register_library` defines WHAT a register is. `model_register_map` defines HOW it's used for a specific model. `plc_profile` defines WHERE the PLC is. `register_blocks` defines a contiguous RANGE to poll/write in bulk.

---

## 5. User Flow

### First Launch

1. App starts → `Database.initialize()` creates tables from `schema.sql`
2. `main.py` seeds 3 users: ADMIN (password: `admin123`), OPERATOR (`op123`), SUPERVISOR (`super123`)
3. `setup_wizard_page.py` shows if `first_run=1` in `app_config`
4. Admin configures PLC connection (brand, protocol, IP/COM port, baud rate, etc.)
5. App redirects to login overlay

### Login

1. User selects role from dropdown (OPERATOR / SUPERVISOR / ADMIN)
2. Enters password
3. `UserRepository.authenticate()` does case-insensitive username match + `bcrypt.checkpw()` verification
4. On success: `AppState.set_user()`, sidebar appears, navigated to Model page

### Model Selection

1. Operator sees available models on the Model page
2. Selects a model → `AppState.set_model(model_id)` loads register mappings
3. `ConnectionManager.update_poll_list()` hot-reloads the polling targets
4. Model config may be "pushed" to PLC via `ModelPushWorker`

### Auto Test (Dashboard)

1. TestPage shows parameter cards for the selected model
2. `PassFailEvaluator` evaluates readings in real-time against model rules
3. Cards show LIVE values with PASS/FAIL/PENDING/RUNNING indicators
4. Operator clicks START → `SessionController.on_test_started()` opens a DB session
5. PLC signals test completion → `SessionController.on_test_completed()` records results, closes session
6. Overall result (PASS/FAIL) displayed with counters (ok/ng/batch)

### Manual Test

1. ManualPage shows a grid of coils and registers for direct control
2. Operator can trigger individual coils (START, STOP, RESET) or write register values
3. All writes go through `PLCWriteManager` for audit logging

### Reports

1. ReportsPage shows session history with filtering (by model, date range)
2. Operator can view session details, add comments
3. Export to Excel (shift report) or PDF (test certificate)

### Configuration (Admin Only)

1. ConfigPage has 8 tabs: Connection, Register Library, Model Mapping, I/O List, Register Blocks, Controls, Messages, Export/Import
2. Admin manages register definitions, model configurations, control mappings
3. **Register Blocks tab:** CRUD for bulk address ranges (name, register type HOLDING/COIL/DISCRETE/INPUT, start address, count, data type, scale/units, access READ_ONLY/READ_WRITE, group). Bit types force BOOL and cap count at 2000; word types cap at 1000; DISCRETE/INPUT lock access to READ_ONLY. Changes refresh the poll list immediately (`AppState.refresh_poll_config()`)
4. Export/Import allows backup/restore of configuration (partially implemented)

---

## 6. Technical Details

### PLC Driver Hierarchy

```
PLCDriver (base_driver.py)
├── MitsubishiDriver (mitsubishi_driver.py) — Modbus TCP
│   └── MitsubishiRTUDriver (mitsubishi_rtu_driver.py) — Modbus RTU
└── DeltaDriver (delta_driver.py) — Modbus TCP with Delta address offsets
    └── DeltaRTUDriver (delta_rtu_driver.py) — Modbus RTU with Delta offsets
```

**Address Translation:**
- Mitsubishi: D register n → holding address n, M coil n → coil address 1+n
- Delta: D register n → holding address n (same), M coil n → coil address 2049+n
- Generic: pass-through (no offset)

**Driver Factory:** `PLCDriverFactory.create(profile)` dispatches based on `brand` + `protocol` from the plc_profile dict. Instances are cached by connection key to prevent port conflicts.

### Connection Manager (Polling Loop)

`ConnectionManager` extends `QThread` and runs:

```
while running:
    if not connected:
        try connect (with max_retries counter)
        on failure: emit comm_error, break after max_retries
    
    for register in poll_list:
        result = driver.read_registers(address, type, count)
        model.update_reading(register_id, reading)
    
    for block in blocks_to_poll:            # register_blocks (batched)
        raw = driver.read_block(start, type, count)   # chunked per FC limits
        model.update_block_reading(block_id, BlockReading(...))
        # on failure: keep last-good values, mark stale
    
    read message_register for status bar
    emit readings_updated, status_updated, quality_updated, blocks_updated
    sleep(poll_interval_ms)
```

### Register Blocks (Bulk Read/Write)

**Polling:** `ConnectionManager.blocks_to_poll` is a lock-guarded snapshot refreshed from `AppState.refresh_poll_config()` on connect and whenever CONFIG changes. Each active block is read once per cycle via `PLCDriver.read_block()` — chunked to the protocol's per-request limits (123 words / 1968 bits) — decoded with the block's data-type stride into `BlockReading.elements`. Failed reads keep the last good values and set `stale=True`.

**Live viewer:** The I/O List page appends one tab per active block after the I/O group tabs. It shows address / raw / decoded value per row (FLOAT32 uses stride 2; bits use the block's ON/OFF labels and colors), marks stale readings with a `(STALE)` header and `LAST READ FAILED` tooltip, and offers a **Write to PLC** button (ADMIN/SUPERVISOR only, blocks with `access=READ_WRITE`).

**Bulk write:** `PLCWriteManager.execute_block_write()` validates values against the block definition (count, coil 0/1, word 0–65535), takes the shared write lock, and calls `PLCDriver.write_block()` — FC16 (words, 123/chunk) or FC0F (bits, 1968/chunk). It then reads the range back (`read_block`) and compares before reporting `block_write_success` / `block_write_failed`. Both outcomes are audited to `plc_write_log` with `reason=BLOCK_WRITE` and the `block_id`; validation failures never reach the PLC.

### Authentication

- Passwords stored as bcrypt hashes (cost factor 12)
- Login uses role name as username (ADMIN/OPERATOR/SUPERVISOR)
- Case-insensitive username matching via `UPPER()` SQL
- No brute-force protection or account lockout

### Report Generation

- **Excel:** `openpyxl` — shift reports with conditional formatting (green for PASS, red for FAIL)
- **PDF:** `reportlab` — test certificates with parameter tables and results
- **Worker:** `ReportWorker` (QThread) for background generation

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PyQt6 | >=6.6.0 | GUI framework |
| pymodbus | >=3.6.0 | Modbus TCP/RTU communication |
| pyserial | >=3.5 | Serial port access for RTU |
| bcrypt | >=4.1.0 | Password hashing |
| openpyxl | >=3.1.0 | Excel report generation |
| reportlab | >=4.0.0 | PDF report generation |
| pytest | >=8.0.0 | Testing framework |
| pytest-qt | >=4.3.0 | PyQt6 testing helpers |

---

## 7. QA Report — Bug Inventory

### Critical Bugs (Application crashes or data corruption)

| ID | File | Line(s) | Description | Trigger |
|----|------|---------|-------------|---------|
| C1 | `src/ui/dialogs/plc_profile_dialog.py` | 27-31 | Imports `DEFAULT_STATE_REGISTER`, `DEFAULT_START_COIL`, `DEFAULT_OVERALL_RESULT_REGISTER`, `DEFAULT_OK_COUNT_REGISTER`, `DEFAULT_NG_COUNT_REGISTER` from `constants.py` — these constants do NOT exist. Causes `ImportError` on import. | Admin opens PLC Profile editor |
| C2 | `src/ui/components/manual_grid.py` | 18 | Imports `COLOR_NAVY`, `COLOR_WHITE`, `COLOR_AMBER` from `constants.py` — these constants do NOT exist. Causes `ImportError` on import. | Opening Manual Test window |
| C3 | `src/logic/session_controller.py` | 86-111 | `_ok_count`, `_ng_count`, and `_batch_count` are each incremented TWICE per test session completion (once at lines 87/92/95 and again at lines 107-111). After 10 test cycles, counters show 20. | Every auto-test completion |
| C4 | `src/ui/login_window.py` | 276, 278 | Calls `self.app_state.can_edit_settings()` and `self.app_state.is_operator()` but `AppState` does not define these methods. Raises `AttributeError`. | Login via legacy LoginWindow (not current MainWindow) |
| C5 | `src/ui/dialogs/plc_profile_dialog.py` + `src/ui/components/plc_config_panel.py` | 267, 354 / 175, 219 | References `self._app_state.plc_profile_repo` but `AppState` defines it as `self.profile_repo`. Raises `AttributeError`. | View or edit PLC profile |
| C6 | `src/ui/pages/settings_page.py` | 187 | Calls `ConfirmDialog.show_error(...)` but `ConfirmDialog` only has a static `ask()` method. Raises `AttributeError`. | User attempts to delete own account |
| C7 | `src/ui/components/param_card.py` | 182 | `QPropertyAnimation(self, b"windowOpacity")` animates the **entire application window** opacity, not just the card. The whole app pulses when a card enters RUNNING state. | Card enters RUNNING state during test |
| C8 | `src/ui/components/plc_tag_editor.py` | 12-15 | Imports from non-existent modules (`database.model_repo`, `database.db_manager`, `core.constants`, `plc.plc_driver`). File is completely non-functional dead code. | N/A (not imported anywhere) |

### High Bugs (Major functionality broken)

| ID | File | Line(s) | Description | Trigger |
|----|------|---------|-------------|---------|
| H1 | `src/ui/dialogs/model_dialog.py` | all | `class ModelDialog: pass` — empty stub. Called by `model_manager.py:172` and `settings_window.py` with `ModelDialog(mode="add")`, `.exec()`, `.result_data`. All fail. | Add or edit a model |
| H2 | `src/ui/dialogs/password_dialog.py` | all | `class PasswordDialog: pass` — empty stub. Any usage fails. | Any code referencing this dialog |
| H3 | `src/ui/dialogs/reports_dialog.py` | 408 | Sends report type `"pdf_certificate"` to `ReportWorker`, but the worker's method dict uses key `"pdf_cert"`. PDF export silently fails. | Export PDF certificate |
| H4 | `src/ui/components/plc_block_editor.py` | 315-320 | Calls `ConfirmDialog.ask(..., confirm_text="Clear", danger=True)` but the method doesn't accept `confirm_text`. Raises `TypeError`. | Clear all block values |
| H5 | `src/logic/session_controller.py` | 95, 107 | `_batch_count` incremented twice per session (same root cause as C3). | Every test completion |
| H6 | `src/ui/main_window.py` | 149-154 | After logout, `connection_manager.stop()` is called. On re-login, `_start_plc_connection()` is NOT called. PLC connection stays dead. | Logout then re-login |
| H7 | `src/ui/main_window.py` | 137-142 | Page routing uses magic integer indices (`page_map = {PAGE_MODEL: 2, PAGE_TEST: 3, ...}`). If pages are reordered in the stack, routing breaks silently. | Any page reorder |
| H8 | `src/ui/dialogs/reports_dialog.py` | 440 | `btn_ex_shift` is never enabled/disabled based on session selection. Always enabled. | Report dialog open |

### Medium Bugs (Functionality degraded)

| ID | File | Line(s) | Description |
|----|------|---------|-------------|
| M1 | `src/ui/pages/test_page.py` | 166-169 | Signal `readings_updated.connect()` called on every `on_page_shown()` without disconnecting previous. Multiple slots fire simultaneously. |
| M2 | `src/ui/pages/manual_page.py` | 211-213 | "Show All Mapped" filter uses `current_model_id` instead of showing all. Filter doesn't work as labeled. |
| M3 | `src/ui/pages/config_page.py` | 1638-1672 | Export only exports library section. Import only imports library. I/O list, controls, messages, models are silently skipped. |
| M4 | `src/ui/components/nav_bar.py` | 88 | Model name extraction from `current_model.get("model", {}).get("name", "")` — wrong dict nesting. Always shows empty. |
| M5 | `src/ui/components/status_bar.py` | 67 | `show_message()` crashes if `color` parameter is `None` (`color.lower()` → `AttributeError`). |
| M6 | `src/ui/app_state.py` | 101 | `set_model()` loads ALL models to find one by ID. Should use `get_model_by_id()`. |
| M7 | `src/ui/app_state.py` | all | No thread-safety on mutable state (`current_user`, `poll_registers`, `is_plc_connected`) accessed from both UI and PLC threads. |
| M8 | `src/ui/pages/io_list_page.py` | 100 | Timer starts polling regardless of PLC connection state. Burns CPU when disconnected. |
| M9 | Multiple components | — | 4 stub components (`ParamEditor`, `RegisterMapper`, `LimitsEditor`, `PLCBlockEditor`) block Config page functionality. |
| M10 | `src/db/database.py` | 115-117 | `fetchone()` returns `None` on SQL errors (constraint violations, typos). Silent error swallowing makes bugs invisible. |
| M11 | `src/db/database.py` | 89 | Every `execute()` auto-commits. No support for multi-statement atomic transactions. |
| M12 | `src/ui/pages/setup_wizard_page.py` | 287-292 | No input validation on save. Empty host, invalid COM port, empty slave_id all accepted. |

### Low Bugs (Minor issues)

| ID | File | Description |
|----|------|-------------|
| L1 | `src/ui/login_overlay.py:11` | Dead imports: `QSequentialAnimationGroup`, `pyqtSignal` |
| L2 | `src/ui/pages/io_list_page.py:223` | Duplicate `from PyQt6.QtGui import QFont` at end of file |
| L3 | `src/ui/components/top_bar.py:42` | `text-transform: uppercase` CSS not supported by Qt (silently ignored) |
| L4 | `src/ui/components/counter_panel.py:20` | `_app_state` stored but never used in any method |
| L5 | `main.py` / `config.json` | `config.json` exists but is never read by the application (dead config file) |
| L6 | Multiple files | Hardcoded inline colors ignore the dark/light theme system |
| L7 | `src/ui/dialogs/comments_dialog.py:182` | 500-char limit check is `pass` (no-op). Only truncation is in `_on_add_comment`. |
| L8 | `src/ui/main_window.py:123` | PLC connection starts before user logs in (if PLC is configured) |
| L9 | `src/ui/pages/reports_page.py:279` | Export worker reference not cleaned up if re-exported before first finishes |
| L10 | `src/ui/dialogs/confirm_dialog.py:24` | Hardcoded light-on-dark text color invisible in light theme |

---

## 8. Test Suite Status

### Overview

**Current gated suite (updated after Register Blocks feature, schema v4.3):**

| Metric | Value |
|--------|-------|
| Gated command | `pytest -q --tb=no --ignore=tests/test_login_visual.py --ignore=tests/test_settings_window.py` |
| Result | **51 failed / 276 passed / 15 errors** |
| Failing test IDs | 66 — identical to pre-feature baseline (`new=0 fixed=0`) |
| Register Blocks tests | 174 new tests across 6 files: `test_block_repo.py` (42), `test_block_driver.py` (37), `test_block_polling.py` (17), `test_block_write.py` (20), `test_block_config_tab.py` (27), `test_block_viewer.py` (31) |
| Zero-regression proof | Failing-ID diff against baseline after every phase |

Historical audit snapshot (below) predates the Register Blocks feature:

| Category | Count | Notes |
|----------|-------|-------|
| Total test files | 17 + 1 mock server | |
| Proper pytest files | 8 | Of which 1 is empty |
| Standalone scripts (not pytest) | 9 | Cannot be discovered by `pytest` |
| Tests estimated to PASS | ~35 | Mostly `test_db.py`, `test_plc_driver.py` |
| Tests estimated to FAIL | ~50 | `test_settings_window.py` (all), most of `test_main_window.py` |
| Broken imports | 2 files | `test_login_visual.py` imports non-existent modules |
| Stub source classes blocking tests | 4 | ParamEditor, RegisterMapper, LimitsEditor, PLCBlockEditor |

### Tests That PASS

| File | Coverage | Notes |
|------|----------|-------|
| `test_db.py` | Database layer | Most comprehensive. Tests schema, CRUD, auth, seed idempotency. Uses `tmp_path` for isolation. |
| `test_plc_driver.py` | PLC drivers | Address conversion (Mitsubishi/Delta), data type conversion, driver factory, mocked read operations. |
| `test_exporters.py` | Excel/PDF | File creation, sheet structure, cell coloring, illegal character handling. Partially fragile. |
| `test_login_ui.py` | Login window | Window sizing, wrong password, correct login, role visibility. Some attribute mismatches. |
| `test_manual_window.py` | Manual grid | Column count, button states, read-only cells, reset. Some inverted test logic. |

### Tests That FAIL

| File | Root Cause |
|------|-----------|
| `test_settings_window.py` | ALL tests target stub classes (`ParamEditor`, `RegisterMapper`, `LimitsEditor`, `PLCBlockEditor`) that have no implementation. Every test raises `AttributeError`. |
| `test_main_window.py` | ~15 of ~28 tests reference wrong attribute names (e.g., `sidebar._nav_buttons` should be `sidebar._buttons`, `status_bar.d21_lbl` should be `status_bar.message_lbl`, `login_overlay.password_field` should be `login_overlay.password_input`). Tests were written against an older version of the source. |

### Broken Test Files (Won't Import)

| File | Issue |
|------|-------|
| `test_login_visual.py` | `from src.db.repositories import ...` — module does not exist |
| `test_connection_live.py` | Uses old `PLCDriverFactory.create(brand, protocol, host, port)` API — current API takes a single dict |
| `test_dashboard_live.py` | Uses old API signatures for PLCDataModel, PLCDriverFactory, ConnectionManager |
| `test_full_flow.py` | Uses old API signatures throughout |

### Test Infrastructure Issues

- **No `pytest.ini` or `[tool.pytest.ini_options]`** in `pyproject.toml` — no markers, no testpaths, no parallel config
- **`conftest.py`** only adds root to `sys.path` — no shared fixtures for Database, AppState, or repos
- **`test_pass_fail.py`** is empty (placeholder with single empty test function)
- **9 of 17 "test" files are standalone scripts** that must be run manually with `python <file>.py` — they cannot be discovered or run by `pytest`
- **No integration tests** that actually use pytest to start mock server, run a cycle, and verify results programmatically

---

## 9. Current Standing & Next Steps

### What Works

- **Database layer** — Solid schema design, WAL mode, thread-local connections, proper foreign keys
- **PLC driver abstraction** — Clean inheritance chain for Mitsubishi/Delta, TCP/RTU
- **Address translation** — Brand-specific Modbus address formulas properly implemented
- **Register polling** — ConnectionManager reads registers, updates data model, emits signals
- **Basic authentication** — Login overlay, bcrypt verification, role-based navigation
- **Config page** — 7-tab admin hub for register library, model mapping, I/O list, controls, messages
- **Report generation** — Excel shift reports and PDF certificates (when worker keys match)

### What's Broken

- **Critical import errors** prevent PLC profile editing and manual test from loading
- **Double-counting bug** corrupts production counters on every test completion
- **Model dialog stub** prevents adding/editing models from the UI
- **PLC connection doesn't restart after logout/re-login**
- **Pulse animation** affects entire window instead of just the card
- **4 Config page components** are empty stubs (ParamEditor, RegisterMapper, LimitsEditor)
- **Export/Import** only partially implemented (library only)
- **Test suite** is ~60% broken due to stale attribute references and stub dependencies

### What's Missing

- **Implement stub components:** `ParamEditor`, `RegisterMapper`, `LimitsEditor`, `ModelDialog`, `PasswordDialog`
- **Fix all critical bugs** (C1-C8) and high bugs (H1-H8)
- **Complete Export/Import** in config page
- **Add pytest configuration** and fix stale test attribute references
- **Add missing test coverage** for: `pass_fail_evaluator.py`, `write_manager.py`, `connection_manager.py`, all pages, all dialogs
- **Remove dead code:** `plc_tag_editor.py`, `app_window.py`, `config.json`, duplicate login screens
- **Add brute-force protection** for login (rate limiting or account lockout)
- **Implement proper theming** — many components use hardcoded inline colors that ignore the theme system
- **Add multi-statement transaction support** to Database class
- **Fix signal connection leaks** in test_page.py
- **Add input validation** in setup wizard and config forms
- **Remove or integrate `config.json`** — currently dead configuration that confuses users

### Recommended Fix Priority

| Phase | Focus | Items |
|-------|-------|-------|
| **Phase 1** | Critical Fixes | C1-C7: Missing constants, double-counting, wrong attribute names, window pulse animation |
| **Phase 2** | High Fixes | H1-H8: Stub implementations, PLC reconnect on re-login, report type mismatch |
| **Phase 3** | Stub Implementations | Implement ParamEditor, RegisterMapper, LimitsEditor, ModelDialog, PasswordDialog |
| **Phase 4** | Feature Completion | Complete Export/Import, add brute-force protection, implement proper theming |
| **Phase 5** | Test Suite | Update stale tests, add pytest config, cover missing modules, delete broken scripts |
| **Phase 6** | Code Quality | Remove dead code, fix silent error handling, add transactions, clean up imports |

---

*This document is intended to provide a comprehensive understanding of the PLC Monitor application for development handoff. It covers architecture, data model, user flows, and a complete bug inventory with reproduction steps.*
