import sys
import socket
import logging
from PyQt6.QtWidgets import QApplication

from src.db.database import Database
from src.db.seed import seed_database
from src.db.user_repo import UserRepository
from src.db.model_repo import ModelRepository
from src.db.parameter_repo import ParameterRepository
from src.db.session_repo import SessionRepository
from src.db.plc_profile_repo import PLCProfileRepository
from src.plc.driver_factory import PLCDriverFactory
from src.plc.data_model import PLCDataModel
from src.plc.connection_manager import ConnectionManager
from src.plc.write_manager import PLCWriteManager
from src.logic.pass_fail_evaluator import PassFailEvaluator
from src.ui.app_state import AppState
from src.ui.main_window import MainWindow

def check_server(host="127.0.0.1", port=5020):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((host, port))
        s.close()
        return True
    except (ConnectionRefusedError, TimeoutError):
        # We will return False to let warning log handle indicating mock server is missing
        return False

def main():
    if not check_server():
        print("Start mock server first")
        print("Run `python mock_plc_server.py` in another terminal, configured to 5020.")
        sys.exit(1)
        
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    app = QApplication(sys.argv)
    
    # 2. Init real DB + seed
    db = Database("plc_monitor.db")
    db.init_db()
    seed_database(db)

    # 3. Build AppState with all repos
    state = AppState.get_instance()
    state.db = db
    state.user_repo = UserRepository(db)
    state.model_repo = ModelRepository(db)
    state.param_repo = ParameterRepository(db)
    state.session_repo = SessionRepository(db)
    state.plc_profile_repo = PLCProfileRepository(db)
    
    # 4. Load MI-7646AZ full config
    model_configs = state.model_repo.get_all_models()
    model = next((m for m in model_configs if m["name"] == "MI-7646AZ"), model_configs[0])
    
    model_id = model["id"]
    params = state.param_repo.get_parameters(model_id)
    register_map = state.param_repo.get_register_map(model_id)
    limits_map = state.param_repo.get_limits_map(model_id)
    
    full_model_config = {
        "model": model,
        "parameters": params,
        "register_map": register_map,
        "limits_map": limits_map
    }
    state.set_model(full_model_config)
    
    admin_user = state.user_repo.get_by_username("admin")
    if not admin_user:
         admin_user = {"id": 1, "username": "admin", "role": "ADMIN"}
    state.set_user(admin_user)
    
    plc_profiles = state.plc_profile_repo.get_all()
    profile = plc_profiles[0] if plc_profiles else {
        "brand": "mitsubishi",
        "protocol": "TCP",
        "host": "127.0.0.1",
        "port": 5020,
        "poll_interval_ms": 500,
        "write_verify_delay_ms": 100,
        "max_write_retries": 3,
        "default_state_register": 20,
        "default_start_coil": 300,
        "default_overall_result_register": 45,
        "default_ok_count_register": 90,
        "default_ng_count_register": 91
    }
    state.set_plc_profile(profile)

    # 5. Create PLCDriverFactory
    driver = PLCDriverFactory.create(
        brand=profile["brand"],
        protocol=profile["protocol"],
        host=profile["host"],
        port=profile["port"],
        serial_config={}
    )
    
    # 6. Create PLCDataModel
    data_model = PLCDataModel(profile, full_model_config["model"], full_model_config["parameters"])

    # 7. Create ConnectionManager
    conn_mgr = ConnectionManager(
        driver=driver,
        data_model=data_model,
        poll_interval_ms=profile.get("poll_interval_ms", 500)
    )
    state.connection_manager = conn_mgr
    
    # 8. Create PLCWriteManager
    write_mgr = PLCWriteManager(driver, data_model)
    state.write_manager = write_mgr
    
    # 9. PassFailEvaluator internally created by MainWindow
    # 10. Load stylesheet
    try:
        from src.ui.styles.style_loader import load_stylesheet
        stylesheet = load_stylesheet()
        app.setStyleSheet(stylesheet)
    except Exception as e:
         print(f"Warning: stylesheet not loaded ({e})")
         
    # 11. Create + show MainWindow
    main_win = MainWindow(state)
    main_win.show()
    
    # 12. Start ConnectionManager
    conn_mgr.start()
    
    # 13. Print checklist
    print("=== LIVE DASHBOARD TEST ===")
    print(f"Mock PLC: {profile['host']}:{profile['port']}")
    print(f"Model: {model['name']} | Params: {len(params)}")
    print("")
    print("Watch for:")
    print("  [ ] PLC banner turns GREEN")
    print("  [ ] Grid cells update every 500ms")
    print("  [ ] WITHOUT LOAD and WITH LOAD sections visible")
    print("  [ ] Test cycle: IDLE→RUNNING→COMPLETE")
    print("  [ ] Result row shows PASS (green) or FAIL (red)")
    print("  [ ] OK/NG counts increment correctly")
    print("  [ ] Cycle time updates each cycle")
    print("  [ ] Message bar shows state transitions")
    print("  [ ] Reset button clears counts in PLC + UI")
    print("")

    # 14. Execute app
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
