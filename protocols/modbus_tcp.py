"""Modbus TCP protocol implementation for ETCS testbed.

This protocol maps ETCS messages to Modbus TCP holding registers,
enabling realistic ICS-style communication with intentional security
vulnerabilities for adversarial testing.

Register Mapping:
  0-1:   position_km (32-bit float)
  2-3:   speed_kmh (32-bit float)
  4-5:   speed_limit (32-bit float)
  6-7:   next_checkpoint_km (32-bit float)
  8:     ma_id (16-bit integer)
  9:     message_type (16-bit integer)
  10:    train_id (16-bit integer, hash of train ID string)
  11:    timestamp_high (16-bit, upper 16 bits of Unix timestamp)
  12:    timestamp_low (16-bit, lower 16 bits of Unix timestamp)
  13-18: signature/checksum (6 registers for HMAC truncated to 96 bits)

Security Note: This implementation deliberately has NO encryption
and weak authentication (optional HMAC) to demonstrate ICS vulnerabilities.
"""

import hashlib
import hmac
import struct
import time
from typing import Any, Dict, Optional

from protocols.base import MessageType, Protocol


# Message type encoding for Modbus register 9
MESSAGE_TYPE_MAP = {
    MessageType.HELLO: 1,
    MessageType.MA: 2,
    MessageType.EMERGENCY_UPDATE: 3,
    MessageType.POSITION_REPORT: 4,
    MessageType.CHECKPOINT_REACHED: 5,
    MessageType.UNKNOWN: 0,
}

REVERSE_MESSAGE_TYPE_MAP = {v: k for k, v in MESSAGE_TYPE_MAP.items()}


