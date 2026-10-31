"""Fixtures for pass_marker.sh.

Each case runs the script's real entry point against a throwaway OACP_HOME with a
pinned clock (PASS_MARKER_NOW) and a pinned zone (SELF_IMPROVE_TZ), so it needs no
real markers and no particular time of day or machine timezone.

    python3 -m unittest discover -s skills/self-improve/tests   (pytest runs it too)
"""

import datetime as dt
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pass_marker.sh"
ZONE = "America/New_York"
TZ = ZoneInfo(ZONE)


def epoch(stamp):
    """'YYYY-MM-DD HH:MM' wall-clock in ZONE -> epoch seconds."""
    return int(dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M").replace(tzinfo=TZ).timestamp())


class PassMarker(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.project = root / "fixtureproj"          # not a git repo: project = cwd basename
        self.project.mkdir()
        self.home = root / "home"
        self.state = self.home / "state" / "self-improve"
        self.state.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def mark(self, day, written_at):
        """A marker for <day> (YYYYMMDD) whose mtime is <written_at> (epoch)."""
        f = self.state / f"fixtureproj-{day}.marker"
        f.write_text("x scope=test\n")
        os.utime(f, (written_at, written_at))
        return f

    def run_script(self, now, *args):
        env = {**os.environ, "OACP_HOME": str(self.home), "PASS_MARKER_NOW": str(now),
               "SELF_IMPROVE_TZ": ZONE}
        out = subprocess.run(["bash", str(SCRIPT), *args], cwd=self.project, env=env,
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()

    def check_at(self, stamp):
        return self.run_script(epoch(stamp), "check")

    # --- check ---------------------------------------------------------------------

    def test_post_midnight_pass_is_seen_by_a_morning_check(self):
        # A pass at 00:05 files under yesterday; a check at 06:40 the same day still sees it.
        self.mark("20260928", epoch("2026-09-29 00:05"))
        self.assertEqual(self.check_at("2026-09-29 06:40"), "PRIOR_PASS")

    def test_yesterday_marker_from_30_hours_ago_is_another_day(self):
        self.mark("20260928", epoch("2026-09-28 00:40"))
        self.assertEqual(self.check_at("2026-09-29 06:40"), "NO_PRIOR_PASS")

    def test_todays_marker_counts_whatever_its_age(self):
        self.mark("20260929", epoch("2026-09-29 08:00"))
        self.assertEqual(self.check_at("2026-09-29 21:00"), "PRIOR_PASS")

    def test_marathon_check_before_five_accepts_any_yesterday_marker(self):
        self.mark("20260928", epoch("2026-09-28 07:00"))
        self.assertEqual(self.check_at("2026-09-29 03:00"), "PRIOR_PASS")

    def test_no_marker(self):
        self.assertEqual(self.check_at("2026-09-29 06:40"), "NO_PRIOR_PASS")

    def test_yesterday_is_found_across_a_dst_change(self):
        # 2026-03-08 is 23 hours long in ZONE; at 00:30 the next day "yesterday" is still the 8th.
        self.mark("20260308", epoch("2026-03-08 10:00"))
        self.assertEqual(self.check_at("2026-03-09 00:30"), "PRIOR_PASS")

    # --- append --------------------------------------------------------------------

    def test_append_writes_todays_marker_then_check_sees_it(self):
        out = self.run_script(epoch("2026-09-29 14:15"), "append", "narrow")
        marker = self.state / "fixtureproj-20260929.marker"
        self.assertIn(str(marker), out)
        self.assertEqual(marker.read_text(), "14:15 scope=narrow\n")
        self.assertEqual(self.check_at("2026-09-29 22:00"), "PRIOR_PASS")

    def test_append_before_five_joins_an_existing_yesterday_marker(self):
        self.mark("20260928", epoch("2026-09-28 20:00"))
        self.run_script(epoch("2026-09-29 02:10"), "append", "full")
        self.assertEqual((self.state / "fixtureproj-20260928.marker").read_text(), "02:10 scope=full\n")
        self.assertFalse((self.state / "fixtureproj-20260929.marker").exists())


if __name__ == "__main__":
    unittest.main()
