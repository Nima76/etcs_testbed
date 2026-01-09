"""JSON protocol implementation for ETCS testbed.

This is the original ETCS protocol using JSON over TCP with HMAC-SHA256 signatures.
Refactored to use the protocol abstraction layer for consistency.
"""

import hashlib
import hmac
import json
from typing import Any, Dict

from protocols.base import Protocol


class JsonProtocol(Protocol):
    """JSON-based ETCS protocol with HMAC-SHA256 signing."""
    
    def encode(self, payload: Dict[str, Any]) -> bytes:
        """Encode message as JSON with signature.
        
        Args:
            payload: Message payload dictionary
            
        Returns:
            JSON-encoded message with newline terminator
        """
        signature = self.sign(payload)
        message = {
            "payload": payload,
            "signature": signature
        }
        return json.dumps(message).encode("utf-8") + b"\n"
    
    def decode(self, data: bytes) -> Dict[str, Any]:
        """Decode JSON message and extract payload.
        
        Args:
            data: Raw JSON bytes (may include newline)
            
        Returns:
            Dictionary with 'payload' and 'signature' keys
            
        Raises:
            ValueError: If JSON is invalid
        """
        line = data.strip()
        if not line:
            raise ValueError("Empty message")
        
        try:
            message = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        
        if not isinstance(message, dict):
            raise ValueError("Message must be a JSON object")
        
        return message
    
    def sign(self, payload: Dict[str, Any]) -> str:
        """Generate HMAC-SHA256 signature for payload.
        
        Args:
            payload: Message payload to sign
            
        Returns:
            Hexadecimal signature string
        """
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        mac = hmac.new(self.key, data, hashlib.sha256).hexdigest()
        return mac
    
    def verify(self, payload: Dict[str, Any], signature: str) -> bool:
        """Verify HMAC-SHA256 signature.
        
        Args:
            payload: Message payload to verify
            signature: Signature to check
            
        Returns:
            True if signature matches, False otherwise
        """
        expected = self.sign(payload)
        return hmac.compare_digest(expected, signature)


# Register JSON protocol as default
from protocols.registry import ProtocolRegistry
ProtocolRegistry.register("json", JsonProtocol)
