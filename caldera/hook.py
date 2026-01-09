"""CALDERA plugin entry point for ETCS testbed."""

from app.utility.base_world import BaseWorld

name = "etcs_testbed"
description = "ETCS Railway Control System ICS Testbed"
address = "/plugin/etcs_testbed/gui"


async def enable(services):
    """Enable the ETCS testbed plugin.
    
    Args:
        services: CALDERA services object
    """
    app = services.get("app_svc").application
    data_svc = services.get("data_svc")
    
    # Load abilities
    await data_svc.reload_database()
    
    print("[ETCS] Plugin loaded successfully")


async def initialize(app, services):
    """Initialize the ETCS testbed plugin."""
    pass
