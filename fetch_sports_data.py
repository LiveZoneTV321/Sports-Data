#!/usr/bin/env python3

import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ============================================================
# CONFIG
# ============================================================

SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "sm-monirulislam/Upcoming-and-Live-Sports-Data/"
    "refs/heads/main/Sports_data.json"
)

MANUAL_CONTROL_FILE = "manual_control.json"

BD_TIMEZONE = ZoneInfo("Asia/Dhaka")

EVENT_TIME_FORMAT = "%d/%m/%Y %I:%M:%S %p"


# ============================================================
# FETCH MAIN API
# ============================================================

def fetch_data():

    print()
    print("=" * 70)
    print("FETCHING MAIN API")
    print("=" * 70)

    print("Source URL:")
    print(SOURCE_URL)

    req = Request(
        SOURCE_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36"
            )
        },
        method="GET"
    )

    try:

        with urlopen(
            req,
            timeout=30
        ) as response:

            status_code = response.getcode()

            print(
                "HTTP Status:",
                status_code
            )

            raw_data = response.read()

            print(
                "Response bytes:",
                len(raw_data)
            )

            if not raw_data:

                raise RuntimeError(
                    "Main API returned EMPTY response."
                )

            try:

                text = raw_data.decode(
                    "utf-8-sig"
                )

            except UnicodeDecodeError as exc:

                raise RuntimeError(
                    f"Failed to decode API response: {exc}"
                ) from exc

            try:

                data = json.loads(
                    text
                )

            except json.JSONDecodeError as exc:

                print()
                print(
                    "API response is NOT valid JSON."
                )

                print(
                    "First 500 characters:"
                )

                print(
                    repr(
                        text[:500]
                    )
                )

                raise RuntimeError(
                    f"Invalid JSON from Main API: {exc}"
                ) from exc

            print(
                "Main API JSON loaded successfully."
            )

            if isinstance(
                data,
                dict
            ):

                print(
                    "Top-level keys:",
                    list(data.keys())
                )

            elif isinstance(
                data,
                list
            ):

                print(
                    "API returned a list."
                )

            else:

                raise RuntimeError(
                    "Main API returned unsupported JSON type."
                )

            print("=" * 70)
            print()

            return data

    except HTTPError as exc:

        print()
        print("=" * 70)
        print("HTTP ERROR")
        print("=" * 70)

        print(
            "Status:",
            exc.code
        )

        print(
            "Reason:",
            exc.reason
        )

        print(
            "URL:",
            SOURCE_URL
        )

        print("=" * 70)

        raise

    except URLError as exc:

        print()
        print("=" * 70)
        print("URL ERROR")
        print("=" * 70)

        print(
            "Reason:",
            exc.reason
        )

        print(
            "URL:",
            SOURCE_URL
        )

        print("=" * 70)

        raise

    except TimeoutError:

        print()
        print("=" * 70)
        print("TIMEOUT ERROR")
        print("=" * 70)

        print(
            "Main API did not respond within 30 seconds."
        )

        print("=" * 70)

        raise


# ============================================================
# FIND MATCHES
# ============================================================

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


# ============================================================
# TEXT NORMALIZER
# ============================================================

def normalize_text(value):
    if value is None:
        return ""

    value = str(value).strip().lower()

    # Remove extra spaces
    value = re.sub(r"\s+", " ", value)

    # Normalize common Vs variations
    value = re.sub(
        r"\s+vs\.?\s+",
        " vs ",
        value
    )

    # Remove punctuation
    value = re.sub(
        r"[^a-z0-9\s]",
        "",
        value
    )

    # Remove duplicate spaces again
    value = re.sub(
        r"\s+",
        " ",
        value
    ).strip()

    return value


# ============================================================
# AUTO EVENT ID
# ============================================================

