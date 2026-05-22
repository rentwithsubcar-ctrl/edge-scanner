import os
import json
import time
import requests
from datetime import datetime, timedelta
import anthropic

TELEGRAM_TOKEN = "8862177532:AAFNSOBLKSc_lrkKcl8KUgj-CPmVDPXZBeI"
TELEGRAM_CHAT_ID = "8972510470"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BANKROLL = 10.00

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def send_telegram(message, chat_id=TELEGRAM_CHAT_ID):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.ok
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 5, "offset": offset}
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json().get("result", [])
    except:
        return []

def scan_and_recommend():
    today = datetime.now().strftime("%A %d %B %Y")
    max_risk = round(BANKROLL * 0.1, 2)
    expiry = (datetime.now() + timedelta(days=6)).strftime("%d/%m/%Y")

    print("Calling Claude with web search...")

    prompt = (
        "Today is " + today + ". Search for current data on SPY, QQQ, and IWM ETFs.\n"
        "Search separately for: closing price, day change %, RSI(14), 50-day MA, and VIX.\n"
        "Try searches like 'SPY RSI 14 today', 'QQQ technical indicators', 'IWM 50 day moving average'.\n\n"
        "Entry rules - ALL four must pass for a BUY signal:\n"
        "RULE 1: Day drop >= 1% (PASS = dropped 1%+, FAIL = flat or up)\n"
        "RULE 2: RSI(14) <= 42 (PASS = oversold at 42 or below, FAIL = above 42)\n"
        "RULE 3: Price above 50-day MA (PASS = above MA, FAIL = below MA)\n"
        "RULE 4: VIX >= 13 (PASS = fear elevated at 13+, FAIL = only if VIX below 13)\n\n"
        "Bankroll: $" + str(BANKROLL) + ", max risk per trade: $" + str(max_risk) + ".\n\n"
        "Use EXACTLY this format:\n\n"
        "VERDICT: [BUY SPY / BUY QQQ / BUY IWM / NO TRADE]\n\n"
        "CONDITIONS:\n"
        "SPY: [day%] | RSI [value] | MA [above/below $value] | VIX [value] | [PASS/FAIL]\n"
        "QQQ: [day%] | RSI [value] | MA [above/below $value] | VIX [value] | [PASS/FAIL]\n"
        "IWM: [day%] | RSI [value] | MA [above/below $value] | VIX [value] | [PASS/FAIL]\n\n"
        "TRADE (fill in if BUY, otherwise N/A):\n"
        "Ticker: | Strike: $ | Expiry: " + expiry + " | Est. premium: $\n"
        "- Limit BUY at: $\n"
        "- Limit SELL (profit +90%): $\n"
        "- Stop SELL (loss -50%): $\n\n"
        "REASON: [2 sentences on why BUY or NO TRADE]\n\n"
        "WATCH: [what to look for tomorrow]"
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1200,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=(
            "You are an options trading analyst. Search the web thoroughly for current ETF market data. "
            "Do multiple searches to get RSI and moving average data. Never leave data as unavailable. "
            "Follow the exact output format requested."
        ),
        messages=[{"role": "user", "content": prompt}]
    )

    text = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
    print(f"Got response: {text[:100]}...")
    return text

def format_message(recommendation):
    now = datetime.now().strftime("%d %b %Y %I:%M %p")
    verdict_line = ""
    for line in recommendation.split("\n"):
        if line.strip().upper().startswith("VERDICT:"):
            verdict_line = line.strip().upper()
            break
    is_buy = "BUY" in verdict_line and "NO TRADE" not in verdict_line
    header = "🟢 *EDGE AGENT — BUY SIGNAL*" if is_buy else "⛔ *EDGE AGENT — NO TRADE*"
    return f"{header}\n_{now} AEST_\n\n{recommendation}"

def run_scan(chat_id=TELEGRAM_CHAT_ID):
    send_telegram("⏳ Scanning market conditions...", chat_id)
    try:
        recommendation = scan_and_recommend()
        message = format_message(recommendation)
        if len(message) > 4000:
            message = message[:3990] + "...\n_(truncated)_"
        send_telegram(message, chat_id)
        print("Done.")
    except Exception as e:
        send_telegram(f"⚠️ *Error:* `{str(e)}`", chat_id)
        print(f"Error: {e}")
        raise

def listen_for_commands():
    print("Listening for Telegram commands for 30s...")
    offset = None
    deadline = time.time() + 30
    while time.time() < deadline:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if text.strip().lower() in ["/scan", "/scan@stockcheckmybot"]:
                print(f"Got /scan from {chat_id}")
                run_scan(chat_id)
                return True
        time.sleep(2)
    return False

def main():
    print(f"[{datetime.now()}] Edge Scanner starting...")
    mode = os.environ.get("RUN_MODE", "cron")
    if mode == "manual":
        print("Manual mode - running scan now...")
        run_scan()
    else:
        handled = listen_for_commands()
        if not handled:
            hour = datetime.utcnow().hour
            if hour == 21:
                print("Running scheduled cron scan...")
                run_scan()
            else:
                print("No command received and not cron time. Exiting.")

if __name__ == "__main__":
    main()
