#!/usr/bin/env python3

import os
import select
import socket
import threading
import time
from typing import Tuple

RBC_HOST = os.getenv("RBC_HOST", "127.0.0.1")
RBC_PORT = int(os.getenv("RBC_PORT", "9000"))

GSMR_LISTEN_HOST = os.getenv("GSMR_LISTEN_HOST", "0.0.0.0")
GSMR_LISTEN_PORT = int(os.getenv("GSMR_LISTEN_PORT", "9001"))

ADMIN_LISTEN_HOST = os.getenv("ADMIN_LISTEN_HOST", "0.0.0.0")
ADMIN_LISTEN_PORT = int(os.getenv("ADMIN_LISTEN_PORT", "9100"))


class AdminClientHandler(threading.Thread):
    """Simple text-based admin interface for injection.

    An attacker who connects here can inject arbitrary lines towards the train
    side of the connection, simulating a MITM / noise injection attack.
    """

    def __init__(self, conn: socket.socket, addr: Tuple[str, int], train_sock_getter):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.train_sock_getter = train_sock_getter

    def run(self) -> None:
        print(f"[GSM-R][ADMIN] Client connected from {self.addr}")
        self.conn.sendall(
            b"Welcome to GSM-R admin interface. Type lines to inject towards train.\n"
        )
        try:
            while True:
                data = self.conn.recv(4096)
                if not data:
                    break
                for line in data.split(b"\n"):
                    line = line.strip()
                    if not line:
                        continue
                    msg = line + b"\n"
                    train_sock = self.train_sock_getter()
                    if train_sock is not None:
                        try:
                            train_sock.sendall(msg)
                            print(f"[GSM-R][ADMIN] Injected towards train: {msg!r}")
                        except OSError:
                            self.conn.sendall(b"Train connection not available.\n")
                    else:
                        self.conn.sendall(b"No train connected.\n")
        finally:
            print(f"[GSM-R][ADMIN] Client from {self.addr} disconnected")
            self.conn.close()


def admin_server(train_sock_getter) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((ADMIN_LISTEN_HOST, ADMIN_LISTEN_PORT))
        s.listen(5)
        print(f"[GSM-R][ADMIN] Listening on {ADMIN_LISTEN_HOST}:{ADMIN_LISTEN_PORT}")
        while True:
            conn, addr = s.accept()
            handler = AdminClientHandler(conn, addr, train_sock_getter)
            handler.start()


def proxy_loop():
    # Retry loop to wait for RBC to be ready (useful in Docker and dev)
    while True:
        try:
            print(f"[GSM-R] Connecting to RBC at {RBC_HOST}:{RBC_PORT}...")
            rbc_sock = socket.create_connection((RBC_HOST, RBC_PORT))
            print("[GSM-R] Connected to RBC")
            break
        except OSError as exc:
            print(f"[GSM-R] RBC not reachable yet ({exc}), retrying in 2s...")
            time.sleep(2.0)

    train_sock_holder = {"sock": None}

    def get_train_sock():
        return train_sock_holder["sock"]

    # Start admin interface in background
    threading.Thread(target=admin_server, args=(get_train_sock,), daemon=True).start()

    # Listen for a single train connection (for demo simplicity)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listen_sock:
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind((GSMR_LISTEN_HOST, GSMR_LISTEN_PORT))
        listen_sock.listen(1)
        print(f"[GSM-R] Listening for Train on {GSMR_LISTEN_HOST}:{GSMR_LISTEN_PORT}")

        train_sock, train_addr = listen_sock.accept()
        train_sock_holder["sock"] = train_sock
        print(f"[GSM-R] Train connected from {train_addr}")

        sockets = [rbc_sock, train_sock]

        try:
            while True:
                readable, _, _ = select.select(sockets, [], [])
                for sock in readable:
                    data = sock.recv(4096)
                    if not data:
                        print("[GSM-R] One side closed connection, shutting down proxy")
                        return

                    if sock is rbc_sock:
                        print(f"[GSM-R] RBC -> Train: {data!r}")
                        train_sock.sendall(data)
                    else:
                        print(f"[GSM-R] Train -> RBC: {data!r}")
                        rbc_sock.sendall(data)
        finally:
            train_sock.close()
            rbc_sock.close()


if __name__ == "__main__":
    proxy_loop()
