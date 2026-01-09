"""Unit tests for protocol implementations."""

import time

import pytest

from protocols.base import MessageType
from protocols.json_protocol import JsonProtocol
from protocols.modbus_tcp import ModbusTcpProtocol
from protocols.registry import ProtocolRegistry


def test_protocol_registry():
    """Test protocol registration and retrieval."""
    # Check that JSON protocol is registered
    assert "json" in ProtocolRegistry.list_protocols()
    
    # Get JSON protocol
    proto = ProtocolRegistry.get("json")
    assert isinstance(proto, JsonProtocol)
    
    # Test with custom key
    custom_key = b"my-custom-key"
    proto = ProtocolRegistry.get("json", key=custom_key)
    assert proto.key == custom_key


def test_json_protocol_encode_decode():
    """Test JSON protocol encoding and decoding."""
    proto = JsonProtocol(key=b"test-key")
    
    payload = {
        "type": "MA",
        "ma_id": 42,
        "position_km": 1.5,
        "speed_limit": 100.0,
        "next_checkpoint_km": 5.3,
    }
    
    # Encode
    encoded = proto.encode(payload)
    assert isinstance(encoded, bytes)
    assert encoded.endswith(b"\n")
    
    # Decode
    decoded = proto.decode(encoded)
    assert "payload" in decoded
    assert "signature" in decoded
    assert decoded["payload"] == payload


def test_json_protocol_sign_verify():
    """Test JSON protocol signing and verification."""
    proto = JsonProtocol(key=b"test-key")
    
    payload = {
        "type": "MA",
        "ma_id": 1,
        "speed_limit": 80.0,
    }
    
    # Sign
    signature = proto.sign(payload)
    assert isinstance(signature, str)
    assert len(signature) == 64  # SHA256 hex digest
    
    # Verify valid signature
    assert proto.verify(payload, signature) is True
    
    # Verify tampered payload
    tampered = dict(payload)
    tampered["speed_limit"] = 200.0
    assert proto.verify(tampered, signature) is False


def test_modbus_protocol_encode_decode():
    """Test Modbus TCP protocol encoding and decoding."""
    proto = ModbusTcpProtocol(key=b"test-key", slave_id=1)
    
    payload = {
        "type": "MA",
        "ma_id": 42,
        "position_km": 1.5,
        "speed_kmh": 75.0,
        "speed_limit": 100.0,
        "next_checkpoint_km": 5.3,
        "train_id": "TrainA",
        "timestamp": time.time(),
    }
    
    # Encode
    encoded = proto.encode(payload)
    assert isinstance(encoded, bytes)
    assert len(encoded) >= 38  # 19 registers minimum
    
    # Decode
    decoded = proto.decode(encoded)
    assert "payload" in decoded
    assert "signature" in decoded
    
    # Check values (with small floating point tolerance)
    decoded_payload = decoded["payload"]
    assert decoded_payload["type"] == "MA"
    assert decoded_payload["ma_id"] == 42
    assert abs(decoded_payload["position_km"] - 1.5) < 0.01
    assert abs(decoded_payload["speed_kmh"] - 75.0) < 0.1
    assert abs(decoded_payload["speed_limit"] - 100.0) < 0.1
    assert abs(decoded_payload["next_checkpoint_km"] - 5.3) < 0.01


def test_modbus_protocol_message_types():
    """Test Modbus encoding of different message types."""
    proto = ModbusTcpProtocol(key=None)  # No signatures for simpler test
    
    message_types = [
        MessageType.HELLO,
        MessageType.MA,
        MessageType.EMERGENCY_UPDATE,
        MessageType.POSITION_REPORT,
        MessageType.CHECKPOINT_REACHED,
    ]
    
    for msg_type in message_types:
        payload = {
            "type": msg_type.value,
            "position_km": 2.0,
            "speed_kmh": 50.0,
            "speed_limit": 80.0,
            "next_checkpoint_km": 4.0,
            "ma_id": 10,
        }
        
        encoded = proto.encode(payload)
        decoded = proto.decode(encoded)
        
        assert decoded["payload"]["type"] == msg_type.value


def test_modbus_protocol_sign_verify():
    """Test Modbus protocol signing and verification."""
    proto = ModbusTcpProtocol(key=b"test-key")
    
    payload = {
        "type": "MA",
        "position_km": 1.0,
        "speed_limit": 80.0,
        "next_checkpoint_km": 3.0,
        "ma_id": 5,
    }
    
    # Sign
    signature = proto.sign(payload)
    assert isinstance(signature, str)
    
    # Verify valid signature
    assert proto.verify(payload, signature) is True
    
    # Verify tampered payload
    tampered = dict(payload)
    tampered["speed_limit"] = 200.0
    assert proto.verify(tampered, signature) is False


def test_modbus_protocol_no_signature():
    """Test Modbus protocol without signatures (insecure mode)."""
    proto = ModbusTcpProtocol(key=None)
    
    payload = {
        "type": "MA",
        "position_km": 1.0,
        "speed_limit": 100.0,
    }
    
    # Encode without signature
    encoded = proto.encode(payload)
    decoded = proto.decode(encoded)
    
    # Signature should be zeros
    assert decoded["signature"] == "000000000000000000000000"


def test_protocol_message_type_extraction():
    """Test message type extraction from payloads."""
    proto = JsonProtocol()
    
    # Test valid message types
    for msg_type in MessageType:
        if msg_type != MessageType.UNKNOWN:
            payload = {"type": msg_type.value}
            extracted = proto.get_message_type(payload)
            assert extracted == msg_type
    
    # Test unknown type
    payload = {"type": "INVALID"}
    extracted = proto.get_message_type(payload)
    assert extracted == MessageType.UNKNOWN


def test_protocol_create_message():
    """Test message creation helper."""
    proto = JsonProtocol()
    
    # Create MA message
    msg = proto.create_message(
        MessageType.MA,
        ma_id=1,
        speed_limit=100.0,
        position_km=0.0,
        next_checkpoint_km=2.0
    )
    
    assert msg["type"] == "MA"
    assert msg["ma_id"] == 1
    assert msg["speed_limit"] == 100.0
    assert msg["position_km"] == 0.0
    assert msg["next_checkpoint_km"] == 2.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
