"""
mock_plc_server.py — Two-Wheeler Handle Test Fixture Mock PLC Server

Simulates a Modbus TCP PLC for testing two-wheeler handle assemblies
(left and right). Includes realistic analog sensor simulation with noise,
digital I/O simulation, and a test cycle state machine.

Register Map:
  D0       - Heartbeat (auto-increment)
  D21      - Machine State (0=IDLE, 99=RUNNING, 1=PASS, 2=FAIL)
  D22      - Overall Result (1=PASS, 2=FAIL)
  D23      - OK Count
  D24      - NG Count
  D25      - Batch Count
  D100-106 - Left Handle analog parameters
  D111-118 - Right Handle analog parameters
  M100     - Start Test trigger (write 1 to start)
  M101     - Stop Test trigger
  M102     - Reset Batch trigger
  M110-118 - Digital output states

Usage:
  python tests/mock_plc_server.py --port 5020 --sim-mode interactive --fail-rate 0.1
"""
import asyncio
import logging
import math
import random
import argparse
import time
import threading
from datetime import datetime
from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("MockPLC")

# ---------------------------------------------------------------------------
# Register addresses
# ---------------------------------------------------------------------------
D_HEARTBEAT = 0
D_MSG_STATE = 21
D_RESULT = 22
D_OK_COUNT = 23
D_NG_COUNT = 24
D_BATCH_COUNT = 25

LEFT_START = 100
LEFT_END = 106
RIGHT_START = 111
RIGHT_END = 118

# Mitsubishi coil offset: M100 → Modbus coil 101 (base=1 + plc_address)
# Holding registers have no offset: D100 → Modbus holding 100
MITSUBISHI_COIL_BASE = 1

M_START_TEST  = MITSUBISHI_COIL_BASE + 100  # coil 101
M_STOP_TEST   = MITSUBISHI_COIL_BASE + 101  # coil 102
M_RESET_BATCH = MITSUBISHI_COIL_BASE + 102  # coil 103
M_LEFT_IND    = MITSUBISHI_COIL_BASE + 110  # coil 111
M_RIGHT_IND   = MITSUBISHI_COIL_BASE + 111  # coil 112
M_HORN        = MITSUBISHI_COIL_BASE + 112  # coil 113
M_HIGH_BEAM   = MITSUBISHI_COIL_BASE + 113  # coil 114
M_LOW_BEAM    = MITSUBISHI_COIL_BASE + 114  # coil 115
M_KILL_SWITCH = MITSUBISHI_COIL_BASE + 115  # coil 116
M_STARTER     = MITSUBISHI_COIL_BASE + 116  # coil 117
M_BRAKE       = MITSUBISHI_COIL_BASE + 117  # coil 118
M_CLUTCH      = MITSUBISHI_COIL_BASE + 118  # coil 119

# ---------------------------------------------------------------------------
# Pass/fail limits per register  (below_min, above_max)
#   None means no bound on that side
# ---------------------------------------------------------------------------
LIMITS = {
    D_HEARTBEAT: (None, None),
    D_MSG_STATE: (None, None),
    D_RESULT: (None, None),
    D_OK_COUNT: (None, None),
    D_NG_COUNT: (None, None),
    D_BATCH_COUNT: (None, None),
    100: (180, 370),       # Left Indicator Current mA
    101: (180, 370),       # Right Indicator Current mA
    102: (None, 5.0),      # Horn Resistance ohm
    103: (0.45, 1.05),     # Clutch Lever Voltage V
    104: (280, 620),       # High Beam Current mA
    105: (180, 420),       # Low Beam Current mA
    106: (280, 620),       # Pass Light Current mA
    111: (0.45, 0.55),     # Throttle Position V
    112: (3.8, 4.2),       # Front Brake Voltage V
    113: (None, 5.0),      # Kill Switch ohm
    114: (80, 520),        # Starter Current mA
    115: (180, 420),       # Headlight Current mA
    116: (3.8, 4.2),       # Rear Brake Voltage V
    117: (10, 50),         # Panel Light mA
    118: (4.8, 5.2),       # USB Charger V
}