class ModbusTcpProtocol(Protocol):
    """Modbus TCP protocol for ETCS messages.
    
    Uses Modbus function code 03 (Read Holding Registers) and
    16 (Write Multiple Registers) to communicate ETCS data.
    """
    
    def __init__(self, key: Optional[bytes] = None, slave_id: int = 1, register_base: int = 0):
        """Initialize Modbus protocol.
        
        Args:
            key: Secret key for HMAC (optional, for secure mode)
            slave_id: Modbus slave/unit ID (default: 1)
            register_base: Base register address (default: 0)
        """
        super().__init__(key=key)
        self.slave_id = slave_id
        self.register_base = register_base
        self._use_signatures = key is not None
    
    def encode(self, payload: Dict[str, Any]) -> bytes:
        """Encode ETCS message as Modbus register values.
        
        Args:
            payload: ETCS message payload
            
        Returns:
            Modbus register data (raw register values, 2 bytes each)
        """
        # Extract fields with defaults
        position_km = float(payload.get("position_km", 0.0))
        speed_kmh = float(payload.get("speed_kmh", 0.0))
        speed_limit = float(payload.get("speed_limit", 0.0))
        next_checkpoint_km = float(payload.get("next_checkpoint_km", 0.0))
        ma_id = int(payload.get("ma_id", 0))
        msg_type = payload.get("type", "UNKNOWN")
        train_id = payload.get("train_id", "TrainA")
        timestamp = float(payload.get("timestamp", time.time()))
        
        # Convert message type to integer
        try:
            msg_type_enum = MessageType(msg_type)
        except ValueError:
            msg_type_enum = MessageType.UNKNOWN
        msg_type_val = MESSAGE_TYPE_MAP[msg_type_enum]
        
        # Hash train ID to 16-bit integer
        train_id_hash = hash(train_id) & 0xFFFF
        
        # Split timestamp into high and low 16 bits
        timestamp_int = int(timestamp)
        timestamp_high = (timestamp_int >> 16) & 0xFFFF
        timestamp_low = timestamp_int & 0xFFFF
        
        # Pack floating-point values as 32-bit IEEE 754 (big-endian)
        registers = []
        
        # Registers 0-1: position_km
        pos_bytes = struct.pack(">f", position_km)
        registers.extend(struct.unpack(">HH", pos_bytes))
        
        # Registers 2-3: speed_kmh
        speed_bytes = struct.pack(">f", speed_kmh)
        registers.extend(struct.unpack(">HH", speed_bytes))
        
        # Registers 4-5: speed_limit
        limit_bytes = struct.pack(">f", speed_limit)
        registers.extend(struct.unpack(">HH", limit_bytes))
        
        # Registers 6-7: next_checkpoint_km
        checkpoint_bytes = struct.pack(">f", next_checkpoint_km)
        registers.extend(struct.unpack(">HH", checkpoint_bytes))
        
        # Register 8: ma_id (truncated to 16 bits)
        registers.append(ma_id & 0xFFFF)
        
        # Register 9: message_type
        registers.append(msg_type_val & 0xFFFF)
        
        # Register 10: train_id hash
        registers.append(train_id_hash)
        
        # Registers 11-12: timestamp
        registers.append(timestamp_high)
        registers.append(timestamp_low)
        
        # Registers 13-18: signature (truncated HMAC to 96 bits / 6 registers)
        if self._use_signatures:
            sig = self.sign(payload)
            sig_bytes = bytes.fromhex(sig[:24])  # Take first 12 bytes (96 bits)
            sig_regs = struct.unpack(">6H", sig_bytes)
            registers.extend(sig_regs)
        else:
            # No signature, pad with zeros
            registers.extend([0] * 6)
        
        # Convert registers to bytes (big-endian 16-bit values)
        return struct.pack(f">{len(registers)}H", *registers)
    
    def decode(self, data: bytes) -> Dict[str, Any]:
        """Decode Modbus register data to ETCS message.
        
        Args:
            data: Raw Modbus register data (38 bytes = 19 registers)
            
        Returns:
            ETCS message payload dictionary
            
        Raises:
            ValueError: If data is invalid
        """
        if len(data) < 38:  # Need at least 19 registers
            raise ValueError(f"Invalid Modbus data length: {len(data)} bytes (expected >= 38)")
        
        # Unpack register values
        registers = struct.unpack(">19H", data[:38])
        
        # Registers 0-1: position_km
        pos_bytes = struct.pack(">HH", registers[0], registers[1])
        position_km = struct.unpack(">f", pos_bytes)[0]
        
        # Registers 2-3: speed_kmh
        speed_bytes = struct.pack(">HH", registers[2], registers[3])
        speed_kmh = struct.unpack(">f", speed_bytes)[0]
        
        # Registers 4-5: speed_limit
        limit_bytes = struct.pack(">HH", registers[4], registers[5])
        speed_limit = struct.unpack(">f", limit_bytes)[0]
        
        # Registers 6-7: next_checkpoint_km
        checkpoint_bytes = struct.pack(">HH", registers[6], registers[7])
        next_checkpoint_km = struct.unpack(">f", checkpoint_bytes)[0]
        
        # Register 8: ma_id
        ma_id = registers[8]
        
        # Register 9: message_type
        msg_type_val = registers[9]
        msg_type_enum = REVERSE_MESSAGE_TYPE_MAP.get(msg_type_val, MessageType.UNKNOWN)
        
        # Register 10: train_id (we can't reverse the hash, use placeholder)
        train_id_hash = registers[10]
        train_id = f"Train_{train_id_hash:04X}"  # Hex representation
        
        # Registers 11-12: timestamp
        timestamp_high = registers[11]
        timestamp_low = registers[12]
        timestamp = (timestamp_high << 16) | timestamp_low
        
        # Registers 13-18: signature
        sig_regs = registers[13:19]
        sig_bytes = struct.pack(">6H", *sig_regs)
        signature = sig_bytes.hex()
        
        # Build payload
        payload = {
            "type": msg_type_enum.value,
            "position_km": position_km,
            "speed_kmh": speed_kmh,
            "speed_limit": speed_limit,
            "next_checkpoint_km": next_checkpoint_km,
            "ma_id": ma_id,
            "train_id": train_id,
            "timestamp": float(timestamp),
        }
        
        # Return with signature for verification
        return {
            "payload": payload,
            "signature": signature
        }
    
    def sign(self, payload: Dict[str, Any]) -> str:
        """Generate HMAC signature for payload.
        
        Note: Signature is truncated to 96 bits for Modbus register storage.
        This is INTENTIONALLY WEAK for vulnerability demonstration.
        
        Args:
            payload: Message payload
            
        Returns:
            Hexadecimal signature (full HMAC-SHA256)
        """
        # Create canonical representation for signing
        canonical = "|".join([
            str(payload.get("type", "")),
            f"{payload.get('position_km', 0.0):.3f}",
            f"{payload.get('speed_kmh', 0.0):.1f}",
            f"{payload.get('speed_limit', 0.0):.1f}",
            f"{payload.get('next_checkpoint_km', 0.0):.3f}",
            str(payload.get("ma_id", 0)),
        ])
        
        mac = hmac.new(self.key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return mac
    
    def verify(self, payload: Dict[str, Any], signature: str) -> bool:
        """Verify message signature.
        
        Note: Only compares first 96 bits (24 hex chars) due to Modbus truncation.
        
        Args:
            payload: Message payload
            signature: Signature to verify (hex string)
            
        Returns:
            True if signature is valid
        """
        expected = self.sign(payload)
        # Compare only first 24 hex characters (96 bits)
        return hmac.compare_digest(expected[:24], signature[:24])


# Register Modbus TCP protocol
from protocols.registry import ProtocolRegistry
ProtocolRegistry.register("modbus_tcp", ModbusTcpProtocol)
ProtocolRegistry.register("modbus", ModbusTcpProtocol)  # Alias
