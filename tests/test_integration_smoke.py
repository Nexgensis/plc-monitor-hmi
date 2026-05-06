"""
Integration smoke test for the PLC Monitor database layer.
Validates the full workflow from initialization to session recording.
"""
import os
import sys
import colorama
from colorama import Fore, Style

# Ensure we can import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.database import Database
from src.db.plc_profile_repo import PLCProfileRepository
from src.db.model_repo import ModelRepository
from src.db.parameter_repo import ParameterRepository
from src.db.session_repo import SessionRepository
from src.db.report_repo import ReportRepository
from src.db.seed import seed_database
import bcrypt

colorama.init()

def log_step(name, success, info=""):
    status = f"{Fore.GREEN}PASSED{Style.RESET_ALL}" if success else f"{Fore.RED}FAILED{Style.RESET_ALL}"
    print(f"[*] {name:.<40} {status} {info}")
    if not success:
        sys.exit(1)

def run_smoke_test():
    db_path = "smoke.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    print(f"\n{Fore.CYAN}Starting Integration Smoke Test (Isolated DB: {db_path}){Style.RESET_ALL}\n")

    try:
        # 1. Fresh DB + Seed
        db = Database(db_path)
        db.initialize()
        seed_database(db)
        log_step("Database Initialization & Seeding", True)

        # 2. Setup Repos
        profile_repo = PLCProfileRepository(db)
        model_repo = ModelRepository(db)
        param_repo = ParameterRepository(db)
        session_repo = SessionRepository(db)
        report_repo = ReportRepository(db)

        # 3. Load PLC Profile
        profile = profile_repo.get_profile()
        is_empty = profile["host"] == ""
        log_step("PLC Profile: Default Host Empty", is_empty, f"Host: '{profile['host']}'")

        # 4. Configured Check
        is_cfg = profile_repo.is_configured()
        log_step("Profile: is_configured() == False", not is_cfg)

        # 5. Update Host
        profile_repo.update_profile(host="192.168.1.30")
        is_cfg = profile_repo.is_configured()
        log_step("Profile: update_profile(IP) -> True", is_cfg)

        # 6. Authenticate
        user = db.fetchone("SELECT * FROM users WHERE username = 'admin'")
        auth_ok = bcrypt.checkpw(b"Admin@1234", user["password_hash"].encode('utf-8'))
        log_step("Authentication: admin login", auth_ok)

        # 7. D21 Messages
        msgs = profile_repo.get_d21_messages()
        log_step("D21 Messages Loaded", len(msgs) > 0, f"Count: {len(msgs)}")

        # 8. All Models
        models = model_repo.get_all_models()
        log_step("Models Seeded", len(models) == 4)

        # 9. Load SW-0256A Full Config
        m_256a = next(m for m in models if m["name"] == "SW-0256A")
        config = model_repo.get_full_model_config(m_256a["id"])
        log_step("Model Config: SW-0256A Loaded", config is not None)

        # 10. Print Register Map Table
        print(f"\n{Fore.YELLOW}Register Map (SW-0256A):{Style.RESET_ALL}")
        print(f"{'Param':<15} | {'Measured':<8} | {'Result':<6} | {'Min Reg':<8} | {'Max Reg':<8}")
        print("-" * 55)
        reg_map = config["register_map"]
        for name, regs in reg_map.items():
            print(f"{name:<15} | {regs['measured']:<8} | {regs['result']:<6} | {regs['limit_min']:<8} | {regs['limit_max']:<8}")
        
        # 11. Assert Register Numbers (D-registers, not Modbus addresses)
        d_val_ok = reg_map["Dipper LOW"]["measured"] == 100
        log_step("Register Map: Uses D Numbers", d_val_ok, "(D100 -> 100)")

        # 12. Load SW-0256U module check
        m_256u = next(m for m in models if m["name"] == "SW-0256U")
        config_u = model_repo.get_full_model_config(m_256u["id"])
        has_wiper = "WIPER MODULE" in config_u["module_groups"]
        log_step("Model Config: SW-0256U Wiper check", has_wiper)

        # 13. Open/Close Session
        sid = session_repo.open_session(m_256a["id"], user["id"])
        session_repo.record_result(sid, 1, "P1", "M1", 10.5, 0.0, 100.0, "PASS")
        session_repo.record_result(sid, 2, "P2", "M1", 5.5, 0.0, 100.0, "FAIL")
        session_repo.close_session(sid, 1, 1, 1)
        log_step("Session Workflow: Open/Record/Close", True)

        # 14. Report Summary
        summary = report_repo.get_sessions_summary(limit=1)[0]
        log_step("Report: Session Summary Generated", True, f"Pass Rate: {summary['pass_rate_pct']}%")

        # 15. New Model CRUD
        test_mid = model_repo.create_model("TEST-XYZ")
        param_repo.add_parameter(test_mid, "T1", "T1", "M", 0)
        log_step("CRUD: Create Model + Param", True)

        # 16. Delete Cascade
        model_repo.delete_model(test_mid)
        exists = db.fetchone("SELECT id FROM models WHERE name = 'TEST-XYZ'")
        p_exists = db.fetchone("SELECT id FROM model_parameters WHERE model_id = ?", (test_mid,))
        log_step("CRUD: Delete Model (Cascade Check)", not exists and not p_exists)

        print(f"\n{Fore.CYAN}Smoke Test Completed Successfully!{Style.RESET_ALL}\n")

    except Exception as e:
        print(f"\n{Fore.RED}ERROR during smoke test: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close_all()
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    run_smoke_test()
