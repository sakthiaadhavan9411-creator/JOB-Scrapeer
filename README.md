# linkedin-hiring-alerts

A small Python 3.11 service that reads Google Alerts Atom/RSS feeds and/or runs an Apify saved task, filters public LinkedIn posts, and forwards new hiring alerts to Telegram. Uses `requests`, `feedparser`, `PyYAML`, `python-dotenv`, and SQLite. No LinkedIn credentials or browser automation are needed by this service.

## Quick start

1. Install Python 3.11 or newer, then open a terminal in this project directory:

   ```sh
   python -m venv .venv
   # Linux/macOS:
   . .venv/bin/activate
   # Windows PowerShell instead:
   # .venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   cp .env.example .env
   ```

   On PowerShell use `Copy-Item .env.example .env`. An editable package install is optional: `python -m pip install -e .`.

2. Create a Telegram bot: open [@BotFather](https://t.me/BotFather), send `/newbot`, choose its name and username, and copy the resulting token into `TELEGRAM_BOT_TOKEN` in `.env`. Keep the token private.

3. Open your new bot, **press Start, and send it a message**. Run:

   ```sh
   python scripts/get_chat_id.py
   ```

   Copy the printed ID into `TELEGRAM_CHAT_ID` in `.env`. Negative IDs are valid for groups. If several chats appear, use the intended chat. For groups, add the bot and send a command addressed to it. The helper uses `getUpdates`; an active webhook or another update consumer can prevent it from seeing messages. It does not delete webhooks or consume updates with an offset.

4. Edit `config.yaml` (or copy `config.example.yaml`). Both sources ship **disabled**; enable and configure at least one. Environment variables override `.env`. The `.env` file is loaded next to the selected configuration, and `state_path` is resolved relative to that configuration.

5. Preview, then initialize:

   ```sh
   python -m hiring_alerts run --dry-run
   python -m hiring_alerts run
   ```

   The first successful fetch of each source silently records its current LinkedIn posts as a baseline. Seeing zero sends here is expected. To preview and send up to five existing matching posts instead, use these commands **before initializing**:

   ```sh
   python -m hiring_alerts run --dry-run --send-backlog 5
   python -m hiring_alerts run --send-backlog 5
   ```

6. Run periodically:

   ```sh
   python -m hiring_alerts loop --interval 900
   ```

   `loop` waits 900 seconds after each pass, reloads config each pass, and continues after operational failures. Ctrl+C exits cleanly. `run` exits 1 if any source or delivery fails, even when healthy sources succeeded. `--config /path/to/config.yaml` works after either subcommand.

## Sources

### Google Alerts RSS

At [Google Alerts](https://www.google.com/alerts), create searches such as `site:linkedin.com/posts "we are hiring" Python`. In the alert options choose RSS delivery and copy the feed URL into `google_alerts.feed_urls`:

```yaml
google_alerts:
  enabled: true
  feed_urls:
    - "https://www.google.com/alerts/feeds/YOUR_ID/YOUR_FEED"
```

Multiple feeds are fetched independently. A broken feed does not stop the others. Treat feed URLs as private: they identify your alerts. RSS coverage depends on Google's indexing; this is not a complete or real-time LinkedIn firehose. Google redirect links using `url=` or `q=` are decoded without following the redirect. HTML tags and entities are cleaned from titles, authors, and text.

### Apify saved actor task

In Apify, choose an actor that returns public LinkedIn posts, configure its search/input and limits, and save it as a task. Put its task ID in `APIFY_TASK_ID` and an Apify API token in `APIFY_TOKEN`. Actor execution may incur Apify charges. Actor input lives in the saved task, not this application.

```yaml
apify:
  enabled: true
  timeout_seconds: 300
  poll_seconds: 5
  fields:
    url_field: url
    author_field: author.name
    text_field: text
    date_field: publishedAt
```

Inspect a dataset item and match the four field paths to its schema. Dotted paths access nested dictionaries; array indexing is not supported. Defaults are `url`, `author`, `text`, `publishedAt`. All mapped fields must exist; null values become empty strings, but an empty URL is an error. Missing or nonscalar fields fail that source with the item index and mapped field path, allowing you to correct the configuration without silently discarding data. Other sources still run.

The adapter starts the task using the [Apify run-task API](https://docs.apify.com/api/v2/actor-task-runs-post), polls its [run status](https://docs.apify.com/api/v2/actor-run-get), and paginates the successful run's default dataset. It sets a server run timeout and a local waiting deadline. Failed, aborted, timed-out, malformed, or partially read runs are not baselined. A lost response can leave a run executing remotely; inspect Apify Console before manually retrying. Task creation is intentionally not automatically retried because that could start duplicate paid runs. A dry run **still executes enabled Apify tasks** and fetches feeds, but never sends Telegram messages or changes saved state.

## Filtering, state, and delivery

- Pipeline: fetch → common `Post(url, title, author, text, source, published)` → normalize → LinkedIn host check → keyword filter → SQLite dedupe/queue → Telegram.
- Keywords match case-insensitive substrings across title, author, and text. Includes use any-match; excludes use none-match. An empty include list accepts all posts. URLs themselves are not keyword searched.
- Only HTTP(S) `linkedin.com` or its subdomains are accepted. Lookalike domains, credentials in URLs, and unusual ports are rejected. HTTPS, common LinkedIn host variants, trailing slashes, fragments, query ordering, `utm_*`, and common LinkedIn tracking parameters are normalized. Identity-bearing query parameters are retained. This deduplicates normalized URLs, not semantically equivalent posts with unrelated URLs.
- Each feed and Apify task has a separate initialization marker. Successful empty results initialize it; failed fetches do not. Newly added sources also receive a silent baseline. Initial baselines include all valid LinkedIn URLs, even those not matching today's keywords, to avoid future floods after changing filters.
- `--send-backlog N` selects up to N newest matching, unseen posts across sources being initialized, using parsed ISO/RFC dates. Missing/unparseable dates sort last with stable input order. Remaining initial posts are baselined. It does not resend seen posts or reset initialized sources. The regular per-run cap still applies; selected backlog overflow stays queued.
- **Baseline is the one deliberate exception to “seen only after send.”** Regular posts and selected backlog are only marked seen after a successful Telegram response containing `ok: true` and a message ID. Failed sends stay pending. State is committed after every confirmed post.
- Pending posts are stored with their content, so they can be delivered after disappearing from a feed. Current keywords are reapplied to the queue each run; nonmatching queued posts remain stored and may qualify after a later filter change. Source toggles stop fetching; they do not purge already queued posts.
- `max_messages_per_run` defaults to **15**, including the summary. With 20 pending posts, one pass sends 14 alerts plus `+6 more…`. The minimum is 2 so every overflow pass can make progress and include its summary. Excess posts remain queued for later runs. Summaries do not acknowledge queued posts.
- Sends and retries are spaced at least 1.05 seconds apart. HTTP 429 uses Telegram's `retry_after`; network errors, HTTP 408, and 5xx receive exponential backoff, up to three total attempts. Permanent errors stop delivery for that pass. See the [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage).
- All dynamic message fields use `html.escape`; text is capped at 300 characters, the label at 300, and unusually long URLs are rejected. Message previews are disabled. Logs are JSON lines on stdout; raw HTTP exceptions/responses and credentials are never logged. Dry-run logs include message content, so treat those logs as private.
- A local OS lock prevents concurrent real runs using the same SQLite path. Dry runs use an in-memory snapshot of state and print `would_send` events; they do not create a database or modify initialization, pending, or seen records.
- Delivery is **at least once**, not exactly once. A crash after Telegram receives a message but before SQLite commits, or a lost HTTP response followed by a retry, can cause a duplicate. Telegram `sendMessage` has no application idempotency key. Keep and back up the SQLite file. Do not run multiple installations against the same chat with separate state if you want shared deduplication.

## GitHub Actions: hosted every six hours

Use a private repository. The included workflow runs a one-pass check on GitHub's computers every six hours; your PC can be off. It uses `config.apify.yaml` (Google Alerts plus Apify) by default, so Apify usage charges still apply. GitHub Actions usage is subject to your account's included minutes and billing settings.

Set these repository Actions secrets from your local `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `APIFY_TOKEN`, and `APIFY_TASK_ID`. Do not upload `.env`, your Windows certificate bundle, or the virtual environment. The Ubuntu runner uses its own trusted certificates.

The schedule is `17 */6 * * *` UTC: approximately **05:47, 11:47, 17:47, and 23:47 India time**. GitHub schedules can be delayed; see [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

1. Push the project to the default branch and set the four secrets.
2. Keep the repository variable `ALERTS_ENABLED` unset or `false` during setup.
3. Stop the local sending loop before switching to hosted runs. Optionally seed its database into the private `alerts-state` branch using `python scripts/github_state.py save` from an authenticated checkout. This preserves deduplication when moving to GitHub.
4. Under **Actions → Hiring alerts → Run workflow**, select the source config and initial backlog (0 or 5). First-run baselines still apply. Confirm the run and state-save step succeed.
5. Set repository variable `ALERTS_ENABLED` to `true` to activate scheduled runs. Set `ALERTS_CONFIG` to `config.yaml` for Google-only operation, or `config.apify.yaml` for both sources. The default is both.
6. To pause, set `ALERTS_ENABLED` to `false` or disable the workflow. Watch the Actions page for failures.

State is stored in a dedicated **alerts-state** Git branch, containing only `alerts.sqlite3`, never credentials or code. Every pass restores it and saves changes even after partial source/delivery failure. Jobs are serialized and state writes never force-push over another commit. Keep the repository private because alert history is personal. Preserve this branch; deleting it resets the baseline and loses queued posts. A cancellation or failed state push after a Telegram delivery can still cause a duplicate, so inspect failed runs before manually retrying.

Both config files must retain `state_path: state/alerts.sqlite3` for this workflow. Workflow changes require `contents: write` to persist state. Pull requests do not trigger sending; manual and scheduled sends are restricted to the default branch. Tests run independently. Deployment is not complete until the remote workflow has passed and the schedule variable has been enabled.

## VPS / Raspberry Pi

Install the project and its virtual environment under `/opt/linkedin-hiring-alerts`. Give a dedicated `alerts` user access to the project and write access to `state/`; restrict `.env` permissions (`chmod 600 .env`). Preserve `state/alerts.sqlite3` across upgrades. Back it up while the service is stopped, or use SQLite's backup API while it runs.

Cron, every 15 minutes (edit this user's crontab with `crontab -e`):

```cron
*/15 * * * * cd /opt/linkedin-hiring-alerts && /opt/linkedin-hiring-alerts/.venv/bin/python -m hiring_alerts run >> /opt/linkedin-hiring-alerts/alerts.log 2>&1
```

Use logrotate for this file. Alternatively, save `/etc/systemd/system/linkedin-hiring-alerts.service`:

```ini
[Unit]
Description=LinkedIn hiring alerts to Telegram
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=alerts
Group=alerts
WorkingDirectory=/opt/linkedin-hiring-alerts
ExecStart=/opt/linkedin-hiring-alerts/.venv/bin/python -m hiring_alerts loop --interval 900
Restart=on-failure
RestartSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/linkedin-hiring-alerts/state
UMask=0077

[Install]
WantedBy=multi-user.target
```

Create the writable `state` directory first, then `sudo systemctl daemon-reload` and `sudo systemctl enable --now linkedin-hiring-alerts`. Read JSON logs with `journalctl -u linkedin-hiring-alerts -f`. Use either cron or systemd, not both. Restart the service after changing `.env`.

## Docker

```sh
docker build -t linkedin-hiring-alerts .
docker volume create hiring-alerts-state
docker run -d --name hiring-alerts --restart unless-stopped \
  --env-file .env \
  -v "$(pwd)/config.yaml:/app/config.yaml:ro" \
  -v hiring-alerts-state:/app/state \
  linkedin-hiring-alerts
```

The image runs as UID 10001. A named volume preserves SQLite state; bind-mounted state directories must be writable by that UID. Override the default command by appending `run --dry-run --send-backlog 3`. The image excludes `.env`, tests, local state, and caches. `docker logs hiring-alerts` shows stdout logs. Do not use a second container to send concurrently with a different state volume.

## Development

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use mock HTTP only: redirect decoding, HTML cleaning, filtering, URL identity, SQLite persistence, first-run/backlog/dry-run behavior, partial source failures, caps, rate limiting, 429/backoff, RSS/Atom, Apify schema validation, polling, timeout, and pagination. GitHub CI and Docker target Python 3.11. No real Telegram or Apify credentials are needed for tests.

Modules: `sources/` fetches and maps source records; `normalize.py` cleans records and URLs; `filters.py` matches keywords; `dedupe.py` owns SQLite and locking; `telegram.py` formats/delivers messages; `pipeline.py` orchestrates a pass; `cli.py` configures the command line and loop.
