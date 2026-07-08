"# 🌊 OTP Ocean Bot v2

Telegram bot for selling pre-loaded Telegram accounts with wallet, referral, leaderboard, multi-language, and OTP fetch.

## 🐛 THE BUG THAT WAS FIXED

**Silent failure**: previously the bot started successfully, showed no errors in logs, but never responded to any Telegram command.

**Cause**: `@app.on_message()` (global debug logger) was registered in the default handler group (`group=0`) — same as all the real handlers. In Pyrogram, **only ONE handler per group fires per update**. The debug logger's filter matches everything, so it silently consumed every incoming message before any command handler could run.

**Fix**: The debug logger now lives in `group=-1`, a separate group. All handlers now fire correctly.

## ✨ New Features

- 👥 **Referral system** — admin sets percent via `/setrefer <percent>`. Set to `0` to disable. Referrer gets `percent%` of every referred user's approved deposit. Optional min-deposit threshold via `/setmindep`.
- 🏆 **Leaderboard** — top 10 referrers + top 10 depositors, visible to all users.
- 🌐 **Multi-language** — English + Hindi. `/language` or main-menu button.
- 🚫 **Ban / unban** — `/ban <uid>`, `/unban <uid>`.
- 🎁 **Welcome bonus** — `/setwelcome <amt>` grants amount to every new user.
- ⚡ **Rate limiting** — 20 messages / 30s per user (anti-spam).
- 💤 **Sleep fix** — aiohttp `/health` endpoint + self-ping every 14 min (needs `APP_URL`).
- 🛡️ **All existing features intact**: shop, deposit, orders, OTP fetch, `/login` interactive setup, FSub, payment approve/reject.

## 🚀 Deploy on Heroku

```bash
git init
git add .
git commit -m \"OTP Ocean v2\"
heroku create your-app-name
heroku config:set BOT_TOKEN=... API_ID=... API_HASH=... ADMIN_ID=... LOG_GROUP=... MONGO_URL=...
git push heroku main
heroku config:set APP_URL=https://your-app-name.herokuapp.com   # after first deploy
```

Or click \"Deploy to Heroku\" via `app.json`.

## 🚂 Deploy on Railway

1. Push code to a GitHub repo.
2. https://railway.app → **New Project** → **Deploy from GitHub repo**.
3. In **Variables** tab, set `BOT_TOKEN`, `API_ID`, `API_HASH`, `ADMIN_ID`, `LOG_GROUP`, `MONGO_URL`.
4. Go to **Settings → Networking → Generate Domain**.
5. Set `APP_URL=https://your-app.up.railway.app` so keep-alive activates.

## 📋 Required env variables

| Key | Where to get |
|-----|---|
| `BOT_TOKEN` | @BotFather → `/newbot` |
| `API_ID`, `API_HASH` | https://my.telegram.org |
| `ADMIN_ID` | Message @userinfobot |
| `LOG_GROUP` | Create group, add bot as admin, get ID from @getidsbot |
| `MONGO_URL` | https://cloud.mongodb.com (free M0) — whitelist `0.0.0.0/0` |
| `APP_URL` | Your deployed URL (set after first deploy for keep-alive) |

## ⚙️ First-time admin setup (via Telegram)

```
/setupi rahul@paytm Rahul
/fa2 MyStrongPass123
/recovery you@gmail.com
/setrefer 5              # 5% referral commission (0 = disabled)
/setmindep 100           # min ₹100 deposit to trigger bonus (0 = any)
/setwelcome 10           # ₹10 welcome bonus for new users
/setfsub                 # add force-subscribe channels
/login                   # interactively add first account
```

## 🔧 Referral logic

- User A shares `https://t.me/YourBot?start=<A_ID>`.
- User B taps → `referred_by` is set to `A` (one-time; can't be overwritten).
- When B's deposit is **approved**, if `referral_percent > 0` AND deposit ≥ `min_deposit`, A instantly gets `deposit_amount * percent / 100` credited to wallet + `referral_earnings`.
- A gets a Telegram notification about the bonus.
- Set `/setrefer 0` to pause the program (no bonuses trigger).

## 🧠 Architecture

```
main.py            → Entry, routing, rate limit, keep-alive server
info.py            → Env vars (all blank — set at deploy time)
database.py        → MongoDB layer with referral support
keep_alive.py      → Self-ping loop
handlers/
  ├── i18n.py      → English / Hindi translations
  ├── user.py      → Menus, deposit flow, referral, leaderboard, language
  ├── shop.py      → Shop browsing, atomic purchase, OTP fetch
  ├── admin.py     → All admin commands
  ├── payment.py   → Approve/reject payments + referral bonus trigger
  ├── session.py   → /login flow with 2FA & recovery-email automation
  └── fsub.py      → Force-subscribe enforcement
```

## 🩹 Troubleshooting

**Bot builds fine but never responds** → this exact bug is now fixed. If it recurs, check that no new `@app.on_message()` was added without a `group=` argument.

**MongoDB connection failed** → URL-encode special chars in password (`@` → `%40`), whitelist `0.0.0.0/0` in Atlas Network Access.

**Sleep on free tier** → set `APP_URL` env var to your deployed URL; the self-pinger will hit `/health` every 14 min.

**Referral not paying out** → check `/stats` — the `Referral %` line must be > 0, and the deposit must meet `min_deposit`.
"
