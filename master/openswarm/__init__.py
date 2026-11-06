"""
OpenSwarm Master SDK
====================
Zero-Control-Logic Distributed Hardware Abstraction Layer (Remote HAL) Master.
All robot intelligence, sensor reading, and actuator control runs here on the Master.
"""

from .master import SwarmMaster
from .node import RemoteSwarmNode

__version__ = "0.1.1"
__all__ = ["SwarmMaster", "RemoteSwarmNode"]
