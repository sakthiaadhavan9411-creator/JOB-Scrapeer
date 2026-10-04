# Apify connection for Sakthi's role searches

Prepared actor: `harvestapi/linkedin-post-search`.
Documentation: https://apify.com/harvestapi/linkedin-post-search

`apify-input.json` now contains 14 grouped searches for operations, business analysis, project/program coordination, PMO, product analysis, management trainees, implementation, customer/support operations, supply chain/logistics coordination, office/admin operations, Founder's Office, strategy and operations, associate project managers, and executive assistants. There is no remote-only or location restriction. Results are limited to the past week, newest first, up to 7 per query (98 before deduplication). The existing 100-item and USD 0.50 actor-charge limits remain. Comments and reactions are disabled. `role_keywords` additionally filters both new and queued posts to these roles.

The local config has the actor's documented output mapping prepared:

- URL: `linkedinUrl`
- Author: `author.name`
- Text: `content`
- Date: `postedAt.date`

The token and task ID are now saved in the local `.env`. Task: `uL2DLSkvf3LAcsMvM`.
Open https://console.apify.com/actors/tasks/uL2DLSkvf3LAcsMvM/input to inspect it.
The original `config.yaml` remains Google-only. `config.apify.yaml` enables both sources explicitly.

Validation on 2026-10-04: run `GEcFamVeEoRqbeiW2` succeeded with 10 results, all successfully mapped and matching the hiring keyword filter. Reported usage was USD 0.02005. No Telegram messages were sent by this validation, and no deduplication baseline was changed. The trial used 2 results per query; the saved task now uses 7 per query across the expanded role searches. Saved task options bound actor charges to USD 0.50 per run and the run timeout to 300 seconds.

To start both sources, stop any old loop with Ctrl+C, then run:

```powershell
.\.venv\Scripts\python.exe -m hiring_alerts loop --config config.apify.yaml --interval 21600 --send-backlog 5
```

This starts a new run immediately and then waits six hours between passes. It selects up to five initial matching posts from uninitialized sources; subsequent passes send new matches. Actual charges vary. No recurring process or Apify schedule was started by the assistant.

## Connect

1. Sign in to Apify, then get an API token from your account settings. Save it locally in `.env` as `APIFY_TOKEN`. Do not paste it in chat.
2. Create a saved task for the actor above with the input from `apify-input.json`; alternatively, once the token is saved, the assistant can create the task through the API. Save the resulting task ID as `APIFY_TASK_ID` in `.env`.
3. Check current actor pricing and account spending limits before enabling repeated runs. The actor may bill repeated results even when local deduplication prevents Telegram duplicates. At a 15-minute interval, this setup could request up to 9,408 results daily. Start with one manual validation run and a less frequent interval, such as every 6 hours, before choosing a recurring cadence.
4. Stop the existing loop before enabling Apify, so it cannot start paid runs unexpectedly. Set `apify.enabled: true` only when ready. Restart after editing `.env`, which is loaded once at startup.
5. For the first real Apify fetch, use `python -m hiring_alerts run --send-backlog 5` to deliver up to five existing matching posts. Without this flag, the first fetch is silently baselined. The existing Google Alerts baseline is preserved.

Do not create a second schedule in Apify if the Python loop starts the task. A dry run also starts a paid Apify task, even though it sends no Telegram messages.

The live task and dataset mapping have been verified. Search quality still depends on the actor's results and the configured keyword searches; passing a keyword filter does not guarantee a suitable vacancy.
