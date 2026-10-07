# Mock PLC Server

A pymodbus-based async TCP server that simulates a **Two-Wheeler Handle Test Fixture** PLC for development and testing purposes.

## Quick Start

```bash
# Install dependencies (if not already installed)
pip install pymodbus

# Seed the database with simulation data (registers, models, mappings, controls)
python scripts/seed_two_wheeler.py --db plc_monitor.db --reset

# Start the mock server (in a separate terminal)
python tests/mock_plc_server.py --port 5020 --sim-mode interactive

# Start the application
python main.py
# Login: admin / Admin@1234
```

## Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | `5020` | TCP port to listen on |
| `--sim-mode` | `cycling` | `cycling` (auto-ramp demo) or `interactive` (triggered by M100) |
| `--fail-rate` | `0.0` | Probability of random test failure (0.0–1.0) |

## Database Seed Script

Before using the mock server, run the seed script to populate the database:

```bash
python scripts/seed_two_wheeler.py --db plc_monitor.db --reset
```

This seeds:

| Data | Count | Description |
|------|-------|-------------|
| Registers | 26 | System (6) + Left Handle (7) + Right Handle (8) + Coils (12) |
| Models | 2 | Left Handle Assembly, Right Handle Assembly |
| Mappings | 34 | Register-to-model links with pass/fail limits |
| Controls | 3 | Start Test, Stop Test, Reset Batch |
| Messages | 8 | Machine State status messages with colors |
| I/O List | 16 | Digital outputs + system status for I/O monitoring page |
| PLC Profile | 1 | Points to `127.0.0.1:5020` (Mitsubishi TCP) |

## How It Works

### Server Architecture

The mock server uses pymodbus to expose four Modbus data blocks:

| Data Block | Size | Purpose |
|------------|------|---------|
| Holding Registers | 65,536 | Analog sensor values, state machine, counters |
| Coils | 65,536 | Digital I/O, control triggers |
| Discrete Inputs | 256 | Digital input states |
| Input Registers | 100 | Additional analog inputs |

### Simulation Modes

#### Cycling Mode (Default)

All analog registers automatically ramp through their pass ranges using a sinusoidal pattern with Gaussian noise (±2% sigma). Digital outputs remain ON. The heartbeat counter increments every 100ms.

```
IDLE ──────────────────────────────────────> IDLE
      (analog values oscillate continuously)
```

Use this mode for visual testing of dashboards and live data displays.

#### Interactive Mode

A full state machine that responds to the Start Test trigger (M100 coil):

```
IDLE ──> RUNNING ──> PASS/FAIL ──> COMPLETE ──> IDLE
  ^                                          │
  └──────────────────────────────────────────┘
```

**State transitions:**

1. **IDLE** (D21=0): Waiting for M100=1 trigger
2. **RUNNING** (D21=99): Analog values ramp up from 0 to nominal over 1.5 seconds
3. **PASS** (D21=1) or **FAIL** (D21=2): Evaluation at 3.5 seconds, result held for 2 seconds
4. **COMPLETE** (D21=6): Analog values fade to zero over 1.5 seconds, digital outputs turn off

### Evaluation Logic

At the end of each test cycle, the simulator checks all 15 analog registers against their pass/fail limits:

- **PASS**: All values within limits → D22=1, D23 increments
- **FAIL**: Any value out of limits → D22=2, D24 increments
- **Random Failure**: If `--fail-rate > 0`, a random failure is injected at the specified probability

## Register Map

### System Registers

| Address | Name | Description |
|---------|------|-------------|
| D0 | Heartbeat | Auto-incrementing counter (updates every 100ms) |
| D21 | Machine State | 0=IDLE, 99=RUNNING, 1=PASS, 2=FAIL, 6=COMPLETE |
| D22 | Overall Result | 0=none, 1=PASS, 2=FAIL |
| D23 | OK Count | Cumulative pass count |
| D24 | NG Count | Cumulative fail count |
| D25 | Batch Count | Current batch count |

### Left Handle Sensors (D100–D106)

| Address | Name | Unit | Nominal | Pass Range |
|---------|------|------|---------|------------|
| D100 | Left Indicator Current | mA | 260.0 | 180–370 |
| D101 | Right Indicator Current | mA | 260.0 | 180–370 |
| D102 | Horn Button Resistance | Ω | 2.5 | <5.0 |
| D103 | Clutch Lever Voltage | V | 0.75 | 0.45–1.05 |
| D104 | High Beam Current | mA | 450.0 | 280–620 |
| D105 | Low Beam Current | mA | 300.0 | 180–420 |
| D106 | Pass Light Current | mA | 450.0 | 280–620 |

### Right Handle Sensors (D111–D118)

| Address | Name | Unit | Nominal | Pass Range |
|---------|------|------|---------|------------|
| D111 | Throttle Position Voltage | V | 0.50 | 0.45–0.55 |
| D112 | Front Brake Lever Voltage | V | 4.00 | 3.8–4.2 |
| D113 | Kill Switch Continuity | Ω | 2.5 | <5.0 |
| D114 | Starter Button Current | mA | 300.0 | 80–520 |
| D115 | Headlight Switch Current | mA | 300.0 | 180–420 |
| D116 | Rear Brake Voltage | V | 4.00 | 3.8–4.2 |
| D117 | Panel Light Current | mA | 30.0 | 10–50 |
| D118 | USB Charger Voltage | V | 5.00 | 4.8–5.2 |

### Coil Map

