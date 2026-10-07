# Development Status

**Current Version:** 1.0.0
**App Name:** PLC Monitor
**Stack:** PyQt6, SQLite (WAL), pymodbus, bcrypt, openpyxl, reportlab

---

## Session Log

### Session 1 — Project Setup & Foundation
**Status:** ✅ Complete

- SQLite database with WAL mode, thread-safe singleton pattern
- PLC drivers: Mitsubishi (TCP), Delta (TCP/RTU), Inovance, custom brands
- Modbus communication layer with reconnection logic
- User authentication (admin/supervisor/operator) with bcrypt
- Config wizard for first-run PLC setup
- Register library and I/O list configuration

### Session 2 — UI Core & Navigation
**Status:** ✅ Complete

- Main window with sidebar, top bar, status bar layout
- Role-based sidebar navigation (7 pages)
- Model selection page with PLC push simulation
- Test dashboard with real-time parameter cards
- Manual register read/write page
- I/O list monitoring page with tabbed groups
- Settings page (user management, password change, theme)
- Config page (PLC profiles, registers, I/O, messages, controls)
- Login overlay with animated card shake on error
- Dark and light theme support via QSS

### Session 3 — Testing & Evaluation
**Status:** ✅ Complete

- Pass/fail evaluator with per-parameter and overall result logic
- Session controller for recording test cycles to database
- Report generation (Excel via openpyxl, PDF via reportlab)
- Reports page with session history, detail view, comments
- Mock PLC server for development/testing (pymodbus async)
- Seed script for two-wheeler handle test fixture data

### Session 4 — Phase 1: Quick Wins (UI Polish)
**Status:** ✅ Complete

- Sidebar active indicator (3px left border)
- Top bar: quality dot (green/yellow/red), user avatar with initials
- Login: loading spinner during auth, exit confirmation dialog
- Test page: fullscreen toggle button, dynamic result card styling
- QSS updates for both dark and light themes

### Session 5 — Phase 2: Navigation & Layout
**Status:** ✅ Complete

- Expandable/collapsible sidebar (68px ↔ 200px) with animation
- Toggle button (☰/◀) and section dividers
- Breadcrumb navigation below top bar with clickable path links
- Keyboard shortcuts: Ctrl+1-7 (page nav), F11 (fullscreen), Escape (exit fullscreen)
- Responsive layout: min width 1024px, auto-collapse sidebar on narrow windows

### Session 6 — Phase 3: Data Visualization
**Status:** ✅ Complete

- Reports page: date range presets (Today, 7, 30, 90, All days)
- Reports page: summary stats row (Total Sessions, OK, NG, Avg Pass Rate)
- Pie chart widget (donut style with center percentage)
- Bar chart widget (top 5 parameter failures, horizontal bars)
- Param card sparkline trend lines (last 20 data points)
- I/O list: larger LED-style indicators (20px) with glow on active state

### Session 7 — Phase 4 & 5: Polish, Accessibility & Notifications
**Status:** ✅ Complete

- **Loading States (4.3):** Custom animated spinner widget (`Spinner`) with configurable size/color/speed; `SpinnerOverlay` for full-page loading; skeleton loaders (`SkeletonBar`, `SkeletonCard`, `SkeletonTable`) with gradient animation for placeholder content
- **Toast Notifications (5.3):** Non-blocking toast notification system (`ToastManager` singleton) with 4 severity levels (info/success/warning/error), fade-in/out animation, auto-dismiss on hover; integrated into PLC connect/disconnect, login/logout, report export
- **Theme Fixes (4.1):** Removed hardcoded inline `setStyleSheet()` calls from 10+ components; replaced with property-based QSS (`quality_dot[quality]`, `stat_value[rate_level]`, `status_lbl[status]`); added QSS rules to both dark.qss and theme_manager.py for editor components, legacy NavBar, skeleton loaders
- **ConfirmDialog Fix:** Removed hardcoded `font-size` inline style, added object names for QSS targeting, added `setAccessibleName`/`setToolTip`/`setTabOrder`
- **Accessibility (4.2):** Font size adjustment (Small/Medium/Large) in Settings page with persistence; high contrast mode toggle with border-based contrast override; tab order added to ConfirmDialog; extended `AppConfigRepo` with `get_font_size`/`set_font_size` and `get_high_contrast`/`set_high_contrast`
- **NavBar Refactor:** Replaced all hardcoded inline styles with object names and QSS property-based styling for theme compatibility