# ---------------------------------------------------------------------------
# Nominal pass values for each analog register
# ---------------------------------------------------------------------------
NOMINAL = {
    100: 260.0,
    101: 260.0,
    102: 2.5,
    103: 0.75,
    104: 450.0,
    105: 300.0,
    106: 450.0,
    111: 0.50,
    112: 4.00,
    113: 2.5,
    114: 300.0,
    115: 300.0,
    116: 4.00,
    117: 30.0,
    118: 5.00,
}

# Scale factors (raw = display_value / scale_factor)
SCALE = {
    100: 100, 101: 100, 102: 10, 103: 1000, 104: 100,
    105: 100, 106: 100, 111: 1000, 112: 1000, 113: 10,
    114: 100, 115: 100, 116: 1000, 117: 100, 118: 1000,
}

# Digital output bits to set during a test cycle
DIGITAL_OUTPUTS = [
    (M_LEFT_IND, True),
    (M_RIGHT_IND, True),
    (M_HORN, True),
    (M_HIGH_BEAM, True),
    (M_LOW_BEAM, True),
    (M_KILL_SWITCH, True),
    (M_STARTER, True),
    (M_BRAKE, True),
    (M_CLUTCH, True),
]


# ---------------------------------------------------------------------------
# LoggingDataBlock — logs all register R/W
# ---------------------------------------------------------------------------
class LoggingDataBlock(ModbusSequentialDataBlock):
    def __init__(self, name, start, values):
        self.name = name
        super().__init__(start, values)

    def getValues(self, address, count=1):
        values = super().getValues(address, count)
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        logger.info(f"[{ts}] READ  {self.name} addr={address} count={count} -> {values}")
        return values

    def setValues(self, address, values):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        logger.info(f"[{ts}] WRITE {self.name} addr={address} val={values}")
        super().setValues(address, values)


