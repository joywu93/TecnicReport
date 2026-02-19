import yfinance as yf
import pandas as pd
import os
import re
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone

# ==========================================
# 🔧 系統設定 (112 檔同步)
# ==========================================
STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2228": "劍麟", "2313": "華通", "2317": "鴻海", "2327": "國巨", "2330": "台積電",
    "2344": "華邦電", "2368": "金像電", "2376": "技嘉", "2377": "微星", "2379": "瑞昱",
    "2382": "廣達", "2383": "台光電", "2397": "友通", "2404": "漢唐", "2408": "南亞科",
    "2439": "美律", "2441": "超豐", "2449": "京元電子", "2454": "聯發科", "2493": "揚博",
    "2615": "萬海", "3005": "神基", "3014": "聯陽", "3017": "奇鋐", "3023": "信邦",
    "3030": "德律", "3037": "欣興", "3042": "晶技", "3078": "僑威", "3163": "波若威",
    "3167": "大量", "3217": "優群", "3219": "倚強科", "3227": "原相", "3231": "緯創",
    "3264": "欣銓", "3265": "台星科", "3303": "岱稜", "3357": "臺慶科", "3402": "漢科",
    "3406": "玉晶光", "3416": "融程電", "3441": "聯一光", "3450": "聯鈞", "3455": "由田",
    "3479": "安勤", "3483": "力致", "3484": "崧騰", "3515": "華擎", "3526": "凡甲",
    "3548": "兆利", "3570": "大塚", "3596": "智易", "3679": "新至陞", "3711": "日月光投控",
    "3712": "永崴投控", "4554": "橙的", "4760": "勤凱", "4763": "材料*-KY", "4766": "南寶",
    "4915": "致伸", "4953": "緯軟", "4961": "天鈺", "4979": "華星光", "5225": "東科-KY",
    "5236": "凌陽創新", "5284": "jpp-KY", "5388": "中磊", "5439": "高技", "5871": "中租-KY",
    "6104": "創惟", "6121": "新普", "6139": "亞翔", "6143": "振曜", "6158": "禾昌",
    "6176": "瑞儀", "6187": "萬潤", "6197": "佳必琪", "6203": "海韻電", "6221": "晉泰",
    "6227": "茂崙", "6257": "矽格", "6261": "久元", "6274": "台燿", "6278": "台表科",
    "6285": "啟碁", "6290": "良維", "6538": "倉和", "6579": "研揚", "6605": "帝寶",
    "6613": "朋億*", "6629": "泰金-KY", "6651": "全宇昕", "6667": "信紘科", "6768": "志強-KY",
    "6788": "華景電", "6894": "衛司特", "6951": "靑新-創", "6967": "汎瑋材料", "6996": "力領科技",
    "8081": "致新", "8358": "金居", "8432": "東生華", "8473": "山林水", "8938": "明安",
    "9914": "美利達", "9939": "宏全"
}

MY_GMAIL = os.environ.get("GMAIL_USER")
MY_PWD = os.environ.get("GMAIL_PASSWORD")