### Session 8 — Critical & High Severity Bug Fixes
**Status:** ✅ Complete

- **Runtime Crashes Fixed:** `session_controller.update_evaluator()` called nonexistent `update_config()` → fixed to `update_from_model()`; `pass_fail_evaluator.evaluate_all()` now checks `read_success` flag to avoid evaluating stale/garbage data; `plc_profile_repo.is_configured()` now handles `None` profile; `model_map_repo.copy_mappings()` filters dict keys to only those accepted by `add_mapping()`
- **Thread Safety:** `connection_manager.stop()` now uses `threading.Event` + `event.wait()` instead of `msleep()`, making stop interruptible; `PLCDataModel` is now stored in `AppState` and reused across reconnects instead of creating a new one each time; old `ConnectionManager` signals are properly disconnected before creating new ones on reconnect
- **Null Safety:** Added `current_user` null checks in `test_page._execute_control()`, `manual_page._execute_control()`, and `settings_page._on_delete_user()` to prevent `TypeError` when user session expires
- **Security:** Removed plaintext default passwords from log output; fixed bare `except: pass` in `settings_page._refresh_about()` that silently swallowed all exceptions including `SystemExit`
- **Data Integrity:** `STATE_COMPLETE` constant changed from `0` (same as `STATE_IDLE`) to `6`; `database.fetchall()` now re-raises `sqlite3.Error` instead of silently returning `[]`; `session_controller.on_test_completed()` now attempts to close orphaned sessions in the DB on error; `main.py` graceful shutdown now stops `write_manager` before `connection_manager`
- **Config Import:** Silent `except: pass` blocks in config import (models, I/O, controls, messages) now count skipped items and report them to the user
- **Driver Cache:** Added `PLCDriverFactory.invalidate()` method to clear cached drivers when connection parameters change

### Session 9 — UI/UX Audit Improvements (Antigravity AI Plan)
**Status:** ✅ Complete

- **Critical (4/4):** Fullscreen icon toggle (C-01), version mismatch fix (C-02), STOP button state logic (C-03), comment crash fix (C-04)
- **High (11/11):** Right panel QSS styling (H-01), param card value display (H-02), group label pills (H-03), theme card previews (H-04), font size active state (H-05), config tab Unicode icons (H-06), single-click session select (H-07), export button state (H-08), ThemeManager fix (M-10), param card QSS (T-01), banner QSS (T-03)
- **Medium (11/11):** Cycle label visibility (M-01), PLC status max width (M-02), sidebar chevron icon (M-03), sidebar tooltips (M-04), message table columns (M-06), pie chart auto-populate (M-07), comments box hidden (M-08), right panel width (M-09), high contrast QSS accumulation (M-11)
- **Low (5/5):** Admin label styling (L-04), F5/F9 shortcuts (L-05), drag handle character (L-09), audit trail username (L-10), empty state message (A-01)
- **Files Modified:** 9 files, ~1200+ lines changed
- **Full E2E Testing:** Verified with mock PLC server - all flows pass

### Session 10 — Reports Page: Complete Rewrite & Consolidation
**Status:** ✅ Complete

