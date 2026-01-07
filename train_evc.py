#!/usr/bin/env python3

import json
import os
import socket
import threading
import time
import hmac
import hashlib
from typing import Dict, Any, Optional

HOST = os.getenv("EVC_LISTEN_HOST", "0.0.0.0")
PORT = int(os.getenv("EVC_LISTEN_PORT", "9002"))

DMI_HOST = os.getenv("DMI_HOST", "127.0.0.1")
DMI_PORT = int(os.getenv("DMI_PORT", "9003"))

KEY_FILE = os.getenv("RBC_KEY_FILE", "rbc_key.txt")  # Shared secret (unsafe storage)
TRAIN_DATA_FILE = os.getenv("TRAIN_DATA_FILE", "train_data.conf")


def load_secret_key() -> bytes:
    with open(KEY_FILE, "rb") as f:
        return f.read().strip()


def load_train_data() -> Dict[str, float]:
    data: Dict[str, float] = {}
    try:
        with open(TRAIN_DATA_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                try:
                    data[key] = float(value.strip())
                except ValueError:
                    continue
    except FileNotFoundError:
        print(f"[EVC] WARNING: {TRAIN_DATA_FILE} not found, using defaults")
    return data


def verify_signature(key: bytes, payload: Dict[str, Any], signature: str) -> bool:
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    mac = hmac.new(key, data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature)


class DmiPublisher(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.current_speed = 0.0
        self.target_speed = 0.0
        self.distance_to_go = 0.0
        self.lock = threading.Lock()
        self.running = True
        # Info about the last Movement Authority accepted by the EVC
        self.last_ma_id: Optional[int] = None
        self.last_ma_issuer: str = ""
        self.last_ma_timestamp: float = 0.0

    def update_ma(
        self,
        speed_kmh: float,
        distance_m: float,
        ma_id: int | None = None,
        issuer: str | None = None,
        ma_timestamp: float | None = None,
    ) -> None:
        with self.lock:
            self.target_speed = speed_kmh
            self.distance_to_go = distance_m
            if ma_id is not None:
                self.last_ma_id = ma_id
            if issuer is not None:
                self.last_ma_issuer = issuer
            if ma_timestamp is not None:
                self.last_ma_timestamp = ma_timestamp

    def run(self) -> None:
        while self.running:
            with self.lock:
                # Simple speed model: move towards target speed
                if self.current_speed < self.target_speed:
                    self.current_speed += 2.0
                elif self.current_speed > self.target_speed:
                    self.current_speed -= 2.0

                if self.current_speed < 0:
                    self.current_speed = 0.0

                # Simple distance model: reduce distance based on current speed
                # v (km/h) -> m/s, dt ≈ 2 s per loop
                dt = 2.0
                speed_mps = self.current_speed / 3.6
                self.distance_to_go = max(self.distance_to_go - speed_mps * dt, 0.0)

                status = {
                    "current_speed_kmh": round(self.current_speed, 1),
                    "target_speed_kmh": round(self.target_speed, 1),
                    "distance_to_go_m": round(self.distance_to_go, 1),
                    "timestamp": time.time(),
                    "last_ma_id": self.last_ma_id,
                    "last_ma_issuer": self.last_ma_issuer,
                    "last_ma_timestamp": self.last_ma_timestamp,
                }

            payload = json.dumps(status).encode("utf-8")
            self.sock.sendto(payload, (DMI_HOST, DMI_PORT))
            # Slow down changes a bit so they are easier to follow
            time.sleep(2.0)


class EvcServer(threading.Thread):
    def __init__(self, dmi_publisher: DmiPublisher, key: bytes, train_data: Dict[str, float]):
        super().__init__(daemon=True)
        self.dmi_publisher = dmi_publisher
        self.key = key
        self.train_data = train_data
        self.running = True

    def _send_ack_after_delay(
        self,
        conn: socket.socket,
        ma_id: Optional[int],
        distance_m: float,
        delay_s: float,
    ) -> None:
        if ma_id is None or delay_s <= 0:
            return
        try:
            time.sleep(delay_s)
            ack = {
                "type": "ACK",
                "ma_id": ma_id,
                "train_id": "TrainA",
                "position_m": distance_m,
                "timestamp": time.time(),
            }
            line = json.dumps(ack).encode("utf-8") + b"\n"
            conn.sendall(line)
            print(f"[EVC] Sent ACK for MA id={ma_id} after reaching {distance_m} m")
        except OSError:
            print("[EVC] Failed to send ACK (connection closed)")

    def run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen(1)
            print(f"[EVC] Listening on {HOST}:{PORT}")
            print(f"[EVC] Train data: {self.train_data}")

            conn, addr = s.accept()
            print(f"[EVC] Radio connected from {addr}")
            buffer = b""
            with conn:
                while self.running:
                    chunk = conn.recv(4096)
                    if not chunk:
                        print("[EVC] Radio disconnected")
                        break
                    buffer += chunk

                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line.decode("utf-8"))
                            payload = msg.get("payload")
                            signature = msg.get("signature", "")
                            if not isinstance(payload, dict):
                                print("[EVC] Invalid message payload format")
                                continue
                            if not verify_signature(self.key, payload, signature):
                                print("[EVC] INVALID SIGNATURE, discarding message")
                                continue

                            speed = float(payload.get("speed_kmh", 0.0))
                            distance = float(payload.get("distance_m", 0.0))
                            ma_id = payload.get("id")
                            issuer = str(payload.get("issuer", "unknown"))
                            ma_ts = float(payload.get("timestamp", time.time()))
                            print(
                                f"[EVC] Accepted MA id={ma_id} issuer={issuer} speed={speed} km/h distance={distance} m"
                            )
                            self.dmi_publisher.update_ma(
                                speed,
                                distance,
                                ma_id=ma_id,
                                issuer=issuer,
                                ma_timestamp=ma_ts,
                            )

                            # Schedule an ACK back to the RBC once the
                            # train is expected to have reached the end of
                            # this authority (distance / speed).
                            if speed > 0 and distance > 0:
                                speed_mps = speed / 3.6
                                travel_time_s = distance / speed_mps
                                threading.Thread(
                                    target=self._send_ack_after_delay,
                                    args=(conn, ma_id, distance, travel_time_s),
                                    daemon=True,
                                ).start()
                        except json.JSONDecodeError:
                            print("[EVC] Failed to decode JSON from line")
                        except Exception as exc:  # noqa: BLE001
                            print(f"[EVC] Error processing message: {exc}")


def start_evc() -> None:
    key = load_secret_key()
    train_data = load_train_data()

    dmi_publisher = DmiPublisher()
    dmi_publisher.start()

    evc_server = EvcServer(dmi_publisher, key, train_data)
    evc_server.start()

    print("[EVC] EVC and DMI publisher started. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[EVC] Shutting down...")
        dmi_publisher.running = False
        evc_server.running = False


if __name__ == "__main__":
    start_evc()
