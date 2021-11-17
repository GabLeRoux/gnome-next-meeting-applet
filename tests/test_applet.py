import datetime
from unittest import TestCase

import pytz

from gnome_next_meeting_applet.applet import Applet, DEFAULT_CONFIG, get_human_readable_week_day

ZOOM_URL_EXAMPLE = "https://us02web.zoom.us/j/01234567891?pwd=abcdefghijklmnopqrstuvwxyz012345"


class _MockDescription:
    @staticmethod
    def get_value():
        return ZOOM_URL_EXAMPLE


class _MockEvent:
    @staticmethod
    def get_descriptions():
        return [_MockDescription()]


class TestApplet(TestCase):
    def test__match_videocall_url_from_summary(self):
        c = Applet()
        c.config = DEFAULT_CONFIG
        result = c._match_videocall_url_from_summary(_MockEvent())
        self.assertEqual(ZOOM_URL_EXAMPLE, result)

    def test_get_human_readable_week_day(self):
        result = get_human_readable_week_day(start_time=datetime.datetime(2020, 1, 1, 0, 0, 0))
        self.assertEqual("Wednesday (01 Jan)", result)

        result = get_human_readable_week_day(start_time=datetime.datetime(2020, 1, 2, 0, 0, 0))
        self.assertEqual("Thursday (02 Jan)", result)

        result = get_human_readable_week_day(start_time=datetime.datetime(2020, 1, 3, 0, 0, 0))
        self.assertEqual("Friday (03 Jan)", result)

        result = get_human_readable_week_day(start_time=datetime.datetime(2020, 1, 4, 0, 0, 0))
        self.assertEqual("Saturday (04 Jan)", result)

        result = get_human_readable_week_day(start_time=datetime.datetime(2020, 1, 5, 0, 0, 0))
        self.assertEqual("Sunday (05 Jan)", result)

        now = datetime.datetime.now(pytz.timezone("UTC"))
        result = get_human_readable_week_day(start_time=now)
        self.assertEqual(now.strftime("Today (%d %b)"), result)
