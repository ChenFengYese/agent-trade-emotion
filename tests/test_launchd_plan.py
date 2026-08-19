import plistlib
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from trade_system.capture_plan import ForwardCapturePlan


ROOT = Path(__file__).resolve().parents[1]


class LaunchdPlanTests(unittest.TestCase):
    def test_calendar_triggers_match_every_frozen_utc_slot_in_shanghai_time(self):
        plan = ForwardCapturePlan.load(ROOT / "config" / "forward_capture_plan.g1.v1.json")
        plist = plistlib.loads((ROOT / "ops" / "launchd" / "com.agent-trade-emotion.capture-supervisor.plist").read_bytes())
        schedules = plist["StartCalendarInterval"]
        actual = {(item["Month"], item["Day"], item["Hour"], item["Minute"]) for item in schedules}
        expected = set()
        for slot in plan.slots:
            local = slot.start.astimezone(ZoneInfo("Asia/Shanghai"))
            expected.add((local.month, local.day, local.hour, local.minute))
        self.assertEqual(28, len(schedules))
        self.assertEqual(expected, actual)
        self.assertNotIn("StartInterval", plist)
        self.assertTrue(plist["RunAtLoad"])
        arguments = plist["ProgramArguments"]
        self.assertNotIn("/Users/wt/Documents", "\n".join(arguments))
        self.assertIn("/Users/wt/Library/Application Support/agent-trade-emotion", "\n".join(arguments))
