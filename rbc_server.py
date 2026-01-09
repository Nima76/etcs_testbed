#!/usr/bin/env python3

import json
import os
import socket
import threading
import time
import hmac
import hashlib
from datetime import datetime

HOST = os.getenv("RBC_LISTEN_HOST", "0.0.0.0")
PORT = int(os.getenv("RBC_LISTEN_PORT", "9000"))
DB_PATH = "rbc_db.json"
KEY_FILE = os.getenv("RBC_KEY_FILE", "rbc_key.txt")
ADMIN_HOST = os.getenv("RBC_ADMIN_HOST", "0.0.0.0")
ADMIN_PORT = int(os.getenv("RBC_ADMIN_PORT", "9101"))


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def load_db() -> dict:
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[{ts()}] [RBC] WARNING: {DB_PATH} not found, using defaults")
        return {
            "zones": [
                {"start_km": 0.0, "end_km": 2.0, "speed_limit": 100, "message": "PROCEED"},
                {"start_km": 2.0, "end_km": 3.0, "speed_limit": 50, "message": "SLOW"},
                {"start_km": 3.0, "end_km": 6.0, "speed_limit": 90, "message": "PROCEED"},
            ]
        }
    except json.JSONDecodeError as exc:
        print(f"[{ts()}] [RBC] ERROR: Failed to parse {DB_PATH}: {exc}")
        return {
            "zones": [
                {"start_km": 0.0, "end_km": 2.0, "speed_limit": 100, "message": "PROCEED"},
                {"start_km": 2.0, "end_km": 3.0, "speed_limit": 50, "message": "SLOW"},
                {"start_km": 3.0, "end_km": 6.0, "speed_limit": 90, "message": "PROCEED"},
            ]
        }


def speed_for_position_km(position_km: float):
    """Return (speed_limit, message, next_checkpoint_km) for a position.

    If beyond the last zone, reuse the last zone's speed and end_km.
    """
    zones = RBC_CONFIG.get("zones", [])
    last_end = 0.0
    last_speed = 0.0
    last_msg = "PROCEED"
    for z in zones:
        start = float(z.get("start_km", 0.0))
        end = float(z.get("end_km", start))
        spd = float(z.get("speed_limit", 0.0))
        msg = str(z.get("message", "PROCEED"))
        if start <= position_km < end:
            return spd, msg, end
        last_end = end
        last_speed = spd
        last_msg = msg
    return last_speed, last_msg, last_end


# Load RBC configuration once at startup.
# Runtime attacks should not be able to change the speed
# limit just by editing rbc_db.json after the process has
# started; they must instead forge signed commands.
RBC_CONFIG = load_db()


def load_secret_key() -> bytes:
    try:
        with open(KEY_FILE, "rb") as f:
            key = f.read().strip()
    except FileNotFoundError:
        print(f"[{ts()}] [RBC] WARNING: key file {KEY_FILE} not found, using default demo key")
        key = b"super_insecure_demo_key_for_rbc"
    return key


def sign_message(key: bytes, payload: dict) -> str:
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    mac = hmac.new(key, data, hashlib.sha256).hexdigest()
    return mac