# --- 核心邏輯：與網頁完全同步 ---
def analyze_strategy(df):
    close = df['Close']
    volume = df['Volume']
    if len(close) < 240: return "資料不足", 0, 0, "", False, ""
    
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price
    
    sma5 = close.rolling(5).mean()
    sma10 = close.rolling(10).mean()
    sma20 = close.rolling(20).mean()
    sma60 = close.rolling(60).mean()
    sma240 = close.rolling(240).mean()
    
    v5, v10, v20, v60, v240 = sma5.iloc[-1], sma10.iloc[-1], sma20.iloc[-1], sma60.iloc[-1], sma240.iloc[-1]
    p5, p10, p20, p60 = sma5.iloc[-2], sma10.iloc[-2], sma20.iloc[-2], sma60.iloc[-2]

    # 年線高低
    high_240 = close.rolling(240).max().iloc[-1]
    low_240 = close.rolling(240).min().iloc[-1]
    pos_msg = ""
    if high_240 > low_240:
        pos_rank = (curr_price - low_240) / (high_240 - low_240)
        if pos_rank >= 0.95: pos_msg = f"⚠️ 年線高點區(M頭風險)"
        elif pos_rank <= 0.05: pos_msg = f"✨ 年線低點區(W底機會)"

    messages = []
    is_alert = False
    bias_val = ((curr_price - v60) / v60) * 100
    bias_msg = ""
    if bias_val >= 30:
        bias_msg = f"🔥 乖離過大(60SMA:{v60:.2f})"
        is_alert = True
    elif bias_val >= 15:
        bias_msg = f"🔸 乖離偏高(60SMA:{v60:.2f}) | 提防破5SMA({v5:.2f})"

    # 均線糾結判斷
    p_min_ma = min(p5, p10, p20)
    is_entangled_yesterday = (max(p5, p10, p20) - p_min_ma) / p_min_ma < 0.02

    # 爆量突破優先
    if is_entangled_yesterday and curr_vol > prev_vol * 1.5 and pct_change >= 0.05:
        msg = f"🌀 均線糾結突破 (防假破，守{prev_price:.2f})"
        if curr_price < v60: msg += " | ⚠️ 60SMA壓力"
        messages.append(msg)
        is_alert = True
    elif pct_change >= 0.04 and curr_vol > prev_vol * 1.5:
        msg = "🔥 強勢反彈 (漲爆量)"
        if curr_price < v60: msg += " | ⚠️ 60SMA壓力"
        messages.append(msg)
        is_alert = True
    elif is_entangled_yesterday and curr_vol > prev_vol * 1.2 and pct_change <= -0.05:
        messages.append(f"🌀 均線糾結跌破 (守{prev_price:.2f})")
        is_alert = True
    
    # 其他轉折邏輯
    if not messages:
        if curr_price > v60 and v5 > p5 and v5 > v10:
            messages.append(f"✨ 多方整理轉折(5SMA{v5:.2f} > 10SMA)")
            is_alert = True
        elif curr_price > v60 and v5 < p5 and curr_price < v5 and v5 < v10:
            messages.append(f"✨ 多方整理向下(5SMA{v5:.2f} < 10SMA)")
            is_alert = True
        elif prev_price < p60 and curr_price > v60:
            messages.append("🚀 轉多訊號：站上60SMA")
            is_alert = True
        elif prev_price > p60 and curr_price < v60:
            messages.append("📉 轉空警示：跌破60SMA")
            is_alert = True
            
    final_signal = " | ".join(messages) if messages else "🌊 多方行進" if curr_price > v60 else "☁️ 空方盤整"
    return final_signal, curr_price, bias_val, bias_msg, is_alert, pos_msg

def main():
    tw_now = datetime.now(timezone(timedelta(hours=8)))
    time_str = tw_now.strftime('%H:%M')
    tickers = list(STOCK_NAMES.keys())
    download_list = [f"{t}.TW" for t in tickers] + [f"{t}.TWO" for t in tickers]
    
    print(f"🚀 掃描開始...")
    data = yf.download(download_list, period="2y", group_by='ticker', threads=True, progress=False)
    
    results = []
    for t in tickers:
        df = pd.DataFrame()
        if f"{t}.TW" in data.columns.levels[0]: df = data[f"{t}.TW"]
        if df.empty and f"{t}.TWO" in data.columns.levels[0]: df = data[f"{t}.TWO"]
        if df.empty or df['Close'].dropna().empty: continue
        
        signal, price, bias, b_msg, alert, p_msg = analyze_strategy(df)
        results.append({
            "code": t, "name": STOCK_NAMES[t], "price": price, 
            "signal": signal, "b_msg": b_msg, "alert": alert, "p_msg": p_msg
        })

    # 置頂排序：有警示的在前
    results.sort(key=lambda x: 0 if x['alert'] else 1)
    
    report = [f"📊 股市戰略定時報 ({time_str})\n" + "="*30]
    for r in results:
        line = f"【{r['name']} {r['code']}】${r['price']:.2f} | {r['signal']}"
        if r['b_msg']: line += f" | {r['b_msg']}"
        if r['p_msg']: line += f" | {r['p_msg']}"
        report.append(line)

    if report:
        msg = MIMEText("\n".join(report))
        msg['Subject'] = f"📈 股市戰略通知 ({time_str})"
        msg['From'] = f"戰略機器人 <{MY_GMAIL}>"
        msg['To'] = MY_GMAIL
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(MY_GMAIL, MY_PWD)
            s.send_message(msg)
        print("✅ 報告已送出")

if __name__ == "__main__":
    main()
