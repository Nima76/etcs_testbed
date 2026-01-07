# ERTMS/ETCS Cybersecurity Testbed: The "Iron Range"

## 1. Architectural Overview
The testbed simulates a complete end-to-end Railway Control System divided into three distinct zones. This structure allows us to test attacks on the Trackside, the Network, and the Onboard components independently.

### Zone A: Trackside (The Authority)
* **Component:** `rbc_server.py`
* **Role:** The Radio Block Centre. It generates "Movement Authorities" (Speed/Distance) based on a database.
* **Vukberabilities & Attack Surface:**
* **Vulnerability:** The RBC generate Movment Authorities and sign them with specifc key stored somewhere unsafe (e.g., local file). and attacker had access to this file. so attacker can sign a bad command and send to train

### Zone B: The "Public" Network
* **Component:** `gsmr_network_emulator.py`
* **Role:** Acts as the "Air Gap" or Mobile Network Service Provider.
* **Function:** It is a TCP Proxy. It listens on one port for the RBC and another for the Train, relaying messages between them.
* **Attack Surface:** This component prints all traffic to the console (Sniffing) and allows for "Noise Injection" or "Man-in-the-Middle" if an attacker connects to its administrative interface.

### Zone C: Onboard Train (The Victim)
This zone simulates the internal network of the train. All components run on `same network` but use distinct ports to simulate an "Onboard Ethernet Bus."

1.  **GSM-R Receiver (`train_radio.py`):**
    * The Gateway. It connects to Zone B (Network Emulator) and forwards data to the EVC.
2.  **EVC Core (`train_evc.py`):**
    * The Brain. It reads `train_data.conf` (Wheel Diameter) at startup.
    * It processes incoming commands from the Radio.
    * It calculates current speed and sends display data to the DMI.
3.  **DMI (`train_dmi.py`):**
    * The Screen. It listens for UDP packets from the EVC to update the driver's display.

## 2. Communication Topology & Ports
* **RBC (Trackside):** Listens on TCP `9000`.
* **Network Emulator:** Connects to RBC `9000`; Listens on TCP `9001` for the Train.
* **Train Radio:** Connects to Network `9001`; Forwards to EVC via TCP `9002`.
* **Train EVC:** Listens on TCP `9002` (Internal Bus); Sends to DMI via UDP `9003`.
* **Train DMI:** Listens on UDP `9003`.

## 3. Attack Scenarios & Validation

### Scenario 1: RBC Compromise (Bad Command)
* **Attack:** Attacker gains shell access to the RBC Server and modifies `rbc_db.json` to set `speed_limit: 300` (Overspeed).
* **Execution:** Run a script or manual command to overwrite the JSON file while the system is running.
* **Observation:** The RBC reads the new file, sends "300" to the Network -> Radio -> EVC. EVC calculates derailment risk.
* **ERTMS Check:** Does the EVC validate the "Safety Layer" (MAC/Key)? (In this testbed: No, showing the failure).

### Scenario 2: Parameter Tampering (Wheel Diameter)
* **Attack:** Attacker modifies `train_data.conf` on the EVC machine. Changes `wheel_diameter` from `1000` to `500`.
* **Execution:** Restart EVC process.
* **Observation:** EVC reads bad config. It calculates speed incorrectly (e.g., Train thinks it's doing 50km/h, but physically doing 100km/h).
* **ERTMS Check:** Does the EVC perform a CRC/Integrity check on the config file at boot?

### Scenario 3: DMI Blindness (DoS Flood)
* **Attack:** Attacker floods UDP Port `9003` (DMI Port) with garbage data.
* **Execution:** Use `hping3` or a Python script to send 10,000 packets/sec to the DMI.
* **Observation:** The DMI script freezes or displays garbage, preventing the driver from seeing the real RBC commands.
* **ERTMS Check:** Does the DMI have a "Stale Data" timer (e.g., screen goes black/red if no valid EVC packet for 1 second)?

### Scenario 4: Kill Safety Process
* **Attack:** Attacker kills the `train_evc.py` process.
* **Execution:** `kill -9 [PID]`
* **Observation:** EVC dies. DMI stops updating.
* **ERTMS Check:** Does the "Emergency Brake" trigger? (Since this is software, we check if the DMI detects the loss of the EVC heartbeat).