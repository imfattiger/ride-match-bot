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

## Database

Two modes detected by `USE_PG = bool(os.getenv('DATABASE_URL'))`:
- **SQLite** (local dev): `ridematch_v15.db`, `?` placeholders, `INSERT OR REPLACE / OR IGNORE`, `cursor.lastrowid`
- **PostgreSQL** (Render): `%s` placeholders via `q()` helper, `ON CONFLICT DO UPDATE`, `RETURNING id`

All schema changes must be applied in **both** the `CREATE TABLE` block and the migration list inside `init_db()`.

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
