import os
import json
import time
import requests
from datetime import datetime, timedelta
import anthropic

# ── CONFIG ──
TELEGRAM_TOKEN = "8862177532:AAFNSOBLKSc_lrkKcl8KUgj-CPmVDPXZBeI"
TELEGRAM_CHAT_ID = "8972510470"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TICKERS = ["SPY", "QQQ", "IWM"]
BANKROLL = 10.00

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def send_telegram(message: str, chat_id: str = TELEGRAM_CHAT_ID):
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

def scan_and_recommend() -> str:
    """Single Claude call with web search — scan + recommend in one shot."""
    today = datetime.now().strftime("%A %d %B %Y")
    max_risk = round(BANKROLL * 0.1, 2)
    expiry = (datetime.now() + timedelta(days=6)).strftime("%d/%m/%Y")

    print("Calling Claude with web search...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=(
            "You are an options trading analyst. Search for current ETF market data "
            "then give a concise trading recommendation. Be brief and specific."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Today is {today}. Search for today's closing prices and performance for SPY, QQQ, and IWM ETFs.\n\n"
                f"Then assess each against these mean-reversion entry rules:\n"
                f"1. Day drop >= 1%\n"
                f"2. RSI(14) <= 42 (oversold)\n"
                f"3. Price above 50-day MA\n"
                f"4. VIX not below 13\n\n"
                f"Bankroll: ${BANKROLL:.2f}, max risk: ${max_risk:.2f} per trade.\n\n"
                f"Reply in this exact format:\n\n"
                f"VERDICT: [BUY ticker / NO TRADE]\n"
                f"CONDITIONS:\n"
                f"SPY: [day%] | RSI [x] | MA [above/below] | [pass/fail]\n"
                f"QQQ: [day%] | RSI [x] | MA [above/below] | [pass/fail]\n"
                f"IWM: [day%] | RSI [x] | MA [above/below] | [pass/fail]\n\n"
                f"TRADE (if BUY):\n"
                f"Strike: $x | Expiry: {expiry} | Premium: ~$x/contract\n"
                f"Buy limit: $x | Profit target: $x | Stop loss: $x\n\n"
                f"REASON: [1-2 sentences]\n\n"
                f"If no trade: what to watch for tomorrow."
            )
        }]
    )

    text = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
    print(f"Got response: {text[:100]}...")
    return text

def format_message(recommendation: str) -> str:
    now = datetime.now().strftime("%d %b %Y %I:%M %p")
    is_buy = "BUY" in recommendation.upper() and "NO TRADE" not in recommendation.upper().split("\n")[0]
    header = "🟢 *EDGE AGENT — BUY SIGNAL*" if is_buy else "⛔ *EDGE AGENT — NO TRADE*"
    return f"{header}\n_{now} AEST_\n\n{recommendation}"

def run_scan(chat_id: str = TELEGRAM_CHAT_ID):
    send_telegram("⏳ Scanning market conditions...", chat_id)
    try:
        recommendation = scan_and_recommend()
        message = format_message(recommendation)
        send_telegram(message, chat_id)
        print("Done.")
    except Exception as e:
        send_telegram(f"⚠️ *Error:* `{str(e)}`", chat_id)
        print(f"Error: {e}")
        raise

def listen_for_commands():
    """Listen for /scan command for 30 seconds, then exit."""
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
                return True  # handled a command, exit

        time.sleep(2)

    return False  # no command received

def main():
    print(f"[{datetime.now()}] Edge Scanner starting...")

    # Check if this is a cron run (scheduled) or triggered manually
    # Either way: first check for /scan commands, then run scheduled scan if it's cron time
    
    hour = datetime.utcnow().hour
    is_cron_time = (hour == 21)  # 9pm UTC = 7am AEST

    # Always listen for /scan commands first
    handled = listen_for_commands()

    # If no command was sent AND it's cron time, run the scheduled scan
    if not handled and is_cron_time:
        print("Running scheduled cron scan...")
        run_scan()
    elif not handled:
        print("No command received and not cron time. Exiting.")

if __name__ == "__main__":
    main()
