#!/usr/bin/env python3

import json
import sys
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "sm-monirulislam/Upcoming-and-Live-Sports-Data/"
    "refs/heads/main/Sports_data.json"
)

MANUAL_CONTROL_FILE = "manual_control.json"

BD_TIMEZONE = ZoneInfo("Asia/Dhaka")

EVENT_TIME_FORMAT = "%d/%m/%Y %I:%M:%S %p"


# =========================================================
# FETCH SOURCE API
# =========================================================

def fetch_data():

    req = Request(
        SOURCE_URL,
        headers={
            "User-Agent": "sports-data-fetcher/1.0"
        }
    )

    with urlopen(req, timeout=30) as response:
        return json.load(response)


# =========================================================
# LOAD MANUAL CONTROL
# =========================================================

def load_manual_control():

    try:

        with open(
            MANUAL_CONTROL_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        return data

    except FileNotFoundError:

        print(
            "WARNING: manual_control.json not found."
        )

        return {}

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            f"Invalid manual_control.json: {exc}"
        )


# =========================================================
# FIND MATCHES
# =========================================================

def find_matches(data):

    if isinstance(data, list):
        return data

    if isinstance(data, dict):

        for key in (
            "matches",
            "events",
            "data",
            "sports"
        ):

            if isinstance(
                data.get(key),
                list
            ):
                return data[key]

    return []


# =========================================================
# EVENT ID
# =========================================================

def get_event_id(match):

    if not isinstance(match, dict):
        return ""

    # Prefer id
    event_id = match.get("id")

    if event_id is not None:
        return str(event_id).strip()

    # Fallback
    event_id = match.get("event_id")

    if event_id is not None:
        return str(event_id).strip()

    return ""


# =========================================================
# EVENT NAME
# =========================================================

def get_event_name(match):

    if not isinstance(match, dict):
        return "Unknown Event"

    return str(
        match.get(
            "event_name",
            "Unknown Event"
        )
    ).strip()


# =========================================================
# SOURCE STATUS
# =========================================================

def get_source_status(match):

    if not isinstance(match, dict):
        return ""

    return str(
        match.get(
            "status",
            match.get(
                "match_status",
                ""
            )
        )
    ).strip().upper()


# =========================================================
# PARSE START TIME
# =========================================================

def parse_event_start_time(match):

    if not isinstance(match, dict):
        return None

    event_info = match.get("eventInfo")

    if not isinstance(event_info, dict):
        return None

    start_time = event_info.get("startTime")

    if not start_time:
        return None

    try:

        parsed = datetime.strptime(
            str(start_time).strip(),
            EVENT_TIME_FORMAT
        )

        return parsed.replace(
            tzinfo=BD_TIMEZONE
        )

    except (
        ValueError,
        TypeError
    ):

        return None


# =========================================================
# MANUAL REMOVE EVENT
# =========================================================

def remove_manual_events(
    matches,
    manual_control
):

    remove_events = manual_control.get(
        "remove_events",
        []
    )

    if not isinstance(
        remove_events,
        list
    ):
        return matches

    remove_ids = {
        str(event_id).strip()
        for event_id in remove_events
        if str(event_id).strip()
    }

    if not remove_ids:
        return matches

    original_count = len(matches)

    filtered = []

    for match in matches:

        event_id = get_event_id(match)

        if event_id in remove_ids:

            print(
                f"[REMOVE EVENT] "
                f"{get_event_name(match)} "
                f"(ID={event_id})"
            )

            continue

        filtered.append(match)

    removed_count = (
        original_count -
        len(filtered)
    )

    print(
        "Manual events removed:",
        removed_count
    )

    return filtered


# =========================================================
# MANUAL STATUS OVERRIDE
# =========================================================

def apply_status_override(
    match,
    manual_control
):

    event_id = get_event_id(match)

    if not event_id:
        return False

    overrides = manual_control.get(
        "status_override",
        {}
    )

    if not isinstance(
        overrides,
        dict
    ):
        return False

    if event_id not in overrides:
        return False

    status = str(
        overrides[event_id]
    ).strip().upper()

    if status not in {
        "LIVE",
        "UPCOMING",
        "ENDED"
    }:

        print(
            f"[WARNING] Invalid manual status "
            f"for {get_event_name(match)}: "
            f"{status}"
        )

        return False

    match["status"] = status

    print(
        f"[MANUAL STATUS] "
        f"{get_event_name(match)} "
        f"(ID={event_id}) "
        f"→ {status}"
    )

    return True


