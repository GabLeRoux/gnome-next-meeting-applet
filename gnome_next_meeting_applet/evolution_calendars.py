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
#
# from Gab Leroux (@GabLeRoux) https://askubuntu.com/a/1371087
import pytz
import datetime

import gi

gi.require_version("EDataServer", "1.2")
from gi.repository import EDataServer

gi.require_version("ECal", "2.0")
from gi.repository import ECal

from gi.repository import Gio

# https://lazka.github.io/pgi-docs/Gio-2.0/classes/Cancellable.html#Gio.Cancellable
GIO_CANCELLABLE = Gio.Cancellable.new()


def get_ecal_as_utc(ecalcomp) -> datetime.datetime:
    if not ecalcomp:
        return datetime.datetime.now().astimezone(pytz.timezone("UTC"))
    tz = pytz.timezone(ecalcomp.get_tzid() or "UTC")
    ts = ecalcomp.get_value().as_timet()
    dt = tz.normalize(tz.localize(datetime.datetime.utcfromtimestamp(ts)))
    return dt.astimezone(pytz.timezone("UTC"))


class EvolutionCalendarWrapper:
    @staticmethod
    def _get_gnome_calendars():
        # https://lazka.github.io/pgi-docs/EDataServer-1.2/classes/SourceRegistry.html#EDataServer.SourceRegistry.new_sync
        registry = EDataServer.SourceRegistry.new_sync(GIO_CANCELLABLE)
        # https://lazka.github.io/pgi-docs/EDataServer-1.2/classes/SourceRegistry.html#EDataServer.SourceRegistry.list_sources
        return EDataServer.SourceRegistry.list_sources(
            registry, EDataServer.SOURCE_EXTENSION_CALENDAR
        )
        # return EDataServer.SourceRegistry.list_sources(registry)

    def _get_gnome_events_from_calendar_source(self, source: EDataServer.Source):
        # https://lazka.github.io/pgi-docs/ECal-2.0/classes/Client.html#ECal.Client
        client = ECal.Client()

        # https://lazka.github.io/pgi-docs/ECal-2.0/classes/Client.html#ECal.Client.connect_sync
        new_client = client.connect_sync(
            source=source,
            source_type=ECal.ClientSourceType.EVENTS,
            wait_for_connected_seconds=1,  # this should probably be configured
            cancellable=GIO_CANCELLABLE,
        )
        events = []
        seen = []
        if not new_client:
            return events
        # https://lazka.github.io/pgi-docs/ECal-2.0/classes/Client.html#ECal.Client.get_object_list_as_comps_sync
        ret, values = new_client.get_object_list_as_comps_sync(
            sexp="#t", cancellable=GIO_CANCELLABLE
        )
        if not ret:
            return events

        for value in values:
            if not value:
                continue
            start_time = get_ecal_as_utc(value.get_dtstart())
            end_time = get_ecal_as_utc(value.get_dtend())
            now = datetime.datetime.now().astimezone(pytz.timezone("UTC"))

            if now >= end_time:
                continue

            # save memory for stuff we won't care
            if start_time > (now + datetime.timedelta(weeks=4)):
                continue

            uuid = value.get_id().get_uid()
            # sometime we get duplicates whatever the reasons is
            if uuid in seen:
                continue
            seen.append(uuid)
            events.append(value)
        return events

    # TODO: calendar filtering
    def get_all_events(self, restrict_to_calendars=None):
        if restrict_to_calendars is None:
            restrict_to_calendars = []
        calendars = self._get_gnome_calendars()
        print(f"Found following calendars: {[source.get_display_name() for source in calendars]}")
        events = []
        for source in calendars:
            if restrict_to_calendars and source.get_display_name() not in restrict_to_calendars:
                continue
            events += self._get_gnome_events_from_calendar_source(source)
        return events
