# Handoff Context — PLC Monitor

**Snapshot date:** 2026-10-09
**Branch:** `main` (8 commits ahead of `origin/main`, **not pushed**)
**HEAD:** `70b87a2` — docs: record cleanup stage 4 + F7 in STATUS (session 17)
**Suite:** 347 passed / 0 failed · flake8 src 0 · compile OK

This file is a point-in-time handoff snapshot. The authoritative history is `STATUS.md` (session log, sessions 1–17) — read it first.

---

## 1. What this project is

Desktop app for monitoring/testing PLCs: PyQt6 + SQLite (WAL) + pymodbus, bcrypt auth (admin/supervisor/operator), pass/fail evaluation, Excel/PDF reporting.

Run: `venv\Scripts\activate` → `python main.py`
Mock PLC (no hardware): `python -m src.plc.mock_server --host 127.0.0.1 --port 5020 --mode cycling`, then connect brand=Mitsubishi/TCP at 127.0.0.1:5020.
Seed: `python scripts/seed_two_wheeler.py --db plc_monitor.db --reset`
Mock server docs: `docs/mock_plc_server.md`.

## 2. Current state of the work

Three arcs have been completed since the May 2026 v1 merge:

1. **Sessions 1–13 (foundation → refinement)** — features, bug-fix sweeps, reports rewrite, register blocks (bulk read/write), test-debt elimination, flake8 cleanup. Details in `STATUS.md`.
2. **Sessions 14–15 — UI overhaul phases 0–2** (`8b22314`): teal/cyan palette transform of both live QSS, design tokens + `ThemeManager` rewrite with a `_ThemeBus.theme_changed` signal (charts/spinner/toast/etc. recolor on theme change), breadcrumb overlap root-cause fix, typography parity between dark/light.
3. **Sessions 16–17 — dead-code cleanup plan, fully executed** (`cccc4e7`, `5d1e551`, `a46d8f0`, `a63c6ee`, `caa9b4d`): −7k lines in stage 1 alone (legacy UI island, dead components/dialogs/stubs, push worker), plus stages 2/4/5 and F7. Every decision D1–D9 in the plan is resolved; nothing is deferred.

**No work is in progress.** Working tree is clean except untracked local artifacts (§6).

## 3. Architecture map

```
main.py                  entry point; wires MainWindow, graceful shutdown
                         (stops write_manager BEFORE connection_manager)
schema.sql               reference schema (live migrations run inline in
                         src/db/database.py — _run_migrations(), currently v4.3)
src/db/                  one repo per table; Database is thread-safe singleton,
                         WAL, Database.transaction() honoured by execute()
src/plc/                 base_driver (shared read_block), mitsubishi/delta (+RTU),
                         driver_factory (has invalidate() for param changes),
                         connection_manager (poll loops, blocks_to_poll,
                           blocks_updated signal), write_manager (single write
                           lock + plc_busy, read-back verify, audit-then-signal),
                         data_model (PLCDataModel, stored in AppState)
src/logic/               pass_fail_evaluator, session_controller
src/ui/main_window.py    signal hub — toast wiring, page nav, shortcuts
src/ui/app_state.py      AppState; refresh_poll_config() must be called after
                         any change to registers/blocks/IO (hot-reload)
src/ui/theme_manager.py  ThemeManager + token bus (get_color/current); no
                         qss.replace hacks — do not reintroduce them
src/ui/pages/            config_page.py is the big one (88 KB, 6 tabs)
src/utils/constants.py   design tokens mirror the live QSS; exporters.py is the
                         single export implementation (Excel + PDF, session + bulk)
assets/themes/           dark.qss, light.qss — the two live stylesheets
tests/                   15 files, 347 tests; tests/mock_plc_server.py helper
```

Deleted and **not to be resurrected**: `src/ui/styles/`, `src/reports/`, `reports/`, `migrations/*.sql`, `src/db/parameter_repo.py`, `config.json` (all config is DB-backed), skeleton loaders/`SpinnerOverlay`, push-model-to-PLC worker, `PLCMonitor.spec`, `description.md` (marked historical).

