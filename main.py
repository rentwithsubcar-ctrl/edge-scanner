import os
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
    try:
        r = requests.get(url, params={"timeout": 5, "offset": offset}, timeout=10)
        return r.json().get("result", [])
    except:
        return []

def scan_and_recommend():
    today = datetime.now().strftime("%A %d %B %Y")
    max_risk = round(BANKROLL * 0.1, 2)
    expiry = (datetime.now() + timedelta(days=6)).strftime("%d/%m/%Y")

    print("Calling Claude...")

    # Single concise prompt — no multiple searches, fast response
    prompt = (
        "Today is " + today + ". Do ONE web search for 'SPY QQQ IWM ETF performance today RSI technical analysis' "
        "and use the results to fill in this exact template. Estimate any missing values from context.\n\n"
        "VERDICT: [BUY SPY / BUY QQQ / BUY IWM / NO TRADE]\n\n"
        "CONDITIONS:\n"
        "SPY: [day%] | RSI [value] | MA [above/below] | [PASS/FAIL]\n"
        "QQQ: [day%] | RSI [value] | MA [above/below] | [PASS/FAIL]\n"
        "IWM: [day%] | RSI [value] | MA [above/below] | [PASS/FAIL]\n\n"
        "VIX: [value] | [PASS if >=13 / FAIL if <13]\n\n"
        "TRADE (if BUY only):\n"
        "Ticker: | Strike: $ | Expiry: " + expiry + "\n"
        "Buy limit: $ | Profit target: $ | Stop loss: $\n\n"
        "REASON: [1-2 sentences]\n"
        "WATCH: [1 sentence for tomorrow]\n\n"
        "Rules: BUY needs ALL: drop>=1%, RSI<=42, price above 50MA, VIX>=13. "
        "Max spend: $" + str(max_risk) + ". Reply with the template only, no preamble."
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        tool_choice={"type": "auto"},
        system="You are a concise options trading analyst. Do exactly one web search, fill in the template, stop.",
        messages=[{"role": "user", "content": prompt}]
    )

    text = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
    print(f"Response: {text[:120]}...")
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
    msg = f"{header}\n_{now} AEST_\n\n{recommendation}"
    return msg[:4000]

def run_scan(chat_id=TELEGRAM_CHAT_ID):
    send_telegram("⏳ Scanning...", chat_id)
    try:
        rec = scan_and_recommend()
        send_telegram(format_message(rec), chat_id)
        print("Done.")
    except Exception as e:
        send_telegram(f"⚠️ Error: {str(e)}", chat_id)
        print(f"Error: {e}")

def listen_for_commands():
    print("Listening for /scan for 30s...")
    offset = None
    deadline = time.time() + 30
    while time.time() < deadline:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if "/scan" in text.lower():
                print(f"Got /scan from {chat_id}")
                run_scan(chat_id)
                return True
        time.sleep(2)
    return False

def main():
    print(f"[{datetime.now()}] Starting...")
    mode = os.environ.get("RUN_MODE", "cron")
    if mode == "manual":
        run_scan()
    else:
        handled = listen_for_commands()
        if not handled:
            if datetime.utcnow().hour == 21:
                run_scan()
            else:
                print("Not cron time. Exiting.")

if __name__ == "__main__":
    main()
