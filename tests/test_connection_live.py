# tests/test_connection_live.py
"""
LIVE CONNECTION TEST
--------------------
Run against tests/mock_plc_server.py.
Tests heartbeat, register reading, limit writing, model block writing,
and triggers a full test cycle.

Usage: python tests/test_connection_live.py [--brand delta]
"""

import sys
import time
import argparse
import colorama
from colorama import Fore, Style

# Add root to sys.path
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.plc.driver_factory import PLCDriverFactory
from src.utils.constants import (
    STATE_LABELS,
    PLC_BRAND_MITSUBISHI,
    PLC_BRAND_DELTA,
    PLC_PROTOCOL_TCP
)

colorama.init()

def log(msg, color=Fore.WHITE):
    print(f"{color}{msg}{Style.RESET_ALL}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", choices=['mitsubishi', 'delta'], default='mitsubishi')
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5020)
    args = parser.parse_args()

    log(f"=== PLC LIVE CONNECTION TEST ({args.brand.upper()}) ===", Fore.CYAN)
    
    # 1. Connect
    driver = PLCDriverFactory.create(args.brand, PLC_PROTOCOL_TCP, args.host, args.port)
    if not driver.connect():
        log(f"FAILED: Could not connect to {args.host}:{args.port}", Fore.RED)
        return

    log(f"CONNECTED to mock server at {args.host}:{args.port}\n", Fore.GREEN)

    # 3. Read heartbeat
    log("Reading Heartbeat (D0)...")
    for i in range(3):
        res = driver.read_holding_registers(0, 1)
        if res.success:
            log(f"  [{i+1}/3] Heartbeat: {res.values[0]}")
        time.sleep(1)
    print()

    # 4. Read parameters table
    log("Reading Parameter Measured Values (D100-D102)...")
    res = driver.read_holding_registers(100, 3)
    if res.success:
        print(f"{'Param':<10} | {'D Reg':<6} | {'Modbus':<7} | {'Raw':<6}")
        print("-" * 40)
        for idx, val in enumerate(res.values):
            d_reg = 100 + idx
            mb_addr = driver.d_to_modbus(d_reg)
            print(f"Param {idx+1:<3} | {d_reg:<6} | {mb_addr:<7} | {val:<6}")
    print()

    # 5. Read state
    log("Checking State (D20)...")
    res = driver.read_holding_registers(20, 1)
    if res.success:
        state_name = STATE_LABELS.get(res.values[0], "UNKNOWN")
        log(f"  Current State: {state_name} ({res.values[0]})")
    print()

    # 6. Write Limits
    log("Testing Write Limit Registers (D260/261)...")
    w_min = 3800
    w_max = 6200
    
    # Write Min
    res_w = driver.write_holding_register(260, w_min)
    time.sleep(0.2)
    res_r = driver.read_holding_registers(260, 1)
    if res_r.success and res_r.values[0] == w_min:
        log(f"  D260 Min Limit: Written {w_min}, Read {res_r.values[0]} - OK", Fore.GREEN)
    else:
        log(f"  D260 Min Limit: Verification FAILED", Fore.RED)

    # Write Max
    res_w = driver.write_holding_register(261, w_max)
    time.sleep(0.2)
    res_r = driver.read_holding_registers(261, 1)
    if res_r.success and res_r.values[0] == w_max:
        log(f"  D261 Max Limit: Written {w_max}, Read {res_r.values[0]} - OK", Fore.GREEN)
    else:
        log(f"  D261 Max Limit: Verification FAILED", Fore.RED)
    print()

    # 7. Write Model Block (D3000)
    log("Testing Model Block Write (D3000-D3005)...")
    block = [37, 38, 37, 2, 1, 0]
    res_w = driver.write_holding_registers(3000, block)
    time.sleep(0.2)
    res_r = driver.read_holding_registers(3000, 6)
    if res_r.success and res_r.values == block:
        log(f"  Model Block: {res_r.values} - OK", Fore.GREEN)
    else:
        log(f"  Model Block: Verification FAILED (Read: {res_r.values})", Fore.RED)
    print()

    # 8. Trigger Test Start (M300)
    log(f"Triggering Test Start (M300 Coil)...", Fore.YELLOW)
    res_c = driver.write_coil(300, True)
    if not res_c.success:
        log(f"FAILED to trigger start: {res_c.error}", Fore.RED)
        return

    # 9. Poll State Machine
    log("Polling D20 for test completion (max 15s)...", Fore.CYAN)
    last_state = -1
    start_poll = time.time()
    while time.time() - start_poll < 15:
        res = driver.read_holding_registers(20, 1)
        if res.success:
            curr_state = res.values[0]
            if curr_state != last_state:
                log(f"  >> State changed: {STATE_LABELS.get(curr_state, 'UNKNOWN')} ({curr_state})")
                last_state = curr_state
            
            if curr_state == 6: # COMPLETE
                log("\nPLC reports COMPLETE!", Fore.GREEN)
                break
        time.sleep(0.5)

    if last_state != 6:
        log("TIMED OUT waiting for COMPLETE state.", Fore.RED)
        return

    # 10. Print final results
    log("\n=== FINAL TEST RESULTS ===", Fore.CYAN)
    res_vals = driver.read_holding_registers(100, 3)
    res_code = driver.read_holding_registers(30, 3)
    res_over = driver.read_holding_registers(45, 1)
    
    if res_vals.success and res_code.success:
        print(f"{'Param':<10} | {'Value':<6} | {'Result':<10} | {'Target Range':<15}")
        print("-" * 55)
        ranges = ["3800-6200", "4000-6000", "500-2000"]
        for i in range(3):
            val = res_vals.values[i]
            code = "PASS" if res_code.values[i] == 1 else "FAIL"
            color = Fore.GREEN if code == "PASS" else Fore.RED
            print(f"Param {i+1:<3} | {val:<6} | {color}{code:<10}{Style.RESET_ALL} | {ranges[i]}")
    
    if res_over.success:
        over_res = "PASS" if res_over.values[0] == 1 else "FAIL"
        over_color = Fore.GREEN if over_res == "PASS" else Fore.RED
        log(f"\nOVERALL BATCH RESULT: {over_color}{over_res}{Style.RESET_ALL}", Style.BRIGHT)

    # Done
    driver.disconnect()
    log("\nLIVE TEST FINISHED.", Fore.CYAN)

if __name__ == "__main__":
    main()
