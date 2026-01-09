# ETCS Testbed ICS Protocol Integration - Implementation Plan

## Overview
This document outlines the plan to extend the ETCS testbed to support Industrial Control System (ICS) protocols, specifically Modbus and other common ICS specifications, to enable adversarial testing and CALDERA integration.

## Current Architecture Summary
- **RBC Server** (Port 9000): Radio Block Centre - generates Movement Authorities
- **GSM-R Network Emulator** (Port 9001): Network proxy with MITM capabilities (Port 9100)
- **Train Radio** (Port 9002): Onboard gateway
- **EVC Core**: Onboard brain with driver command interface (Port 9102)
- **DMI** (Port 8080 HTTP, 9003 UDP): Driver Machine Interface

Current communication: JSON over TCP with HMAC-SHA256 signatures

## Goals
1. Support Modbus TCP/RTU protocol for SCADA-like communication
2. Enable protocol-agnostic adversarial testing
3. Integrate with CALDERA for automated red team operations
4. Maintain backward compatibility with existing JSON-based system
5. Create realistic ICS attack scenarios

## Implementation Tasks

### Phase 1: Protocol Abstraction Layer
**Objective**: Create a flexible protocol abstraction that supports both JSON and ICS protocols

#### Task 1.1: Define Protocol Interface
- [ ] Create `protocols/base.py` with abstract `Protocol` class
- [ ] Define methods: `encode()`, `decode()`, `validate()`, `sign()`, `verify()`
- [ ] Support multiple message types: MA, POSITION_REPORT, HELLO, EMERGENCY_UPDATE

#### Task 1.2: Implement JSON Protocol Adapter
- [ ] Refactor existing JSON code into `protocols/json_protocol.py`
- [ ] Maintain backward compatibility with current implementation
- [ ] Move HMAC signing/verification to protocol adapter

#### Task 1.3: Create Protocol Registry
- [ ] Implement `protocols/registry.py` for dynamic protocol selection
- [ ] Support runtime protocol switching via environment variables
- [ ] Enable multi-protocol support in single emulator instance

### Phase 2: Modbus Protocol Implementation
**Objective**: Add Modbus TCP and RTU support for realistic ICS scenarios

#### Task 2.1: Modbus TCP Support
- [ ] Add `pymodbus>=3.0.0` to requirements.txt
- [ ] Create `protocols/modbus_tcp.py` implementing Modbus TCP client/server
- [ ] Map ETCS messages to Modbus registers:
  - Position (km) → Holding registers 0-1 (32-bit float)
  - Speed (km/h) → Holding registers 2-3 (32-bit float)
  - Speed limit → Holding registers 4-5 (32-bit float)
  - Checkpoint → Holding registers 6-7 (32-bit float)
  - MA ID → Holding register 8
  - Message type → Holding register 9
- [ ] Implement function codes: 03 (Read Holding Registers), 16 (Write Multiple Registers)

#### Task 2.2: Modbus RTU Support (Optional)
- [ ] Create `protocols/modbus_rtu.py` for serial communication emulation
- [ ] Support virtual serial ports for testing
- [ ] Implement CRC validation

#### Task 2.3: Modbus Security Vulnerabilities
- [ ] Document common Modbus attacks: unauthorized writes, replay attacks
- [ ] Implement intentional vulnerabilities for testing:
  - No authentication
  - No encryption
  - Predictable transaction IDs
- [ ] Create exploit examples in `attacks/modbus_exploits.py`

### Phase 3: Additional ICS Protocols
**Objective**: Support other common ICS protocols

#### Task 3.1: DNP3 Protocol (Optional)
- [ ] Add `pydnp3` library support
- [ ] Create `protocols/dnp3_protocol.py`
- [ ] Map ETCS messages to DNP3 objects

#### Task 3.2: OPC UA Protocol (Optional)
- [ ] Add `opcua` library support
- [ ] Create `protocols/opcua_protocol.py`
- [ ] Implement OPC UA server/client nodes

### Phase 4: Network Emulator Enhancement
**Objective**: Enable protocol-aware MITM attacks

#### Task 4.1: Multi-Protocol GSM-R Emulator
- [ ] Modify `gsmr_network_emulator.py` to support multiple protocols
- [ ] Add protocol detection/selection logic
- [ ] Implement protocol-specific packet inspection and logging

#### Task 4.2: Protocol Converter
- [ ] Create `protocol_converter.py` for cross-protocol scenarios
- [ ] Support JSON ↔ Modbus conversion
- [ ] Enable mixed-protocol attacks (e.g., JSON RBC, Modbus Train)

#### Task 4.3: Attack Injection Framework
- [ ] Enhance admin interface (port 9100) to support multiple protocols
- [ ] Create `attacks/attack_framework.py` with common attack patterns:
  - Replay attacks
  - Man-in-the-middle
  - Packet injection
  - Register manipulation
  - Function code fuzzing
- [ ] Add REST API for programmatic attack execution

### Phase 5: CALDERA Integration
**Objective**: Enable automated adversarial testing with CALDERA

