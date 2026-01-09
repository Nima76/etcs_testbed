# ERTMS/ETCS "Iron Range" Testbed (Prototype)

This folder contains a minimal end-to-end prototype of the ERTMS/ETCS
cybersecurity testbed described in `plan-etcsBaliseSpoof.prompt.md`.

The focus is on demonstrating message flows and a basic signing
vulnerability where an attacker who obtains the RBC key can craft and
inject valid-looking Movement Authorities (MAs).

## 🚀 NEW: Multi-Protocol Support

The testbed now supports multiple Industrial Control System (ICS) protocols:
- **JSON over TCP** (default): Human-readable, HMAC-SHA256 signatures
- **Modbus TCP**: Realistic ICS protocol with intentional vulnerabilities
- **Protocol abstraction layer**: Easy to add new protocols (DNP3, OPC UA, etc.)

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the full roadmap and
[docs/MODBUS_PROTOCOL.md](docs/MODBUS_PROTOCOL.md) for Modbus usage guide.

## Components & Ports

- **RBC (Trackside authority)**: `rbc_server.py`
  - TCP server on `9000`.
  - Periodically generates Movement Authorities and signs them with a
    secret key loaded from `rbc_key.txt` (stored in plain text, on disk).

- **GSM-R Network Emulator (Public network)**: `gsmr_network_emulator.py`
  - Connects as a TCP *client* to RBC `127.0.0.1:9000`.
  - Listens for the Train on TCP `0.0.0.0:9001`.
  - Forwards traffic between RBC and Train (simple TCP proxy).
  - Logs all traffic to stdout (sniffing capability).
  - Exposes an **admin/MITM interface** on `127.0.0.1:9100`. Any client
    that connects there can type lines which are injected directly
    toward the Train side.

- **Train Radio (Onboard gateway)**: `train_radio.py`
  - Connects to GSM-R at `127.0.0.1:9001`.
  - Connects to EVC at `127.0.0.1:9002`.
  - Forwards traffic between them.

- **EVC Core (Onboard brain)**: `train_evc.py`
  - Listens on TCP `0.0.0.0:9002` for the Train Radio.
  - Reads configuration from `train_data.conf` at startup.
  - Verifies signatures of incoming MAs using the same key from
    `rbc_key.txt` (simplified symmetric-key demo).
  - Updates an internal speed model and sends periodic status updates to
    the DMI via UDP `127.0.0.1:9003`.

- **DMI (Driver Machine Interface)**: `train_dmi.py`
  - Listens on UDP `0.0.0.0:9003` for status from the EVC.
  - Exposes a simple web UI on HTTP port `8080` showing current speed,
    target speed, and distance to go.

## Message Format

RBC -> Train messages are JSON lines (`\n`-terminated) of the form:

```json
{
  "payload": {
    "type": "MA",
    "id": 1,
    "speed_kmh": 80,
    "distance_m": 1500,
    "timestamp": 1700000000.0
  },
  "signature": "<hex HMAC-SHA256 over payload>"
}
```

The EVC recomputes the HMAC over the `payload` object and compares it
with the attached `signature`. If they match, the MA is accepted and the
target speed/distance are updated.

## Protocol Selection

The testbed supports multiple protocols. Set via environment variable:

```bash
# Use JSON protocol (default, human-readable)
export PROTOCOL=json

# Use Modbus TCP protocol (realistic ICS)
export PROTOCOL=modbus_tcp

# Fallback if primary protocol unavailable
export FALLBACK_PROTOCOL=json
```

**Modbus TCP** maps ETCS messages to holding registers for realistic ICS
vulnerability testing. See [docs/MODBUS_PROTOCOL.md](docs/MODBUS_PROTOCOL.md) for details.

## Running the Testbed (Bare Metal)

Use Python 3.8+.

In separate terminals, from this folder:

1. **Start the DMI (with web UI):**

   ```bash
  pip install -r requirements.txt
  python3 train_dmi.py
   ```

2. **Start the EVC:**

   ```bash
   python3 train_evc.py
   ```

