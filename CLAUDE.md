# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**sun car 順咖媒合** is a LINE Bot for P2P ride-sharing/logistics matching in Taiwan. Single-file Flask app (`app.py`) deployed on Render with gunicorn. Uses LINE Messaging API (webhook-based, no polling).

## Deployment

- **Platform**: Render (free tier) — auto-deploys on push to `main`
- **GitHub repo**: `imfattiger/ride-match-bot`
- **Runtime**: Python 3.11.9 (pinned in `runtime.txt` — do not change; line-bot-sdk 2.4.3 requires aiohttp==3.8.4 which only has wheels for ≤3.11)
- **Process**: `gunicorn app:app` (see `Procfile`)
- **Keep-alive**: thread started at module level (not inside `__main__`) so gunicorn picks it up

## Architecture

Everything lives in `app.py`. Key sections in order:

1. **CITY_DATA / DISTRICT_DATA / CITY_WEIGHTS** — Taiwan geography lookup tables for matching
2. **DISTRICT_GROUPS** — cluster districts within major cities (for same-city matching precision)
3. **DB helpers** — `get_db()`, `q(sql)`, `init_db()`, `is_blocked()` — dual SQLite/PostgreSQL mode via `DATABASE_URL` env var
4. **Flex card builders** — `get_welcome_flex`, `get_rules_flex`, `get_terms_flex`, `get_match_notify_flex`, `get_publish_confirm_flex`, etc.
5. **`do_publish(uid, reply_token)`** — core publish logic: checks active trip limit (max 3), inserts trip, finds matches, stores pairs, sends cards, push notifications
6. **`find_matches_v15`** — matching algorithm: direction vectors via CITY_WEIGHTS, ±1hr/±4hr time buffer, waypoint inclusion, district cluster matching
7. **Flask routes** — `/` health check, `/callback` webhook, `/health`, `/stats`, `/debug-bot`, `/logs`
8. **`handle_postback`** — time picker, delete, complete (→ mutual rating prompt), rate, cancel, report, agree_terms
9. **`handle_message`** — terms gate → blocked gate → full publish state machine + all text commands

## Debugging Priorities

When something breaks, always check in this order — skipping layers causes wasted rounds:

1. **Webhook URL** — must be `https://<your-render-url>/callback` (POST only); `/ping` for health monitors
2. **psycopg2 cursor usage** — `conn.execute()` works only on the `_PGWrapper` wrapper; raw `conn.cursor().execute()` returns `None` (DBAPI2 spec), so **never chain `.fetchone()` directly after `.execute()` on a raw cursor**
3. **Connection pool** — Render free tier caps at 5 connections; every `get_db()` must have a matching `conn.close()` in `finally`
4. **Render cold-start** — free tier sleeps after 15 min inactivity; first request takes ~10s; not a bug
5. **App logic** — only after all above are ruled out

Recent incidents:
- `'NoneType' object has no attribute 'fetchone'` — raw psycopg2 cursor `.execute()` returns `None`; fix: split execute + fetchone onto two lines
- UptimeRobot all-red — monitor was pointing at `/callback` (POST-only); fix: change to `/ping`

## Database

Two modes detected by `USE_PG = bool(os.getenv('DATABASE_URL'))`:
- **SQLite** (local dev): `ridematch_v15.db`, `?` placeholders, `INSERT OR REPLACE / OR IGNORE`, `cursor.lastrowid`
- **PostgreSQL** (Render): `%s` placeholders via `q()` helper, `ON CONFLICT DO UPDATE`, `RETURNING id`

All schema changes must be applied by **appending a new entry to `SCHEMA_MIGRATIONS`** (not editing existing entries). `init_db()` tracks applied versions via `schema_version` table and skips already-applied migrations.

**psycopg2 vs SQLite API differences** (common gotchas):
- Placeholders: SQLite uses `?`, PostgreSQL uses `%s` — always use `q(sql)` helper to auto-convert
- `INSERT OR REPLACE` / `INSERT OR IGNORE` → PostgreSQL: `ON CONFLICT DO UPDATE` / `ON CONFLICT DO NOTHING`
- `cursor.lastrowid` → PostgreSQL: `RETURNING id` + `cursor.fetchone()[0]`
- `connection.execute()` → works on `_PGWrapper` but NOT on raw psycopg2 connection; always call `conn.cursor()` explicitly when chaining `.fetchone()`

Tables:
- `matches` — trips (user_id, user_type driver/seeker, time_info, s/e city/dist, fee, status active/completed/cancelled, expires_at)
- `user_state` — per-user draft state machine + `agreed_terms` flag
- `ratings` — post-trip scores; uses `rater_id`/`ratee_id` columns; UNIQUE index on `(match_id, rater_id)`
- `pairs` — confirmed match relationships for mutual rating; keyed on `(uid_a, match_id_a, uid_b, match_id_b)`
- `blocked_users` — banned user IDs; checked at entry of every handler via `is_blocked(uid)`

## Publish Flow (State Machine)