- **Database Migration (v4.1):** Added `limit_min` and `limit_max` columns to `test_results` table; automatic migration via `_run_migrations()` in `database.py`; values snapshotted during test execution in `session_repo.record_result()`
- **Bulk Query:** New `get_all_results_for_range()` method in `report_repo.py` — joins `test_results` with `test_sessions`, `users`, `models` to return enriched rows with session date, time, and operator name
- **10-Column Results Table:** Rewrote `reports_page.py` — results table now shows Session# | Date | Time | Module | Parameter | Measured | Min | Max | User | Result; displays ALL results from ALL sessions in the selected date range (complete report without downloading)
- **Session Highlight:** Click a session in left panel → its rows highlighted in blue in right panel; click again to clear; auto-scrolls to first matching row
- **Bulk Export Buttons:** "Export All (Excel)" and "Export All (PDF)" with dedicated `BulkExportWorker(QThread)`; progress indicator during export
- **Consolidated Exporters:** Expanded `src/utils/exporters.py` with `export_bulk()` methods; Excel bulk produces 3 sheets (Summary, All Results, Failures Only); PDF bulk produces cover page + summary table + per-session detail pages
- **Export Cleanup:** Deleted `src/reports/` (6 files) and `reports/` (6 files) — duplicate exporters with broken imports; updated `reports_dialog.py` and test files to use consolidated API
- **QSS Styling:** Added `btn_accent` (bulk export buttons with blue border), `export_separator` styling for both dark and light themes
- **Export Bug Fix:** Fixed `_on_session_selected` crash on empty-state row (`columnSpan` guard); added error handling in `_start_export`; `QFileDialog` parent changed to `self.window()` for proper Windows display; logging added throughout export flow
- **Files Modified:** 10 files modified, 12 files deleted
- **Verification:** All compile checks pass, all imports OK, bulk export tested end-to-end with realistic data

### Session 11 — Reports Cleanup, Sidebar Redesign & Enterprise UI
**Status:** ✅ Complete

- **Reports Page Cleanup:** Filter bar (date range, status, model) replaces preset buttons; removed preset search; 2x2 export card grid (Excel/PDF + bulk); pie chart binding to analyzer; consolidated metrics
- **Sidebar SVG Redesign:** Replaced emoji icons with inline SVG (genset, gauge, list, sliders, play, download, logout); section headers (Main, Monitoring, System); brand header with logo + status pill; cyan accent active state; expand/collapse (200px ↔ 68px)
- **Enterprise UI Overhaul:** Config page pill badges (Type/Unit/Limit/Status pill kinds), model cards with ACTIVE pill, IO LED status dots, refined QSS (tables, scrollbars, cards, top-bar pill), industrial visual language
- **Model Mapping Tab:** Fixed blank space + oversized button footprint — removed dead `QSplitter` (single pane), 12 columns now size properly; added "＋ Add Register" + "⋮ Actions" toolbutton + db count label; right-panel form replaced with dialogs; row context menu (Edit/Move Up/Down/Remove); column Stretch sizing fills pane with zero trailing gap
- **Bug Fixes:** `content_panel` was added to tabs while widgets lived on orphaned page (QComboBox deleted) → now added to `page` layout; removed dead `_pill_for`/`_on_map_role_changed`/`_on_map_apply`; enabled NoEditTriggers on mapping table
- **Verification:** Model Mapping table at 1380px pane → viewport 1362, sumCols 1362, gap 0, no horizontal scroll; move up/down handlers verified

---

### Session 12 — Register Blocks (Bulk Read/Write)
**Status:** ✅ Complete (7/7 phases, all gates green)

- **DB (v4.3):** `register_blocks` table (start + count + register type + data type/scale/units + READ_ONLY/READ_WRITE access + group), nullable `block_id` on `plc_write_log` (FK ON DELETE SET NULL), `BlockRepo` CRUD with validation (`MAX_BLOCK_COUNT_REGS=1000`, `MAX_BLOCK_COUNT_BITS=2000`), migration `v4.3_register_blocks`
- **Drivers:** `PLCDriver.read_block()` shared base method (chunked 123 words/1968 bits per request, partial-error reporting); `write_block()` on Mitsubishi TCP/RTU (+ Delta/RTU inherit) — FC16/FC0F multi-chunk with per-chunk request tracking, never raises
- **Polling:** `ConnectionManager.blocks_to_poll` lock-guarded snapshots + `blocks_updated` signal; `BlockReading` in data model (stale-last-good on failure); `AppState.refresh_poll_config()` implemented (fixes latent AttributeError at config_page.py:1689); main window wires blocks + throttled comm-error toast
- **Bulk write:** `PLCWriteManager.execute_block_write()` — validation, shared write lock + `plc_busy`, read-back verify, audit before signal emission; signals `block_write_success/failed`
- **CONFIG UI:** Tab 4 "Register Blocks" with CRUD dialog (dynamic rules: bit types → BOOL + 2000 cap, DISCRETE/INPUT → access locked, word-swap only for 32-bit) + debounced filter; poll-list refresh after every change
- **I/O List viewer:** one tab per active block (after I/O groups), address/raw/decoded grid, FLOAT32 stride, bit ON/OFF labels + colors, stale marking; **Write to PLC** dialog gated ADMIN/SUPERVISOR with per-row validation and retry-on-failure
- **Tests:** 174 new tests in 6 files (`test_block_repo` 42, `test_block_driver` 37, `test_block_polling` 17, `test_block_write` 20, `test_block_config_tab` 27, `test_block_viewer` 31); gated suite **51 failed / 276 passed / 15 errors**, failing-ID diff vs baseline `new=0 fixed=0` after every phase