class RbcClientHandler(threading.Thread):
    def __init__(self, conn: socket.socket, addr):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.running = True
        self.key = load_secret_key()
        self.train_id: str | None = None
        self.current_segment: int = 0
        self.last_known_position_km: float = 0.0
        self._next_ma_id: int = 1

        # register as the current active handler (single-train demo)
        global CURRENT_HANDLER
        CURRENT_HANDLER = self

    def run(self) -> None:
        print(f"[{ts()}] [RBC] Client connected from {self.addr}")
        buffer = b""
        try:
            while self.running:
                self.conn.settimeout(1.0)
                try:
                    chunk = self.conn.recv(4096)
                except socket.timeout:
                    continue

                if not chunk:
                    print(f"[{ts()}] [RBC] Client {self.addr} disconnected (EOF)")
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
                        print(f"[{ts()}] [RBC] Invalid JSON from {self.addr}: {line!r}")
                        continue

                    mtype = msg.get("type")
                    if mtype == "HELLO":
                        self.train_id = str(msg.get("train_id", "unknown"))
                        self.current_segment = 1
                        self.last_known_position_km = float(msg.get("position_km", 0.0))
                        print(
                            f"[{ts()}] [RBC] HELLO from train {self.train_id}, initial position={self.last_known_position_km:.3f} km"
                        )
                        # Send initial authority based on current position
                        self._send_movement_authority(self.last_known_position_km)
                    elif mtype == "POSITION_REPORT":
                        self.last_known_position_km = float(msg.get("position_km", 0.0))
                        speed = float(msg.get("speed_kmh", 0.0))
                        train_id = msg.get("train_id", self.train_id)
                        allowed_speed, _msg, _next = speed_for_position_km(self.last_known_position_km)
                        print(
                            f"[{ts()}] [RBC] POSITION_REPORT from {train_id}: "
                            f"pos={self.last_known_position_km:.3f}km speed={speed:.1f}km/h "
                            f"(limit={allowed_speed:.1f}km/h)"
                        )

                        # If current speed exceeds allowed speed from last MA/zone,
                        # clamp the train down to the zone limit instead of forcing
                        # a full stop. This lets it continue into the next zone but
                        # prevents sustained overspeed.
                        if allowed_speed > 0.0 and speed > allowed_speed:
                            print(
                                f"[{ts()}] [RBC] OVERSPEED detected for {train_id}: "
                                f"speed={speed:.1f}km/h > limit={allowed_speed:.1f}km/h "
                                f"-> EMERGENCY SLOWDOWN to zone limit"
                            )
                            try:
                                # Emergency update with speed_limit set to the
                                # maximum allowed, not 0 km/h.
                                self.send_emergency_update(allowed_speed)
                            except Exception as exc:  # noqa: BLE001
                                print(f"[{ts()}] [RBC] Failed to send emergency slowdown: {exc}")
                    elif mtype == "CHECKPOINT_REACHED":
                        position = float(msg.get("position_km", 0.0))
                        train_id = msg.get("train_id", self.train_id)
                        self.last_known_position_km = position
                        print(
                            f"[{ts()}] [RBC] CHECKPOINT_REACHED from {train_id}: position_km={position:.3f}"
                        )
                        # Issue a new authority for the new zone boundary
                        self._send_movement_authority(position)
        finally:
            self.conn.close()
            print(f"[{ts()}] [RBC] Client {self.addr} disconnected")

            # If this was the active handler, clear it
            global CURRENT_HANDLER
            if CURRENT_HANDLER is self:
                CURRENT_HANDLER = None

    def _send_movement_authority(self, position_km: float) -> None:
        speed_limit, message, next_checkpoint = speed_for_position_km(position_km)
        ma_id = self._next_ma_id
        self._next_ma_id += 1

        payload = {
            "type": "MA",
            "ma_id": ma_id,
            "position_km": position_km,
            "next_checkpoint_km": next_checkpoint,
            "speed_limit": speed_limit,
            "message": message,
        }
        message = {
            "payload": payload,
            "signature": sign_message(self.key, payload),
        }
        line = json.dumps(message).encode("utf-8") + b"\n"
        try:
            self.conn.sendall(line)
            print(
                f"[{ts()}] [RBC] Sent MA ma_id={ma_id} to {self.addr}: "
                f"pos={position_km:.3f} next_cp={next_checkpoint:.3f} "
                f"speed_limit={speed_limit} message={message}"
            )
        except OSError:
            print(f"[{ts()}] [RBC] Failed to send MA to {self.addr}")

    def send_emergency_update(self, speed_limit: float) -> None:
        """Send an immediate signed emergency update to the train.

        This uses the same HMAC key but marks the payload type as
        EMERGENCY_UPDATE so the EVC can log it differently. The EVC
        will still treat the speed_limit as the new target speed.
        """
        if not self.running:
            print(f"[{ts()}] [RBC] Cannot send emergency update, client {self.addr} not running")
            return

        pos = self.last_known_position_km
        _zone_speed, _msg, next_cp = speed_for_position_km(pos)
        ma_id = self._next_ma_id
        self._next_ma_id += 1

        payload = {
            "type": "EMERGENCY_UPDATE",
            "ma_id": ma_id,
            "position_km": pos,
            "next_checkpoint_km": next_cp,
            "speed_limit": float(speed_limit),
            "message": "EMERGENCY UPDATE",
        }
        message = {
            "payload": payload,
            "signature": sign_message(self.key, payload),
        }
        line = json.dumps(message).encode("utf-8") + b"\n"
        try:
            self.conn.sendall(line)
            print(
                f"[{ts()}] [RBC] Sent EMERGENCY_UPDATE ma_id={ma_id} to {self.addr}: "
                f"pos={pos:.3f} next_cp={next_cp:.3f} speed_limit={speed_limit}"
            )
        except OSError:
            print(f"[{ts()}] [RBC] Failed to send EMERGENCY_UPDATE to {self.addr}")


# Global reference to the current train connection (single-train demo)
CURRENT_HANDLER: RbcClientHandler | None = None


def start_admin_server() -> None:
    """Admin endpoint so RBC can change speed at any time.

    Listens for JSON lines like:

        {"type": "EMERGENCY_UPDATE", "speed_limit": 30}

    and forwards a signed EMERGENCY_UPDATE to the current train.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((ADMIN_HOST, ADMIN_PORT))
        s.listen(5)
        print(f"[{ts()}] [RBC] Admin interface listening on {ADMIN_HOST}:{ADMIN_PORT}")

        while True:
            conn, addr = s.accept()
            threading.Thread(target=_handle_admin_client, args=(conn, addr), daemon=True).start()


def _handle_admin_client(conn: socket.socket, addr) -> None:
    print(f"[{ts()}] [RBC-ADMIN] Client connected from {addr}")
    buffer = b""
    with conn:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
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
                    print(f"[{ts()}] [RBC-ADMIN] Invalid JSON from {addr}: {line!r}")
                    continue

                speed_limit = msg.get("speed_limit")
                if speed_limit is None:
                    print(f"[{ts()}] [RBC-ADMIN] Missing speed_limit in {msg!r}")
                    continue

                handler = CURRENT_HANDLER
                if handler is None:
                    print(f"[{ts()}] [RBC-ADMIN] No active train to send emergency update")
                    continue

                try:
                    handler.send_emergency_update(float(speed_limit))
                except Exception as exc:  # noqa: BLE001
                    print(f"[{ts()}] [RBC-ADMIN] Failed to send emergency update: {exc}")

    print(f"[{ts()}] [RBC-ADMIN] Client {addr} disconnected")


def start_server() -> None:
    # Start admin interface in the background
    threading.Thread(target=start_admin_server, daemon=True).start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)
        print(f"[{ts()}] [RBC] Listening on {HOST}:{PORT}")

        while True:
            conn, addr = s.accept()
            handler = RbcClientHandler(conn, addr)
            handler.start()


if __name__ == "__main__":
    start_server()
