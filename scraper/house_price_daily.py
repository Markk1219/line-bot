#!/usr/bin/env python3
"""
新北市預售屋每日快報 - 每天早上 8:00（台北時間）執行
"""
import os, json, subprocess, re
from datetime import datetime, timezone, timedelta

tz_taipei = timezone(timedelta(hours=8))
now = datetime.now(tz_taipei)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN_HOUSE"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = [
    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "-H", "Referer: https://dualtaipei.datazen.info/newtaipei",
    "-H", "Accept: application/json"
]

def fetch(url):
    r = subprocess.run(["curl", "-s"] + HEADERS + [url], capture_output=True, text=True)
    return json.loads(r.stdout)

def format_rows(transactions):
    lines = []
    for t in transactions:
        d = datetime.fromisoformat(t['date'].replace('Z', '+00:00')).astimezone(tz_taipei)
        lines.append(f"  • {d.strftime('%m/%d')} {t['projectName']} | {t['floor']} | {round(t['area'],1)}坪 | {t['unitPrice']}萬/坪 | 總價{t['totalPrice']}萬")
    return "\n".join(lines)

targets = [
    ("📍 中和區", "https://dualtaipei.datazen.info/api/newtaipei/district/%E4%B8%AD%E5%92%8C%E5%8D%80?limit=50&offset=0"),
    ("📍 永和區", "https://dualtaipei.datazen.info/api/newtaipei/district/%E6%B0%B8%E5%92%8C%E5%8D%80?limit=15&offset=0"),
    ("📍 三重區", "https://dualtaipei.datazen.info/api/newtaipei/district/%E4%B8%89%E9%87%8D%E5%8D%80?limit=15&offset=0"),
    ("📍 新店區", "https://dualtaipei.datazen.info/api/newtaipei/district/%E6%96%B0%E5%BA%97%E5%8D%80?limit=15&offset=0"),
]

msg = f"🏠 新北市預售屋每日快報\n📅 {now.strftime('%Y-%m-%d')}\n"

all_zhonghe = []
for name, url in targets:
    data = fetch(url)
    txns = data.get('transactions', [])
    if '中和區' in name:
        all_zhonghe = txns
        non_fengsen = [t for t in txns if t['projectName'] != '豐森大境'][:15]
        msg += f"\n{name}（15筆）\n{format_rows(non_fengsen)}\n"
    else:
        msg += f"\n{name}（15筆）\n{format_rows(txns[:15])}\n"

fengsen_txns = [t for t in all_zhonghe if t['projectName'] == '豐森大境'][:15]
msg += f"\n🏢 豐森大境（{len(fengsen_txns)}筆）\n{format_rows(fengsen_txns)}\n"

r = subprocess.run([
    "curl", "-s", "-X", "POST",
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
    "-d", f"chat_id={CHAT_ID}",
    "--data-urlencode", f"text={msg}"
], capture_output=True, text=True)

ok = re.search(r'"ok":(true|false)', r.stdout)
print("推播結果:", ok.group(0) if ok else r.stdout[:200])