# =========================================================
# AUTOMATIC STATUS
# =========================================================

def update_match_status(
    match,
    now_bd,
    manual_control
):

    if not isinstance(match, dict):
        return "UPCOMING"

    event_name = get_event_name(match)

    source_status = get_source_status(match)

    # -----------------------------------------------------
    # MANUAL STATUS OVERRIDE
    # -----------------------------------------------------

    if apply_status_override(
        match,
        manual_control
    ):

        return match["status"]

    # -----------------------------------------------------
    # SOURCE ENDED
    # -----------------------------------------------------

    if source_status == "ENDED":

        match["status"] = "ENDED"

        print(
            f"[STATUS] {event_name} | "
            f"Source=ENDED | "
            f"Final=ENDED"
        )

        return "ENDED"

    # -----------------------------------------------------
    # START TIME
    # -----------------------------------------------------

    start_time = parse_event_start_time(
        match
    )

    # -----------------------------------------------------
    # INVALID / MISSING START TIME
    # -----------------------------------------------------

    if start_time is None:

        if source_status in {
            "LIVE",
            "INPLAY",
            "IN-PLAY",
            "ONGOING",
            "STARTED",
            "PLAYING"
        }:

            match["status"] = "LIVE"

            print(
                f"[STATUS] {event_name} | "
                f"Start=MISSING | "
                f"Source={source_status} | "
                f"Final=LIVE"
            )

            return "LIVE"

        if source_status in {
            "UPCOMING",
            "SCHEDULED",
            "NOT STARTED"
        }:

            match["status"] = "UPCOMING"

            print(
                f"[STATUS] {event_name} | "
                f"Start=MISSING | "
                f"Source={source_status} | "
                f"Final=UPCOMING"
            )

            return "UPCOMING"

        match["status"] = (
            source_status or
            "UPCOMING"
        )

        return match["status"]

    # -----------------------------------------------------
    # PREVIOUS DATE
    # -----------------------------------------------------

    if now_bd.date() > start_time.date():

        match["status"] = "ENDED"

        print(
            f"[STATUS] {event_name} | "
            f"Start={start_time} | "
            f"Now={now_bd} | "
            f"Final=ENDED"
        )

        return "ENDED"

    # -----------------------------------------------------
    # FUTURE DATE
    # -----------------------------------------------------

    if now_bd.date() < start_time.date():

        match["status"] = "UPCOMING"

        print(
            f"[STATUS] {event_name} | "
            f"Start={start_time} | "
            f"Now={now_bd} | "
            f"Final=UPCOMING"
        )

        return "UPCOMING"

    # -----------------------------------------------------
    # SAME DATE - BEFORE START
    # -----------------------------------------------------

    if now_bd < start_time:

        match["status"] = "UPCOMING"

        print(
            f"[STATUS] {event_name} | "
            f"Start={start_time} | "
            f"Now={now_bd} | "
            f"Final=UPCOMING"
        )

        return "UPCOMING"

    # -----------------------------------------------------
    # SAME DATE - STARTED
    # -----------------------------------------------------

    match["status"] = "LIVE"

    print(
        f"[STATUS] {event_name} | "
        f"Start={start_time} | "
        f"Now={now_bd} | "
        f"Final=LIVE"
    )

    return "LIVE"


# =========================================================
# UPDATE ALL STATUSES
# =========================================================

def update_all_match_statuses(
    matches,
    now_bd,
    manual_control
):

    live_count = 0
    upcoming_count = 0
    ended_count = 0

    for match in matches:

        status = update_match_status(
            match,
            now_bd,
            manual_control
        )

        if status == "LIVE":

            live_count += 1

        elif status == "UPCOMING":

            upcoming_count += 1

        elif status == "ENDED":

            ended_count += 1

    return (
        live_count,
        upcoming_count,
        ended_count
    )


# =========================================================
# REMOVE STREAMS
# =========================================================

