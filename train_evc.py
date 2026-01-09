#!/usr/bin/env python3

import json
import os
import socket
import threading
import time
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Any

HOST = os.getenv("EVC_LISTEN_HOST", "0.0.0.0")
PORT = int(os.getenv("EVC_LISTEN_PORT", "9002"))

DMI_HOST = os.getenv("DMI_HOST", "127.0.0.1")
DMI_PORT = int(os.getenv("DMI_PORT", "9003"))

TRAIN_DATA_FILE = os.getenv("TRAIN_DATA_FILE", "train_data.conf")
KEY_FILE = os.getenv("RBC_KEY_FILE", "rbc_key.txt")


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def load_wheel_diameter() -> float:
    wheel_diameter = 1000.0
    section = None
    try:
        with open(TRAIN_DATA_FILE, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip().upper()
                    continue
                if section == "PHYSICAL" and "=" in line:
                    key, value = line.split("=", 1)
                    if key.strip() == "wheel_diameter":
                        try:
                            wheel_diameter = float(value.strip())
                        except ValueError:
                            pass
    except FileNotFoundError:
        print(f"[{ts()}] [EVC] WARNING: {TRAIN_DATA_FILE} not found, using default wheel_diameter={wheel_diameter}")
    print(f"[{ts()}] [EVC] Loaded wheel_diameter={wheel_diameter} mm")
    return wheel_diameter


def load_secret_key() -> bytes:
    try:
        with open(KEY_FILE, "rb") as f:
            key = f.read().strip()
    except FileNotFoundError:
        print(f"[{ts()}] [EVC] WARNING: key file {KEY_FILE} not found, using default demo key")
        key = b"super_insecure_demo_key_for_rbc"
    return key


def verify_signature(key: bytes, payload: Dict[str, Any], signature: str) -> bool:
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    mac = hmac.new(key, data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature)


def start_evc() -> None:
    key = load_secret_key()
    wheel_diameter = load_wheel_diameter()
    factor = wheel_diameter / 1000.0

    # Shared state for simple train physics
    state_lock = threading.Lock()
    state: Dict[str, Any] = {
        "target_speed_limit": 0.0,       # km/h from RBC (zone limit)
        "driver_target_speed": 0.0,      # km/h commanded by driver
        "physical_speed": 0.0,           # km/h actual train speed
        "position_km": 0.0,              # current position along line
        "next_checkpoint_km": 0.0,       # where the next checkpoint is
        "current_segment": 0,
        "last_reported_segment": 0,
        "last_reported_position_km": 0.0,
        "accept_unsigned": False,        # whether to accept unsigned/invalid-signed MAs
        "last_event": "",
        "wheel_diameter": wheel_diameter,
    }

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def record_event(msg: str) -> None:
        text = f"{ts()} {msg}"
        with state_lock:
            state["last_event"] = text

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(1)
        print(f"[{ts()}] [EVC] Listening on {HOST}:{PORT}")

        conn, addr = srv.accept()
        print(f"[{ts()}] [EVC] Radio connected from {addr}")

        # Optional driver command interface (TCP) so speed policy can be changed
        # onboard and the scenario can be reset without restarting containers.
        def driver_server() -> None:
            host = os.getenv("EVC_DRIVER_HOST", "0.0.0.0")
            port = int(os.getenv("EVC_DRIVER_PORT", "9102"))
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ds:
                ds.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    ds.bind((host, port))
                except OSError as exc:
                    print(f"[{ts()}] [EVC] Driver server bind failed: {exc}")
                    return
                ds.listen(1)
                print(
                    f"[{ts()}] [EVC] Driver command interface on {host}:{port} "
                    f"(commands: SPEED <kmh>, BRAKE, STOP, RESET, UNSIGNED ON/OFF)"
                )
                while True:
                    dconn, daddr = ds.accept()
                    print(f"[{ts()}] [EVC] Driver connected from {daddr}")
                    with dconn:
                        buf = b""
                        while True:
                            chunk = dconn.recv(1024)
                            if not chunk:
                                break
                            buf += chunk
                            while b"\n" in buf:
                                line, buf = buf.split(b"\n", 1)
                                cmd = line.decode("utf-8", errors="ignore").strip()
                                if not cmd:
                                    continue
                                parts = cmd.split()
                                cmd_name = parts[0].upper()
                                if cmd_name == "SPEED" and len(parts) == 2:
                                    try:
                                        val = float(parts[1])
                                    except ValueError:
                                        dconn.sendall(b"ERR invalid speed\n")
                                        continue
                                    with state_lock:
                                        state["driver_target_speed"] = val
                                    dconn.sendall(f"OK speed set to {val} km/h\n".encode("utf-8"))
                                    record_event(f"Driver set speed to {val:.1f} km/h")
                                elif cmd_name in {"BRAKE", "STOP"}:
                                    with state_lock:
                                        state["driver_target_speed"] = 0.0
                                    dconn.sendall(b"OK brake applied\n")
                                    record_event("Driver applied brake")
                                elif cmd_name == "UNSIGNED" and len(parts) == 2:
                                    mode = parts[1].upper()
                                    if mode not in {"ON", "OFF"}:
                                        dconn.sendall(b"ERR expected UNSIGNED ON or UNSIGNED OFF\n")
                                        continue
                                    accept = mode == "ON"
                                    with state_lock:
                                        state["accept_unsigned"] = accept
                                    dconn.sendall(
                                        f"OK accept_unsigned set to {accept}\n".encode("utf-8")
                                    )
                                    record_event(
                                        "Signature policy set to RELAXED (accept unsigned)"
                                        if accept
                                        else "Signature policy set to STRICT (signed only)"
                                    )
                                elif cmd_name == "RESET":
                                    # Reset local EVC physics state and restart from position 0.
                                    with state_lock:
                                        state["target_speed_limit"] = 0.0
                                        state["driver_target_speed"] = 0.0
                                        state["physical_speed"] = 0.0
                                        state["position_km"] = 0.0
                                        state["next_checkpoint_km"] = 0.0
                                        state["current_segment"] = 0
                                        state["last_reported_segment"] = 0
                                        state["last_reported_position_km"] = 0.0
                                    # Inform RBC that we are starting again from 0 km.
                                    hello_msg = {
                                        "type": "HELLO",
                                        "train_id": "TrainA",
                                        "position_km": 0.0,
                                    }
                                    try:
                                        conn.sendall(json.dumps(hello_msg).encode("utf-8") + b"\n")
                                        dconn.sendall(b"OK reset: state cleared and HELLO sent\n")
                                        print(f"[{ts()}] [EVC] RESET requested by driver; HELLO re-sent")
                                        record_event("Scenario reset by driver; HELLO re-sent")
                                    except OSError as exc:
                                        err = f"ERR reset failed to send HELLO: {exc}\n".encode("utf-8")
                                        dconn.sendall(err)
                                else:
                                    dconn.sendall(
                                        b"ERR expected 'SPEED <kmh>', BRAKE, STOP, RESET, or UNSIGNED ON/OFF\n"
                                    )

        threading.Thread(target=driver_server, daemon=True).start()

        # Physics loop: update speed and position continuously and send to DMI
        def physics_loop() -> None:
            last = time.time()
            # simple linear accel / brake in km/h per second
            max_rate = 10.0
            while True:
                time.sleep(1)
                now = time.time()
                dt = now - last
                last = now
                with state_lock:
                    rbc_limit = state["target_speed_limit"]
                    driver_cmd = state["driver_target_speed"]
                    if driver_cmd <= 0.0:
                        driver_cmd = rbc_limit

                    v = state["physical_speed"]
                    # accelerate or brake towards driver commanded speed
                    if v < driver_cmd:
                        v = min(v + max_rate * dt, driver_cmd)
                    elif v > driver_cmd:
                        v = max(v - max_rate * dt, driver_cmd)
                    # update position from current speed
                    state["physical_speed"] = v
                    state["position_km"] += (v * dt) / 3600.0
                    position_km = state["position_km"]
                    next_cp = state["next_checkpoint_km"]
                    current_seg = state["current_segment"]
                    last_reported = state["last_reported_segment"]
                    last_pos_report = state["last_reported_position_km"]

                    # If we passed the checkpoint, inform RBC once
                    if next_cp > 0.0 and position_km >= next_cp and current_seg > last_reported:
                        msg = {
                            "type": "CHECKPOINT_REACHED",
                            "train_id": "TrainA",
                            "segment": current_seg,
                            "position_km": position_km,
                            "timestamp": now,
                        }
                        try:
                            conn.sendall(json.dumps(msg).encode("utf-8") + b"\n")
                            print(f"[{ts()}] [EVC] Sent CHECKPOINT_REACHED for segment={current_seg}")
                            state["last_reported_segment"] = current_seg
                        except OSError:
                            pass

                    # Periodic position report every 0.5 km
                    if position_km - last_pos_report >= 0.5:
                        pos_msg = {
                            "type": "POSITION_REPORT",
                            "train_id": "TrainA",
                            "position_km": position_km,
                            "speed_kmh": v,
                            "timestamp": now,
                        }
                        try:
                            conn.sendall(json.dumps(pos_msg).encode("utf-8") + b"\n")
                            state["last_reported_position_km"] = position_km
                            print(
                                f"[{ts()}] [EVC] Sent POSITION_REPORT position_km={position_km:.3f} "
                                f"speed={v:.1f} km/h"
                            )
                        except OSError:
                            pass

                    # Compute display speed using wheel diameter factor
                    display_speed = v * factor
                    event_msg = state.get("last_event", "")

                out = {
                    "display_speed": display_speed,
                    "raw_speed_limit": rbc_limit,
                    "position_km": position_km,
                    "next_checkpoint_km": next_cp,
                    "timestamp": now,
                    "event": event_msg,
                }
                try:
                    udp_sock.sendto(json.dumps(out).encode("utf-8"), (DMI_HOST, DMI_PORT))
                except OSError:
                    pass

        # Initial HELLO handshake towards RBC via Radio + GSM-R
        hello = {"type": "HELLO", "train_id": "TrainA", "position_km": 0.0}
        try:
            conn.sendall(json.dumps(hello).encode("utf-8") + b"\n")
            print(f"[{ts()}] [EVC] Sent HELLO handshake")
        except OSError:
            print(f"[{ts()}] [EVC] Failed to send HELLO, closing")
            return

        # Start the physics thread
        threading.Thread(target=physics_loop, daemon=True).start()

        buffer = b""
        with conn:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    print(f"[{ts()}] [EVC] Radio disconnected")
                    break
                buffer += chunk

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        print(f"[{ts()}] [EVC] Invalid JSON from radio: {line!r}")
                        continue

                    payload = msg.get("payload")
                    signature = msg.get("signature", "")
                    if not isinstance(payload, dict):
                        print(f"[{ts()}] [EVC] Invalid payload structure: {msg!r}")
                        continue

                    with state_lock:
                        accept_unsigned = bool(state.get("accept_unsigned", False))

                    valid_sig = verify_signature(key, payload, signature)
                    if not valid_sig and not accept_unsigned:
                        print(f"[{ts()}] [EVC] INVALID SIGNATURE, discarding message (strict mode)")
                        record_event("MA rejected: invalid signature (strict mode)")
                        continue
                    if not valid_sig and accept_unsigned:
                        print(f"[{ts()}] [EVC] INVALID SIGNATURE, but accept_unsigned=True -> ACCEPTING")
                        record_event("MA accepted with INVALID signature (relaxed mode)")

                    ptype = payload.get("type", "MA")
                    speed_limit = float(payload.get("speed_limit", 0.0))
                    next_cp = float(payload.get("next_checkpoint_km", 0.0))

                    with state_lock:
                        state["target_speed_limit"] = speed_limit
                        state["next_checkpoint_km"] = next_cp
                        # By default obey RBC; emergency updates forcibly clamp driver command.
                        # In unsigned/relaxed mode, injected MAs can also change target speed.
                        if ptype == "EMERGENCY_UPDATE" or state["driver_target_speed"] <= 0.0:
                            state["driver_target_speed"] = speed_limit

                    ma_id = payload.get("ma_id")
                    if ptype == "EMERGENCY_UPDATE" and speed_limit <= 0.0:
                        record_event("Emergency brake from RBC (speed_limit=0)")
                    elif ptype == "EMERGENCY_UPDATE":
                        record_event(f"Emergency slowdown from RBC to {speed_limit:.1f} km/h")
                    else:
                        record_event(
                            f"New MA from RBC: ma_id={ma_id}, speed_limit={speed_limit:.1f} km/h, "
                            f"next_cp={next_cp:.3f} km"
                        )

                    print(
                        f"[{ts()}] [EVC] {ptype} ma_id={ma_id} speed_limit={speed_limit} next_cp={next_cp} -> "
                        f"target_speed updated (wheel_diameter={wheel_diameter} mm)"
                    )


if __name__ == "__main__":
    start_evc()
