# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RideMatch is a LINE Bot for P2P ride-sharing/logistics matching in Taiwan. Single-file Flask app (`app.py`) deployed on Render with gunicorn. Uses LINE Messaging API (webhook-based, no polling).

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
3. **DB helpers** — `get_db()`, `q(sql)`, `init_db()` — dual SQLite/PostgreSQL mode via `DATABASE_URL` env var
4. **Flex card builders** — `get_welcome_flex`, `get_rules_flex`, `get_match_notify_flex`, `get_publish_confirm_flex`, etc.
5. **`do_publish(uid, reply_token)`** — core publish logic: insert trip, find matches, send cards, push notifications to matched users
6. **`find_matches_v15`** — matching algorithm: direction vectors via CITY_WEIGHTS, ±1hr/±4hr time buffer, waypoint inclusion, district cluster matching
7. **Flask routes** — `/` health check, `/callback` webhook
8. **`handle_postback`** — time picker, delete, complete (→ rating prompt), rate, cancel
9. **`handle_message`** — full publish state machine + all text commands

## Database

Two modes detected by `USE_PG = bool(os.getenv('DATABASE_URL'))`:
- **SQLite** (local dev): `ridematch_v15.db`, `?` placeholders, `INSERT OR REPLACE`, `cursor.lastrowid`
- **PostgreSQL** (Render): `%s` placeholders via `q()` helper, `ON CONFLICT DO UPDATE`, `RETURNING id`

Tables: `matches` (trips), `user_state` (per-user draft state machine), `ratings` (post-trip scores)

## Publish Flow (State Machine)

`user_state.step` drives the multi-step form:
`START` → time picker → area carousel (s_city/s_dist) → `END` → area carousel (e_city/e_dist) → `DONE` → waypoint → detail Flex (人數/費用/彈性) → tag categories → `最終確認發布` → `WAIT_LINE_ID` → `do_publish()`

`WAIT_LINE_ID` is handled in the `else` fallback block of `handle_message`.

## Required Environment Variables

```
LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET
DATABASE_URL          # PostgreSQL URL (triggers PG mode)
RENDER                # any value — activates module-level keep_alive thread
```

## LINE SDK Version

Uses **`line-bot-sdk==2.x`** (NOT v3). Imports are from `linebot` not `linebot.v3`. Do not upgrade to 3.x without rewriting all handlers and Flex message constructors.
