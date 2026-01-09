#!/usr/bin/env python3

import json
import logging
import os
import socket
import threading
import time
from datetime import datetime
from typing import Any, Dict

from flask import Flask, jsonify, render_template_string, request

UDP_HOST = os.getenv("DMI_LISTEN_HOST", "0.0.0.0")
UDP_PORT = int(os.getenv("DMI_LISTEN_PORT", "9003"))

HTTP_HOST = os.getenv("DMI_HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("DMI_HTTP_PORT", "8080"))

EVC_DRIVER_HOST = os.getenv("EVC_DRIVER_HOST", "evc")
EVC_DRIVER_PORT = int(os.getenv("EVC_DRIVER_PORT", "9102"))

# Attacker path to GSM-R admin (use host.docker.internal:9100 by default so
# the DMI container can talk to the host-exposed GSM-R admin port).
GSMR_ADMIN_HOST = os.getenv("GSMR_ADMIN_HOST", "host.docker.internal")
GSMR_ADMIN_PORT = int(os.getenv("GSMR_ADMIN_PORT", "9100"))

WATCHDOG_TIMEOUT = 10.0


def ts() -> str:
        return datetime.now().strftime("%H:%M:%S")


app = Flask(__name__)

# Silence Flask/werkzeug HTTP access logs to avoid console spam
logging.getLogger("werkzeug").setLevel(logging.ERROR)
app.logger.disabled = True

_state_lock = threading.Lock()
_state: Dict[str, Any] = {
        "display_speed": 0.0,
        "raw_speed_limit": 0.0,
        "position_km": 0.0,
    "next_checkpoint_km": 0.0,
        "timestamp": 0.0,
        "status": "WAITING",
    "accept_unsigned": False,
}

_events_lock = threading.Lock()
_events: list[str] = []
_MAX_EVENTS = 30


HTML = """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>ETCS DMI - Iron Range</title>
    <style>
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #0b1020;
            color: #f5f7ff;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .panel {
            background: #141a33;
            border-radius: 16px;
            padding: 24px 32px;
            box-shadow: 0 18px 45px rgba(0,0,0,0.45);
            display: grid;
            grid-template-columns: 1.5fr 1fr;
            column-gap: 32px;
            min-width: 520px;
        }
        .speed {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            border-right: 1px solid rgba(255,255,255,0.08);
            padding-right: 24px;
        }
        .speed-label {
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: .18em;
            color: #9aa3d3;
            margin-bottom: 8px;
        }
        .speed-value {
            font-size: 4rem;
            font-weight: 600;
            letter-spacing: .05em;
        }
        .unit {
            font-size: 1.2rem;
            color: #9aa3d3;
            margin-top: -8px;
        }
        .details {
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 12px;
        }
        .metric label {
            display: block;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: .18em;
            color: #9aa3d3;
            margin-bottom: 4px;
        }
        .metric span {
            font-size: 1.2rem;
        }
        .metric small {
            color: #9aa3d3;
            margin-left: 4px;
        }
        .status {
            margin-top: 8px;
            font-size: 0.9rem;
            color: #f1c96b;
        }
        .timestamp {
            margin-top: 4px;
            font-size: 0.75rem;
            color: #6c75a3;
        }
        .toggle-row {
            margin-top: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.8rem;
            color: #9aa3d3;
        }
        .toggle-row button {
            padding: 4px 10px;
            border-radius: 999px;
            border: none;
            background: #2a936a;
            color: #f5f7ff;
            cursor: pointer;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: .12em;
        }
        .toggle-row button.off {
            background: #8a2a3b;
        }
        .driver-row {
            margin-top: 10px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 0.75rem;
            color: #9aa3d3;
        }
        .driver-row input {
            background: #0b1020;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.12);
            padding: 4px 8px;
            color: #f5f7ff;
        }
        .driver-row button {
            align-self: flex-start;
            padding: 4px 10px;
            border-radius: 999px;
            border: none;
            background: #2a6f93;
            color: #f5f7ff;
            cursor: pointer;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: .12em;
        }
        .events {
            margin-top: 12px;
            border-top: 1px solid rgba(255,255,255,0.12);
            padding-top: 8px;
            max-height: 150px;
            overflow-y: auto;
            font-size: 0.75rem;
            color: #9aa3d3;
        }
        .events-title {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: .18em;
            margin-bottom: 4px;
            color: #9aa3d3;
        }
        .events ul {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        .events li {
            margin-bottom: 2px;
        }
        .attack-row {
            margin-top: 10px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 0.75rem;
            color: #9aa3d3;
        }
        .attack-row input {
            background: #0b1020;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.12);
            padding: 4px 8px;
            color: #f5f7ff;
        }
        .attack-row button {
            align-self: flex-start;
            padding: 4px 10px;
            border-radius: 999px;
            border: none;
            background: #b4551a;
            color: #f5f7ff;
            cursor: pointer;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: .12em;
        }
    </style>
</head>
<body>
    <div class="panel">
        <div class="speed">
            <div class="speed-label">Display speed</div>
            <div class="speed-value" id="display-speed">0.0</div>
            <div class="unit">km/h</div>
        </div>
        <div class="details">
            <div class="metric">
        <label>RBC speed limit</label>
                <span id="raw-speed">0.0</span><small>km/h</small>
            </div>
        <div class="metric">
        <label>Train position</label>
        <span id="position">0.0</span><small>km</small>
        </div>
    <div class="metric">
    <label>Next checkpoint at</label>
    <span id="next-checkpoint">0.0</span><small>km</small>
    </div>
            <div class="status" id="status">WAITING FOR DATA…</div>
            <div class="timestamp" id="timestamp"></div>
            <div class="toggle-row">
                <span>Signature policy:</span>
                <button id="sig-toggle" class="off" onclick="toggleUnsigned()">
                    STRICT (signed only)
                </button>
            </div>
            <div class="driver-row">
                <span>Driver controls (train speed):</span>
                <div>
                    <input id="drv-speed" type="number" step="1" placeholder="target speed km/h (e.g. 80)">
                </div>
                <div style="display:flex; gap:6px; margin-top:4px;">
                    <button onclick="sendDriverSpeed()">SET SPEED</button>
                    <button onclick="sendDriverBrake()">BRAKE / STOP</button>
                </div>
            </div>
            <div class="attack-row">
                <span>Inject MA towards Train (simulated attacker):</span>
                <div>
                    <input id="atk-pos" type="number" step="0.1" placeholder="position_km (e.g. 1.0)">
                </div>
                <div>
                    <input id="atk-next" type="number" step="0.1" placeholder="next_checkpoint_km (e.g. 2.0)">
                </div>
                <div>
                    <input id="atk-speed" type="number" step="1" placeholder="speed_limit km/h (e.g. 150)">
                </div>
                <button onclick="sendAttackMA()">SEND ATTACK MA</button>
            </div>
            <div class="events">
                <div class="events-title">Event log</div>
                <ul id="events-list"></ul>
            </div>
        </div>
    </div>

    <script>
        async function refresh() {
            try {
                const res = await fetch('/status');
                if (!res.ok) return;
                const data = await res.json();
                document.getElementById('display-speed').textContent = data.display_speed.toFixed(1);
                document.getElementById('raw-speed').textContent = data.raw_speed_limit.toFixed(1);
                var pos = (typeof data.position_km === 'number' ? data.position_km : 0);
                document.getElementById('position').textContent = pos.toFixed(1);
                var nextCp = (typeof data.next_checkpoint_km === 'number' ? data.next_checkpoint_km : 0);
                document.getElementById('next-checkpoint').textContent = nextCp.toFixed(1);
                document.getElementById('status').textContent = data.status;
                const ts = new Date(data.timestamp * 1000);
                if (!isNaN(ts.getTime()) && data.timestamp) {
                    document.getElementById('timestamp').textContent = 'Last update: ' + ts.toLocaleTimeString();
                } else {
                    document.getElementById('timestamp').textContent = '';
                }

                const btn = document.getElementById('sig-toggle');
                if (data.accept_unsigned) {
                    btn.classList.remove('off');
                    btn.textContent = 'RELAXED (accept unsigned)';
                } else {
                    btn.classList.add('off');
                    btn.textContent = 'STRICT (signed only)';
                }

                const events = Array.isArray(data.events) ? data.events : [];
                const list = document.getElementById('events-list');
                list.innerHTML = '';
                for (const ev of events) {
                    const li = document.createElement('li');
                    li.textContent = ev;
                    list.appendChild(li);
                }
            } catch (e) {
                // ignore
            }
        }
        async function toggleUnsigned() {
            try {
                await fetch('/toggle_unsigned', { method: 'POST' });
                // state will be reflected on next refresh
            } catch (e) {
                // ignore
            }
        }
        async function sendDriverSpeed() {
            try {
                const v = parseFloat(document.getElementById('drv-speed').value || '0');
                await fetch('/driver_speed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ speed_kmh: v })
                });
            } catch (e) {
                // ignore
            }
        }
        async function sendDriverBrake() {
            try {
                await fetch('/driver_brake', { method: 'POST' });
            } catch (e) {
                // ignore
            }
        }
        async function sendAttackMA() {
            try {
                const pos = parseFloat(document.getElementById('atk-pos').value || '0');
                const nextCp = parseFloat(document.getElementById('atk-next').value || '0');
                const speed = parseFloat(document.getElementById('atk-speed').value || '0');
                const payload = {
                    type: 'MA',
                    ma_id: Date.now(),
                    position_km: pos,
                    next_checkpoint_km: nextCp,
                    speed_limit: speed,
                    message: 'UI_ATTACK'
                };
                await fetch('/inject_ma', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch (e) {
                // ignore
            }
        }
        // Poll once per second to keep load low
        setInterval(refresh, 1000);
        refresh();
    </script>
</body>
</html>
"""


def udp_listener() -> None:
        last_packet_time = time.time()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.bind((UDP_HOST, UDP_PORT))
                s.settimeout(0.5)
                print(f"[{ts()}] [DMI] Listening for EVC updates on {UDP_HOST}:{UDP_PORT}")
                while True:
                    now = time.time()
                    if now - last_packet_time > WATCHDOG_TIMEOUT:
                        with _state_lock:
                            _state["status"] = "COMMUNICATION LOST - EMERGENCY BRAKE"

                    try:
                        data, addr = s.recvfrom(4096)
                    except socket.timeout:
                        continue

                    last_packet_time = time.time()
                    event_msg = ""
                    try:
                        msg = json.loads(data.decode("utf-8"))
                        display_speed = float(msg.get("display_speed", 0.0))
                        raw_speed = float(msg.get("raw_speed_limit", 0.0))
                        position_km = float(msg.get("position_km", 0.0))
                        next_cp_km = float(msg.get("next_checkpoint_km", 0.0))
                        ts_val = float(msg.get("timestamp", 0.0))
                        event_msg = msg.get("event", "")
                    except (json.JSONDecodeError, ValueError):
                        print(f"[{ts()}] [DMI] Invalid UDP data from {addr}: {data!r}")
                        continue

                    with _state_lock:
                        _state["display_speed"] = display_speed
                        _state["raw_speed_limit"] = raw_speed
                        _state["position_km"] = position_km
                        _state["next_checkpoint_km"] = next_cp_km
                        _state["timestamp"] = ts_val
                        _state["status"] = "OK"

                    if isinstance(event_msg, str) and event_msg:
                        with _events_lock:
                            if not _events or _events[-1] != event_msg:
                                _events.append(event_msg)
                                if len(_events) > _MAX_EVENTS:
                                    del _events[0:len(_events) - _MAX_EVENTS]

                    print(
                        f"[{ts()}] [DMI] Packet from {addr}: display_speed={display_speed:.1f} km/h "
                        f"(raw_limit={raw_speed:.1f})"
                    )


@app.route("/")
def index() -> str:
        return render_template_string(HTML)


@app.route("/status")
def status() -> Any:
    with _state_lock, _events_lock:
        data = dict(_state)
        data["events"] = list(_events)
        return jsonify(data)


def _send_driver_command(cmd: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(1.0)
            s.connect((EVC_DRIVER_HOST, EVC_DRIVER_PORT))
            s.sendall((cmd + "\n").encode("utf-8"))
        except OSError as exc:
            print(f"[{ts()}] [DMI] Failed to send driver command '{cmd}': {exc}")


@app.route("/toggle_unsigned", methods=["POST"])
def toggle_unsigned() -> Any:
    with _state_lock:
        current = bool(_state.get("accept_unsigned", False))
        new_val = not current
        _state["accept_unsigned"] = new_val

    cmd = "UNSIGNED ON" if new_val else "UNSIGNED OFF"
    _send_driver_command(cmd)
    return jsonify({"accept_unsigned": new_val})


@app.route("/driver_speed", methods=["POST"])
def driver_speed() -> Any:
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:  # noqa: BLE001
        return jsonify({"error": "invalid JSON"}), 400

    speed = float(data.get("speed_kmh", 0.0))
    _send_driver_command(f"SPEED {speed}")
    return jsonify({"ok": True})


@app.route("/driver_brake", methods=["POST"])
def driver_brake() -> Any:
    _send_driver_command("BRAKE")
    return jsonify({"ok": True})


def _send_attack_line(line: str) -> None:
    """Send a raw line towards the Train via the GSM-R admin port.

    This simulates what an nc client on the host would do.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(1.0)
            s.connect((GSMR_ADMIN_HOST, GSMR_ADMIN_PORT))
            s.sendall((line + "\n").encode("utf-8"))
        except OSError as exc:
            print(f"[{ts()}] [DMI] Failed to send attack line: {exc}")


@app.route("/inject_ma", methods=["POST"])
def inject_ma() -> Any:
    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:  # noqa: BLE001
        return jsonify({"error": "invalid JSON"}), 400

    message = {
        "payload": payload,
        # Deliberately bogus signature so behaviour depends on
        # strict vs relaxed mode in the EVC.
        "signature": "00deadbeef",
    }
    line = json.dumps(message)
    _send_attack_line(line)
    return jsonify({"ok": True})


def run_dmi() -> None:
        t = threading.Thread(target=udp_listener, daemon=True)
        t.start()
        print(f"[{ts()}] [DMI] Web UI listening on http://{HTTP_HOST}:{HTTP_PORT}")
        app.run(host=HTTP_HOST, port=HTTP_PORT, threaded=True)


if __name__ == "__main__":
        run_dmi()
