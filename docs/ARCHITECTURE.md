# ETCS Testbed Architecture

## Overview
The ETCS (European Train Control System) testbed is a cybersecurity research platform that simulates railway control systems with intentional vulnerabilities for adversarial testing. The testbed supports multiple Industrial Control System (ICS) protocols including JSON over TCP and Modbus TCP.

## System Architecture

### Architectural Zones

```
┌─────────────────────────────────────────────────────────────────┐
│                    Zone A: Trackside (Authority)                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  RBC Server (Radio Block Centre)                           │ │
│  │  - Port 9000: Main communication                           │ │
│  │  - Port 9101: Admin interface                              │ │
│  │  - Generates Movement Authorities (MAs)                    │ │
│  │  - Supports JSON and Modbus TCP protocols                  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              Zone B: Public Network (GSM-R)                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  GSM-R Network Emulator                                    │ │
│  │  - Port 9001: Train connection                             │ │
│  │  - Port 9100: Admin/MITM interface                         │ │
│  │  - Forwards traffic between RBC and Train                  │ │
│  │  - Protocol-aware packet inspection                        │ │
│  │  - Attack injection capabilities                           │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               Zone C: Onboard Train (Victim)                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Train Radio (Gateway)                                     │ │
│  │  - Connects to GSM-R (Zone B)                              │ │
│  │  - Forwards to EVC (onboard network)                       │ │
│  └────────────────────────────────────────────────────────────┘ │
│                               ▼                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  EVC Core (European Vital Computer)                        │ │
│  │  - Port 9002: Radio connection (internal)                  │ │
│  │  - Port 9102: Driver command interface                     │ │
│  │  - Processes MAs and controls train                        │ │
│  │  - Physics simulation                                      │ │
│  │  - Multi-protocol support                                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                               ▼                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  DMI (Driver Machine Interface)                            │ │
│  │  - Port 9003: UDP status from EVC                          │ │
│  │  - Port 8080: Web UI                                       │ │
│  │  - Displays speed, position, authority                     │ │
│  │  - Driver controls                                         │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Protocol Abstraction Layer

The testbed implements a protocol-agnostic architecture that supports multiple ICS protocols:

### Protocol Interface
All protocols implement the `Protocol` abstract base class:
- `encode(payload) -> bytes`: Convert message to wire format
- `decode(data) -> dict`: Parse wire format to message
- `sign(payload) -> str`: Generate message signature
- `verify(payload, signature) -> bool`: Verify message signature

### Supported Protocols

#### 1. JSON over TCP (Default)
- **File**: `protocols/json_protocol.py`
- **Format**: JSON with HMAC-SHA256 signatures
- **Security**: Optional signature verification
- **Use case**: Original ETCS protocol, human-readable

#### 2. Modbus TCP
- **File**: `protocols/modbus_tcp.py`
- **Format**: Modbus holding registers
- **Register map**:
  - 0-1: position_km (32-bit float)
  - 2-3: speed_kmh (32-bit float)
  - 4-5: speed_limit (32-bit float)
  - 6-7: next_checkpoint_km (32-bit float)
  - 8: ma_id (16-bit integer)
  - 9: message_type (16-bit integer)
  - 10: train_id hash (16-bit integer)
  - 11-12: timestamp (32-bit split)
  - 13-18: signature (96-bit truncated HMAC)
- **Security**: NO encryption, optional weak HMAC
- **Use case**: Realistic ICS vulnerability testing

### Protocol Selection

Set via environment variable:
```bash
export PROTOCOL=json           # Use JSON protocol (default)
export PROTOCOL=modbus_tcp     # Use Modbus TCP protocol
export FALLBACK_PROTOCOL=json  # Fallback if primary fails
```

Or programmatically:
```python
from protocols import get_protocol

# Get protocol from environment
proto = get_protocol()

