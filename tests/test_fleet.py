import unittest
from unittest.mock import patch

try:
    from openswarm.web_server import OpenSwarmServer, SwarmWorld
except ImportError:
    OpenSwarmServer = None


@unittest.skipIf(OpenSwarmServer is None, "Install master[demo] for fleet tests")
class FleetTests(unittest.TestCase):
    def test_simulation_cannot_dispatch_to_unmarked_physical_nodes(self):
        with patch("openswarm.web_server.SwarmMaster") as master:
            server = OpenSwarmServer()
            node = master.return_value.get.return_value
            node.is_online = True
            node.is_virtual = False
            self.assertFalse(server._send_drive("tug_esp32", 100, 100))
            node.drive.assert_not_called()
            node.is_virtual = True
            self.assertTrue(server._send_drive("tug_esp32", 100, 100))
            node.drive.assert_called_once_with("drive", left=100, right=100)

    def test_torque_does_not_depend_on_robot_iteration_order(self):
        first, second = SwarmWorld(), SwarmWorld()
        for world in (first, second):
            for index, bot in enumerate(world.robots.values()):
                bot.update(x=-0.85, y=(-0.2 if index else 0.2), theta=0, motor_l=180, motor_r=180)
        second.robots = dict(reversed(list(second.robots.items())))
        first.update_physics(0.016)
        second.update_physics(0.016)
        self.assertAlmostEqual(first.box["v_theta"], second.box["v_theta"])

    def test_unmeasured_latency_and_offline_nodes_are_not_fabricated(self):
        world = SwarmWorld()
        self.assertIsNone(world.stats["latency_ms"])
        self.assertTrue(all(not bot["online"] for bot in world.robots.values()))
