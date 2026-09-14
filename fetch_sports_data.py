#!/usr/bin/env python3

import json
import sys
from datetime import datetime, timezone
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

    Expected format:

        14/09/2026 05:00:00 AM

    Returns timezone-aware Bangladesh datetime.
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

    1. If source says ENDED:
           ENDED

    2. If event date is already over:
           ENDED

    3. If start time has not arrived:
           UPCOMING

    4. If start time has arrived:
           LIVE
    """

    if not isinstance(match, dict):
        return "UPCOMING"

    source_status = get_source_status(match)

    # --------------------------------------------------
    # Priority 1:
    # If main/source API explicitly says ENDED,
    # always keep it ENDED.
    # --------------------------------------------------
    if source_status == "ENDED":
        match["status"] = "ENDED"
        return "ENDED"

    # --------------------------------------------------
    # Get event start time
    # --------------------------------------------------
    start_time = parse_event_start_time(match)

    # --------------------------------------------------
    # If start time cannot be parsed,
    # safely use source status.
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
            return "LIVE"

        if source_status in {
            "UPCOMING",
            "SCHEDULED",
            "NOT STARTED"
        }:
            match["status"] = "UPCOMING"
            return "UPCOMING"

        # Unknown status fallback
        match["status"] = source_status or "UPCOMING"

        return match["status"]

    # --------------------------------------------------
    # Event date is already finished.
    #
    # Example:
    #
    # Event = 14/09/2026
    # Today = 15/09/2026
    #
    # Automatically ENDED.
    # --------------------------------------------------
    if now_bd.date() > start_time.date():

        match["status"] = "ENDED"

        return "ENDED"

    # --------------------------------------------------
    # Same date:
    #
    # Before start time = UPCOMING
    # Start time reached = LIVE
    # --------------------------------------------------
    if now_bd < start_time:

        match["status"] = "UPCOMING"

        return "UPCOMING"

    # Start time has arrived
    match["status"] = "LIVE"

    return "LIVE"


def update_all_match_statuses(matches):
    """
    Recalculate status for every match
    using Bangladesh current time.
    """

    now_bd = datetime.now(BD_TIMEZONE)

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

    Example:

        "kid": "abc",
        "key": "123"

    becomes:

        "drm_key": "abc:123"

    DRM ছাড়া streams কোনোভাবেই পরিবর্তন হবে না.
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

            # Get kid and key
            kid = stream.get("kid")
            key = stream.get("key")

            # Convert only when BOTH exist
            if kid is not None and key is not None:

                kid = str(kid).strip()
                key = str(key).strip()

                if kid and key:

                    # Create combined DRM key
                    stream["drm_key"] = f"{kid}:{key}"

                    # Remove old fields
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

    now_bd = datetime.now(BD_TIMEZONE)

    print(
        "Fetch start time (Bangladesh):",
        now_bd.isoformat(timespec="seconds")
    )

    try:

        # -----------------------------------------
        # 1. Fetch original source JSON
        # -----------------------------------------
        data = fetch_data()

        # -----------------------------------------
        # 2. Find matches
        # -----------------------------------------
        matches = find_matches(data)

        # -----------------------------------------
        # 3. Update match status using time
        # -----------------------------------------
        (
            live_count,
            upcoming_count,
            ended_count
        ) = update_all_match_statuses(matches)

        # -----------------------------------------
        # 4. Convert DRM
        # -----------------------------------------
        drm_count = convert_drm_keys(data)

        # -----------------------------------------
        # 5. Update top-level statistics
        # -----------------------------------------
        if isinstance(data, dict):

            data["total_matches"] = len(matches)

            data["live_match"] = live_count

            data["last_update_time"] = now_bd.strftime(
                "%I:%M:%S %p %d-%m-%Y"
            )

        # -----------------------------------------
        # 6. Save final JSON
        # -----------------------------------------
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

        # -----------------------------------------
        # 7. GitHub Actions log
        # -----------------------------------------
        print(
            "Total number of matches:",
            len(matches)
        )

        print(
            "Live matches:",
            live_count
        )

        print(
            "Upcoming matches:",
            upcoming_count
        )

        print(
            "Ended matches:",
            ended_count
        )

        print(
            "DRM streams converted:",
            drm_count
        )

        print(
            "Successfully saved data to:",
            output_file
        )

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
