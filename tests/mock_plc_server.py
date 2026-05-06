"""
Universal mock PLC server for testing.
Simulates a Modbus TCP PLC with 65536 registers and coils.
Supports live simulation modes and fault injection.

Run: python tests/mock_plc_server.py [--port 5020] [--sim-mode cycling]
"""
import asyncio
import logging
import random
import argparse
from datetime import datetime
from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("MockPLC")

class LoggingDataBlock(ModbusSequentialDataBlock):
    """Custom data block that logs all read and write operations."""
    def __init__(self, name, address, values):
        self.name = name
        super().__init__(address, values)

    def getValues(self, address, count=1):
        """Log read operation."""
        values = super().getValues(address, count)
        ts = datetime.now().strftime("%H:%M:%S")
        logger.info(f"[{ts}] READ  {self.name} addr={address} count={count} → {values}")
        return values

    def setValues(self, address, values):
        """Log write operation."""
        ts = datetime.now().strftime("%H:%M:%S")
        logger.info(f"[{ts}] WRITE {self.name} addr={address} val={values}")
        super().setValues(address, values)

async def simulation_task(context, mode="static", fail_rate=0.0):
    """Background task to simulate heartbeat and sensor cycling."""
    slave_id = 0x00
    iteration = 0
    
    while True:
        try:
            # 1. Update heartbeat (Register 0 increments every second)
            curr_heartbeat = context[slave_id].getValues(3, 0, count=1)[0]
            new_heartbeat = (curr_heartbeat + 1) & 0xFFFF
            context[slave_id].setValues(3, 0, [new_heartbeat])

            # 2. Cycling mode: Simulate sensor values in registers 100-128
            if mode == "cycling":
                # Triangle wave pattern for 0->9999->0
                val = iteration % 20000
                if val > 10000:
                    val = 20000 - val
                
                # Update block of registers
                cycling_values = [val] * 29
                context[slave_id].setValues(3, 100, cycling_values)
                iteration += 100 # Speed up for visible cycling

            # 3. Simulate random failures if fail_rate > 0
            # (In a real mock we might override the server response, 
            # but here we just log that a failure would occur)
            if fail_rate > 0 and random.random() < fail_rate:
                logger.warning("!!! Simulated Read Failure Condition !!!")

        except Exception as e:
            logger.error(f"Simulation task error: {e}")

        await asyncio.sleep(1.0)

async def run_mock_server():
    parser = argparse.ArgumentParser(description="Universal Mock PLC Server")
    parser.add_argument("--port", type=int, default=5020, help="TCP port (default 5020)")
    parser.add_argument("--sim-mode", choices=["static", "cycling"], default="static", 
                        help="static: values stay until written | cycling: 100-128 ramp 0-9999")
    parser.add_argument("--fail-rate", type=float, default=0.0, help="0.0-1.0 read failure rate")
    args = parser.parse_args()

    # Initialize data blocks
    # Holding Registers (4x) - Block 3
    hr = LoggingDataBlock("HOLD", 0x00, [0] * 65536)
    # Coils (0x) - Block 1
    co = LoggingDataBlock("COIL", 0x00, [False] * 65536)
    # Discrete Inputs (1x) - Block 2
    di = LoggingDataBlock("DI  ", 0x00, [False] * 256)
    # Input Registers (3x) - Block 4
    ir = LoggingDataBlock("INP ", 0x00, [0] * 100)

    # Seed some discrete inputs
    di.setValues(0, [True, False, True, True, False])

    store = ModbusSlaveContext(di=di, co=co, hr=hr, ir=ir)
    context = ModbusServerContext(slaves=store, single=True)

    logger.info("==========================================")
    logger.info("   Universal Mock PLC Server (v4.0)")
    logger.info(f"   Address: 127.0.0.1:{args.port}")
    logger.info("   Holding regs: 65536 | Coils: 65536 | DI: 256")
    logger.info(f"   Mode: {args.sim_mode}")
    logger.info("   Write any Modbus register and read it back.")
    logger.info("   Ctrl+C to stop.")
    logger.info("==========================================")

    # Start simulation heartbeat
    asyncio.create_task(simulation_task(context, args.sim_mode, args.fail_rate))

    # Start Modbus server
    await StartAsyncTcpServer(context, address=("0.0.0.0", args.port))

if __name__ == "__main__":
    try:
        asyncio.run(run_mock_server())
    except KeyboardInterrupt:
        logger.info("Mock server stopped.")
