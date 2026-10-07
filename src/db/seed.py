"""
seed.py — Universal PLC Monitor
Minimal database seeding for a fresh installation.

Design intent (Schema v4.0):
  - Seeds ONLY the minimum required to start the app.
  - NO hardcoded register addresses, model names, or parameters.
  - NO D21 messages, NO model_register_map rows.
  - Admin must configure everything via the CONFIG screen.
  - first_run=1 in app_config triggers the setup wizard on first launch.
"""
import logging
import bcrypt

from src.db.database import Database

logger = logging.getLogger(__name__)


def seed_database(db: Database) -> None:
    """
    Seeds the database with the absolute minimum required to boot the app.

    Idempotent: checks users table first; exits immediately if data exists.
    Nothing is seeded if the database has already been initialized.

    Seeded data:
        1. Two users: admin (ADMIN) and operator (OPERATOR)
        2. PLC profile row (id=1) with empty host — must be configured by admin
        3. App config defaults: theme, first_run flag, poll interval
    """
    existing_users = db.fetchall("SELECT id FROM users LIMIT 1")
    if existing_users:
        logger.info("seed_database: users table already populated — skipping seed.")
        return

    logger.info("seed_database: empty database detected — seeding defaults...")

    # -------------------------------------------------------------------------
    # 1. Create default users
    #    Passwords are hashed with bcrypt (cost factor 12).
    # -------------------------------------------------------------------------
    admin_hash = bcrypt.hashpw(b"Admin@1234", bcrypt.gensalt(rounds=12)).decode("utf-8")
    op_hash    = bcrypt.hashpw(b"Op@1234",    bcrypt.gensalt(rounds=12)).decode("utf-8")

    db.execute(
        "INSERT INTO users (username, role, password_hash) VALUES (?, ?, ?)",
        ("admin", "ADMIN", admin_hash),
    )
    db.execute(
        "INSERT INTO users (username, role, password_hash) VALUES (?, ?, ?)",
        ("operator", "OPERATOR", op_hash),
    )
    logger.info("seed_database: users created — admin, operator")

    # -------------------------------------------------------------------------
    # 2. PLC profile (id=1, single row)
    #    host is intentionally empty — admin must configure in CONFIG screen.
    #    No register addresses are stored here.
    # -------------------------------------------------------------------------
    db.execute(
        """
        INSERT OR IGNORE INTO plc_profile (
            id,
            brand,
            protocol,
            host,
            port,
            slave_id,
            poll_interval_ms,
            timeout_ms,
            reconnect_delay_ms,
            max_retries
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (1, "mitsubishi", "TCP", "", 502, 1, 500, 3000, 3000, 3),
    )
    logger.info("seed_database: plc_profile created (host='' — not configured)")

    # -------------------------------------------------------------------------
    # 3. App config defaults
    #    first_run=1 → triggers setup wizard on next launch.
    # -------------------------------------------------------------------------
    config_defaults: list[tuple[str, str]] = [
        ("theme",               "dark"),
        ("first_run",           "1"),    # 1 = show setup wizard
        ("poll_interval_ms",    "500"),
        ("max_dashboard_cards", "20"),
    ]
    db.executemany(
        "INSERT OR IGNORE INTO app_config (key, value) VALUES (?, ?)",
        config_defaults,
    )
    logger.info("seed_database: app_config defaults written (%d keys)", len(config_defaults))

    # -------------------------------------------------------------------------
    # Summary output
    # -------------------------------------------------------------------------
    print("[OK] Users:      admin (ADMIN) + operator (OPERATOR) created")
    print("[OK] PLC profile: not configured (host is empty — set in CONFIG screen)")
    print("[OK] App config:  theme=dark | first_run=1 | poll_interval_ms=500")
    print()
    print("Database initialized. No registers or models preset.")
    print("Login as admin -> go to CONFIG to set up the register library and models.")

    logger.info("seed_database: complete.")