`user_state.step` drives the multi-step form:
`START` → time picker → area carousel (s_city/s_dist) → `END` → area carousel (e_city/e_dist) → `DONE` → waypoint → detail Flex (人數/費用/彈性) → tag categories → `最終確認發布` → `WAIT_LINE_ID` → `do_publish()`

`WAIT_LINE_ID` is handled in the `else` fallback block of `handle_message`.

## Terms of Service Gate

Every `handle_message` and `handle_postback` call checks `user_state.agreed_terms` before proceeding. New users see the 6-bubble terms carousel on FollowEvent and on every message until they agree. The only bypass is `msg in ["免責聲明", "使用條款"]`.

## Moderation

- `is_blocked(uid)` — DB lookup against `blocked_users`; called at the top of both handlers; returns silently if blocked
- Admin commands (only if `uid == ADMIN_LINE_ID`): `/ban <uid>` and `/unban <uid>`
- Report button on browse trip cards → `action=report` postback → pushes alert to `ADMIN_LINE_ID` with `/ban` shortcut

## Rating System

- Only users with a matching `pairs` record can rate each other (prevents self-rating and rating strangers)
- `action=complete` looks up pairs, prompts both sides with QuickReply star buttons
- `action=rate` validates pair existence, then `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` to prevent duplicates
- `get_user_rating(conn, user_id)` queries `ratee_id`, not the old `user_id` column

## Required Environment Variables

```
LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET
DATABASE_URL          # PostgreSQL URL (triggers PG mode)
RENDER                # any value — activates module-level keep_alive thread
ADMIN_LINE_ID         # bot owner's LINE uid — use /myid command to retrieve
```

## LINE SDK Version

Uses **`line-bot-sdk==2.x`** (NOT v3). Imports are from `linebot` not `linebot.v3`. Do not upgrade to 3.x without rewriting all handlers and Flex message constructors.

## Key Constraints

- `find_matches_v15` SELECT must include `id` as the **last column** (index 11) — `pairs` table insertion depends on this
- Same-city direction is detected by `sc == ec`, not weight equality (weights can collide, e.g. 新竹市/新竹縣)
- `get_district_cluster()` fallback returns `city` (not `dist`) for cities without DISTRICT_GROUPS entries
- Active trip limit is 3 per user, enforced in `do_publish()` before the duplicate-check
## UX Changes

When modifying input flows (QuickReply menus, Flex carousels, state machine steps):
- **Preserve existing selection mechanisms unless explicitly told to replace them**
- Add new inputs **alongside** existing ones — do NOT substitute
- Before changing any input flow, state what you plan to keep vs. add vs. replace, and wait for confirmation
- Example: "add vehicle model free text input AFTER the existing QuickReply selector" means keep the QuickReply AND add a new step after it

Common mistake: replacing a QuickReply category selector with free text when the user wanted both preserved.

## Environment

- **Primary OS**: Windows 10. Be aware of Windows file lock issues — suggest closing apps or using Resource Monitor before file operations
- **Remote access**: User accesses projects from iOS via Tailscale
- **Render free tier**: 5 DB connection limit, 15-min sleep, cold-start ~10s
- **Node.js path on Windows**: `export PATH="/c/Program Files/nodejs:$PATH"`

## Claude Code Working Rules

### Validation — never report done without verifying
After editing any Python file, re-read the changed function to confirm the edit landed correctly. Do not say "Done" or "fixed" based on memory alone.

### Large file reading — app.py is a single large file
`app.py` exceeds 500 lines. Always read in segments using `offset` + `limit`. Never assume you've seen the whole file from a single read. Re-read the target section immediately before making changes.

### Search results may be truncated
If a grep/search returns suspiciously few results, narrow the query and search again. Tool output over 50K chars gets silently truncated.

### Schema changes — append only
Never edit existing entries in `SCHEMA_MIGRATIONS`. Always append a new migration entry. Query table schema before assuming any column exists.

### After long conversations — re-read before editing
Re-read the relevant section of `app.py` before making any edit. Context compression may have silently dropped earlier reads.

### Verification mindset
After implementing any feature, re-read the changed code and actively look for edge cases that would break it before reporting complete.

### Pre-commit integrity check
Before any `git commit` that touches `app.py`, run `git diff --stat HEAD` and report the line-count delta. If more than 20 lines were removed, pause and confirm the deletion was intentional before committing.

### Diagnose infra before code
When the bot is unresponsive in production, always check in this order BEFORE touching code:
1. Is the Render deploy branch `main`? Is the latest commit on `main`?
2. Is the webhook URL in LINE console pointing to the correct Render URL + `/callback`?
3. Are all required env vars set on Render (`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`, `DATABASE_URL`, `ADMIN_LINE_ID`)?
4. Are Render deploy logs showing a successful build?
Only after all four confirmed → look at app logic.

### Windows file locks
If any file operation (delete, rename, move) fails due to Windows file locks, do NOT retry with force flags. Tell the user which process likely holds the lock and ask them to close it via Task Manager or File Explorer.
