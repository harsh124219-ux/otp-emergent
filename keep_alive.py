"""keep_alive.py — self-pinger to prevent Render/Railway/Heroku eco-dyno sleep."""

import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)

PING_INTERVAL_SECONDS = 14 * 60  # 14 minutes


async def self_ping_loop() -> None:
    """Continuously pings APP_URL/health every 14 minutes. No-op if APP_URL unset."""
    from info import APP_URL
    if not APP_URL:
        logger.info("ℹ️  APP_URL not set — keep-alive disabled.")
        return

    ping_url = f"{APP_URL}/health"
    logger.info(f"💓 Keep-alive → {ping_url} (every {PING_INTERVAL_SECONDS // 60} min)")

    await asyncio.sleep(30)

    fails = 0
    while True:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.get(ping_url) as r:
                    if r.status == 200:
                        fails = 0
                    else:
                        fails += 1
                        logger.warning(f"⚠️  Self-ping {r.status} (#{fails})")
        except Exception as e:
            fails += 1
            logger.warning(f"⚠️  Self-ping error: {e} (#{fails})")

        if fails == 3:
            logger.error("❌ 3 consecutive self-ping failures! Check APP_URL.")

        await asyncio.sleep(PING_INTERVAL_SECONDS)
