#!/usr/bin/env python3

import json
import os
import socket
import threading
import time
import hmac
import hashlib
from typing import Dict, Any

HOST = os.getenv("RBC_LISTEN_HOST", "0.0.0.0")
PORT = int(os.getenv("RBC_LISTEN_PORT", "9000"))
KEY_FILE = os.getenv("RBC_KEY_FILE", "rbc_key.txt")


def load_secret_key() -> bytes:
    """Load the RBC signing key from a local file (intentionally insecure)."""
    with open(KEY_FILE, "rb") as f:
        return f.read().strip()


def sign_message(key: bytes, payload: Dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    mac = hmac.new(key, data, hashlib.sha256).hexdigest()
    return mac


def build_movement_authority(counter: int) -> Dict[str, Any]:
    # Toy movement authority for demonstration
    base_speed = 40
    base_distance = 1000
    return {
        "type": "MA",
        "id": counter,
        "issuer": "RBC",  # informational only; attacker can spoof
        "speed_kmh": base_speed + 10 * (counter % 5),
        "distance_m": base_distance + 250 * (counter % 4),
        "timestamp": time.time(),
    }


class RbcClientHandler(threading.Thread):
    def __init__(self, conn: socket.socket, addr, key: bytes):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.key = key
        self.running = True

    def run(self) -> None:
        print(f"[RBC] Client connected from {self.addr}")
        counter = 1
        buffer = b""
        awaiting_ack_for: int | None = None
        try:
            while self.running:
                # If not currently waiting for an ACK, issue a new
                # Movement Authority to the train.
                if awaiting_ack_for is None:
                    ma_payload = build_movement_authority(counter)
                    signature = sign_message(self.key, ma_payload)
                    message = {
                        "payload": ma_payload,
                        "signature": signature,
                    }
                    line = json.dumps(message).encode("utf-8") + b"\n"
                    self.conn.sendall(line)
                    print(
                        f"[RBC] Sent MA {counter} to {self.addr}: "
                        f"speed={ma_payload['speed_kmh']} km/h distance={ma_payload['distance_m']} m"
                    )
                    awaiting_ack_for = counter
                    counter += 1

                # Wait for ACKs or other messages from the train
                self.conn.settimeout(1.0)
                try:
                    chunk = self.conn.recv(4096)
                    if not chunk:
                        print(f"[RBC] Client {self.addr} disconnected")
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        raw_line, buffer = buffer.split(b"\n", 1)
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        try:
                            msg = json.loads(raw_line.decode("utf-8"))
                        except json.JSONDecodeError:
                            print(f"[RBC] Received non-JSON line: {raw_line!r}")
                            continue
                        if not isinstance(msg, dict):
                            continue
                        if msg.get("type") == "ACK":
                            ack_id = msg.get("ma_id")
                            train_id = msg.get("train_id", "?")
                            position = msg.get("position_m")
                            print(
                                f"[RBC] ACK from train {train_id} for MA {ack_id} "
                                f"at position {position} m"
                            )
                            if ack_id == awaiting_ack_for:
                                awaiting_ack_for = None
                except socket.timeout:
                    # No data; loop again. If still waiting for ACK,
                    # we simply keep waiting in this simple demo.
                    pass
        except ConnectionError:
            print(f"[RBC] Connection error with {self.addr}")
        finally:
            self.conn.close()


def start_server() -> None:
    key = load_secret_key()
    print(f"[RBC] Loaded secret key from {KEY_FILE} (insecure storage!)")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)
        print(f"[RBC] Listening on {HOST}:{PORT}")

        while True:
            conn, addr = s.accept()
            handler = RbcClientHandler(conn, addr, key)
            handler.start()


if __name__ == "__main__":
    start_server()