def generate_event_id(match):
    """
    Main API তে id না থাকলেও এখানে automatically
    stable deterministic ID তৈরি হবে।

    Primary identity:
        Category
        teamA
        teamB
        eventName

    Fallback:
        category
        event_name
        startTime
    """

    if not isinstance(match, dict):
        return "evt_unknown"

    category = normalize_text(
        match.get(
            "Category",
            match.get(
                "category",
                ""
            )
        )
    )

    event_name = normalize_text(
        match.get(
            "event_name",
            match.get(
                "eventName",
                ""
            )
        )
    )

    event_info = match.get(
        "eventInfo",
        {}
    )

    if not isinstance(
        event_info,
        dict
    ):
        event_info = {}

    team_a = normalize_text(
        event_info.get(
            "teamA",
            ""
        )
    )

    team_b = normalize_text(
        event_info.get(
            "teamB",
            ""
        )
    )

    tournament_name = normalize_text(
        event_info.get(
            "eventName",
            ""
        )
    )

    start_time = normalize_text(
        event_info.get(
            "startTime",
            ""
        )
    )

    # --------------------------------------------------------
    # Primary identity
    # --------------------------------------------------------

    identity_parts = [
        category,
        team_a,
        team_b,
        tournament_name
    ]

    identity = "|".join(
        part
        for part in identity_parts
        if part
    )

    # --------------------------------------------------------
    # Fallback identity
    # --------------------------------------------------------

    if not identity:
        identity = "|".join(
            part
            for part in [
                category,
                event_name,
                start_time
            ]
            if part
        )

    if not identity:
        identity = "unknown_event"

    # --------------------------------------------------------
    # SHA256 short ID
    # --------------------------------------------------------

    hash_id = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:12]

    return f"evt_{hash_id}"


# ============================================================
# ASSIGN IDS TO ALL EVENTS
# ============================================================

def assign_event_ids(matches):
    used_ids = set()
    generated_count = 0

    for match in matches:

        if not isinstance(
            match,
            dict
        ):
            continue

        existing_id = match.get(
            "id"
        )

        if existing_id:

            event_id = str(
                existing_id
            ).strip()

        else:

            event_id = generate_event_id(
                match
            )

            generated_count += 1

        # ----------------------------------------------------
        # Duplicate protection
        # ----------------------------------------------------

        original_id = event_id
        counter = 2

        while event_id in used_ids:

            event_id = (
                f"{original_id}_{counter}"
            )

            counter += 1

        match["id"] = event_id

        used_ids.add(
            event_id
        )

    return generated_count


# ============================================================
# EVENT NAME
# ============================================================

def get_event_name(match):

    if not isinstance(
        match,
        dict
    ):
        return "Unknown Event"

    return str(
        match.get(
            "event_name",
            match.get(
                "eventName",
                "Unknown Event"
            )
        )
    ).strip()


# ============================================================
# SOURCE STATUS
# ============================================================

def get_source_status(match):

    if not isinstance(
        match,
        dict
    ):
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


# ============================================================
# START TIME PARSER
# ============================================================

def parse_event_start_time(match):

    if not isinstance(
        match,
        dict
    ):
        return None

    event_info = match.get(
        "eventInfo"
    )

    if not isinstance(
        event_info,
        dict
    ):
        return None

    start_time = event_info.get(
        "startTime"
    )

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


# ============================================================
# MANUAL CONTROL LOADER
# ============================================================