# ---------------------------------------------------------------------------
# TwoWheelerSimulator — drives simulation on the data blocks
# ---------------------------------------------------------------------------
class TwoWheelerSimulator:
    """Manages the two-wheeler test fixture simulation.

    Modes:
      cycling     — Analog registers auto-ramp through pass ranges with noise.
      interactive — Waits for M100=1, runs full state machine cycle.
    """

    STATE_IDLE = 0
    STATE_RUNNING = 99
    STATE_PASS = 1
    STATE_FAIL = 2
    STATE_COMPLETE = 6

    def __init__(self, context, mode="cycling", fail_rate=0.0):
        self.ctx = context[0x00]
        self.mode = mode
        self.fail_rate = fail_rate
        self._iteration = 0
        self._state = self.STATE_IDLE
        self._state_enter_time = 0.0
        self._analog_targets = {}
        self._lock = threading.Lock()
        self._start_analog_ramp()

    def _start_analog_ramp(self):
        """Initialize analog registers to zero."""
        for addr in NOMINAL:
            self._analog_targets[addr] = 0.0

    def _set_analog(self, addr, display_value):
        """Write display_value to holding register using scale factor."""
        raw = int(display_value * SCALE.get(addr, 1))
        raw = max(0, min(65535, raw))
        self.ctx.setValues(3, addr, [raw])

    def _get_analog(self, addr):
        """Read display value from holding register."""
        raw = self.ctx.getValues(3, addr, count=1)[0]
        return raw / SCALE.get(addr, 1) if SCALE.get(addr, 1) else raw

    def _set_holding(self, addr, value):
        """Write a holding register (16-bit)."""
        self.ctx.setValues(3, addr, [int(value) & 0xFFFF])

    def _get_holding(self, addr):
        """Read a holding register."""
        return self.ctx.getValues(3, addr, count=1)[0]

    def _set_coil(self, addr, value):
        """Write a coil."""
        self.ctx.setValues(1, addr, [bool(value)])

    def _get_coil(self, addr):
        """Read a coil."""
        return self.ctx.getValues(1, addr, count=1)[0]

    def _noise(self, value, pct=0.02):
        """Add Gaussian noise ±pct of range around value."""
        import random
        sigma = abs(value) * pct if value != 0 else 0.5
        return value + random.gauss(0, sigma)

    def _check_pass_fail(self):
        """Evaluate all analog registers against limits. Returns (pass, failures)."""
        failures = []
        for addr in NOMINAL:
            display = self._get_analog(addr)
            lo, hi = LIMITS.get(addr, (None, None))
            if lo is not None and display < lo:
                failures.append((addr, f"{display:.2f} < {lo}"))
            if hi is not None and display > hi:
                failures.append((addr, f"{display:.2f} > {hi}"))
        return len(failures) == 0, failures

    def _cycling_tick(self):
        """Cycling mode: ramp all analog registers through pass ranges."""
        self._iteration += 1

        for addr, nom in NOMINAL.items():
            lo, hi = LIMITS.get(addr, (None, None))
            if lo is None or hi is None:
                target = nom
            else:
                mid = (lo + hi) / 2
                amp = (hi - lo) / 2 * 0.8
                target = mid + amp * math.sin(self._iteration * 0.05 + addr * 0.3)

            noisy = self._noise(target, pct=0.015)
            self._set_analog(addr, noisy)

        # Set all digital outputs
        for coil_addr, _ in DIGITAL_OUTPUTS:
            self._set_coil(coil_addr, True)

    def _interactive_tick(self):
        """Interactive mode: state machine driven by M100 trigger."""
        now = time.monotonic()

        if self._state == self.STATE_IDLE:
            start = self._get_coil(M_START_TEST)
            if start:
                logger.info("[SIM] Start Test triggered — entering RUNNING")
                self._state = self.STATE_RUNNING
                self._state_enter_time = now
                self._set_coil(M_START_TEST, False)
                self._set_holding(D_MSG_STATE, self.STATE_RUNNING)

                for coil_addr, _ in DIGITAL_OUTPUTS:
                    self._set_coil(coil_addr, True)

        elif self._state == self.STATE_RUNNING:
            elapsed = now - self._state_enter_time
            ramp_progress = min(elapsed / 1.5, 1.0)

            for addr, nom in NOMINAL.items():
                target = nom * ramp_progress
                noisy = self._noise(target, pct=0.02)
                self._set_analog(addr, noisy)

            if elapsed >= 3.5:
                self._evaluate()

        elif self._state in (self.STATE_PASS, self.STATE_FAIL):
            elapsed = now - self._state_enter_time
            if elapsed >= 2.0:
                self._cooldown()

        elif self._state == self.STATE_COMPLETE:
            elapsed = now - self._state_enter_time
            fade = max(0.0, 1.0 - elapsed / 1.5)

            for addr in NOMINAL:
                current = self._get_analog(addr)
                self._set_analog(addr, current * fade)

            if elapsed >= 1.5:
                for coil_addr, _ in DIGITAL_OUTPUTS:
                    self._set_coil(coil_addr, False)
                self._state = self.STATE_IDLE
                self._set_holding(D_MSG_STATE, self.STATE_IDLE)

    def _evaluate(self):
        """Run pass/fail check and update counters."""
        import random as rnd
        all_pass, failures = self._check_pass_fail()

        if all_pass and self.fail_rate > 0 and rnd.random() < self.fail_rate:
            all_pass = False
            failures = [("RANDOM", f"Injected failure (rate={self.fail_rate})")]

        if all_pass:
            self._state = self.STATE_PASS
            self._set_holding(D_MSG_STATE, self.STATE_PASS)
            self._set_holding(D_RESULT, 1)
            ok = self._get_holding(D_OK_COUNT)
            self._set_holding(D_OK_COUNT, ok + 1)
            logger.info("[SIM] Result: PASS")
        else:
            self._state = self.STATE_FAIL
            self._set_holding(D_MSG_STATE, self.STATE_FAIL)
            self._set_holding(D_RESULT, 2)
            ng = self._get_holding(D_NG_COUNT)
            self._set_holding(D_NG_COUNT, ng + 1)
            logger.info(f"[SIM] Result: FAIL — {failures}")

        batch = self._get_holding(D_BATCH_COUNT)
        self._set_holding(D_BATCH_COUNT, batch + 1)
        self._state_enter_time = time.monotonic()

    def _cooldown(self):
        """Ramp analogs down and return to IDLE."""
        self._state = self.STATE_COMPLETE
        self._set_holding(D_MSG_STATE, self.STATE_COMPLETE)
        self._set_holding(D_RESULT, 0)
        self._state_enter_time = time.monotonic()
        logger.info("[SIM] Cooldown — returning to IDLE")

    async def run(self):
        """Main simulation loop — runs every 100ms."""
        logger.info(f"[SIM] Started in {self.mode} mode (fail_rate={self.fail_rate})")
        while True:
            try:
                curr = self._get_holding(D_HEARTBEAT)
                self._set_holding(D_HEARTBEAT, (curr + 1) & 0xFFFF)

                stop = self._get_coil(M_STOP_TEST)
                if stop and self._state != self.STATE_IDLE:
                    logger.info("[SIM] Stop Test triggered — resetting to IDLE")
                    self._state = self.STATE_IDLE
                    self._set_holding(D_MSG_STATE, self.STATE_IDLE)
                    self._set_coil(M_STOP_TEST, False)
                    for coil_addr, _ in DIGITAL_OUTPUTS:
                        self._set_coil(coil_addr, False)
                    for addr in NOMINAL:
                        self._set_analog(addr, 0)

                reset = self._get_coil(M_RESET_BATCH)
                if reset:
                    logger.info("[SIM] Reset Batch — counters zeroed")
                    self._set_holding(D_OK_COUNT, 0)
                    self._set_holding(D_NG_COUNT, 0)
                    self._set_holding(D_BATCH_COUNT, 0)
                    self._set_coil(M_RESET_BATCH, False)

                if self.mode == "cycling":
                    self._cycling_tick()
                elif self.mode == "interactive":
                    self._interactive_tick()

            except Exception as e:
                logger.error(f"[SIM] Error: {e}")

            await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def run_mock_server():
    parser = argparse.ArgumentParser(
        description="Two-Wheeler Handle Test Fixture — Mock PLC Server"
    )
    parser.add_argument(
        "--port", type=int, default=5020, help="TCP port (default: 5020)"
    )
    parser.add_argument(
        "--sim-mode",
        choices=["cycling", "interactive"],
        default="cycling",
        help="cycling: auto-ramp demo | interactive: triggered by M100",
    )
    parser.add_argument(
        "--fail-rate",
        type=float,
        default=0.0,
        help="Probability of random test failure (0.0-1.0)",
    )
    args = parser.parse_args()

    hr = LoggingDataBlock("HOLD", 0x00, [0] * 65536)
    co = LoggingDataBlock("COIL", 0x00, [False] * 65536)
    di = LoggingDataBlock("DI  ", 0x00, [False] * 256)
    ir = LoggingDataBlock("INP ", 0x00, [0] * 100)

    store = ModbusSlaveContext(di=di, co=co, hr=hr, ir=ir)
    context = ModbusServerContext(slaves=store, single=True)

    sim = TwoWheelerSimulator(context, mode=args.sim_mode, fail_rate=args.fail_rate)

    banner = f"""
==========================================
  Two-Wheeler Handle Test Fixture — Mock PLC
  Address:   127.0.0.1:{args.port}
  Mode:      {args.sim_mode}
  Fail rate: {args.fail_rate}
  Holding:   65536 | Coils: 65536
  DI:        256   | Input: 100
==========================================
  Left Handle:
    D100  Left Indicator Current (mA)
    D101  Right Indicator Current (mA)
    D102  Horn Button Resistance (ohm)
    D103  Clutch Lever Voltage (V)
    D104  High Beam Current (mA)
    D105  Low Beam Current (mA)
    D106  Pass Light Current (mA)
  Right Handle:
    D111  Throttle Position Voltage (V)
    D112  Front Brake Lever Voltage (V)
    D113  Kill Switch Continuity (ohm)
    D114  Starter Button Current (mA)
    D115  Headlight Switch Current (mA)
    D116  Rear Brake Voltage (V)
    D117  Panel Light Current (mA)
    D118  USB Charger Voltage (V)
  System:
    D0    Heartbeat
    D21   Machine State
    D22   Overall Result
    D23   OK Count | D24   NG Count
    D25   Batch Count
  Control:
    M100  Start Test | M101  Stop
    M102  Reset Batch
  Digital Outputs:
    M110-M118  Indicator/Horn/Beam/etc
==========================================
  Ctrl+C to stop.
"""
    logger.info(banner)

    asyncio.create_task(sim.run())

    await StartAsyncTcpServer(context, address=("0.0.0.0", args.port))


if __name__ == "__main__":
    try:
        asyncio.run(run_mock_server())
    except KeyboardInterrupt:
        logger.info("Mock server stopped.")