### Session 13 — Refinement (Test Debt, Lint, Bug Fixes, Block UX)
**Status:** ✅ Complete (R1–R4, all gates green)

- **R1 — Test debt eliminated:** rewrote `test_db.py` and `test_main_window.py` against live APIs/seed reality, fixture hygiene for `test_login_ui.py`, deleted legacy `test_manual_window.py` → new `test_manual_page.py`; baseline **66 failing IDs → 0** (gate 341 passed / 0 failed)
- **R2 — Static analysis clean:** autoflake (~120 unused imports) + E722/F841/E741/F541/E501/E111 fixes + `.flake8` config (whitespace-style rules excluded, `__init__.py` re-exports preserved); **flake8 2004 → 0**, compile clean
- **R3 — Functional fixes:** F1 `refresh_poll_config` (verified), F2 model mappings re-imported by name, F3 **atomic config import** (`Database.transaction()` now honored by `execute()` + `_apply_import` refactor), F4 message-source combo refresh, F5 acting-user `created_by`, F6 live write-log refresh (`write_log_updated` wired to Control tab), F8 safe label-clear timers; plus model-card selection now visibly checked and a distinct empty-password message; F7 template buttons remain the one known stub
- **R4 — Block write dialog UX:** Enter can no longer fire a bulk PLC write (no default/autoDefault buttons), read-back mismatches highlight the exact row with wrote/read tooltip, value cells locked while a write is in flight
- **Gates:** single-run **362 passed / 0 failed / 0 errors**, flake8 0, compile OK (suite grew 276 → 362 tests)
- **Note:** `IO_LIST_REFRESH_MS` tuned 2000 → 250 ms via an out-of-band edit; `test_io_only_tabs_unchanged` now derives its expectation from the constant

### Session 14 — UI Overhaul Phase 0/1 (Palette, Tokens, Theme Reactivity, Cleanup)
**Status:** ✅ Complete (all gates green)

