#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SOURCE_URL = "https://raw.githubusercontent.com/sm-monirulislam/Upcoming-and-Live-Sports-Data/refs/heads/main/Sports_data.json"


def fetch_data():
    req = Request(
        SOURCE_URL,
        headers={"User-Agent": "sports-data-fetcher/1.0"}
    )

    with urlopen(req, timeout=30) as response:
        return json.load(response)


def find_matches(data):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("matches", "events", "data", "sports"):
            if isinstance(data.get(key), list):
                return data[key]

    return []


def is_live(match):
    if not isinstance(match, dict):
        return False

    for key in ("live", "isLive", "is_live"):
        if isinstance(match.get(key), bool):
            return match[key]

    status = str(
        match.get("status", match.get("match_status", ""))
    ).strip().lower()

    return status in {
        "live",
        "inplay",
        "in-play",
        "ongoing",
        "started",
        "playing"
    }


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

    Empty or missing kid/key will not create drm_key.
    """

    matches = find_matches(data)

    converted_count = 0

    for match in matches:
        if not isinstance(match, dict):
            continue

        streams = match.get("streams")

        if not isinstance(streams, list):
            continue

        for stream in streams:
            if not isinstance(stream, dict):
                continue

            kid = str(stream.get("kid", "")).strip()
            key = str(stream.get("key", "")).strip()

            # Only create drm_key when BOTH values exist
            if kid and key:
                stream["drm_key"] = f"{kid}:{key}"
                converted_count += 1

            # Remove old fields
            stream.pop("kid", None)
            stream.pop("key", None)

    return converted_count


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "sports_data.json"

    print(
        "Fetch start time:",
        datetime.now(timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds")
    )

    try:
        # Fetch source data
        data = fetch_data()

        # Find matches
        matches = find_matches(data)

        # Convert kid + key -> drm_key
        drm_count = convert_drm_keys(data)

        # Count live matches
        live_count = sum(is_live(m) for m in matches)

        # Save final JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )
            f.write("\n")

        print("Total number of matches:", len(matches))
        print("Number of live matches:", live_count)
        print("DRM streams converted:", drm_count)
        print("Successfully saved data to:", output_file)

        return 0

    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
        OSError
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
