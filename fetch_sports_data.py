#!/usr/bin/env python3

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "sm-monirulislam/Upcoming-and-Live-Sports-Data/"
    "refs/heads/main/Sports_data.json"
)

# Bangladesh Time
BD_TIMEZONE = ZoneInfo("Asia/Dhaka")

# Source event time format
EVENT_TIME_FORMAT = "%d/%m/%Y %I:%M:%S %p"


def fetch_data():
    req = Request(
        SOURCE_URL,
        headers={
            "User-Agent": "sports-data-fetcher/1.0"
        }
    )

    with urlopen(req, timeout=30) as response:
        return json.load(response)


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
            if isinstance(data.get(key), list):
                return data[key]

    return []


def get_source_status(match):
    """
    Get original status from source API.
    """

    if not isinstance(match, dict):
        return ""

    return str(
        match.get(
            "status",
            match.get("match_status", "")
        )
    ).strip().upper()


def parse_event_start_time(match):
    """
    Read eventInfo.startTime.

    Expected:
        14/09/2026 05:00:00 AM

    Returns Bangladesh timezone datetime.
    """

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

    except (ValueError, TypeError):
        return None


def update_match_status(match, now_bd):
    """
    Final status logic:

    1. Source ENDED -> ENDED

    2. Event date already passed -> ENDED

    3. Same day but start time not reached -> UPCOMING

    4. Start time reached -> LIVE
    """

    if not isinstance(match, dict):
        return "UPCOMING"

    event_name = str(
        match.get("event_name", "Unknown Event")
    ).strip()

    source_status = get_source_status(match)

    start_time = parse_event_start_time(match)

    # --------------------------------------------------
    # SOURCE ENDED HAS HIGHEST PRIORITY
    # --------------------------------------------------
    if source_status == "ENDED":

        match["status"] = "ENDED"

        print(
            f"[STATUS] {event_name} | "
            f"Source={source_status} | "
            f"Start={start_time} | "
            f"Now={now_bd} | "
            f"Final=ENDED"
        )

        return "ENDED"

    # --------------------------------------------------
    # If startTime is missing or invalid,
    # use source status safely.
    # --------------------------------------------------
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
                f"Source={source_status} | "
                f"Start=INVALID/MISSING | "
                f"Now={now_bd} | "
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
                f"Source={source_status} | "
                f"Start=INVALID/MISSING | "
                f"Now={now_bd} | "
                f"Final=UPCOMING"
            )

            return "UPCOMING"

        match["status"] = source_status or "UPCOMING"

        print(
            f"[STATUS] {event_name} | "
            f"Source={source_status or 'EMPTY'} | "
            f"Start=INVALID/MISSING | "
            f"Now={now_bd} | "
            f"Final={match['status']}"
        )

        return match["status"]

    # --------------------------------------------------
    # EVENT DATE ALREADY PASSED
    #
    # Example:
    #
    # Event = 04/09/2026
    # Today = 14/09/2026
    #
    # Result = ENDED
    # --------------------------------------------------
    if now_bd.date() > start_time.date():

        match["status"] = "ENDED"

        print(
            f"[STATUS] {event_name} | "
            f"Source={source_status or 'EMPTY'} | "
            f"Start={start_time} | "
            f"Now={now_bd} | "
            f"Final=ENDED"
        )

        return "ENDED"

    # --------------------------------------------------
    # FUTURE DATE
    # --------------------------------------------------
    if now_bd.date() < start_time.date():

        match["status"] = "UPCOMING"

        print(
            f"[STATUS] {event_name} | "
            f"Source={source_status or 'EMPTY'} | "
            f"Start={start_time} | "
            f"Now={now_bd} | "
            f"Final=UPCOMING"
        )

        return "UPCOMING"

    # --------------------------------------------------
    # SAME DATE
    #
    # Before start = UPCOMING
    # At/after start = LIVE
    # --------------------------------------------------
    if now_bd < start_time:

        match["status"] = "UPCOMING"

        print(
            f"[STATUS] {event_name} | "
            f"Source={source_status or 'EMPTY'} | "
            f"Start={start_time} | "
            f"Now={now_bd} | "
            f"Final=UPCOMING"
        )

        return "UPCOMING"

    # --------------------------------------------------
    # START TIME REACHED
    # --------------------------------------------------
    match["status"] = "LIVE"

    print(
        f"[STATUS] {event_name} | "
        f"Source={source_status or 'EMPTY'} | "
        f"Start={start_time} | "
        f"Now={now_bd} | "
        f"Final=LIVE"
    )

    return "LIVE"


def update_all_match_statuses(matches, now_bd):
    """
    Recalculate every match using
    the SAME Bangladesh current time.
    """

    live_count = 0
    upcoming_count = 0
    ended_count = 0

    for match in matches:

        status = update_match_status(
            match,
            now_bd
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


def convert_drm_keys(data):
    """
    Convert:

        kid + key

    into:

        drm_key = kid:key

    DRM ছাড়া streams-এর কোনো data পরিবর্তন করা হবে না.
    """

    matches = find_matches(data)

    converted_count = 0

    for match in matches:

        if not isinstance(match, dict):
            continue

        streams = match.get("streams", [])

        if not isinstance(streams, list):
            continue

        for stream in streams:

            if not isinstance(stream, dict):
                continue

            kid = stream.get("kid")
            key = stream.get("key")

            # Only convert when BOTH exist
            if kid is not None and key is not None:

                kid = str(kid).strip()
                key = str(key).strip()

                if kid and key:

                    stream["drm_key"] = f"{kid}:{key}"

                    stream.pop("kid", None)
                    stream.pop("key", None)

                    converted_count += 1

    return converted_count


def main():

    output_file = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "sports_data.json"
    )

    # One fixed Bangladesh time for this entire run
    now_bd = datetime.now(BD_TIMEZONE)

    print("=" * 70)
    print("SPORTS DATA FETCH START")
    print(
        "Bangladesh Time:",
        now_bd.strftime("%d/%m/%Y %I:%M:%S %p")
    )
    print("=" * 70)

    try:

        # --------------------------------------------------
        # 1. Fetch latest source API
        # --------------------------------------------------
        data = fetch_data()

        print("Source API fetched successfully.")

        # --------------------------------------------------
        # 2. Find matches
        # --------------------------------------------------
        matches = find_matches(data)

        print(
            "Source matches found:",
            len(matches)
        )

        # --------------------------------------------------
        # 3. Update status
        # --------------------------------------------------
        (
            live_count,
            upcoming_count,
            ended_count
        ) = update_all_match_statuses(
            matches,
            now_bd
        )

        # --------------------------------------------------
        # 4. Convert DRM
        # --------------------------------------------------
        drm_count = convert_drm_keys(data)

        # --------------------------------------------------
        # 5. Update top-level information
        # --------------------------------------------------
        if isinstance(data, dict):

            data["total_matches"] = len(matches)

            data["live_match"] = live_count

            data["last_update_time"] = now_bd.strftime(
                "%I:%M:%S %p %d-%m-%Y"
            )

        # --------------------------------------------------
        # 6. Save final JSON
        # --------------------------------------------------
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

        # --------------------------------------------------
        # 7. Final summary
        # --------------------------------------------------
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
            "DRM converted:",
            drm_count
        )

        print(
            "Output file:",
            output_file
        )

        print("=" * 70)
        print("SPORTS DATA UPDATE SUCCESS")
        print("=" * 70)

        return 0

    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
        OSError
    ) as exc:

        print(
            f"ERROR: {exc}",
            file=sys.stderr
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
