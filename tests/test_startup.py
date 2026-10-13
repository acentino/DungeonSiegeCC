"""Headless regression coverage for startup update and framework checks."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from importer import App
import manager
import update_helper


class Status:
    def __init__(self):
        self.history = []

    def set(self, value):
        self.history.append(value)


class AppStub:
    """Call real startup methods without opening a Tk window."""
    def __init__(self):
        self.status = Status()
        self.events = []
        self.scheduled = []
        self._checking_updates = False
        self._startup_framework_running = False
        self._pending_startup_update = None

    def check_update(self, startup=False):
        self.events.append(("online_check", startup))
        App.finish_update_check(self, True, {"newer": False}, startup=startup)

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))

    def first_launch(self):
        self.events.append(("framework_check", True))

    def update_offer(self, release):
        self.events.append(("update_result", release["newer"]))

    def finish_update_check(self, success, outcome, startup=False):
        App.finish_update_check(self, success, outcome, startup=startup)

    def startup_framework_check(self):
        App.startup_framework_check(self)


class StartupChecksTests(unittest.TestCase):
    def test_startup_runs_both_checks_and_serializes_prompts(self):
        app = AppStub()
        App.startup_checks(app)
        self.assertEqual(app.events, [("online_check", True)])
        self.assertTrue(app._startup_framework_running)
        self.assertIsNotNone(app._pending_startup_update)
        self.assertEqual(len(app.scheduled), 1)
        app.scheduled[0][1]()
        self.assertEqual(app.events, [
            ("online_check", True),
            ("framework_check", True),
            ("update_result", False)
        ])
        self.assertFalse(app._startup_framework_running)

    def test_automatic_framework_check_when_path_already_saved(self):
        class Game:
            def get(self):
                return "game"
        class Fake:
            game = Game()
            def __init__(self):
                self.events = []
            def framework(self):
                self.events.append("verified")
            def choose_game(self):
                self.events.append("choose")
        app = Fake()
        with patch.object(manager, "valid_game_folder", return_value=True):
            App.first_launch(app)
        self.assertEqual(app.events, ["verified"])

    def test_update_relaunch_invokes_new_importer(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "importer.py").write_text("# new importer", encoding="utf-8")
            with patch("subprocess.Popen") as popen:
                update_helper.relaunch_importer(root)
                self.assertEqual(popen.call_count, 1)
                args, kwargs = popen.call_args
                self.assertEqual(Path(args[0][1]).resolve(), (root / "importer.py").resolve())
                self.assertEqual(Path(kwargs["cwd"]).resolve(), root.resolve())


if __name__ == "__main__":
    unittest.main()
