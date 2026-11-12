#!/usr/bin/env python3
"""
Refresh Jellyfin after Tdarr finishes all transcodes.

- Ignores health-check workers and health-check queues.
- Refreshes Jellyfin only when Tdarr transitions from:
  1+ active/queued transcodes -> 0 active/queued transcodes.
- Reads configuration from .env.
- Stores state and logs inside the project folder.
- Uses only the Python standard library.
"""

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

TRANSCODE_TYPES = {"transcodecpu", "transcodegpu"}


def load_env(path: Path) -> dict:
    """Load a simple KEY=value .env file."""
    values = {}

    if not path.exists():
        raise FileNotFoundError(f"Missing environment file: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def request_json(url: str, headers: dict, timeout: int = 15) -> dict:
    """Perform a GET request and parse the JSON response."""
    request = urllib.request.Request(url, headers=headers, method="GET")

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def count_active_transcode_workers(nodes: dict) -> int:
    """Count active Tdarr transcode workers, ignoring health checks."""
    active = 0

    for node in nodes.values():
        workers = node.get("workers") or {}

        for worker in workers.values():
            worker_type = worker.get("workerType", "")

            if worker_type in TRANSCODE_TYPES and worker.get("idle") is not True:
                active += 1

    return active


def count_queued_transcodes(nodes: dict) -> int:
    """Count queued Tdarr transcode jobs, ignoring health checks."""
    total = 0

    for node in nodes.values():
        queues = node.get("queueLengths") or {}

        for worker_type, length in queues.items():
            if worker_type in TRANSCODE_TYPES and isinstance(length, (int, float)):
                total += int(length)

    return total


def read_previous_state(state_file: Path) -> bool:
    """Return True if the previous run saw one or more active/queued transcodes."""
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        return bool(state.get("transcodes_were_active", False))
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def write_current_state(state_file: Path, transcodes_active: bool) -> None:
    """Persist whether transcodes were active during this run."""
    state_file.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "transcodes_were_active": transcodes_active,
        "updated_at": datetime.now().isoformat(),
    }

    temporary_file = state_file.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )
    temporary_file.replace(state_file)


def refresh_jellyfin(url: str, api_key: str, timeout: int = 15) -> None:
    """Trigger a Jellyfin library refresh using the modern authorization header."""
    headers = {
        "Authorization": f'MediaBrowser Token="{api_key}"',
        "Content-Type": "application/json",
    }

    request = urllib.request.Request(
        f"{url}/Library/Refresh",
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status not in (200, 204):
            raise RuntimeError(
                f"Jellyfin refresh failed with HTTP {response.status}"
            )


def main() -> int:
    env = load_env(ENV_FILE)

    tdarr_url = env["TDARR_URL"].rstrip("/")
    tdarr_api_key = env["TDARR_API_KEY"]
    jellyfin_url = env["JELLYFIN_URL"].rstrip("/")
    jellyfin_api_key = env["JELLYFIN_API_KEY"]
    state_file = Path(env["STATE_FILE"])
    log_file = Path(env["LOG_FILE"])

    tdarr_headers = {
        "x-api-key": tdarr_api_key,
        "Accept": "application/json",
    }

    nodes = request_json(
        f"{tdarr_url}/api/v2/get-nodes",
        tdarr_headers,
    )

    active_workers = count_active_transcode_workers(nodes)
    queued_jobs = count_queued_transcodes(nodes)

    transcodes_active = active_workers > 0 or queued_jobs > 0
    previous_state = read_previous_state(state_file)

    should_refresh = previous_state and not transcodes_active

    log_file.parent.mkdir(parents=True, exist_ok=True)

    with log_file.open("a", encoding="utf-8") as log:
        log.write(
            f"{datetime.now().isoformat()} "
            f"previous_transcodes_active={previous_state} "
            f"current_transcodes_active={transcodes_active} "
            f"active_workers={active_workers} "
            f"queued_jobs={queued_jobs}\n"
        )

        if should_refresh:
            refresh_jellyfin(jellyfin_url, jellyfin_api_key)

            log.write(
                f"{datetime.now().isoformat()} "
                "Transcodes changed from active to idle; "
                "Jellyfin library refresh requested\n"
            )
        else:
            log.write(
                f"{datetime.now().isoformat()} "
                "No active-to-idle transcode transition; "
                "no Jellyfin refresh\n"
            )

    write_current_state(state_file, transcodes_active)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"jellyfin-tdarr-updater failed: {exc}", file=sys.stderr)
        sys.exit(1)