#!/usr/bin/env python3

import os
import random
import select
import socket
import threading
import time
from datetime import datetime

RBC_HOST = os.getenv("RBC_HOST", "rbc")
RBC_PORT = int(os.getenv("RBC_PORT", "9000"))

LISTEN_HOST = os.getenv("GSMR_LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("GSMR_LISTEN_PORT", "9001"))

ADMIN_HOST = os.getenv("ADMIN_LISTEN_HOST", "0.0.0.0")
ADMIN_PORT = int(os.getenv("ADMIN_LISTEN_PORT", "9100"))

DROP_PROBABILITY = float(os.getenv("GSMR_DROP_PROBABILITY", "0.0"))  # 0.0 = no drops by default


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def run_emulator() -> None:
    # Connect to RBC
    while True:
        try:
            print(f"[{ts()}] [NET] Connecting to RBC at {RBC_HOST}:{RBC_PORT}...")
            rbc_sock = socket.create_connection((RBC_HOST, RBC_PORT))
            print(f"[{ts()}] [NET] Connected to RBC")
            break
        except OSError as exc:
            print(f"[{ts()}] [NET] RBC not reachable yet ({exc}), retrying in 2s...")
            time.sleep(2.0)

    # Listen for Train Radio
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listen_sock:
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind((LISTEN_HOST, LISTEN_PORT))
        listen_sock.listen(1)
        print(f"[{ts()}] [NET] Listening for Train on {LISTEN_HOST}:{LISTEN_PORT}")

        train_sock, train_addr = listen_sock.accept()
        print(f"[{ts()}] [NET] Train connected from {train_addr}")

        sockets = [rbc_sock, train_sock]

        # Simple attacker / MITM admin interface: anything typed here is
        # injected towards the Train side (Radio/EVC).
        def admin_server() -> None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as admin_sock:
                admin_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    admin_sock.bind((ADMIN_HOST, ADMIN_PORT))
                except OSError as exc:
                    print(f"[{ts()}] [NET] Admin bind failed on {ADMIN_HOST}:{ADMIN_PORT}: {exc}")
                    return
                admin_sock.listen(5)
                print(
                    f"[{ts()}] [NET] Admin / attacker interface on {ADMIN_HOST}:{ADMIN_PORT} "
                    f"(nc 127.0.0.1 {ADMIN_PORT})"
                )
                while True:
                    conn, addr = admin_sock.accept()
                    print(f"[{ts()}] [NET-ADMIN] Client connected from {addr}")
                    threading.Thread(
                        target=_handle_admin_client, args=(conn, train_sock), daemon=True
                    ).start()

        threading.Thread(target=admin_server, daemon=True).start()

        try:
            while True:
                readable, _, _ = select.select(sockets, [], [])
                for sock in readable:
                    data = sock.recv(4096)
                    if not data:
                        print(f"[{ts()}] [NET] One side closed connection, shutting down")
                        return

                    if sock is rbc_sock:
                        direction = "RBC -> Train"
                        target = train_sock
                    else:
                        direction = "Train -> RBC"
                        target = rbc_sock

                    if random.random() < DROP_PROBABILITY:
                        print(f"[{ts()}] [NET] DROPPED packet ({direction}): {data!r}")
                        continue

                    print(f"[{ts()}] [NET] Relaying packet ({direction}): {data!r}")
                    target.sendall(data)
        finally:
            train_sock.close()
            rbc_sock.close()


def _handle_admin_client(conn: socket.socket, train_sock: socket.socket) -> None:
    buf = b""
    with conn:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.rstrip(b"\r")
                if not line:
                    continue
                # Forward raw line towards the Train side.
                data = line + b"\n"
                try:
                    train_sock.sendall(data)
                    print(f"[{ts()}] [NET-ADMIN] Injected towards Train: {data!r}")
                except OSError as exc:
                    print(f"[{ts()}] [NET-ADMIN] Failed to inject towards Train: {exc}")
                    return


if __name__ == "__main__":
    run_emulator()