def load_manual_control():

    try:

        with open(
            MANUAL_CONTROL_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(
            data,
            dict
        ):
            return {}

        return data

    except FileNotFoundError:

        print(
            f"[MANUAL] "
            f"{MANUAL_CONTROL_FILE} not found. "
            "Using empty manual control."
        )

        return {}

    except json.JSONDecodeError as exc:

        print(
            f"[MANUAL] Invalid JSON in "
            f"{MANUAL_CONTROL_FILE}: {exc}"
        )

        return {}


# ============================================================
# STATUS OVERRIDE
# ============================================================

def apply_status_override(
    match,
    manual_control
):

    if not isinstance(
        match,
        dict
    ):
        return False

    event_id = str(
        match.get(
            "id",
            ""
        )
    ).strip()

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

    new_status = str(
        overrides[event_id]
    ).strip().upper()

    if not new_status:
        return False

    match["status"] = new_status

    print(
        f"[MANUAL STATUS] "
        f"{event_id} | "
        f"{get_event_name(match)} | "
        f"Status={new_status}"
    )

    return True


# ============================================================
# UPDATE MATCH STATUS
# ============================================================

def update_match_status(
    match,
    now_bd,
    manual_control
):

    if not isinstance(
        match,
        dict
    ):
        return "UPCOMING"

    event_name = get_event_name(
        match
    )

    source_status = get_source_status(
        match
    )

    # --------------------------------------------------------
    # 1. MANUAL STATUS OVERRIDE
    # Highest priority
    # --------------------------------------------------------

    if apply_status_override(
        match,
        manual_control
    ):

        return match["status"]


    # --------------------------------------------------------
    # 2. SOURCE SAYS ENDED
    # --------------------------------------------------------

    if source_status == "ENDED":

        match["status"] = "ENDED"

        print(
            f"[STATUS] "
            f"{event_name} | "
            f"Source=ENDED | "
            f"Final=ENDED"
        )

        return "ENDED"


    # --------------------------------------------------------
    # 3. PARSE EVENT START TIME
    # --------------------------------------------------------

    start_time = parse_event_start_time(
        match
    )


    # --------------------------------------------------------
    # 4. NO START TIME
    # --------------------------------------------------------

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


        match["status"] = (
            source_status
            or "UPCOMING"
        )

        return match["status"]


    # --------------------------------------------------------
    # 5. BEFORE START TIME = UPCOMING
    # --------------------------------------------------------

    if now_bd < start_time:

        match["status"] = "UPCOMING"

        return "UPCOMING"


    # --------------------------------------------------------
    # 6. START TIME REACHED = LIVE
    #
    # Midnight/date change হলেও ENDED হবে না.
    #
    # Source API ENDED না বলা পর্যন্ত LIVE থাকবে.
    # অথবা manual_control এ ENDED দেওয়া হলে ENDED হবে.
    # --------------------------------------------------------

    match["status"] = "LIVE"

    return "LIVE"


# ============================================================
# UPDATE ALL STATUSES
# ============================================================

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


# ============================================================
# SORT EVENTS BY STATUS
# ============================================================

def sort_matches_by_status(matches):
    """
    Final event order:

    LIVE     -> first
    UPCOMING -> second
    ENDED    -> last
    """

    status_order = {
        "LIVE": 0,
        "UPCOMING": 1,
        "ENDED": 2
    }

    return sorted(
        matches,
        key=lambda match: status_order.get(
            str(
                match.get(
                    "status",
                    ""
                )
            ).strip().upper(),
            1
        )
    )


# ============================================================
# REMOVE EVENTS
# ============================================================

def remove_manual_events(
    matches,
    manual_control
):

    remove_ids = manual_control.get(
        "remove_events",
        []
    )

    if not isinstance(
        remove_ids,
        list
    ):
        return matches, 0

    remove_ids = {
        str(event_id).strip()
        for event_id in remove_ids
        if str(event_id).strip()
    }

    if not remove_ids:

        return matches, 0

    original_count = len(
        matches
    )

    matches = [
        match
        for match in matches
        if not (
            isinstance(
                match,
                dict
            )
            and str(
                match.get(
                    "id",
                    ""
                )
            ).strip()
            in remove_ids
        )
    ]

    removed_count = (
        original_count
        - len(matches)
    )

    if removed_count:

        print(
            f"[MANUAL] "
            f"Events removed: "
            f"{removed_count}"
        )

    return (
        matches,
        removed_count
    )


# ============================================================
# REMOVE STREAMS
# ============================================================

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

        if not isinstance(
            match,
            dict
        ):
            continue

        event_id = str(
            match.get(
                "id",
                ""
            )
        ).strip()

        if event_id not in remove_streams:

            continue

        stream_names = (
            remove_streams[event_id]
        )

        if not isinstance(
            stream_names,
            list
        ):
            continue

        stream_names = {
            str(name).strip().lower()
            for name in stream_names
            if str(name).strip()
        }

        streams = match.get(
            "streams",
            []
        )

        if not isinstance(
            streams,
            list
        ):
            continue

        original_count = len(
            streams
        )

        match["streams"] = [
            stream
            for stream in streams
            if not (
                isinstance(
                    stream,
                    dict
                )
                and str(
                    stream.get(
                        "channel_name",
                        stream.get(
                            "channelName",
                            ""
                        )
                    )
                ).strip().lower()
                in stream_names
            )
        ]

        removed_count += (
            original_count
            - len(
                match["streams"]
            )
        )

    if removed_count:

        print(
            f"[MANUAL] "
            f"Streams removed: "
            f"{removed_count}"
        )

    return removed_count


# ============================================================
# ADD MANUAL STREAMS
# ============================================================

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

        if not isinstance(
            match,
            dict
        ):
            continue

        event_id = str(
            match.get(
                "id",
                ""
            )
        ).strip()

        if event_id not in add_streams:

            continue

        new_streams = (
            add_streams[event_id]
        )

        if not isinstance(
            new_streams,
            list
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
            streams = []

        existing_names = {
            str(
                stream.get(
                    "channel_name",
                    stream.get(
                        "channelName",
                        ""
                    )
                )
            ).strip().lower()
            for stream in streams
            if isinstance(
                stream,
                dict
            )
        }

        for new_stream in new_streams:

            if not isinstance(
                new_stream,
                dict
            ):
                continue

            channel_name = str(
                new_stream.get(
                    "channel_name",
                    ""
                )
            ).strip()

            stream_url = str(
                new_stream.get(
                    "stream_url",
                    ""
                )
            ).strip()

            # ------------------------------------------------
            # Empty URL add হবে না
            # ------------------------------------------------

            if not channel_name:

                continue

            if not stream_url:

                print(
                    f"[MANUAL] "
                    f"Skipped empty URL: "
                    f"{channel_name}"
                )

                continue

            # ------------------------------------------------
            # Duplicate stream name
            # ------------------------------------------------

            if (
                channel_name.lower()
                in existing_names
            ):

                print(
                    f"[MANUAL] "
                    f"Stream already exists: "
                    f"{channel_name}"
                )

                continue

            streams.append(
                copy.deepcopy(
                    new_stream
                )
            )

            existing_names.add(
                channel_name.lower()
            )

            added_count += 1

            print(
                f"[MANUAL] "
                f"Stream added | "
                f"{event_id} | "
                f"{channel_name}"
            )

        match["streams"] = streams

    return added_count


# ============================================================
# REMOVE EMPTY STREAM URLs
# ============================================================

def remove_empty_stream_urls(
    matches
):

    removed_count = 0

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

        valid_streams = []

        for stream in streams:

            if not isinstance(
                stream,
                dict
            ):
                continue

            stream_url = str(
                stream.get(
                    "stream_url",
                    ""
                )
            ).strip()

            # ------------------------------------------------
            # Empty URL বাদ যাবে
            # ------------------------------------------------

            if not stream_url:

                removed_count += 1

                print(
                    f"[AUTO REMOVE] "
                    f"Empty stream URL | "
                    f"{get_event_name(match)} | "
                    f"{stream.get(
                        'channel_name',
                        'Unknown Stream'
                    )}"
                )

                continue

            valid_streams.append(
                stream
            )

        match["streams"] = (
            valid_streams
        )

    return removed_count