3. **Start the GSM-R network emulator:**

   ```bash
   python3 gsmr_network_emulator.py
   ```

4. **Start the Train radio:**

   ```bash
   python3 train_radio.py
   ```

5. **Start the RBC:**

   ```bash
   python3 rbc_server.py
   ```

You should see the RBC periodically emit Movement Authorities, the
GSM-R proxy log the traffic, the Radio forward it, the EVC accept and
apply the MA, and the DMI display changing speed/target/distance.

To view the DMI UI in a browser, open:

- http://127.0.0.1:8080/

> Note: The startup order can be changed; you may need to restart the
> GSM-R emulator if it cannot connect to the RBC yet.

## Demonstrating the Vulnerability

The key material is stored **insecurely** in `rbc_key.txt`, which is
also used by the EVC for verification. Any attacker who gains read
access to this file can generate their own signed Movement Authorities.

One way to simulate a MITM/injection attacker:

1. Start all components as above.
2. Open an additional terminal and connect to the GSM-R admin interface:

   ```bash
   nc 127.0.0.1 9100
   ```

3. Craft a malicious JSON line with a very high `speed_kmh`, sign it
   using a separate script that knows the key from `rbc_key.txt`, and
   paste the full line into the admin connection. The emulator will
   inject it towards the Train.

4. The EVC will verify the signature, accept the MA, and the DMI will
   show the abnormal target speed.

You can create your own small helper script (outside this demo) that
reads `rbc_key.txt`, builds a payload, computes the HMAC-SHA256, and
prints the ready-to-send JSON line.

## Running the Testbed with Docker

From this directory you can run the complete system using Docker
Compose. All components share one image (see `Dockerfile`) and are
wired into two Docker networks:

- `public_net`: connects **RBC**, **GSM-R emulator**, and the **Train Radio**.
- `onboard_net`: connects the **Train Radio**, **EVC**, and **DMI**.

This models a dual-homed radio gateway that bridges the public network
to the internal onboard network.

To start everything:

```bash
docker compose up --build
```

This will start the five services defined in `docker-compose.yml`.

- The GSM-R admin / MITM interface is exposed on `localhost:9100`.
- The DMI UDP port is exposed on `localhost:9003/udp`.
- The DMI web UI is exposed on `http://localhost:8080/`.

You can then connect an attacker client from the host, for example:

```bash
nc 127.0.0.1 9100
```

and inject malicious signed Movement Authorities as before.

## Attack Framework

The testbed includes built-in attack tools for adversarial testing:

### Generic Attacks (JSON/Modbus)
```python
from attacks import AttackFramework

atk = AttackFramework(target_host="127.0.0.1", target_port=9100)

# Overspeed attack
atk.overspeed_attack(speed_limit=300.0, protocol="json")

# Emergency brake injection
atk.emergency_brake_attack(protocol="json")

# DoS flood
atk.dos_flood(duration=10.0, rate=100)
```

### Modbus-Specific Attacks
```python
from attacks import ModbusAttacks

atk = ModbusAttacks(target_host="127.0.0.1", target_port=502)

# Direct register manipulation
atk.overspeed_via_registers(speed_limit=250.0)

# Position spoofing
atk.manipulate_position(position_km=99.9)

# Function code fuzzing
results = atk.function_code_fuzzing(max_attempts=20)

# Register scanning
registers = atk.register_scanning(start=0, count=100)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for complete attack documentation.

## Running Unit Tests

Unit tests live under the `tests/` directory and focus on the
cryptographic signing and basic EVC behaviour.

First install `pytest` (in your virtualenv or system environment):

```bash
pip install pytest
```

Then, from this directory, run:

```bash
pytest
```

This will run tests such as:

- Protocol encoding/decoding (JSON, Modbus TCP)
- Signing + verification round-trip via `sign_message` and
  `verify_signature`.
- Protocol registry and abstraction layer
- Rejection of tampered Movement Authorities with mismatched signatures.
- Basic `DmiPublisher.update_ma` state update behaviour.