def remove_manual_streams(
    matches,
    manual_control
):

    remove_streams = manual_control.get(
        "remove_streams",
        {}
    )

    if not isinstance(
        remove_streams,
        dict
    ):
        return 0

    removed_count = 0

    for match in matches:

        event_id = get_event_id(match)

        if not event_id:
            continue

        stream_names = remove_streams.get(
            event_id,
            []
        )

        if not isinstance(
            stream_names,
            list
        ):
            continue

        stream_names_set = {
            str(name).strip().lower()
            for name in stream_names
        }

        if not stream_names_set:
            continue

        streams = match.get(
            "streams",
            []
        )

        if not isinstance(
            streams,
            list
        ):
            continue

        new_streams = []

        for stream in streams:

            if not isinstance(
                stream,
                dict
            ):

                new_streams.append(stream)
                continue

            channel_name = str(
                stream.get(
                    "channel_name",
                    ""
                )
            ).strip().lower()

            if channel_name in stream_names_set:

                print(
                    f"[REMOVE STREAM] "
                    f"{get_event_name(match)} | "
                    f"{channel_name}"
                )

                removed_count += 1

                continue

            new_streams.append(stream)

        match["streams"] = new_streams

    return removed_count


# =========================================================
# ADD STREAMS
# =========================================================

def add_manual_streams(
    matches,
    manual_control
):

    add_streams = manual_control.get(
        "add_streams",
        {}
    )

    if not isinstance(
        add_streams,
        dict
    ):
        return 0

    added_count = 0

    for match in matches:

        event_id = get_event_id(match)

        if not event_id:
            continue

        streams_to_add = add_streams.get(
            event_id,
            []
        )

        if not isinstance(
            streams_to_add,
            list
        ):
            continue

        if not streams_to_add:
            continue

        if not isinstance(
            match.get("streams"),
            list
        ):

            match["streams"] = []

        existing_streams = match["streams"]

        # Existing channel names
        existing_names = {
            str(
                stream.get(
                    "channel_name",
                    ""
                )
            ).strip().lower()

            for stream in existing_streams

            if isinstance(
                stream,
                dict
            )
        }

        for stream in streams_to_add:

            if not isinstance(
                stream,
                dict
            ):
                continue

            channel_name = str(
                stream.get(
                    "channel_name",
                    ""
                )
            ).strip()

            stream_url = str(
                stream.get(
                    "stream_url",
                    ""
                )
            ).strip()

            if not channel_name:

                print(
                    "[WARNING] Manual stream "
                    "without channel_name skipped."
                )

                continue

            if not stream_url:

                print(
                    f"[WARNING] Manual stream "
                    f"{channel_name} has empty URL. "
                    f"Skipped."
                )

                continue

            name_key = channel_name.lower()

            # Prevent duplicate channel
            if name_key in existing_names:

                print(
                    f"[MANUAL STREAM EXISTS] "
                    f"{get_event_name(match)} | "
                    f"{channel_name}"
                )

                continue

            existing_streams.append(
                deepcopy(stream)
            )

            existing_names.add(
                name_key
            )

            added_count += 1

            print(
                f"[ADD STREAM] "
                f"{get_event_name(match)} | "
                f"{channel_name}"
            )

    return added_count


# =========================================================
# ADD NEW EVENTS
# =========================================================

def add_manual_events(
    matches,
    manual_control
):

    add_events = manual_control.get(
        "add_events",
        []
    )

    if not isinstance(
        add_events,
        list
    ):
        return 0

    existing_ids = {
        get_event_id(match)
        for match in matches
        if get_event_id(match)
    }

    added_count = 0

    for event in add_events:

        if not isinstance(
            event,
            dict
        ):
            continue

        event_id = get_event_id(
            event
        )

        if not event_id:

            print(
                "[WARNING] Manual event "
                "without id skipped."
            )

            continue

        if event_id in existing_ids:

            print(
                f"[MANUAL EVENT EXISTS] "
                f"{get_event_name(event)} "
                f"(ID={event_id})"
            )

            continue

        # Ensure streams exists
        if not isinstance(
            event.get("streams"),
            list
        ):

            event["streams"] = []

        matches.append(
            deepcopy(event)
        )

        existing_ids.add(
            event_id
        )

        added_count += 1

        print(
            f"[ADD EVENT] "
            f"{get_event_name(event)} "
            f"(ID={event_id})"
        )

    return added_count


# =========================================================
# DRM CONVERSION
# =========================================================