| PLC Address | Modbus Coil | Function |
|-------------|-------------|----------|
| M100 | 101 | Start Test trigger (write 1 to start) |
| M101 | 102 | Stop Test trigger (write 1 to stop) |
| M102 | 103 | Reset Batch trigger (write 1 to reset counters) |
| M110 | 111 | Left Indicator Lamp (digital output) |
| M111 | 112 | Right Indicator Lamp |
| M112 | 113 | Horn Active |
| M113 | 114 | High Beam ON |
| M114 | 115 | Low Beam ON |
| M115 | 116 | Kill Switch ON |
| M116 | 117 | Starter Active |
| M117 | 118 | Brake Lever Pressed |
| M118 | 119 | Clutch Lever Engaged |

### Scale Factors

Analog values are stored as scaled integers in the holding registers. The application must divide by the scale factor to get the display value.

| Address | Scale Factor | Example |
|---------|--------------|---------|
| D100–D101 | 100 | 260.0 mA → raw 26000 |
| D102 | 10 | 2.5 Ω → raw 25 |
| D103 | 1000 | 0.75 V → raw 750 |
| D104–D106 | 100 | 450.0 mA → raw 45000 |
| D111 | 1000 | 0.50 V → raw 500 |
| D112 | 1000 | 4.00 V → raw 4000 |
| D113 | 10 | 2.5 Ω → raw 25 |
| D114–D115 | 100 | 300.0 mA → raw 30000 |
| D116 | 1000 | 4.00 V → raw 4000 |
| D117 | 100 | 30.0 mA → raw 3000 |
| D118 | 1000 | 5.00 V → raw 5000 |

### I/O List Configuration

The seed script populates the I/O monitoring page with these entries:

| Group | Display Name | Register | On Label | Off Label |
|-------|--------------|----------|----------|-----------|
| **Control** | Start Test Trigger | M100 | ACTIVE | OFF |
| **Control** | Stop Test Trigger | M101 | ACTIVE | OFF |
| **Control** | Reset Batch Trigger | M102 | ACTIVE | OFF |
| **Left Handle - Outputs** | Left Indicator Lamp | M110 | ON | OFF |
| **Left Handle - Outputs** | Right Indicator Lamp | M111 | ON | OFF |
| **Left Handle - Outputs** | Horn Active | M112 | ON | OFF |
| **Left Handle - Outputs** | High Beam ON | M113 | ON | OFF |
| **Left Handle - Outputs** | Low Beam ON | M114 | ON | OFF |
| **Left Handle - Outputs** | Clutch Lever Engaged | M118 | ENGAGED | DISENGAGED |
| **Right Handle - Outputs** | Kill Switch ON | M115 | ON | OFF |
| **Right Handle - Outputs** | Starter Active | M116 | ACTIVE | OFF |
| **Right Handle - Outputs** | Brake Lever Pressed | M117 | PRESSED | RELEASED |
| **System** | Machine State | D21 | RUN | IDLE |
| **System** | Overall Result | D22 | PASS | FAIL |
| **System** | Heartbeat | D0 | ACTIVE | STOPPED |

## Connecting from the Application

### PLC Profile Configuration

In the PLC Monitor application, configure the PLC connection with:

| Setting | Value |
|---------|-------|
| PLC Brand | Mitsubishi |
| Protocol | TCP |
| Host/IP | `127.0.0.1` |
| Port | `5020` |
| Slave ID | `1` |
| Timeout | `3000` ms |

### Using the Setup Wizard

1. Launch the application (first run shows the setup wizard)
2. Click **Get Started →**
3. Enter the PLC connection details above
4. Click **Test Connection** to verify
5. Click **Save & Continue →**

### Programmatic Connection

```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=5020)
client.connect()

# Read heartbeat (D0)
result = client.read_holding_registers(0, count=1)
print(f"Heartbeat: {result.registers[0]}")

# Read left indicator current (D100)
result = client.read_holding_registers(100, count=1)
scale = 100
display_value = result.registers[0] / scale
print(f"Left Indicator: {display_value:.1f} mA")

# Read machine state (D21)
result = client.read_holding_registers(21, count=1)
states = {0: "IDLE", 99: "RUNNING", 1: "PASS", 2: "FAIL", 6: "COMPLETE"}
print(f"State: {states.get(result.registers[0], 'UNKNOWN')}")

# Trigger test (write 1 to M100 coil)
client.write_coil(101, True)  # Modbus coil 101 = M100

client.close()
```

## Logging

All register reads and writes are logged with timestamps:

```
[14:30:15.123] READ  HOLD addr=0 count=1 -> [42]
[14:30:15.124] WRITE HOLD addr=100 val=[26015]
[14:30:15.125] READ  COIL addr=101 count=1 -> [False]
[14:30:15.126] WRITE COIL addr=111 val=[True]
```

## Test Scripts

The following test scripts use the mock server:

| Script | Purpose |
|--------|---------|
| `tests/test_full_flow.py` | Automated integration test (spawns server on port 5021) |
| `tests/test_connection_live.py` | Manual connection test (connects to port 5020) |
| `tests/test_full_visual.py` | Visual UI test (checks port 5020 availability) |
| `tests/test_dashboard_live.py` | Dashboard visual test (requires port 5020) |
| `scripts/seed_two_wheeler.py` | Database seeder (configures app for port 5020) |

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 5020
netstat -ano | findstr :5020

# Kill the process (replace PID)
taskkill /PID <PID> /F
```

### Connection Refused

- Ensure the mock server is running before connecting
- Check that the port matches (default: 5020)
- Verify firewall settings allow TCP connections on the port

### Values Not Changing

- In **cycling** mode, values update every 100ms automatically
- In **interactive** mode, write `1` to M100 coil to trigger a test cycle
- Check the server logs for any errors

## Stopping the Server

Press `Ctrl+C` in the terminal where the server is running. The server will shut down gracefully.