# Get specific protocol
json_proto = get_protocol("json")
modbus_proto = get_protocol("modbus_tcp")
```

## Message Flow

### Normal Operation (JSON)
1. EVC sends HELLO to RBC via Radio and GSM-R
2. RBC responds with Movement Authority (MA)
3. EVC verifies signature and applies MA
4. EVC updates physics model
5. EVC sends status to DMI via UDP
6. DMI displays speed, position, target
7. EVC periodically reports position to RBC

### Modbus Operation
1. EVC sends HELLO (encoded as Modbus registers)
2. RBC responds with MA (as register values)
3. EVC reads registers and decodes MA
4. Same verification and physics as JSON mode
5. Status updates continue via UDP to DMI

### Attack Scenarios
1. Attacker connects to GSM-R admin port (9100)
2. Attacker injects forged MA with:
   - Invalid/missing signature
   - Excessive speed limit
   - Manipulated position
3. If EVC is in relaxed mode (UNSIGNED ON), accepts forged MA
4. Train accelerates to dangerous speed
5. DMI displays forged authority

## Security Vulnerabilities (Intentional)

### 1. Weak Key Storage
- **Location**: `rbc_key.txt` (plaintext file)
- **Impact**: Anyone with file access can forge MAs
- **Attack**: Read key, sign malicious MA

### 2. Signature Bypass
- **Component**: EVC
- **Mechanism**: `UNSIGNED ON` mode disables verification
- **Impact**: Accepts any MA regardless of signature
- **Attack**: Send unsigned/invalid MAs

### 3. Modbus Lack of Authentication
- **Protocol**: Modbus TCP
- **Issue**: No authentication required for register writes
- **Impact**: Direct manipulation of speed/position
- **Attack**: Function Code 16 (Write Multiple Registers)

### 4. Truncated HMAC (Modbus)
- **Issue**: Signature truncated to 96 bits for register storage
- **Impact**: Weaker signature strength, easier brute force
- **Attack**: Birthday attack on truncated HMAC

### 5. MITM Capability
- **Component**: GSM-R Network Emulator
- **Port**: 9100 (admin interface)
- **Impact**: Full traffic inspection and injection
- **Attack**: Modify MAs in transit, replay attacks

### 6. No Encryption
- **Protocols**: Both JSON and Modbus
- **Impact**: All traffic readable in plaintext
- **Attack**: Passive sniffing, traffic analysis

## Data Structures

### Movement Authority (MA)
```json
{
  "type": "MA",
  "ma_id": 1,
  "position_km": 0.0,
  "next_checkpoint_km": 5.3,
  "speed_limit": 100.0,
  "message": "PROCEED"
}
```

### Position Report
```json
{
  "type": "POSITION_REPORT",
  "train_id": "TrainA",
  "position_km": 2.5,
  "speed_kmh": 85.0,
  "timestamp": 1700000000.0
}
```

### Emergency Update
```json
{
  "type": "EMERGENCY_UPDATE",
  "ma_id": 999,
  "position_km": 2.5,
  "next_checkpoint_km": 3.0,
  "speed_limit": 0.0,
  "message": "EMERGENCY BRAKE"
}
```

## Attack Framework

The testbed includes built-in attack tools:

### Generic Attacks (`attacks/attack_framework.py`)
- **Overspeed Attack**: Inject MA with excessive speed
- **Emergency Brake**: Force train to stop
- **Replay Attack**: Replay captured messages
- **DoS Flood**: Overwhelm DMI with garbage data
- **Signature Forgery**: Inject with invalid signatures

### Modbus Attacks (`attacks/modbus_exploits.py`)
- **Register Write**: Direct register manipulation
- **Function Code Fuzzing**: Test supported functions
- **Register Scanning**: Discover accessible data
- **Position Spoofing**: Manipulate train position
- **Speed Override**: Directly write speed limit

## Testing Strategy

### Unit Tests
- Protocol encoding/decoding
- Signature generation/verification
- Message type handling
- Registry functionality

### Integration Tests
- End-to-end message flow
- Protocol conversion
- Attack injection
- Recovery procedures

### Security Tests
- Signature bypass validation
- Unauthorized access attempts
- MITM capabilities
- DoS resilience

## Deployment Options

### Bare Metal
Run each component in separate terminals:
```bash
python train_dmi.py
python train_evc.py
python train_radio.py
python gsmr_network_emulator.py
python rbc_server.py
```

### Docker Compose
Run entire stack:
```bash
docker compose up --build
```

Access:
- DMI Web UI: http://localhost:8080
- GSM-R Admin: nc localhost 9100
- EVC Driver: nc localhost 9102

## Extension Points

### Adding New Protocols
1. Create `protocols/new_protocol.py`
2. Extend `Protocol` base class
3. Implement required methods
4. Register with `ProtocolRegistry`
5. Add tests in `tests/test_protocols.py`

### Adding Attack Abilities
1. Create function in `attacks/attack_framework.py`
2. Document parameters and impact
3. Add to demonstration script
4. Create CALDERA ability YAML

### Integration with CALDERA
1. Deploy CALDERA server
2. Install testbed plugin from `caldera/`
3. Configure agent on testbed host
4. Execute operations via CALDERA UI

## Performance Considerations

### Latency
- JSON: ~1-2ms encoding/decoding
- Modbus: ~2-3ms encoding/decoding
- Network: ~10-50ms round-trip (localhost)

### Throughput
- JSON: ~1000 messages/second
- Modbus: ~500 messages/second (register conversion overhead)
- GSM-R proxy: Minimal overhead (<1ms per message)

### Resource Usage
- Each component: ~20-50 MB RAM
- Total system: ~200 MB RAM
- CPU: <5% per component under load

## Future Enhancements

### Additional Protocols
- DNP3 (utility SCADA)
- OPC UA (industrial automation)
- IEC 61850 (power systems)
- CIP (EtherNet/IP)

### Security Features
- Public key infrastructure (PKI)
- Certificate-based authentication
- Encrypted channels (TLS/DTLS)
- Intrusion detection system (IDS)

### Operational Features
- Multi-train support
- Track switching
- Signal systems
- Station stops
- Route planning
