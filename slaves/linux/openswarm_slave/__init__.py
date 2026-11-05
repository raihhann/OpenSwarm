"""
OpenSwarm Linux Slave SDK (`openswarm-slave`)
=============================================
Turns any Linux system (Arduino UNO Q, Portenta X8, Raspberry Pi, Nvidia Jetson, or Linux Laptop)
into a Zero-Control-Logic OpenSwarm Slave node speaking the exact same UDP protocol (4210 / 4211)
as the microcontroller slaves.
"""

from .node import SwarmNode

__version__ = "0.1.0"
__all__ = ["SwarmNode"]