# ============================================================
# ADD MANUAL EVENTS
# ============================================================

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
        str(
            match.get(
                "id",
                ""
            )
        ).strip()
        for match in matches
        if isinstance(
            match,
            dict
        )
    }

    added_count = 0

    for event in add_events:

        if not isinstance(
            event,
            dict
        ):
            continue

        event = copy.deepcopy(
            event
        )

        event_id = str(
            event.get(
                "id",
                ""
            )
        ).strip()

        # ----------------------------------------------------
        # Manual ID না দিলে auto generate
        # ----------------------------------------------------

        if not event_id:

            event_id = generate_event_id(
                event
            )

        original_id = event_id
        counter = 2

        while event_id in existing_ids:

            event_id = (
                f"{original_id}_manual_{counter}"
            )

            counter += 1

        event["id"] = event_id

        # ----------------------------------------------------
        # Streams ensure list
        # ----------------------------------------------------

        streams = event.get(
            "streams",
            []
        )

        if not isinstance(
            streams,
            list
        ):

            event["streams"] = []

        matches.append(
            event
        )

        existing_ids.add(
            event_id
        )

        added_count += 1

        print(
            f"[MANUAL] "
            f"Event added | "
            f"{event_id} | "
            f"{get_event_name(event)}"
        )

    return added_count


