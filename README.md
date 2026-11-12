# Tdarr → Jellyfin Updater

A small Docker service that refreshes Jellyfin after Tdarr finishes all active and queued **transcodes**.

It deliberately ignores Tdarr health-check workers and health-check queues, so a running health check does not prevent Jellyfin from refreshing.

## What it does

The service checks Tdarr every five minutes between **09:00 and 01:00** Amsterdam time.

It refreshes Jellyfin only when Tdarr transitions from:

```text
1+ active or queued transcodes  ->  0 active or queued transcodes
```

This prevents repeated Jellyfin library scans while Tdarr is processing a batch.

### Example

| Previous check | Current check | Jellyfin refresh |
|---|---|---|
| No transcodes | No transcodes | No |
| No transcodes | 1+ transcodes | No |
| 1+ transcodes | 1+ transcodes | No |
| 1+ transcodes | 0 transcodes | **Yes** |

## Files

```text
.
├── app.py
├── .env
├── crontab
├── Dockerfile
├── docker-compose.yml
├── README.md
└── data/
    ├── jellyfin-tdarr-updater.log
    └── state.json
```

- `app.py` — the updater script
- `.env` — Tdarr and Jellyfin configuration
- `crontab` — the schedule
- `Dockerfile` — builds the container
- `docker-compose.yml` — runs the container
- `data/` — persistent state and logs

## Requirements

- Docker
- Docker Compose
- A reachable Tdarr Server API
- A reachable Jellyfin server
- A Tdarr API key
- A Jellyfin API key

No additional Python packages are required; the script uses only the Python standard library.

## Configuration

Create or edit `.env`:

```env
TDARR_URL=http://192.168.1.41:8266
TDARR_API_KEY=tapi_YOUR_TDARR_KEY
JELLYFIN_URL=http://192.168.1.99:8096
JELLYFIN_API_KEY=YOUR_JELLYFIN_API_KEY
STATE_FILE=/app/data/state.json
LOG_FILE=/app/data/jellyfin-tdarr-updater.log
```

### Tdarr

- `TDARR_URL` is the Tdarr Server API URL.
- The Tdarr Server API normally uses port `8266`.
- Create the API key in Tdarr under **Tools → API Keys**.
- The key is sent as the `x-api-key` HTTP header.

### Jellyfin

- `JELLYFIN_URL` is the Jellyfin server URL.
- Create the API key in Jellyfin under **Dashboard → API Keys**.
- The script uses the modern Jellyfin authorization header:

```http
Authorization: MediaBrowser Token="YOUR_JELLYFIN_API_KEY"
```

## Schedule

The included `crontab` runs every five minutes from 09:00 through 01:00:

```cron
*/5 9-23,0-1 * * * /usr/local/bin/python3 /app/app.py >> /proc/1/fd/1 2>&1
```

Cron cannot wrap a hour range across midnight, so the schedule uses two ranges:

```text
9-23,0-1
```

This means:

- 09:00–23:55
- 00:00–01:55

The container uses `TZ=Europe/Amsterdam`.

## Start the service

From the project folder:

```bash
docker compose up -d --build
```

Check that it is running:

```bash
docker compose ps
docker compose logs -f jellyfin-tdarr-updater
```

## Test manually

Run the updater once:

```bash
docker compose exec jellyfin-tdarr-updater python3 /app/app.py
```

Check the log:

```bash
docker compose exec jellyfin-tdarr-updater \
  tail -20 /app/data/jellyfin-tdarr-updater.log
```

Check the saved state:

```bash
docker compose exec jellyfin-tdarr-updater \
  cat /app/data/state.json
```

## Logs

The log is stored inside the repository at:

```text
data/jellyfin-tdarr-updater.log
```

Example output:

```text
2026-11-12T13:05:00 previous_transcodes_active=True current_transcodes_active=False active_workers=0 queued_jobs=0
2026-11-12T13:05:00 Transcodes changed from active to idle; Jellyfin library refresh requested
```

If Tdarr is still busy:

```text
2026-11-12T13:10:00 previous_transcodes_active=True current_transcodes_active=True active_workers=1 queued_jobs=0
2026-11-12T13:10:00 No active-to-idle transcode transition; no Jellyfin refresh
```

## State

The service stores its previous state in:

```text
data/state.json
```

Example:

```json
{
  "transcodes_were_active": true,
  "updated_at": "2026-11-12T13:05:00.123456+01:00"
}
```

This state is required for the edge-triggered behavior: Jellyfin is refreshed only when Tdarr changes from active to idle.

## Health checks

The script only considers these Tdarr worker types:

```python
TRANSCODE_TYPES = {"transcodecpu", "transcodegpu"}
```

It ignores:

```python
healthcheckcpu
healthcheckgpu
```

Therefore, Jellyfin can refresh while a health check is still running, as long as no transcode is active or queued.

## Stop the service

```bash
docker compose down
```

To stop and remove the built image as well:

```bash
docker compose down --rmi local
```

## Security

- Keep `.env` private.
- Do not commit API keys to Git.
- Add `.env` and `data/` to `.gitignore`.
- Rotate Tdarr, Jellyfin, Radarr, Sonarr, and TMDB keys if they have been exposed.

Example `.gitignore`:

```gitignore
.env
data/
__pycache__/
*.pyc
```