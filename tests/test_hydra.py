import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hydra_arm_model import JOINT_CONFIG, validate_episode, step_toward, controller_addresses
from hydra_arm_episodes import EpisodePlayer

try:
    from hydra_arm_studio import HydraArmStudioServer
except ImportError:
    HydraArmStudioServer = None


class FakeNode:
    is_online = True
    ip = "127.0.0.1"
    port = 4210
    board = "TEST"
    sensors = {}

    def __init__(self):
        self.commands = []

    def servo(self, actuator, angle):
        self.commands.append((actuator, angle))


class FakeMaster:
    def __init__(self):
        self.node = None
        self.closed = False

    def subscribe(self, node_id):
        return self.node

    get = subscribe

    def close(self):
        self.closed = True


class ModelTests(unittest.TestCase):
    def test_shared_controller_address_conflicts_are_rejected(self):
        with self.assertRaises(ValueError):
            controller_addresses({"shoulder": "127.0.0.1", "gripper": "127.0.0.2"})
        self.assertEqual(len(controller_addresses({"shoulder": "127.0.0.1", "gripper": "127.0.0.1"})), 1)

    def test_standalone_player_honors_frame_times_dwell_and_cleanup(self):
        class Clock:
            now = 0.0
            def monotonic(self):
                return self.now
            def sleep(self, delay):
                self.now += delay
        clock = Clock()
        master = FakeMaster()
        master.node = FakeNode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timing.json"
            path.write_text(json.dumps({"duration_sec": 0.06, "frames": [
                {"t": 0, "joints": {"base": 92}}, {"t": 0.012, "joints": {"base": 90}}]}))
            with patch("hydra_arm_episodes.SwarmMaster", return_value=master), patch("hydra_arm_episodes.time", clock):
                player = EpisodePlayer()
                player.play_file(str(path))
        # The next target arrives before the first interpolation finishes.
        self.assertEqual(master.node.commands, [("servo", 91), ("servo", 90)])
        self.assertGreaterEqual(clock.now, 2.06)
        self.assertLess(clock.now, 2.09)
        self.assertTrue(master.closed)

    def test_missing_episode_also_closes_master(self):
        master = FakeMaster()
        with patch("hydra_arm_episodes.SwarmMaster", return_value=master):
            EpisodePlayer().play_file("nonexistent-audit-episode.json")
        self.assertTrue(master.closed)

    def test_episode_validation_rejects_invalid_motion_before_playback(self):
        for frame in [{"t": -1, "joints": {"base": 90}},
                      {"t": float("inf"), "joints": {"base": 90}},
                      {"t": 0, "joints": {"shoulder": 180}},
                      {"t": 0, "joints": {"unknown": 90}},
                      {"t": 0, "joints": {"base": True}}]:
            with self.assertRaises(ValueError):
                validate_episode({"frames": [frame]})

    def test_partial_frames_and_final_dwell_are_preserved(self):
        data = validate_episode({"duration_sec": 4, "frames": [{"t": 0, "joints": {"base": 90}}]})
        self.assertEqual(data["duration_sec"], 4)
        self.assertEqual(data["frames"][0]["joints"], {"base": 90})

    def test_interpolation_reaches_target_without_overshooting(self):
        for target in (0, 89, 90, 91, 180):
            current = 90
            for _ in range(200):
                current = step_toward(current, target)
            self.assertEqual(current, target)


@unittest.skipIf(HydraArmStudioServer is None, "Install master[demo] for browser tests")
class StudioTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory_patch = patch("hydra_arm_studio.EPISODES_DIR", self.temp.name)
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)
        with patch("hydra_arm_studio.SwarmMaster", FakeMaster):
            self.server = HydraArmStudioServer()

    async def asyncTearDown(self):
        self.server.stop_playback()
        await asyncio.sleep(0)

    def episode(self, name="test.json"):
        path = Path(self.temp.name) / name
        path.write_text(json.dumps({"duration_sec": 5, "frames": [{"t": 0, "joints": {"base": 120}}]}))
        return name

    async def test_replacing_playback_does_not_cancel_replacement(self):
        filename = self.episode()
        self.server.start_playback(filename)
        await asyncio.sleep(0)
        self.server.start_playback(filename)
        task = self.server._play_task
        await asyncio.sleep(0)
        self.assertTrue(self.server.playing)
        self.assertFalse(task.done())

    async def test_stop_freezes_pending_motion(self):
        self.server.master.node = FakeNode()
        self.server.command_joint("base", 160)
        self.server.motion_tick()
        current = self.server.joints["base"]["angle"]
        self.server.stop_playback()
        self.server.motion_tick()
        self.assertEqual(self.server.joints["base"]["target_angle"], current)
        self.assertEqual(len(self.server.master.node.commands), 1)

    async def test_offline_target_is_delivered_after_discovery(self):
        self.server.command_joint("base", 120)
        self.server.motion_tick()
        self.assertEqual(self.server.joints["base"]["angle"], 90)
        self.server.master.node = FakeNode()
        for _ in range(40):
            self.server.motion_tick()
        self.assertEqual(self.server.master.node.commands[-1], ("servo", 120))
        self.assertFalse(self.server.joints["base"]["pending"])

    async def test_equal_target_is_sent_once(self):
        self.server.master.node = FakeNode()
        self.server.command_joint("base", 90)
        self.server.motion_tick()
        self.server.motion_tick()
        self.assertEqual(self.server.master.node.commands, [("servo", 90)])

    async def test_recording_preserves_dwell_and_writes_valid_episode(self):
        self.server.start_recording("example")
        self.server.record_start_time -= 2
        filename = self.server.stop_recording()
        data = validate_episode(json.loads((Path(self.temp.name) / filename).read_text()))
        self.assertGreaterEqual(data["frames"][-1]["t"], 2)
        self.assertEqual(list(Path(self.temp.name).glob("*.tmp")), [])

    async def test_browser_metadata_comes_from_shared_model(self):
        response = await self.server.handle_index(None)
        self.assertNotIn("__JOINTS_META__", response.text)
        self.assertIn(json.dumps(JOINT_CONFIG["shoulder"]["label"]), response.text)

    async def test_server_cleanup_joins_tasks_and_closes_master(self):
        context = self.server._runtime(self.server.app)
        await context.__anext__()
        self.server.start_playback(self.episode())
        await asyncio.sleep(0)
        with self.assertRaises(StopAsyncIteration):
            await context.__anext__()
        self.assertTrue(self.server.master.closed)
        self.assertFalse(self.server._retired_playbacks)
