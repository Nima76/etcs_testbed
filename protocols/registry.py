"""Protocol registry for dynamic protocol selection."""

import os
from typing import Dict, Optional, Type

from protocols.base import Protocol


class ProtocolRegistry:
    """Registry for managing protocol implementations."""
    
    _protocols: Dict[str, Type[Protocol]] = {}
    
    @classmethod
    def register(cls, name: str, protocol_class: Type[Protocol]) -> None:
        """Register a protocol implementation.
        
        Args:
            name: Protocol identifier (e.g., "json", "modbus_tcp")
            protocol_class: Protocol class to register
        """
        cls._protocols[name.lower()] = protocol_class
    
    @classmethod
    def get(cls, name: str, key: Optional[bytes] = None) -> Protocol:
        """Get a protocol instance by name.
        
        Args:
            name: Protocol identifier
            key: Optional signing key
            
        Returns:
            Protocol instance
            
        Raises:
            KeyError: If protocol not registered
        """
        protocol_class = cls._protocols.get(name.lower())
        if protocol_class is None:
            raise KeyError(f"Protocol '{name}' not registered")
        return protocol_class(key=key)
    
    @classmethod
    def list_protocols(cls) -> list:
        """List all registered protocol names.
        
        Returns:
            List of protocol names
        """
        return list(cls._protocols.keys())


def get_protocol(name: Optional[str] = None, key: Optional[bytes] = None) -> Protocol:
    """Get protocol instance from environment or explicit name.
    
    Args:
        name: Protocol name (overrides environment variable)
        key: Optional signing key
        
    Returns:
        Protocol instance
    """
    if name is None:
        name = os.getenv("PROTOCOL", "json")
    
    try:
        return ProtocolRegistry.get(name, key=key)
    except KeyError:
        # Fallback to JSON protocol
        fallback = os.getenv("FALLBACK_PROTOCOL", "json")
        print(f"WARNING: Protocol '{name}' not found, falling back to '{fallback}'")
        return ProtocolRegistry.get(fallback, key=key)
