import os
import json
import requests
from datetime import datetime, timedelta
import anthropic

# ── CONFIG ──
TELEGRAM_TOKEN = "8862177532:AAFNSOBLKSc_lrkKcl8KUgj-CPmVDPXZBeI"
TELEGRAM_CHAT_ID = "8972510470"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TICKERS = ["SPY", "QQQ", "IWM"]
BANKROLL = 10.00

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, json=payload, timeout=10)
    return r.ok

def scan_market() -> dict:
    """Use Claude + web search to scan market conditions."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.now().strftime("%A, %d %B %Y")
    ticker_str = ", ".join(TICKERS)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=(
            "You are a financial data analyst. Search the web for current ETF market data "
            "and respond ONLY with a valid JSON object. No markdown fences, no explanation — raw JSON only."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Today is {today}. Search for the latest market data for {ticker_str}. "
                f"Return ONLY this JSON:\n"
                f'{{"results":[{{"ticker":"SPY","price":590.12,"dayChangePct":-1.45,"rsi14":36.2,"aboveMa50":true,"ma50":578.50,"ivEnvironment":"ELEVATED"}}],"dataDate":"2025-05-07"}}\n'
                f"ivEnvironment: LOW if VIX<13, NORMAL if 13-20, ELEVATED if >20. "
                f"One entry per ticker. Raw JSON only."
            )
        }]
    )

    raw = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    start = raw.find("{")
    if start > 0:
        raw = raw[start:]
    return json.loads(raw)

def get_recommendation(scan_results: list) -> str:
    """Ask Claude for a trade recommendation based on scan data."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    summary = "\n".join(
        f"{r['ticker']}: Price ${r['price']:.2f}, Day {r['dayChangePct']:.2f}%, "
        f"RSI {r['rsi14']}, 50MA {'ABOVE' if r['aboveMa50'] else 'BELOW'} (${r['ma50']:.2f}), "
        f"IV: {r['ivEnvironment']}"
        for r in scan_results
    )

    today = datetime.now().strftime("%d/%m/%Y")
    expiry_range = (datetime.now() + timedelta(days=5)).strftime("%d/%m") + \
                   " – " + (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")
    max_risk = round(BANKROLL * 0.1, 2)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": (
                f"You are an options trading agent for an Australian retail trader using Moomoo. "
                f"They sleep during US hours and set GTC orders before bed. "
                f"Bankroll: ${BANKROLL:.2f}, max risk per trade: ${max_risk:.2f}.\n\n"
                f"Live scan ({today}):\n{summary}\n\n"
                f"Strategy: ETF Mean Reversion Weekly Calls.\n"
                f"Entry requires ALL of: day drop ≥1%, RSI(14) ≤42, price above 50MA, IV not LOW.\n\n"
                f"Respond in this exact format:\n"
                f"VERDICT: [BUY / NO TRADE / WAIT]\n\n"
                f"TRADE:\n"
                f"- Ticker: \n"
                f"- Strike: $\n"
                f"- Expiry: [{expiry_range}]\n"
                f"- Premium per contract: $\n"
                f"- Max spend: ${max_risk:.2f}\n\n"
                f"ORDERS:\n"
                f"- Limit BUY at: $\n"
                f"- Limit SELL (profit target ~90%): $\n"
                f"- Stop SELL (50% loss limit): $\n\n"
                f"REASONING: [2-3 sentences]\n\n"
                f"If NO TRADE: explain which conditions failed and what to watch for."
            )
        }]
    )

    return "".join(b.text for b in response.content if hasattr(b, "text")).strip()

def format_telegram_message(recommendation: str, scan_results: list) -> str:
    """Format the final Telegram message."""
    now = datetime.now().strftime("%d %b %Y, %I:%M %p AEST")

    # Build condition summary
    conditions = []
    for r in scan_results:
        move_ok = "✅" if r["dayChangePct"] <= -1 else "❌"
        rsi_ok  = "✅" if r["rsi14"] <= 42 else "❌"
        ma_ok   = "✅" if r["aboveMa50"] else "❌"
        iv_ok   = "✅" if r["ivEnvironment"] != "LOW" else "❌"
        conditions.append(
            f"*{r['ticker']}* ${r['price']:.2f} ({r['dayChangePct']:+.2f}%)\n"
            f"{move_ok} Drop≥1%  {rsi_ok} RSI {r['rsi14']}  {ma_ok} 50MA  {iv_ok} IV"
        )

    verdict_line = ""
    for line in recommendation.split("\n"):
        if line.startswith("VERDICT:"):
            verdict_line = line.strip()
            break

    is_buy = "BUY" in verdict_line and "NO" not in verdict_line
    header = "🟢 *EDGE AGENT — BUY SIGNAL*" if is_buy else "🔴 *EDGE AGENT — NO TRADE*"

    msg = (
        f"{header}\n"
        f"_{now}_\n\n"
        f"*Market Conditions:*\n"
        + "\n\n".join(conditions) +
        f"\n\n*Recommendation:*\n{recommendation}"
    )

    # Telegram has 4096 char limit
    if len(msg) > 4000:
        msg = msg[:3990] + "...\n_(truncated)_"

    return msg

def main():
    print(f"[{datetime.now()}] Edge Scanner starting...")

    # 1. Send a "scanning" notice
    send_telegram("⏳ *EDGE AGENT* — Running daily market scan...")

    try:
        # 2. Scan market
        print("Scanning market...")
        scan_data = scan_market()
        results = scan_data.get("results", [])
        if not results:
            raise ValueError("No scan results returned")
        print(f"Got data for: {[r['ticker'] for r in results]}")

        # 3. Get AI recommendation
        print("Getting recommendation...")
        recommendation = get_recommendation(results)
        print(f"Recommendation preview: {recommendation[:100]}...")

        # 4. Format and send
        message = format_telegram_message(recommendation, results)
        success = send_telegram(message)
        print(f"Telegram sent: {success}")

    except Exception as e:
        error_msg = f"⚠️ *EDGE AGENT ERROR*\n`{str(e)}`\nCheck Railway logs."
        send_telegram(error_msg)
        print(f"Error: {e}")
        raise

if __name__ == "__main__":
    main()
