from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient("127.0.0.1", 5021)
if client.connect():
    print("Connected")
    res = client.write_coil(11, True, slave=1)
    print(f"Write result: {res}")
    time.sleep(1)
    res = client.read_coils(11, 1, slave=1)
    print(f"Read result: {res.bits[0]}")
    client.close()
else:
    print("Failed to connect")
