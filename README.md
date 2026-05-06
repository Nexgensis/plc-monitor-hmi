# PLC Monitor

A desktop application for monitoring and interacting with Programmable Logic Controllers (PLCs) using various protocols (Modbus TCP, Modbus RTU, etc.). The application provides a graphical user interface for real-time monitoring, data logging, and report generation.

## Features

- Real-time PLC data monitoring
- Support for multiple PLC brands (Mitsubishi, Delta, etc.) and protocols (TCP, RTU)
- Configurable polling intervals and connection parameters
- Data logging to SQLite database
- Report generation (Excel, PDF)
- User authentication and session management
- Dark/Light theme support
- Manual testing interface for PLC registers
- Pass/Fail evaluation logic

## System Requirements

- Python 3.8 or higher
- Git (for version control)
- PLC hardware or simulator for testing

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd plc_monitor
```

### 2. Set Up Virtual Environment

It is recommended to use a virtual environment to isolate dependencies.

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright Dependencies (if running UI tests)

```bash
playwright install
```

## Configuration

The application uses a `config.json` file located in the root directory for configuration. 

### Default Configuration (`config.json`)

```json
{
  "app": {
    "name": "PLC Monitor",
    "version": "1.0.0",
    "theme": "dark"
  },
  "plc": {
    "brand": "mitsubishi",
    "protocol": "TCP",
    "host": "",
    "port": 502,
    "slave_id": 1,
    "poll_interval_ms": 1,
    "timeout_sec": 3,
    "reconnect_delay_ms": 3000,
    "com_port": "",
    "baud_rate": 9600
  }
}
```

### Configuration Options

#### App Settings
- `name`: Application name (displayed in the title bar)
- `version`: Application version
- `theme`: Initial theme (`dark` or `light`)

#### PLC Settings
- `brand`: PLC brand (`mitsubishi`, `delta`, etc.)
- `protocol`: Communication protocol (`TCP` for Modbus TCP, `RTU` for Modbus RTU)
- `host`: IP address of the PLC (for TCP protocol)
- `port`: Port number (default 502 for Modbus TCP)
- `slave_id`: Slave ID of the PLC device
- `poll_interval_ms`: Polling interval in milliseconds
- `timeout_sec`: Communication timeout in seconds
- `reconnect_delay_ms`: Delay before reconnection attempts in milliseconds
- `com_port`: Serial port name (for RTU protocol, e.g., `COM3` or `/dev/ttyUSB0`)
- `baud_rate`: Baud rate for serial communication (default 9600)

### Environment Variables

Currently, the application does not rely on environment variables for core configuration. All settings are managed through `config.json`. However, you may set environment variables for specific deployment scenarios if needed in the future.

## Usage

### 1. Activate the Virtual Environment (if not already activated)

```bash
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 2. Run the Application

```bash
python main.py
```

### 3. Initial Setup

Upon first launch:
1. Configure your PLC connection settings via the Settings screen (accessible from the main window).
2. Ensure the PLC is reachable at the specified address and port.
3. The application will attempt to connect and start monitoring data.

## Project Structure

```
plc_monitor/
│
├── config.json             # Application configuration
├── main.py                 # Entry point of the application
├── requirements.txt        # Python dependencies
├── schema.sql              # Database schema
│
├── src/                    # Source code
│   ├── db/                 # Database access layer
│   ├── logic/              # Business logic (e.g., pass/fail evaluation)
│   ├── plc/                # PLC communication drivers
│   ├── reports/            # Report generation modules
│   ├── ui/                 # User interface components
│   └── utils/              # Utility functions
│
├── tests/                  # Test suite
│
├── logs/                   # Log files (generated at runtime)
├── reports/output/         # Generated reports (Excel, PDF)
└── scratch/                # Temporary scripts for debugging
```

## Database

The application uses SQLite for data storage. The database file (`plc_monitor.db`) is created automatically in the root directory on first run.

### Schema

Refer to `schema.sql` for the complete database schema. The database includes tables for:
- PLC profiles and configurations
- Register libraries and mappings
- I/O points and their values
- Messages and communication logs
- User accounts and sessions
- Reports and exports

## Testing

### Running Unit Tests

```bash
pytest
```

### Running Specific Test Modules

```bash
pytest tests/test_db.py
pytest tests/test_plc_driver.py
```

### UI Tests (using Playwright)

```bash
pytest tests/test_login_visual.py
pytest tests/test_main_window.py
```

## Building Reports

Reports can be generated from the application interface:
1. Navigate to the Reports section in the UI.
2. Select the report type (Excel or PDF).
3. Configure the date range and parameters.
4. Generate and save the report.

Generated reports are saved in the `reports/output/` directory.

## Logging

Application logs are stored in the `logs/` directory. The log file rotates automatically to prevent excessive growth.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- PyQt5 for the GUI framework
- pymodbus for Modbus communication
- openpyxl and reportlab for report generation
- pytest for testing framework