## 4. Verification gates

Run before declaring any change done:

```powershell
venv\Scripts\python.exe -m pytest -q          # expect 347 passed, ~2 min
venv\Scripts\python.exe -m flake8 src         # expect exit 0
venv\Scripts\python.exe -m compileall -q src main.py
```

- **Known flake:** `tests/test_block_polling.py::TestBlockFailure::test_failure_keeps_last_good_as_stale` failed once in a full-suite run on 2026-10-09 and passed on immediate re-run (full suite green, and file green in isolation). Order/timing sensitive — treat a single occurrence as a flake, investigate only if it repeats.
- **Perf artifact (pre-existing, diagnosed in session 14):** running `test_main_window` late in the order costs minutes because it leaves ~23k widgets alive (`deleteLater` unprocessed) and Qt `setStyleSheet` then takes 30–40 s/call. Order-dependent, not a product regression.
- Visual regression: `scratch/ui_screenshot.py` captures per-page/per-theme shots; luminance must match the phase baselines in `scratch/phase0_baseline.md`.

## 5. Conventions (learned the hard way — follow them)

- **QSS:** never inline `setStyleSheet()` with hardcoded colors. Use object names, dynamic properties, or theme tokens (`_fg(token)` / `ThemeManager.get_color()`). Both `dark.qss` and `light.qss` must stay in selector and font parity.
- **Rebuild paths:** always hide a widget before `deleteLater()`. Deferred deletes never flush without an event loop; the bug shows up as overlapping ghost widgets (breadcrumb fix, session 15 — hardened in 7 paths).
- **Exceptions:** no bare `except: pass`. Count/report or re-raise.
- **PLC writes:** never allow Enter/autoDefault to fire a write; keep verify-mismatch row highlighting and the in-flight edit lock (session 13/14 work).
- **Tests:** match live APIs; no stale expectations. Gate must stay 0 failed / 0 errors, and remember `IO_LIST_REFRESH_MS` is 250 ms.
- **Commits:** small, scoped, imperative subject (`cleanup stage 4: ...`), and update `STATUS.md` in a separate `docs:` commit at the end of each session.
- **Do not push** to `origin/main` unless explicitly asked.

## 6. Local/untracked artifacts

| Path | What it is |
|---|---|
| `.opencode/` | opencode config + `tester` skill (`.opencode/skill/tester/SKILL.md`) — untracked by choice |
| `plc_monitor.db.bak_phase1` | manual DB backup from phase 1 — untracked, safe to delete |
| `plc_monitor.db` | live DB with seed data (tracked-by-gitignore) |
| `scratch/` | throwaway tooling: `palette_transform.py`, `ui_screenshot.py`, `probe_breadcrumb.py`, `revalidate_cleanup.py`, `phase0_baseline.md`, `.qss.mine` copies |

## 7. Open items / likely next moves

Nothing is committed to these — candidate backlog:

1. **Push the 8 local commits** (needs explicit go-ahead).
2. **Light theme coverage:** palette work verified dark-first; light was made parity-complete but only screenshot-verified at fixed sizes.
3. **`config_page.py` size (88 KB):** the largest file by far; a natural refactor target if more config tabs are added.
4. **Flaky block-polling test** (§4) — worth pinning down if it recurs.
5. **Playwright UI tests:** README still references `test_login_visual.py`, which was deleted in cleanup stage 1 — README testing section is stale.
6. **`venv/` is tracked in git** (decision D8 — deliberately kept). Revisit only as a decision, not an accident.
7. Real-hardware validation is untested in this environment (only the mock PLC server has been exercised).

## 8. Key documents

- `STATUS.md` — session-by-session history + feature checklist (source of truth)
- `README.md` — install/run/shortcuts/structure (testing section stale, see §7.5)
- `docs/mock_plc_server.md` — register maps and simulation modes
- `description.md` — historical requirements, explicitly marked obsolete
- `.opencode/skill/tester/SKILL.md` — E2E test procedure and known-issue list