- **Phase 0:** baseline recorded in `scratch/phase0_baseline.md` (362 passed, flake8 src 0); `before_*` screenshots for 7 pages × 2 themes + capture tool `scratch/ui_screenshot.py`
- **Palette:** teal/cyan overhaul of both live QSS via `scratch/palette_transform.py` (exact-value pre-maps + 195–245° hue rotation → 190° teal). Dark: bg `#0a171a`, sidebar `#11292c`, accent `#22d3ee`; Light: bg `#f4f7f6`, sidebar `#1a3c40`, accent `#0e7490`. Light gained dark's missing blocks (quality_dot, stat_value, confirm_dialog_message, Toast/Skeleton/Spinner, `tab:hover:!selected`); dropped `Inter` font
- **Tokens + reactivity:** `constants.py` token block synced to live QSS; `ThemeManager` rewritten (no `qss.replace` hacks, absolute themes path, `_ThemeBus.theme_changed` signal, `get_color()` token bridge, `current()`); charts/spinner/skeleton/toast/login_overlay/reports_page paint via tokens and recolor on theme change
- **De-hex 1.6:** `config_page` `_fg(token)` helper (access badges → pass/accent, limits/bypass → pass/warn/muted, message preview → semantic tokens; DB-persisted IO color defaults → stable `DARK_PASS`/`DARK_TEXT_MUTED`); `io_list_page` fallbacks aligned. Skipped `test_grid`/`plc_profile_dialog`/`manual_grid` — dead files reserved for the staged `dead_code_cleanup_plan.md`
- **Cleanup 1.7:** deleted `src/ui/styles/` (style_loader + 844-line legacy theme_manager + qss files), dead components `module_card`/`counter_panel`/`test_grid`, stale 0-test `test_settings_visual.py`; stripped dead QSS sections (Legacy NavBar, COUNTER PANEL, TEST GRID) from both themes, brace-balanced. **Kept** `editor_title` rule — still styles live `mapping_dialog`
- **Perf diagnosis (order artifact, pre-existing):** reversed-order subset costs 220s+ because `test_main_window` leaves ~23k widgets alive (`deleteLater` unprocessed) and Qt `setStyleSheet` then takes 30–40s/call (191s measured inside Qt); gate order runs `test_critical_fixes` first → same subset in 46s. Independently ruled out: QSS content (HEAD QSS equally slow), theme-bus connection, Python-side `apply()`
- **Gates:** pytest **362 passed / 0 failed** (100s), flake8 src 0, compile OK; 14 `after_*` screenshots verified programmatically (dark avg luminance 19–35, light 236–252, 0 mismatches). Known issue carried to Phase 2: light-theme breadcrumb overlap

### Session 15 — UI Overhaul Phase 2 (Breadcrumb Fix, Typography Pass)
**Status:** ✅ Complete (all gates green)

- **Breadcrumb overlap — root cause:** `Breadcrumb._rebuild()` removed crumbs via `takeAt` + `deleteLater()`, but deferred deletes are never flushed without a running event loop — old crumbs stayed visible as children and overlapped rebuilt ones (probe: 1→4→7→10 accumulating children, gen-1 `Home@15,8` under gen-2 `Home@15,4` → the 4px doubled text). **Fix:** hide before `deleteLater()` — probe now shows exactly 3 visible crumbs at every stage; screenshots show clean `Home > Config` in both themes
- **Same defect class hardened** in 7 live rebuild paths (`test_page` card grid/control buttons/counters, `model_page` model grid, `config_page` quality + status grids, `manual_page` control buttons): hide-before-delete (config grids: `itemAt` variant — hidden widgets occupy no space, auto-removed on delete)
- **Typography pass (both QSS):** `QPushButton` weight aligned 500→600 in dark (light already 600); `QLabel#connection_status_label` 15px→16px (off-scale straggler); tab parity — dark `QTabBar::tab` gained `500`, light `QTabBar::tab:selected` gained `600` (selected tab now semibold in both); dark `QGroupBox` + `warning_banner QLabel` gained the weights light already had; **added missing `QLabel#editor_title` rule to light.qss** (accent `#0e7490`) — last selector asymmetry between themes
- **Parity verification:** selector-set diff NONE, font-declaration diff NONE, font mismatches NONE across both themes (was: 1 selector + 5 font asymmetries)
- **Gates:** pytest **362 passed / 0 failed** (98s), flake8 src 0, compile OK; 14 `after_phase2_*` screenshots generated — luminance within 0.1 of Phase 1 baseline per page (no palette regression), breadcrumb strips visually verified clean in both themes

### Session 16 — Dead-Code Cleanup Plan Execution (Stages 1–3, 5)
**Status:** ✅ Complete (all gates green; Stage 4 deferred by decision)

