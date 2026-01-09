"""Base protocol interface for ETCS testbed."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(Enum):
    """ETCS message types."""
    HELLO = "HELLO"
    MA = "MA"
    EMERGENCY_UPDATE = "EMERGENCY_UPDATE"
    POSITION_REPORT = "POSITION_REPORT"
    CHECKPOINT_REACHED = "CHECKPOINT_REACHED"
    UNKNOWN = "UNKNOWN"


class Protocol(ABC):
    """Abstract base class for protocol implementations.
    
    All protocol adapters must implement these methods to enable
    protocol-agnostic communication in the ETCS testbed.
    """
    
    def __init__(self, key: Optional[bytes] = None):
        """Initialize protocol with optional signing key.
        
        Args:
            key: Secret key for message signing/verification (optional)
        """
        self.key = key or b"super_insecure_demo_key_for_rbc"
    
    @abstractmethod
    def encode(self, payload: Dict[str, Any]) -> bytes:
        """Encode a message payload to wire format.
        
        Args:
            payload: Dictionary containing message fields
            
        Returns:
            Encoded message as bytes
        """
        pass
    
    @abstractmethod
    def decode(self, data: bytes) -> Dict[str, Any]:
        """Decode wire format to message payload.
        
        Args:
            data: Raw bytes from network
            
        Returns:
            Dictionary containing decoded message fields
            
        Raises:
            ValueError: If data cannot be decoded
        """
        pass
    
    @abstractmethod
    def sign(self, payload: Dict[str, Any]) -> str:
        """Generate signature for message payload.
        
        Args:
            payload: Message payload to sign
            
        Returns:
            Signature as string
        """
        pass
    
    @abstractmethod
    def verify(self, payload: Dict[str, Any], signature: str) -> bool:
        """Verify message signature.
        
        Args:
            payload: Message payload to verify
            signature: Signature to check
            
        Returns:
            True if signature is valid, False otherwise
        """
        pass
    
    def get_message_type(self, payload: Dict[str, Any]) -> MessageType:
        """Extract message type from payload.
        
        Args:
            payload: Decoded message payload
            
        Returns:
            MessageType enum value
        """
        msg_type = payload.get("type", "UNKNOWN")
        try:
            return MessageType(msg_type)
        except ValueError:
            return MessageType.UNKNOWN
    
    def create_message(self, msg_type: MessageType, **kwargs) -> Dict[str, Any]:
        """Create a standardized message payload.
        
        Args:
            msg_type: Type of message to create
            **kwargs: Message-specific fields
            
        Returns:
            Message payload dictionary
        """
        payload = {"type": msg_type.value}
        payload.update(kwargs)
        return payload
