"\"\"\"i18n — Minimal English/Hindi translation layer.\"\"\"

LOCALES = {
    \"en\": {
        \"start\": (
            \"🌊 **Welcome to OTP Ocean, {name}!**

\"
            \"Your one-stop shop for pre-loaded Telegram accounts.
\"
            \"Get OTP codes instantly for seamless Telegram logins.

\"
            \"━━━━━━━━━━━━━━━━━━━━━━━━
\"
            \"🛒 **Shop** — Browse accounts by country
\"
            \"💵 **Deposit** — Top up wallet via UPI
\"
            \"📦 **Orders** — View purchases & fetch OTPs
\"
            \"👥 **Refer** — Earn on every friend's deposit
\"
            \"🏆 **Leaderboard** — Top earners & buyers
\"
            \"━━━━━━━━━━━━━━━━━━━━━━━━

\"
            \"💡 _Tap any button below to get started!_\"
        ),
        \"btn_shop\":        \"🛒 Shop\",
        \"btn_deposit\":     \"💵 Deposit\",
        \"btn_profile\":     \"👤 Profile\",
        \"btn_orders\":      \"📦 My Orders\",
        \"btn_refer\":       \"👥 Refer & Earn\",
        \"btn_leaderboard\": \"🏆 Leaderboard\",
        \"btn_support\":     \"🛟 Support\",
        \"btn_rules\":       \"📋 Rules\",
        \"btn_help\":        \"📖 Help\",
        \"btn_balance\":     \"💰 Balance\",
        \"btn_lang\":        \"🌐 Language\",
        \"btn_back\":        \"🔙 Back\",
        \"lang_set\":        \"✅ Language set to English.\",
        \"rate_limited\":    \"⏳ Too many requests — please slow down.\",
        \"banned\":          \"🚫 You are banned from using this bot.\",
    },
    \"hi\": {
        \"start\": (
            \"🌊 **OTP Ocean में स्वागत है, {name}!**

\"
            \"प्री-लोडेड टेलीग्राम अकाउंट्स की एक जगह पर दुकान।
\"
            \"तुरंत OTP पाएँ, आसान लॉगिन।

\"
            \"━━━━━━━━━━━━━━━━━━━━━━━━
\"
            \"🛒 **दुकान** — देश के अनुसार अकाउंट देखें
\"
            \"💵 **डिपॉजिट** — UPI से वॉलेट भरें
\"
            \"📦 **ऑर्डर** — खरीदे गए अकाउंट व OTP
\"
            \"👥 **रेफर** — दोस्त के डिपॉज़िट पर कमाएँ
\"
            \"🏆 **लीडरबोर्ड** — टॉप कमाई करने वाले
\"
            \"━━━━━━━━━━━━━━━━━━━━━━━━

\"
            \"💡 _नीचे किसी बटन पर टैप करके शुरू करें!_\"
        ),
        \"btn_shop\":        \"🛒 दुकान\",
        \"btn_deposit\":     \"💵 डिपॉजिट\",
        \"btn_profile\":     \"👤 प्रोफ़ाइल\",
        \"btn_orders\":      \"📦 मेरे ऑर्डर\",
        \"btn_refer\":       \"👥 रेफर & कमाएँ\",
        \"btn_leaderboard\": \"🏆 लीडरबोर्ड\",
        \"btn_support\":     \"🛟 सहायता\",
        \"btn_rules\":       \"📋 नियम\",
        \"btn_help\":        \"📖 मदद\",
        \"btn_balance\":     \"💰 बैलेंस\",
        \"btn_lang\":        \"🌐 भाषा\",
        \"btn_back\":        \"🔙 वापस\",
        \"lang_set\":        \"✅ भाषा हिंदी पर सेट कर दी गई।\",
        \"rate_limited\":    \"⏳ बहुत तेज़ — कृपया धीमा करें।\",
        \"banned\":          \"🚫 आप इस बॉट से बैन कर दिए गए हैं।\",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    \"\"\"Get translated string. Falls back to English if key/lang missing.\"\"\"
    lang = lang if lang in LOCALES else \"en\"
    text = LOCALES[lang].get(key) or LOCALES[\"en\"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
