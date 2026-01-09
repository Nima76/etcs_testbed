"""Protocol abstraction layer for ETCS testbed.

This module provides a protocol-agnostic interface for encoding,
decoding, signing, and verifying messages in the ETCS testbed.
Supports multiple ICS protocols including JSON, Modbus TCP/RTU, DNP3, etc.
"""

from protocols.base import Protocol, MessageType
from protocols.registry import ProtocolRegistry, get_protocol

__all__ = ["Protocol", "MessageType", "ProtocolRegistry", "get_protocol"]
