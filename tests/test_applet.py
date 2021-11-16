from unittest import TestCase

from gnome_next_meeting_applet.applet import Applet, DEFAULT_CONFIG

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