#### Task 5.1: CALDERA Plugin Structure
- [ ] Create `caldera/` directory with plugin structure
- [ ] Implement CALDERA agent interface
- [ ] Define abilities (atomic red team actions)

#### Task 5.2: Attack Abilities
- [ ] Create YAML ability definitions:
  - `modbus-register-write.yml`: Write arbitrary values to Modbus registers
  - `modbus-function-code-fuzzing.yml`: Test invalid function codes
  - `json-signature-bypass.yml`: Test unsigned message acceptance
  - `mitm-speed-manipulation.yml`: Modify speed limits in transit
  - `rbc-key-theft.yml`: Simulate key file theft
  - `dos-flood.yml`: Flood DMI with garbage data
- [ ] Implement Python payloads for each ability
- [ ] Create facts and relationships for CALDERA planning

#### Task 5.3: CALDERA Adversary Profiles
- [ ] Define adversary profiles:
  - `train-insider`: Onboard attacker with EVC access
  - `network-attacker`: MITM capabilities on GSM-R
  - `rbc-compromise`: Full RBC control
- [ ] Create operation plans combining multiple abilities
- [ ] Document required initial access and privileges

### Phase 6: RBC Server Enhancement
**Objective**: Add Modbus server capabilities and admin interface

#### Task 6.1: Modbus Server Mode
- [ ] Add Modbus TCP server option to `rbc_server.py`
- [ ] Serve zone database via Modbus registers
- [ ] Support both JSON and Modbus clients simultaneously

#### Task 6.2: RBC Admin Interface Enhancement
- [ ] Enhance admin interface (port 9101) with REST API
- [ ] Support dynamic database updates
- [ ] Add emergency broadcast to all trains
- [ ] Implement protocol statistics and monitoring

### Phase 7: EVC Enhancement
**Objective**: Support multiple protocol inputs

#### Task 7.1: Multi-Protocol EVC
- [ ] Modify `train_evc.py` to support protocol selection
- [ ] Implement Modbus register polling for MA reception
- [ ] Maintain dual JSON/Modbus operation

#### Task 7.2: Protocol Validation
- [ ] Add protocol-specific validation rules
- [ ] Implement security policies per protocol
- [ ] Log protocol anomalies

### Phase 8: Testing & Validation
**Objective**: Ensure all components work correctly

#### Task 8.1: Unit Tests
- [ ] Create `tests/test_modbus_protocol.py`
- [ ] Create `tests/test_protocol_registry.py`
- [ ] Create `tests/test_protocol_converter.py`
- [ ] Extend existing tests for backward compatibility

#### Task 8.2: Integration Tests
- [ ] Create `tests/integration/test_modbus_end_to_end.py`
- [ ] Test JSON → Modbus conversion scenarios
- [ ] Test multi-protocol GSM-R emulator
- [ ] Validate CALDERA plugin functionality

#### Task 8.3: Attack Scenario Tests
- [ ] Create `tests/attacks/` directory
- [ ] Implement tests for each attack vector
- [ ] Validate vulnerability detection
- [ ] Test emergency procedures

### Phase 9: Documentation
**Objective**: Comprehensive documentation for users and developers

#### Task 9.1: User Documentation
- [ ] Update `README.md` with ICS protocol usage
- [ ] Create `docs/MODBUS_PROTOCOL.md` with Modbus-specific guide
- [ ] Document register mappings and function codes
- [ ] Add troubleshooting section

#### Task 9.2: Developer Documentation
- [ ] Create `docs/ARCHITECTURE.md` with system design
- [ ] Document protocol abstraction layer
- [ ] Create `docs/ADDING_PROTOCOLS.md` guide
- [ ] Add API reference documentation

#### Task 9.3: Attack Scenario Documentation
- [ ] Create `docs/ATTACK_SCENARIOS.md`
- [ ] Document each adversary profile
- [ ] Provide example commands and expected outcomes
- [ ] Include CALDERA operation setup instructions

#### Task 9.4: CALDERA Integration Guide
- [ ] Create `docs/CALDERA_SETUP.md`
- [ ] Document plugin installation
- [ ] Provide example operations
- [ ] Include troubleshooting tips

### Phase 10: Docker & Deployment
**Objective**: Easy deployment of enhanced testbed

#### Task 10.1: Docker Compose Updates
- [ ] Add Modbus-specific services to `docker-compose.yml`
- [ ] Create separate profiles for JSON-only vs ICS protocols
- [ ] Add environment variables for protocol selection
- [ ] Document multi-protocol deployment scenarios

#### Task 10.2: CALDERA Docker Integration
- [ ] Create `docker-compose.caldera.yml` for CALDERA stack
- [ ] Integrate testbed with CALDERA server
- [ ] Configure agent deployment
- [ ] Document end-to-end setup

## File Structure (New Files)

