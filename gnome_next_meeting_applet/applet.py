# -*- coding: utf-8 -*-
# Author: Chmouel Boudjnah <chmouel@chmouel.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
# pylint: disable=no-self-use
"""Gnome next meeting calendar applet via Google Calendar"""
import datetime
import os.path
import pathlib
import re
import typing

import dateutil.relativedelta as dtrelative
import dateutil.tz as dttz
import pytz
import yaml
import gi

gi.require_version('AppIndicator3', '0.1')
from gi.repository import AppIndicator3 as appindicator
from gi.repository import Gdk as gdk
from gi.repository import GLib as glib
from gi.repository import Gtk as gtk

import gnome_next_meeting_applet.evolution_calendars as evocal

APP_INDICATOR_ID = "gnome-next-meeting-applet"

DEFAULT_CONFIG = {
    "restrict_to_calendars": [],
    "skip_non_accepted": True,
    "show_only_videocall_events": False,
    "my_emails": [],
    "max_results": 10,
    "title_max_char": 20,
    "refresh_interval": 300,
    "event_organizers_icon": {},
    "title_match_icon": {},
    "change_icon_minutes": 2,
    "default_icon": "🗓️",
    "calendar_day_prefix_url": "https://calendar.google.com/calendar/r/day/",
    "videocall_desc_regexp": [
        r"(https://.*zoom.us/j/[^\n]*)",
        r"(https://meet.google.com/[^\n]*)",
        r"(https://teams.microsoft.com/l/meetup-join/[^\n]*)",
        r"(https://meet.lync.com/[^\n]*)",
        r"(https://.*amazon.com/meeting/[^\n]*)",
    ]
}


def get_human_readable_week_day(start_time):
    today = datetime.datetime.now(pytz.timezone("UTC"))
    formatted_date = start_time.strftime("%d %b")
    if start_time.date() == today.date():
        return f"Today ({formatted_date})"
    if start_time.date() == today.date() + datetime.timedelta(days=1):
        return f"Tomorrow ({formatted_date})"
    if start_time.date() < today.date() + datetime.timedelta(days=7):
        return start_time.strftime(f"%A ({formatted_date})")
    return start_time.strftime("%d %b")


