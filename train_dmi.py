#!/usr/bin/env python3

import json
import os
import socket
import threading
from typing import Any, Dict

from flask import Flask, jsonify, render_template_string

UDP_HOST = os.getenv("DMI_LISTEN_HOST", "0.0.0.0")
UDP_PORT = int(os.getenv("DMI_LISTEN_PORT", "9003"))

HTTP_HOST = os.getenv("DMI_HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("DMI_HTTP_PORT", "8080"))


app = Flask(__name__)

_state_lock = threading.Lock()
_current_state: Dict[str, Any] = {
    "current_speed_kmh": 0.0,
    "target_speed_kmh": 0.0,
    "distance_to_go_m": 0.0,
    "timestamp": 0.0,
    "last_ma_id": None,
    "last_ma_issuer": "",
    "last_ma_timestamp": 0.0,
}


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>ETCS DMI</title>
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
            gap: 16px;
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
            font-size: 1.3rem;
        }
        .metric small {
            color: #9aa3d3;
            margin-left: 4px;
        }
        .timestamp {
            margin-top: 8px;
            font-size: 0.75rem;
            color: #6c75a3;
        }
        .ma {
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid rgba(255,255,255,0.08);
        }
        .ma .label {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: .18em;
            color: #9aa3d3;
            margin-bottom: 4px;
        }
        .ma-main {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 12px;
        }
        .ma-id {
            font-size: 1.1rem;
        }
        .ma-issuer {
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: .12em;
            color: #f1c96b;
        }
    </style>
</head>
<body>
    <div class="panel">
        <div class="speed">
            <div class="speed-label">Current speed</div>
            <div class="speed-value" id="current-speed">0.0</div>
            <div class="unit">km/h</div>
        </div>
        <div class="details">
            <div class="metric">
                <label>Target speed</label>
                <span id="target-speed">0.0</span><small>km/h</small>
            </div>
            <div class="metric">
                <label>Distance to go</label>
                <span id="distance">0.0</span><small>m</small>
            </div>
            <div class="timestamp" id="timestamp">Waiting for data…</div>
            <div class="ma">
                <div class="label">Last movement authority</div>
                <div class="ma-main">
                    <span class="ma-id" id="ma-id">—</span>
                    <span class="ma-issuer" id="ma-issuer"></span>
                </div>
                <div class="timestamp" id="ma-ts"></div>
            </div>
        </div>
    </div>

    <script>
        async function refresh() {
            try {
                const res = await fetch('/status');
                if (!res.ok) return;
                const data = await res.json();
                document.getElementById('current-speed').textContent = data.current_speed_kmh.toFixed(1);
                document.getElementById('target-speed').textContent = data.target_speed_kmh.toFixed(1);
                document.getElementById('distance').textContent = data.distance_to_go_m.toFixed(1);
                const ts = new Date(data.timestamp * 1000);
                if (!isNaN(ts.getTime())) {
                    document.getElementById('timestamp').textContent = 'Last update: ' + ts.toLocaleTimeString();
                }

                if (data.last_ma_id !== null) {
                    document.getElementById('ma-id').textContent = 'ID ' + data.last_ma_id;
                } else {
                    document.getElementById('ma-id').textContent = '—';
                }
                document.getElementById('ma-issuer').textContent = data.last_ma_issuer || '';
                const maTs = new Date(data.last_ma_timestamp * 1000);
                if (!isNaN(maTs.getTime()) && data.last_ma_timestamp) {
                    document.getElementById('ma-ts').textContent = 'MA time: ' + maTs.toLocaleTimeString();
                } else {
                    document.getElementById('ma-ts').textContent = '';
                }
            } catch (e) {
                // ignore intermittent errors
            }
        }
        setInterval(refresh, 500);
        refresh();
    </script>
</body>
</html>
"""


def _udp_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((UDP_HOST, UDP_PORT))
        print(f"[DMI] Listening for EVC updates on {UDP_HOST}:{UDP_PORT}")
        while True:
            data, addr = s.recvfrom(4096)
            try:
                msg = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                print(f"[DMI] Received non-JSON data from {addr}: {data!r}")
                continue

            current = float(msg.get("current_speed_kmh", 0.0))
            target = float(msg.get("target_speed_kmh", 0.0))
            distance = float(msg.get("distance_to_go_m", 0.0))
            timestamp = float(msg.get("timestamp", 0.0))
            last_ma_id = msg.get("last_ma_id")
            last_ma_issuer = str(msg.get("last_ma_issuer", ""))
            last_ma_timestamp = float(msg.get("last_ma_timestamp", 0.0))

            with _state_lock:
                _current_state["current_speed_kmh"] = current
                _current_state["target_speed_kmh"] = target
                _current_state["distance_to_go_m"] = distance
                _current_state["timestamp"] = timestamp
                _current_state["last_ma_id"] = last_ma_id
                _current_state["last_ma_issuer"] = last_ma_issuer
                _current_state["last_ma_timestamp"] = last_ma_timestamp

            # Still log to console for debugging
            print(
                f"[DMI] Current: {current:5.1f} km/h  Target: {target:5.1f} km/h  Distance to Go: {distance:7.1f} m"
            )


@app.route("/")
def index() -> str:
        return render_template_string(HTML_TEMPLATE)


@app.route("/status")
def status() -> Any:
        with _state_lock:
                return jsonify(_current_state)


def run_dmi() -> None:
        t = threading.Thread(target=_udp_listener, daemon=True)
        t.start()
        print(f"[DMI] Web UI listening on http://{HTTP_HOST}:{HTTP_PORT}")
        app.run(host=HTTP_HOST, port=HTTP_PORT, threaded=True)


if __name__ == "__main__":
    run_dmi()