# ============================================================
# DRM KEY CONVERSION
# ============================================================

def convert_drm_keys(data):

    matches = find_matches(
        data
    )

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

            kid = stream.get(
                "kid"
            )

            key = stream.get(
                "key"
            )

            if (
                kid is not None
                and key is not None
            ):

                kid = str(
                    kid
                ).strip()

                key = str(
                    key
                ).strip()

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


# ============================================================
# MAIN
# ============================================================

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

        # ----------------------------------------------------
        # FETCH SOURCE
        # ----------------------------------------------------

        data = fetch_data()

        print(
            "Main API fetched successfully."
        )

        matches = find_matches(
            data
        )

        print(
            "Main API matches:",
            len(matches)
        )


        # ----------------------------------------------------
        # AUTO GENERATE EVENT IDS
        # ----------------------------------------------------

        generated_ids = assign_event_ids(
            matches
        )

        print(
            "Auto generated IDs:",
            generated_ids
        )


        # ----------------------------------------------------
        # LOAD MANUAL CONTROL
        # ----------------------------------------------------

        manual_control = (
            load_manual_control()
        )


        # ----------------------------------------------------
        # REMOVE EVENTS
        # ----------------------------------------------------

        (
            matches,
            removed_events
        ) = remove_manual_events(
            matches,
            manual_control
        )


        # ----------------------------------------------------
        # REMOVE STREAMS
        # ----------------------------------------------------

        removed_streams = (
            remove_manual_streams(
                matches,
                manual_control
            )
        )


        # ----------------------------------------------------
        # ADD STREAMS
        # ----------------------------------------------------

        added_streams = (
            add_manual_streams(
                matches,
                manual_control
            )
        )


        # ----------------------------------------------------
        # ADD NEW EVENTS
        # ----------------------------------------------------

        added_events = (
            add_manual_events(
                matches,
                manual_control
            )
        )


        # ----------------------------------------------------
        # REMOVE EMPTY STREAM URLs
        # ----------------------------------------------------

        empty_streams_removed = (
            remove_empty_stream_urls(
                matches
            )
        )


        # ----------------------------------------------------
        # RE-ASSIGN IDS AFTER MANUAL EVENTS
        # ----------------------------------------------------

        assign_event_ids(
            matches
        )


        # ----------------------------------------------------
        # UPDATE STATUS
        # ----------------------------------------------------

        (
            live_count,
            upcoming_count,
            ended_count
        ) = update_all_match_statuses(
            matches,
            now_bd,
            manual_control
        )


        # ----------------------------------------------------
        # SORT EVENTS
        #
        # LIVE     -> first
        # UPCOMING -> second
        # ENDED    -> last
        # ----------------------------------------------------

        matches = sort_matches_by_status(
            matches
        )


        # ----------------------------------------------------
        # UPDATE MATCHES IN DATA
        # ----------------------------------------------------

        if isinstance(
            data,
            dict
        ):

            data["matches"] = matches


        # ----------------------------------------------------
        # DRM CONVERSION
        # ----------------------------------------------------

        drm_count = convert_drm_keys(
            data
        )


        # ----------------------------------------------------
        # FINAL TOP LEVEL DATA
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # WRITE OUTPUT
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        print("=" * 70)

        print(
            "FINAL SUMMARY"
        )

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
            "Auto IDs:",
            generated_ids
        )

        print(
            "Events removed:",
            removed_events
        )

        print(
            "Streams removed:",
            removed_streams
        )

        print(
            "Streams added:",
            added_streams
        )

        print(
            "Events added:",
            added_events
        )

        print(
            "Empty streams removed:",
            empty_streams_removed
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


        except Exception as exc:

        print()
        print("=" * 70)
        print("SPORTS DATA UPDATE FAILED")
        print("=" * 70)

        print(
            "Error type:",
            type(exc).__name__
        )

        print(
            "Error:",
            str(exc)
        )

        print("=" * 70)

        return 1

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
