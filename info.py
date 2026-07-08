"""
info.py — All configuration & text strings for OTP Ocean.

╔══════════════════════════════════════════════════════════════╗
║  IMPORTANT: FILL THESE VALUES BEFORE DEPLOYING               ║
║  You can either:                                             ║
║    (a) Set them as environment variables on Heroku/Railway   ║
║    (b) Hard-code the defaults below (NOT recommended for     ║
║        public repos — anyone can see your token!)            ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════
#  CORE ENVIRONMENT VARIABLES  (SET THESE ON HEROKU / RAILWAY)
# ══════════════════════════════════════════════════════════════

# Telegram Bot API — Get from @BotFather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Telegram API credentials — Get from https://my.telegram.org
API_ID   = int(os.environ.get("API_ID", "0") or "0")
API_HASH = os.environ.get("API_HASH", "")

# Your Telegram user ID (message @userinfobot to get it)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or "0")

# The log group where payment approvals + sale logs go
# (Create a group, add bot as admin, add @getidsbot, copy the -100... ID)
LOG_GROUP = int(os.environ.get("LOG_GROUP", "0") or "0")

# MongoDB connection URI (get free 512MB cluster from https://cloud.mongodb.com)
MONGO_URL = os.environ.get("MONGO_URL", "")

# Web server port (Heroku sets this automatically; Railway uses 8080)
PORT = int(os.environ.get("PORT", "8080") or "8080")

# App URL — set AFTER first deploy to enable keep-alive self-ping
# e.g. https://your-app.up.railway.app  or  https://your-app.herokuapp.com
APP_URL = os.environ.get("APP_URL", "").strip().rstrip("/")

# Support username (shown in error messages)
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "@OTPOceanSupportBot")

# ══════════════════════════════════════════════════════════════
# Loaded from locales/*.py — see handlers/i18n.py for translation helper
DEFAULT_LANG = "en"
SUPPORTED_LANGS = ["en", "hi"]
