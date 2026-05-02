#!/usr/bin/env python3
"""
美股每日快報 - 每天早上 8:00（台北時間）執行
翻譯由 Claude API 完成（需 CLAUDE_API_KEY 環境變數）
"""
import os, subprocess, json, re, xml.etree.ElementTree as ET, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

tz_taipei = timezone(timedelta(hours=8))
now = datetime.now(tz_taipei)
date_str = now.strftime('%Y-%m-%d')

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN_MARKET"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
M7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

def fetch(url, extra=[]):
    r = subprocess.run(["curl", "-s", "-A", "Mozilla/5.0", "-L"] + extra + [url], capture_output=True, text=True)
    return r.stdout

def fetch_json(url):
    try: return json.loads(fetch(url))
    except: return None

def send_telegram(msg):
    subprocess.run([
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        "-d", f"chat_id={CHAT_ID}",
        "--data-urlencode", f"text={msg}"
    ], capture_output=True, text=True)

def gtranslate(text):
    try:
        encoded = urllib.parse.quote(text)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-TW&dt=t&q={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return "".join(x[0] for x in result[0] if x[0])
    except:
        return text

def claude_translate(news_items):
    lines = []
    for i, (t, d) in enumerate(news_items[:5]):
        zh_title = gtranslate(t)
        lines.append(f"{i+1}. {zh_title}\n   {d}")
    return "\n\n".join(lines)

# ── 1. 大盤 ──────────────────────────────────
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

# ── 2. 經濟數據 ──────────────────────────────
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
                        "imp": imp,
                        "name": nm_m.group(1).strip(),
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

# ── 3. 新聞 ──────────────────────────────────
news_items = []
for url in ["https://feeds.content.dowjones.io/public/rss/mw_topstories",
            "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"]:
    rraw = fetch(url)
    try:
        root = ET.fromstring(rraw)
        for item in root.findall('.//item')[:8]:
            t = item.findtext('title','').strip()
            d = re.sub(r'<[^>]+>', '', item.findtext('description','').strip())[:150]
            if t and t not in [x[0] for x in news_items]:
                news_items.append((t, d))
    except: pass
news_items = news_items[:8]

# ── 4. M7 ────────────────────────────────────
m7 = []
for sym in M7:
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

# ── 5. 翻譯新聞 ──────────────────────────────
news_zh = claude_translate(news_items)

# ── 6. 組裝訊息 ──────────────────────────────
parts = [f"📰 美股每日快報\n📅 {date_str}｜盤前版"]
parts.append("\n━━━ 昨日收盤 ━━━\n" + ("\n".join(mkt_lines) if mkt_lines else "（資料暫不可用）"))
if econ_done_lines:
    parts.append("\n━━━ 昨日經濟數據 ━━━\n" + "\n".join(econ_done_lines))
else:
    parts.append("\n━━━ 昨日經濟數據 ━━━\n昨日無重大數據公布")
if econ_today_lines:
    parts.append("\n━━━ 今日待公布 ━━━\n" + "\n".join(econ_today_lines))
parts.append("\n━━━ 今日要事 Top 5 ━━━\n" + news_zh)
m7_str = "\n".join([f"{a} {s}: ${p:.2f} ({c:+.2f}%)" for s,p,c,a in m7])
parts.append("\n━━━ M7 異動 ━━━\n" + m7_str)
parts.append("\n━━━\n僅供參考，非投資建議")

msg = "\n".join(parts)

# ── 7. 推播 ──────────────────────────────────
send_telegram(msg)
print(f"推播完成，訊息長度：{len(msg)}")
