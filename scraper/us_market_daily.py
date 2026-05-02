#!/usr/bin/env python3
"""
美股每日快報 - Gemini 驅動版
每天早上 8:00（台北時間）執行
"""
import os, subprocess, json, re, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

tz_taipei = timezone(timedelta(hours=8))
now = datetime.now(tz_taipei)
date_str = now.strftime('%Y-%m-%d')
weekday_zh = ["一","二","三","四","五","六","日"][now.weekday()]

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN_MARKET"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

def fetch(url, extra=[]):
    r = subprocess.run(["curl", "-s", "-A", "Mozilla/5.0", "-L"] + extra + [url], capture_output=True, text=True)
    return r.stdout

def fetch_json(url):
    try: return json.loads(fetch(url))
    except: return None

def send_telegram(msg):
    r = subprocess.run([
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        "-d", f"chat_id={CHAT_ID}",
        "--data-urlencode", f"text={msg}"
    ], capture_output=True, text=True)
    print("Telegram:", r.stdout[:200])

def gemini(prompt, model="gemini-2.5-pro"):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 3000, "temperature": 0.7}
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}",
        data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"Gemini error: {e}")
        return None

# ── 1. 大盤數據 ──────────────────────────────
mkt_lines = []
for name, sym in [("SPY","SPY"),("QQQ","QQQ"),("道瓊","%5EDJI"),("納指","%5EIXIC"),("VIX","%5EVIX")]:
    d = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2d")
    if d:
        try:
            meta = d['chart']['result'][0]['meta']
            price = meta.get('regularMarketPrice', 0)
            prev  = meta.get('chartPreviousClose', 0)
            vol   = meta.get('regularMarketVolume', 0)
            chg   = ((price - prev) / prev) * 100 if prev else 0
            arrow = "🟢" if chg >= 0 else "🔴"
            vol_str = f"  Vol {vol/1e6:.0f}M" if vol and sym in ["SPY","QQQ"] else ""
            mkt_lines.append(f"{arrow} {name}: {price:,.2f} ({chg:+.2f}%){vol_str}")
        except: pass

# ── 2. M7 ────────────────────────────────────
m7 = []
for sym in ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA"]:
    d = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2d")
    if d:
        try:
            meta = d['chart']['result'][0]['meta']
            price = meta.get('regularMarketPrice', 0)
            prev  = meta.get('chartPreviousClose', 0)
            chg   = ((price - prev) / prev) * 100 if prev else 0
            m7.append((sym, price, chg, "🟢" if chg >= 0 else "🔴"))
        except: pass
m7.sort(key=lambda x: abs(x[2]), reverse=True)

# ── 3. 經濟數據 ──────────────────────────────
def get_econ(tab):
    raw = fetch("https://www.investing.com/economic-calendar/Service/getCalendarFilteredData",
        ["-X","POST","-H","X-Requested-With: XMLHttpRequest",
         "-H","Content-Type: application/x-www-form-urlencoded",
         "--data",f"country[]=5&timeZone=55&timeFilter=timeOnly&currentTab={tab}&limit_from=0"])
    try:
        html = json.loads(raw).get('data','')
        rows = re.findall(r'id="eventRowId_\d+"[^>]*>(.*?)</tr>', html, re.DOTALL)
        out = []
        for row in rows:
            nm_m = re.search(r'class="[^"]*event[^"]*"[^>]*>\s*<a[^>]*>([^<]+)<', row)
            ac_m = re.search(r'id="detailActual_\d+"[^>]*>([^<]*)<', row)
            fc_m = re.search(r'id="detailForecast_\d+"[^>]*>([^<]*)<', row)
            pv_m = re.search(r'id="detailPrevious_\d+"[^>]*>([^<]*)<', row)
            tm_m = re.search(r'class="[^"]*time[^"]*"[^>]*>([^<]+)<', row)
            bl_m = re.search(r'data-img_key="bull(\d)"', row)
            if nm_m:
                imp = int(bl_m.group(1)) if bl_m else 0
                if imp >= 2:
                    out.append({
                        "imp": imp, "name": nm_m.group(1).strip(),
                        "actual": ac_m.group(1).strip() if ac_m else '',
                        "forecast": fc_m.group(1).strip() if fc_m else '',
                        "prev": pv_m.group(1).strip() if pv_m else '',
                        "time": tm_m.group(1).strip() if tm_m else '',
                    })
        return out
    except: return []