class Applet:
    """Applet: class"""

    events: typing.List = []
    indicator = None

    empty_events_message = "No upcoming events"

    def __init__(self):
        self.config = DEFAULT_CONFIG
        self.config_dir = os.path.expanduser(
            f"{glib.get_user_config_dir()}/{APP_INDICATOR_ID}")

        configfile = pathlib.Path(self.config_dir) / "config.yaml"
        print(configfile)
        if configfile.exists():
            with configfile.open() as f:
                self.config = {
                    **DEFAULT_CONFIG,
                    **yaml.safe_load(f)
                }
        else:
            if not configfile.parent.exists():
                configfile.parent.mkdir(parents=True)
            configfile.write_text(yaml.safe_dump(DEFAULT_CONFIG))
            self.config = DEFAULT_CONFIG

        self.autostart_file = pathlib.Path(
            f"{glib.get_user_config_dir()}/autostart/gnome-next-meeting-applet.desktop"
        ).expanduser()

    @staticmethod
    def replace_html_special_chars(text):
        """Replace html chars"""
        return text\
            .replace("&", "&amp;")\
            .replace('"', "&quot;")\
            .replace("<", "&lt;")\
            .replace(">", "&gt;")

    def first_event(self, event):
        """Show first event in menubar"""
        # not sure why but on my gnome version (arch 40.4.0) we don't need to do
        # replace_html_special_chars in bar, but I am sure on ubuntu I needed that, YMMV :-d !
        summary = (event.get_summary().get_value().strip()
                   [:self.config["title_max_char"]])

        start_time = evocal.get_ecal_as_utc(event.get_dtstart())
        end_time = evocal.get_ecal_as_utc(event.get_dtend())

        readable_delay = self._get_readable_delay(start_time, end_time)
        return f"{readable_delay} - {summary}"

    def _get_readable_delay(self, start_time, end_time):
        """Get readable delay"""
        now = datetime.datetime.now(pytz.timezone("UTC"))
        if start_time < now:
            return "past"
        if start_time > now:
            return f"in {self._get_readable_time_delta(start_time - now)}"
        return f"in {self._get_readable_time_delta(end_time - now)}"

    def _get_readable_time_delta(self, time_delta):
        """Get readable time delta"""
        if time_delta.days > 0:
            return f"{time_delta.days}d"
        if time_delta.seconds > 3600:
            return f"{time_delta.seconds // 3600}h{time_delta.seconds % 3600 // 60}m"
        if time_delta.seconds > 60:
            return f"{time_delta.seconds // 60}m"
        return f"{time_delta.seconds}s"

    def get_all_events(self):
        """Get all events from Evolution Calendar"""
        evolution_calendar = evocal.EvolutionCalendarWrapper()
        # TODO: add filtering user option GUI instead of just yaml
        event_list = evolution_calendar.get_all_events(
            restrict_to_calendars=self.config["restrict_to_calendars"])
        ret = []

        events_sorted = sorted(
            event_list, key=lambda x: evocal.get_ecal_as_utc(x.get_dtstart())
        )

        for event in events_sorted:
            if event.get_status().value_name != "I_CAL_STATUS_CONFIRMED":
                print("SKipping not confirmed")
                continue

            skip_it = False
            if self.config["skip_non_accepted"] and self.config["my_emails"]:
                skip_it = True
                for attendee in event.get_attendees():
                    for my_email in self.config["my_emails"]:
                        if (
                            attendee.get_value().replace("mailto:", "") == my_email
                            and attendee.get_partstat().value_name == "I_CAL_PARTSTAT_ACCEPTED"
                        ):
                            skip_it = False
            if skip_it:
                continue

            if self.config["show_only_videocall_events"]:
                videocall_url = self._match_videocall_url_from_summary(event)
                if videocall_url == "":
                    continue

            ret.append(event)

        return ret

    # pylint: disable=unused-argument
    def set_indicator_icon_label(self, source):
        if not self.events:
            source.set_label(self.empty_events_message, APP_INDICATOR_ID)
            return

        now = datetime.datetime.now().astimezone(pytz.timezone("UTC"))
        first_start_time = evocal.get_ecal_as_utc(self.events[0].get_dtstart())
        first_end_time = evocal.get_ecal_as_utc(self.events[0].get_dtend())

        if (now >
            (first_start_time -
             datetime.timedelta(minutes=self.config["change_icon_minutes"]))
                and not now > first_start_time):
            source.set_icon(self.get_icon_path("notification"))
        elif now >= first_end_time:  # need a refresh
            self.make_menu_items()
            return self.set_indicator_icon_label(source)
        else:
            # TODO: DeprecationWarning: AppIndicator3.Indicator.set_icon is deprecated
            source.set_icon(self.get_icon_path("calendar"))

        source.set_label(f"{self.first_event(self.events[0])}",
                         APP_INDICATOR_ID)
        return True

    @staticmethod
    def get_icon_path(icon):
        dev_path = pathlib.Path(__file__).parent.parent / "images"
        if not dev_path.exists():
            dev_path = pathlib.Path(
                "/usr/share/gnome-next-meeting-applet/images")

        for ext in ["svg", "png"]:
            if (dev_path / f"{icon}.{ext}").exists():
                return str(dev_path / f"{icon}.{ext}")
        return "x-office-calendar-symbolic"

    # pylint: disable=unused-argument
    @staticmethod
    def applet_quit(_):
        gtk.main_quit()

    @staticmethod
    def applet_click(source):
        print(f"Clicked {source}")
        if source.location == "":
            return
        print(f"Opening Location: {source.location}")
        gtk.show_uri(None, source.location, gdk.CURRENT_TIME)

    def make_menu_items(self):
        self.events = self.get_all_events()

        menu = gtk.Menu()
        now = datetime.datetime.now().astimezone(pytz.timezone("UTC"))
        current_day = ""

        if not self.events:
            menuitem = gtk.MenuItem(label=self.empty_events_message)
            menu.show_all()
            menu.add(menuitem)
            self.indicator.set_menu(menu)
            return

        event_first = self.events[0]
        event_first_start_time = evocal.get_ecal_as_utc(
            event_first.get_dtstart())
        event_first_end_time = evocal.get_ecal_as_utc(event_first.get_dtend())

        if event_first_start_time < now < event_first_end_time and event_first.get_attachments():
            menuitem = gtk.MenuItem(label="📑 Open current meeting document")
            menuitem.location = event_first.get_attachments()[0].get_url()
            menuitem.connect("activate", self.applet_click)
            menu.add(menuitem)

        for event in self.events[0:int(self.config["max_results"])]:
            start_time = evocal.get_ecal_as_utc(event.get_dtstart())
            start_time = start_time.astimezone(dttz.gettz())

            # get human readable relative date (e.g. "Today", "Tomorrow")
            _current_day = get_human_readable_week_day(start_time)

            if _current_day != current_day:

                today_item = gtk.MenuItem(label=_current_day)
                gtk.MenuItem.set_sensitive(today_item, False)
                calendar_day_prefix_url = self.config["calendar_day_prefix_url"]
                today_item.location = f"{calendar_day_prefix_url}/{start_time.strftime('%Y/%m/%d')}"
                today_item.connect("activate", self.applet_click)
                menu.append(today_item)
                current_day = _current_day

            summary = self.replace_html_special_chars(
                event.get_summary().get_value().strip())

            icon = self.config["default_icon"]
            _organizer = event.get_organizer()
            if _organizer:
                organizer = _organizer.get_value().replace("mailto:", "")
                for regexp in self.config["event_organizers_icon"]:
                    if re.match(regexp, organizer):
                        icon = self.config["event_organizers_icon"][regexp]
                        break

            start_time_str = start_time.strftime("%H:%M")
            if now >= start_time:
                summary = f"<i>{summary}</i>"

            match_videocall_summary = self._match_videocall_url_from_summary(event)

            url = ""
            location = event.get_location()
            if location:
                if match_videocall_summary:
                    icon = "📹"
                    url = match_videocall_summary
                elif location.startswith("https://"):
                    icon = "🕸"
                    url = location
            else:
                if icon == self.config["default_icon"]:
                    title = event.get_summary().get_value()
                    for regexp in self.config["title_match_icon"]:
                        if re.match(regexp, title):
                            icon = self.config["title_match_icon"][regexp]

            menuitem = gtk.MenuItem(label=f"{icon} {summary} - {start_time_str}")
            menuitem.location = url
            menuitem.get_child().set_use_markup(True)
            menuitem.connect("activate", self.applet_click)
            menu.append(menuitem)

        setting_menu = gtk.Menu()
        label = ("Remove autostart" if self.autostart_file.exists() else "Auto start at boot")
        item_autostart = gtk.MenuItem(label=label)
        item_autostart.connect("activate", self.install_uninstall_autostart)
        setting_menu.add(item_autostart)
        # TODO: PyGTKDeprecationWarning: Using positional arguments with the GObject constructor has been deprecated. Please specify keyword(s) for "label" or use a class specific constructor. See: https://wiki.gnome.org/PyGObject/InitializerDeprecations
        #   setting_item = gtk.MenuItem("Setting")
        setting_item = gtk.MenuItem("Setting")
        setting_item.set_submenu(setting_menu)
        menu.add(setting_item)

        item_quit = gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self.applet_quit)
        menu.add(item_quit)

        menu.show_all()

        self.indicator.set_menu(menu)

    def _match_videocall_url_from_summary(self, event) -> str:
        try:
            text = event.get_descriptions()[0].get_value()
        except IndexError:
            return ""
        for reg in self.config['videocall_desc_regexp']:
            match = re.search(reg, text)
            if match:
                url = match.groups()[0]
                return url
        return ""

    def install_uninstall_autostart(self, source):

        if self.autostart_file.exists():
            self.autostart_file.unlink()
            source.set_label("Auto start at boot")
            return

        self.autostart_file.write_text("""#!/usr/bin/env xdg-open
[Desktop Entry]
Categories=Productivity;
Comment=Gnome next meeting applet to jump on your next call in a single click
Exec=gnome-next-meeting-applet
Icon=calendar
Name=Gnome next meeting applet
StartupNotify=false
Type=Application
Version=1.0
""")
        source.set_label("Remove autostart")

    def build_indicator(self):
        self.indicator = appindicator.Indicator.new(
            APP_INDICATOR_ID,
            self.get_icon_path("calendar"),
            appindicator.IndicatorCategory.SYSTEM_SERVICES,
        )
        self.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
        self.make_menu_items()
        self.set_indicator_icon_label(self.indicator)
        glib.timeout_add_seconds(30, self.set_indicator_icon_label, self.indicator)
        glib.timeout_add_seconds(self.config["refresh_interval"], self.make_menu_items)
        gtk.main()

    def main(self):
        self.build_indicator()


def run():
    c = Applet()
    c.main()


if __name__ == "__main__":
    run()
