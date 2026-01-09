#!/usr/bin/env python3

import os
import select
import socket
import time
from datetime import datetime

GSMR_HOST = os.getenv("GSMR_HOST", "gsmr")
GSMR_PORT = int(os.getenv("GSMR_PORT", "9001"))

EVC_HOST = os.getenv("EVC_HOST", "evc")
EVC_PORT = int(os.getenv("EVC_PORT", "9002"))


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def run_radio() -> None:
    # Connect to GSM-R network emulator
    while True:
        try:
            print(f"[{ts()}] [RADIO] Connecting to GSM-R at {GSMR_HOST}:{GSMR_PORT}...")
            gsmr_sock = socket.create_connection((GSMR_HOST, GSMR_PORT))
            print(f"[{ts()}] [RADIO] Connected to GSM-R")
            break
        except OSError as exc:
            print(f"[{ts()}] [RADIO] GSM-R not reachable yet ({exc}), retrying in 2s...")
            time.sleep(2.0)

    # Connect to onboard EVC
    while True:
        try:
            print(f"[{ts()}] [RADIO] Connecting to EVC at {EVC_HOST}:{EVC_PORT}...")
            evc_sock = socket.create_connection((EVC_HOST, EVC_PORT))
            print(f"[{ts()}] [RADIO] Connected to EVC")
            break
        except OSError as exc:
            print(f"[{ts()}] [RADIO] EVC not reachable yet ({exc}), retrying in 2s...")
            time.sleep(2.0)

    sockets = [gsmr_sock, evc_sock]

    try:
        while True:
            readable, _, _ = select.select(sockets, [], [])
            for sock in readable:
                data = sock.recv(4096)
                if not data:
                    print(f"[{ts()}] [RADIO] One side closed connection, shutting down")
                    return
                if sock is gsmr_sock:
                    print(f"[{ts()}] [RADIO] GSM-R -> EVC: {data!r}")
                    evc_sock.sendall(data)
                else:
                    print(f"[{ts()}] [RADIO] EVC -> GSM-R: {data!r}")
                    gsmr_sock.sendall(data)
    finally:
        gsmr_sock.close()
        evc_sock.close()


if __name__ == "__main__":
    run_radio()