yd = get_econ("yesterday")
td = get_econ("today")

econ_done_lines = []
for e in [x for x in yd if x["actual"]][:5]:
    star = "🔴" if e["imp"] == 3 else "🟡"
    beat = ""
    try:
        a = float(re.sub(r'[^\d.\-]', '', e["actual"]))
        f = float(re.sub(r'[^\d.\-]', '', e["forecast"]))
        beat = "  ↑優於預期" if a > f else ("  ↓遜於預期" if a < f else "  →符合預期")
    except: pass
    econ_done_lines.append(f"{star} {e['name']}\n  實際 {e['actual']} / 預期 {e['forecast']} / 前值 {e['prev']}{beat}")

econ_today_lines = []
for e in [x for x in td if not x["actual"]][:4]:
    star = "🔴" if e["imp"] == 3 else "🟡"
    econ_today_lines.append(f"{star} {e['time']} {e['name']}（預期 {e['forecast'] or '—'}）")

# ── 4. 大盤數據摘要給 Gemini 參考 ────────────
mkt_summary = "\n".join(mkt_lines) if mkt_lines else "資料暫不可用"
m7_summary = "\n".join([f"{a} {s}: ${p:.2f} ({c:+.2f}%)" for s,p,c,a in m7])

# ── 5. 讓 Gemini 搜尋新聞並整理 ─────────────
prompt = f"""今天是 {date_str}（星期{weekday_zh}），台北時間早上 8 點。

你是一個專業的財經新聞機器人，請幫我整理今日的國際財經與台灣時事，著重在經濟與股市。

以下是今日的大盤數據供你參考：
{mkt_summary}

M7 個股：
{m7_summary}

請用繁體中文，按以下格式輸出（直接輸出內容，不要加任何前言）：

早安！今天是 {date_str} 星期{weekday_zh}。

[用1-2句話點出今日最重要的市場主題]

📊 今日財經時事

1. [主題標題]
[3-5條重點，每條以「・」開頭，包含具體數字和影響]

2. [主題標題]
[3-5條重點]

3. [主題標題]
[3-5條重點]

4. 台灣股市與產業
[3-5條台灣相關重點]

💡 點評：
[2-3句整體判斷，指出今日最值得關注的風險或機會]

━━━
僅供參考，非投資建議"""

news_section = gemini(prompt)
if not news_section:
    news_section = "（今日新聞整理暫時無法取得）"

# ── 6. 組裝訊息 ──────────────────────────────
parts = [f"📰 美股每日快報\n📅 {date_str}｜盤前版"]
parts.append("\n━━━ 昨日收盤 ━━━\n" + (mkt_summary if mkt_lines else "（資料暫不可用）"))

if econ_done_lines:
    parts.append("\n━━━ 昨日經濟數據 ━━━\n" + "\n".join(econ_done_lines))
else:
    parts.append("\n━━━ 昨日經濟數據 ━━━\n昨日無重大數據公布")

if econ_today_lines:
    parts.append("\n━━━ 今日待公布 ━━━\n" + "\n".join(econ_today_lines))

parts.append("\n━━━ 今日財經要聞 ━━━\n" + news_section)

m7_str = "\n".join([f"{a} {s}: ${p:.2f} ({c:+.2f}%)" for s,p,c,a in m7])
parts.append("\n━━━ M7 異動 ━━━\n" + m7_str)

msg = "\n".join(parts)

# ── 7. 推播 ──────────────────────────────────
send_telegram(msg)
print(f"推播完成，訊息長度：{len(msg)}")