```
etcs_testbed/
├── protocols/
│   ├── __init__.py
│   ├── base.py                 # Abstract protocol interface
│   ├── registry.py             # Protocol registry and factory
│   ├── json_protocol.py        # Existing JSON protocol (refactored)
│   ├── modbus_tcp.py           # Modbus TCP implementation
│   ├── modbus_rtu.py           # Modbus RTU implementation
│   ├── dnp3_protocol.py        # DNP3 protocol (optional)
│   └── opcua_protocol.py       # OPC UA protocol (optional)
├── attacks/
│   ├── __init__.py
│   ├── attack_framework.py     # Common attack patterns
│   ├── modbus_exploits.py      # Modbus-specific attacks
│   └── json_exploits.py        # JSON/ETCS-specific attacks
├── caldera/
│   ├── plugin.yml              # CALDERA plugin definition
│   ├── hook.py                 # Plugin entry point
│   ├── data/
│   │   ├── abilities/
│   │   │   ├── modbus-register-write.yml
│   │   │   ├── modbus-fuzzing.yml
│   │   │   ├── json-signature-bypass.yml
│   │   │   └── mitm-speed-manipulation.yml
│   │   ├── adversaries/
│   │   │   ├── train-insider.yml
│   │   │   ├── network-attacker.yml
│   │   │   └── rbc-compromise.yml
│   │   └── payloads/
│   │       ├── modbus_write.py
│   │       ├── signature_forge.py
│   │       └── mitm_inject.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── MODBUS_PROTOCOL.md
│   ├── ADDING_PROTOCOLS.md
│   ├── ATTACK_SCENARIOS.md
│   └── CALDERA_SETUP.md
├── tests/
│   ├── test_modbus_protocol.py
│   ├── test_protocol_registry.py
│   ├── test_protocol_converter.py
│   ├── integration/
│   │   └── test_modbus_end_to_end.py
│   └── attacks/
│       ├── test_modbus_attacks.py
│       └── test_json_attacks.py
├── protocol_converter.py       # Cross-protocol conversion utility
├── docker-compose.caldera.yml  # CALDERA-integrated deployment
└── IMPLEMENTATION_PLAN.md      # This file
```

## Dependencies to Add

### requirements.txt additions:
```
pymodbus>=3.0.0         # Modbus protocol support
scapy>=2.4.5            # Packet crafting for attacks (optional)
requests>=2.28.0        # REST API for CALDERA integration
pyyaml>=6.0             # YAML parsing for CALDERA abilities
```

### Optional dependencies:
```
pydnp3>=0.2.3          # DNP3 protocol support
opcua>=0.98.13         # OPC UA protocol support
pyserial>=3.5          # Serial port emulation for Modbus RTU
```

## Configuration Changes

### Environment Variables (add to docker-compose.yml):
```yaml
# Protocol selection
PROTOCOL: "json"           # Options: json, modbus_tcp, modbus_rtu, dnp3
FALLBACK_PROTOCOL: "json"  # Protocol to use if primary fails

# Modbus-specific
MODBUS_SLAVE_ID: 1
MODBUS_PORT: 502
MODBUS_REGISTER_BASE: 0

# CALDERA integration
CALDERA_SERVER: "http://caldera:8888"
CALDERA_API_KEY: "changeme"
ENABLE_CALDERA_AGENT: "false"
```

## Security Considerations

### Intentional Vulnerabilities (for testing):
1. **Modbus**: No authentication, no encryption
2. **JSON**: Weak key storage (plaintext file)
3. **Network**: MITM port exposed
4. **EVC**: Unsigned message acceptance mode

### Testing Validations:
- Verify each vulnerability is exploitable
- Ensure defensive measures can be demonstrated
- Document mitigation strategies

## Timeline Estimate

- **Phase 1**: 2-3 days (Protocol abstraction)
- **Phase 2**: 3-4 days (Modbus implementation)
- **Phase 3**: 2-3 days per protocol (Additional protocols)
- **Phase 4**: 2-3 days (Network emulator)
- **Phase 5**: 4-5 days (CALDERA integration)
- **Phase 6**: 1-2 days (RBC enhancement)
- **Phase 7**: 1-2 days (EVC enhancement)
- **Phase 8**: 3-4 days (Testing)
- **Phase 9**: 2-3 days (Documentation)
- **Phase 10**: 1-2 days (Docker/Deployment)

**Total**: ~3-4 weeks for full implementation

## Success Criteria

1. ✅ Testbed operates with both JSON and Modbus protocols
2. ✅ Protocol conversion works bidirectionally
3. ✅ CALDERA can execute attack abilities against testbed
4. ✅ All attack scenarios documented and reproducible
5. ✅ Docker deployment works out-of-the-box
6. ✅ All tests pass (unit, integration, attack scenarios)
7. ✅ Documentation is comprehensive and accurate
8. ✅ Backward compatibility maintained with existing setup

## Next Steps

1. Review and approve this implementation plan
2. Set up development branch
3. Begin Phase 1: Protocol Abstraction Layer
4. Iterate with testing and validation at each phase
5. Conduct final integration testing
6. Update documentation and examples