def convert_drm_keys(data):

    matches = find_matches(data)

    converted_count = 0

    for match in matches:

        if not isinstance(
            match,
            dict
        ):
            continue

        streams = match.get(
            "streams",
            []
        )

        if not isinstance(
            streams,
            list
        ):
            continue

        for stream in streams:

            if not isinstance(
                stream,
                dict
            ):
                continue

            kid = stream.get("kid")
            key = stream.get("key")

            if (
                kid is not None
                and
                key is not None
            ):

                kid = str(kid).strip()
                key = str(key).strip()

                if kid and key:

                    stream["drm_key"] = (
                        f"{kid}:{key}"
                    )

                    stream.pop(
                        "kid",
                        None
                    )

                    stream.pop(
                        "key",
                        None
                    )

                    converted_count += 1

    return converted_count


# =========================================================
# MAIN
# =========================================================

def main():

    output_file = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "sports_data.json"
    )

    now_bd = datetime.now(
        BD_TIMEZONE
    )

    print("=" * 70)

    print(
        "SPORTS DATA UPDATE START"
    )

    print(
        "Bangladesh Time:",
        now_bd.strftime(
            "%d/%m/%Y %I:%M:%S %p"
        )
    )

    print("=" * 70)

    try:

        # -------------------------------------------------
        # 1. Fetch Main API
        # -------------------------------------------------

        data = fetch_data()

        print(
            "Main API fetched successfully."
        )

        # -------------------------------------------------
        # 2. Load Manual Control
        # -------------------------------------------------

        manual_control = (
            load_manual_control()
        )

        print(
            "Manual control loaded."
        )

        # -------------------------------------------------
        # 3. Find Main API matches
        # -------------------------------------------------

        matches = find_matches(
            data
        )

        print(
            "Main API matches:",
            len(matches)
        )

        # -------------------------------------------------
        # 4. Remove unwanted events
        # -------------------------------------------------

        matches = remove_manual_events(
            matches,
            manual_control
        )

        # -------------------------------------------------
        # 5. Add manual new events
        # -------------------------------------------------

        manual_added_events = (
            add_manual_events(
                matches,
                manual_control
            )
        )

        # -------------------------------------------------
        # 6. Remove manual streams
        # -------------------------------------------------

        removed_streams = (
            remove_manual_streams(
                matches,
                manual_control
            )
        )

        # -------------------------------------------------
        # 7. Add manual streams
        # -------------------------------------------------

        added_streams = (
            add_manual_streams(
                matches,
                manual_control
            )
        )

        # -------------------------------------------------
        # 8. Update status
        # -------------------------------------------------

        (
            live_count,
            upcoming_count,
            ended_count
        ) = update_all_match_statuses(
            matches,
            now_bd,
            manual_control
        )

        # -------------------------------------------------
        # 9. DRM conversion
        # -------------------------------------------------

        drm_count = convert_drm_keys(
            data
        )

        # -------------------------------------------------
        # 10. Top-level information
        # -------------------------------------------------

        if isinstance(
            data,
            dict
        ):

            data["matches"] = matches

            data["total_matches"] = (
                len(matches)
            )

            data["live_match"] = (
                live_count
            )

            data["last_update_time"] = (
                now_bd.strftime(
                    "%I:%M:%S %p %d-%m-%Y"
                )
            )

        # -------------------------------------------------
        # 11. Save final JSON
        # -------------------------------------------------

        with open(
            output_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

            f.write("\n")

        # -------------------------------------------------
        # 12. Final log
        # -------------------------------------------------

        print()
        print("=" * 70)
        print("FINAL SUMMARY")
        print("=" * 70)

        print(
            "Total matches:",
            len(matches)
        )

        print(
            "LIVE:",
            live_count
        )

        print(
            "UPCOMING:",
            upcoming_count
        )

        print(
            "ENDED:",
            ended_count
        )

        print(
            "Manual events added:",
            manual_added_events
        )

        print(
            "Manual streams added:",
            added_streams
        )

        print(
            "Manual streams removed:",
            removed_streams
        )

        print(
            "DRM converted:",
            drm_count
        )

        print(
            "Output:",
            output_file
        )

        print("=" * 70)
        print(
            "SPORTS DATA UPDATE SUCCESS"
        )
        print("=" * 70)

        return 0

    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
        RuntimeError
    ) as exc:

        print(
            f"ERROR: {exc}",
            file=sys.stderr
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