- **Decisions applied:** D3 delete `migrations/*.sql` (migrations run inline in `database.py`); D4 Option A (dropped `seed_database` eager re-export; tests already import `src.db.seed` directly); D5 delete `skeleton.py` + `SpinnerOverlay` (`Spinner` itself is live via login_overlay); D6 delete stale `PLCMonitor.spec`; D7 delete the 9 zero-test visual/manual scripts; **D8 declined** (venv stays tracked); D9 retire push-model-to-PLC with the legacy island (feature was non-functional — called removed APIs)
- **Commit `8b22314`** — landed accumulated Phases 0–2 work first (920 files, precondition of the plan)
- **Stage 1 (`cccc4e7`):** 41 files / **−7,131 lines** — legacy UI island (app_window, login_*, settings_window, manual_test_*), 5 stubs, 12 dead components, 5 legacy dialogs, `config_manager`, `model_push_worker`, and their coupled tests (`test_login_ui`, `test_settings_window`, `test_login_visual`, `test_pass_fail` + 7 zero-test scripts). Repaired `test_main_window`'s `model_push_worker` patch → `test_model_selection_completes_when_disconnected`; found + removed missed orphan `src/ui/dialogs/password_utility.py`
- **Stage 2 (`5d1e551`):** deleted unused `parameter_repo.py` (zero refs — test_db's "parameters" tests target a different live feature), removed seed re-export from `src/db/__init__.py`, deleted 3 dead `migrations/*.sql`
- **Stage 3:** collapsed — stale test repairs pre-dated this session (suite was already green); verified 344-test collection with no dead-target references; the two former collection-error files are gone (gate no longer needs `--ignore` flags)
- **Stage 5 (`a46d8f0`):** −193/+18 — 6 dead `validators` functions + `icons.get_stroke_body` (`format_value` verified live, kept), 5 no-op config_page handlers + removed-form comments, orphaned `COLOR_NAVY/WHITE/AMBER`, unused `app_icon.png` (753 KB), `PLCMonitor.spec`, `plc_monitor_config.json`; `.gitignore` fixed for `reports_output/`; README Configuration section rewritten (config.json → DB-backed) + project tree corrected; `pyrightconfig.json` consolidated into `pyproject [tool.pyright]`; `description.md` marked historical
- **Stage 4 deferred (as chosen):** `ConnectionManager.comm_error` and `PLCWriteManager` write-result signals left untouched pending D1/D2 product decisions
- **Test trajectory:** 362 → **344 passed / 0 failed** (−18 legacy tests, all deliberate; 0 collection errors); flake8 src 0; screenshot luminance **identical** to Phase 1 baseline per page (zero visual regression)

### Session 17 — Cleanup Stage 4 + Config F7
**Status:** ✅ Complete (all gates green; cleanup plan now fully executed)

- **D1 (`comm_error`):** verified already wired — `main_window.py` connects it to a throttled error toast (1 per 5 s); plan's "zero listeners" premise was stale. Nothing to do
- **D2 (write-result signals):** audit found `block_write_*`/`plc_busy`/`verify_failed`/`write_log_updated` all live (block dialog, I/O page, config audit list), but `write_success`/`write_failed` had **zero listeners** — control writes were silent on TEST page. Wired both to MainWindow toasts (`_on_write_success`/`_on_write_failed`); manual page's misleading immediate "Write Success" box reworded to "Write Request Sent" (it fires on dispatch, not completion — box call retained per tests)
- **F7:** removed the fake "Quick Setup Templates" buttons + `_load_template` simulation stub from the Export/Import tab — no template data ever existed
- **Tests:** +3 (`TestWriteResultWiring`: signal→handler connection, success/failure toast) → **347 passed / 0 failed**, flake8 src 0, screenshot luminance identical to baseline
- **Commits:** `a63c6ee` (Stage 4), `caa9b4d` (F7)

---

## Feature Checklist

- [x] Real-time PLC data monitoring
- [x] Multi-brand support (Mitsubishi, Delta, Inovance)
- [x] Modbus TCP and RTU protocols
- [x] Configurable polling intervals
- [x] SQLite database with WAL mode
- [x] User authentication (3 roles: admin, supervisor, operator)
- [x] Role-based access control
- [x] Dark and light theme support
- [x] Expandable/collapsible sidebar navigation
- [x] Breadcrumb navigation
- [x] Keyboard shortcuts (Ctrl+1-7, F11, Escape)
- [x] Pass/fail evaluation logic
- [x] Session recording and history
- [x] Report generation (Excel, PDF)
- [x] Date range filtering on reports
- [x] Summary statistics dashboard
- [x] Pie chart and bar chart visualizations
- [x] Real-time sparkline trend lines on cards
- [x] I/O list monitoring with LED indicators
- [x] Manual register read/write interface
- [x] Config wizard for first-run setup
- [x] Mock PLC server for development
- [x] Seed script for test data
- [x] Drag-to-reorder dashboard cards (admin)
- [x] Responsive layout with auto-collapse
- [x] Animated spinner for loading states
- [x] Skeleton loaders for placeholder content
- [x] Toast notification system (non-blocking)
- [x] Property-based QSS theming (no hardcoded colors)
- [x] Font size adjustment (Small/Medium/Large)
- [x] High contrast accessibility mode
- [x] Tab order and accessibility labels throughout
- [x] Thread-safe PLC connection lifecycle (interruptible stop, signal cleanup)
- [x] Robust error handling (no silent exception swallowing)
- [x] Cross-reconnect data model persistence
- [x] Fullscreen toggle with icon state (⛶/✕)
- [x] Theme preview cards in Settings (visual preview)
- [x] Font size active state indicators
- [x] High contrast mode without QSS accumulation
- [x] Single-click session selection in Reports
- [x] Export buttons disabled until session selected
- [x] Pie chart auto-populates on search
- [x] Comments section hidden until session selected
- [x] Right panel responsive width (220-260px)
- [x] Admin-only label styled as amber pill
- [x] F5/F9 global shortcuts for START/STOP
- [x] Param card drag handle renders correctly (⋮)
- [x] Audit trail shows username (not ID)
- [x] Empty state message for reports
- [x] Cycle time label only visible on TEST page
- [x] PLC status label max width with ellipsis
- [x] Sidebar collapse/expand chevron direction fixed
- [x] Sidebar tooltips on both icon and label
- [x] Config tab Unicode icons (no emoji)
- [x] Message register table column auto-sizing
- [x] 10-column results table (Session#, Date, Time, Module, Parameter, Measured, Min, Max, User, Result)
- [x] Bulk results view (all sessions in date range, no download needed)
- [x] Session highlight on results table (click to highlight, click again to clear)
- [x] Bulk export to Excel (3 sheets: Summary, All Results, Failures Only)
- [x] Bulk export to PDF (cover page + summary + per-session detail)
- [x] Limit min/max snapshot per test result (DB migration v4.1)
- [x] Consolidated exporters (single src/utils/exporters.py, no duplicates)
- [x] Export button state management (disabled until session/date range selected)
- [x] Reports filter bar (date range, status, model) with preset removal
- [x] 2x2 export card grid (Excel/PDF + bulk variants)
- [x] Pie chart bound to report data
- [x] SVG sidebar icons (no emoji) with section headers and brand status pill
- [x] Config page pill badges (Type/Unit/Limit/Status)
- [x] Model cards with ACTIVE pill indicator
- [x] I/O list LED status dots
- [x] Model Mapping table fills pane (zero trailing gap, no horizontal scroll)
- [x] Register actions via toolbar + row context menu (Edit/Move/Remove)
- [x] Register blocks — bulk address-range definitions with CRUD (CONFIG tab)
- [x] Register block polling (chunked, stale-last-good, hot-reloaded)
- [x] Bulk register/coil write (FC16/FC0F) with read-back verification
- [x] Block write audit trail (plc_write_log.block_id + BLOCK_WRITE reason)
- [x] I/O List block viewer tabs (live values, FLOAT32 stride, bit labels, stale badge)
- [x] Bulk write dialog with role gating (ADMIN/SUPERVISOR) and retry-on-failure
- [x] Zero-failure regression suite (362 tests) with flake8-clean source
- [x] Atomic config import (all-or-nothing rollback) + mappings restored by name
- [x] Block write safety: explicit-click write, verify-mismatch row highlight, write-in-flight edit lock

- Start the mock PLC server (interactive mode):
- PS C:\Users\Nexgensis\PRATHAMESH\iot_Hardware\plc_monitor\tests> python .\mock_plc_server.py --port 5020 --sim-mode interactive
