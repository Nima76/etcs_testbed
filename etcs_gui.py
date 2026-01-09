#!/usr/bin/env python3

import json
import socket
import tkinter as tk
from tkinter import ttk, messagebox


DRIVER_HOST = "127.0.0.1"  # host-mapped EVC driver interface
DRIVER_PORT = 9102

ATTACK_HOST = "127.0.0.1"  # host-mapped GSM-R admin / MITM interface
ATTACK_PORT = 9100


def send_driver_command(cmd: str) -> str:
    """Send a single-line driver command to the EVC and return response text.

    Commands go to the EVC driver TCP interface (SPEED/BRAKE/RESET/UNSIGNED).
    """
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
    """Inject a fake MA towards the train via the GSM-R admin port.

    This is equivalent to using `nc 127.0.0.1 9100` and pasting a JSON line.
    """
    payload = {
        "type": "MA",
        "ma_id": int(position_km * 1000),  # arbitrary id
        "position_km": float(position_km),
        "next_checkpoint_km": float(next_checkpoint_km),
        "speed_limit": float(speed_limit),
        "message": "GUI_ATTACK",
    }
    wrapper = {"payload": payload, "signature": "00deadbeef"}
    line = json.dumps(wrapper)
    try:
        with socket.create_connection((ATTACK_HOST, ATTACK_PORT), timeout=2.0) as s:
            s.sendall((line + "\n").encode("utf-8"))
        return f"Sent attack MA: {line}"
    except OSError as exc:
        return f"FAILED to send attack MA: {exc}"


class EtcsGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ETCS Control GUI")
        self.configure(bg="#101320")

        self.accept_unsigned = False

        main = ttk.Frame(self, padding=12)
        main.grid(row=0, column=0, sticky="nsew")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Driver controls
        driver_frame = ttk.LabelFrame(main, text="Driver controls (Train)")
        driver_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        ttk.Label(driver_frame, text="Target speed (km/h):").grid(row=0, column=0, sticky="w")
        self.speed_var = tk.StringVar()
        speed_entry = ttk.Entry(driver_frame, textvariable=self.speed_var, width=10)
        speed_entry.grid(row=0, column=1, sticky="w", padx=(4, 0))

        set_btn = ttk.Button(driver_frame, text="Set speed", command=self.on_set_speed)
        set_btn.grid(row=0, column=2, padx=4, pady=2)

        brake_btn = ttk.Button(driver_frame, text="Brake / Stop", command=self.on_brake)
        brake_btn.grid(row=1, column=0, padx=4, pady=4, sticky="w")

        reset_btn = ttk.Button(driver_frame, text="Reset scenario", command=self.on_reset)
        reset_btn.grid(row=1, column=1, padx=4, pady=4, sticky="w")

        self.sig_btn = ttk.Button(driver_frame, text="STRICT (signed only)", command=self.on_toggle_unsigned)
        self.sig_btn.grid(row=1, column=2, padx=4, pady=4)

        # Attacker controls
        atk_frame = ttk.LabelFrame(main, text="Attacker controls (fake MA)")
        atk_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        ttk.Label(atk_frame, text="position_km:").grid(row=0, column=0, sticky="w")
        self.atk_pos = tk.StringVar()
        ttk.Entry(atk_frame, textvariable=self.atk_pos, width=10).grid(row=0, column=1, sticky="w", padx=(4, 0))

        ttk.Label(atk_frame, text="next_checkpoint_km:").grid(row=1, column=0, sticky="w")
        self.atk_next = tk.StringVar()
        ttk.Entry(atk_frame, textvariable=self.atk_next, width=10).grid(row=1, column=1, sticky="w", padx=(4, 0))

        ttk.Label(atk_frame, text="speed_limit (km/h):").grid(row=2, column=0, sticky="w")
        self.atk_speed = tk.StringVar()
        ttk.Entry(atk_frame, textvariable=self.atk_speed, width=10).grid(row=2, column=1, sticky="w", padx=(4, 0))

        atk_btn = ttk.Button(atk_frame, text="Send attack MA", command=self.on_attack)
        atk_btn.grid(row=3, column=0, columnspan=2, pady=6, sticky="w")

        # Log area
        log_frame = ttk.LabelFrame(main, text="Log")
        log_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)

        self.log = tk.Text(log_frame, height=10, width=80, state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log["yscrollcommand"] = scroll.set

        main.rowconfigure(2, weight=1)
        main.columnconfigure(0, weight=1)

        self._log("GUI started. Make sure Docker stack is up (rbc, gsmr, radio, evc).")

    # Helper to append text to log
    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # Button handlers
    def on_set_speed(self) -> None:
        try:
            v = float(self.speed_var.get())
        except ValueError:
            messagebox.showerror("Invalid speed", "Please enter a numeric speed in km/h.")
            return
        resp = send_driver_command(f"SPEED {v}")
        self._log(resp)

    def on_brake(self) -> None:
        resp = send_driver_command("BRAKE")
        self._log(resp)

    def on_reset(self) -> None:
        resp = send_driver_command("RESET")
        self._log(resp)

    def on_toggle_unsigned(self) -> None:
        self.accept_unsigned = not self.accept_unsigned
        cmd = "UNSIGNED ON" if self.accept_unsigned else "UNSIGNED OFF"
        resp = send_driver_command(cmd)
        self._log(resp)
        if self.accept_unsigned:
            self.sig_btn.config(text="RELAXED (accept unsigned)")
        else:
            self.sig_btn.config(text="STRICT (signed only)")

    def on_attack(self) -> None:
        try:
            pos = float(self.atk_pos.get() or "0")
            nxt = float(self.atk_next.get() or "0")
            spd = float(self.atk_speed.get() or "0")
        except ValueError:
            messagebox.showerror("Invalid values", "position_km, next_checkpoint_km and speed_limit must be numbers.")
            return
        resp = send_attack_ma(pos, nxt, spd)
        self._log(resp)


def main() -> None:
    app = EtcsGui()
    app.mainloop()


if __name__ == "__main__":
    main()
