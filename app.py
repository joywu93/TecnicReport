import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import os
from datetime import datetime, timedelta, timezone

# ==========================================
# 🔧 設定監控清單
# ==========================================
TARGET_TICKERS = [
    "2330.TW", "2317.TW", "3231.TW", "6197.TW", "5225.TW", "2454.TW", "2603.TW", "6203.TWO", "4766.TW", "3570.TWO",
    "2323.TW", "2451.TW", "2344.TW", "6788.TWO", "1522.TW", "4763.TW", "6229.TWO", "2404.TW",
    "2368.TW", "4979.TWO", "3163.TWO", "1326.TW", "3491.TWO", "6143.TWO", "2408.TW", "2383.TW",
    "3526.TWO", "8299.TWO", "8069.TWO", "3037.TW", "8046.TW", "4977.TW", "3455.TW"
]

STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "6203": "海韻電", "3570": "大塚", "4766": "南寶", "NVDA": "輝達",
    "2313": "華通", "2454": "聯發科", "2303": "聯電", "2603": "長榮", "2609": "陽明", "2615": "萬海",
    "2323": "中環", "2451": "創見", "6229": "研通", "4763": "材料-KY", "1522": "堤維西", "2404": "漢唐",
    "6788": "華景電", "2344": "華邦電", "1519": "華城", "1513": "中興電", "3231": "緯創", "3035": "智原",
    "2408": "南亞科", "3406": "玉晶光", "2368": "金像電", "4979": "華星光", "3163": "波若威", "1326": "台化",
    "3491": "昇達科", "6143": "振曜", "2383": "台光電", "5225": "東科-KY", "3526": "凡甲", "6197": "佳必琪",
    "8299": "群聯", "8069": "元太", "3037": "欣興", "8046": "南電", "4977": "眾達-KY", "3455": "由田"
}

MY_GMAIL = os.environ.get("GMAIL_USER")
MY_PWD = os.environ.get("GMAIL_PASSWORD")
RECEIVERS = [MY_GMAIL] 

def send_email_batch(subject, body):
    if not MY_GMAIL or not MY_PWD:
        return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市戰略機器人 <{MY_GMAIL}>"
        msg['To'] = ", ".join(RECEIVERS)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MY_GMAIL, MY_PWD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"❌ 發信失敗: {e}")
        return False

def check_strategy(df):
    close = df['Close']
    volume = df['Volume']
    
    # 盤中時，iloc[-1] 是「目前最新的價格與累積量」
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price
    price_4_days_ago = close.iloc[-5] 
    
    s3 = close.rolling(3).mean()
    s5 = close.rolling(5).mean()
    s10 = close.rolling(10).mean()
    s20 = close.rolling(20).mean()
    s60 = close.rolling(60).mean()
    s240 = close.rolling(240).mean()
    
    v240 = s240.iloc[-1] if len(close) >= 240 else s60.iloc[-1]
    v60 = s60.iloc[-1]
    p60 = s60.iloc[-2]
    v5 = s5.iloc[-1]
    v3 = s3.iloc[-1]
    
    trend_up = {5: v5 > s5.iloc[-2], 10: s10.iloc[-1] > s10.iloc[-2], 20: s20.iloc[-1] > s20.iloc[-2], 60: v60 > p60}
    up_count = sum(trend_up.values())
    down_count = 4 - up_count
    
    status = []
    need_notify = False
    
    # 1. 重大轉折 (60SMA)
    if prev_price > p60 and curr_price < v60:
        status.append("📉 轉空警示：跌破季線(60SMA)")
        need_notify = True
    elif prev_price < p60 and curr_price > v60:
        status.append("🚀 轉多訊號：站上季線(60SMA)")
        need_notify = True
    
    # 2. 強勢反彈 (盤中量能較小，10:00很難達標，13:00較有機會)
    if pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > v3:
        status.append("🔥 強勢反彈 (漲>4%, 量>1.5倍, 站上3SMA)")
        need_notify = True
    
    # 3. 底部轉折
    if up_count >= 2 and curr_price <= v60 * 1.1:
        status.append(f"✨ 底部轉折：{up_count}條均線翻揚")
        need_notify = True
        
    # 4. 出貨警訊
    cond_sell_a = (curr_vol > prev_vol * 1.3 and pct_change < 0)
    cond_sell_b = (curr_price < price_4_days_ago)
    if cond_sell_a or cond_sell_b:
        reasons = []
        if cond_sell_a: reasons.append("爆量收黑")
        if cond_sell_b: reasons.append("跌破4日價")
        status.append(f"⚠️ 出貨警訊 ({'+'.join(reasons)})")
        need_notify = True
    
    # 5. 量價背離
    if curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
        status.append("⚠️ 量價背離 (量增價弱，破5SMA)")
        need_notify = True

    # 6. 關鍵位置
    dist_240 = abs(curr_price - v240) / v240
    if dist_240 < 0.05 and down_count >= 3:
        status.append("⚠️ 年線保衛戰：均線偏弱")
        need_notify = True
    elif curr_price < v240 and down_count >= 3:
        status.append("❄️ 空方弱勢整理：均線蓋頭")
        
    if not status:
        if curr_price > v60: status.append("🌊 多方行進 (觀察)")
        else: status.append("☁️ 空方盤整 (觀望)")

    return status, need_notify, curr_price, v60

def main():
    # 取得現在時間 (UTC) 轉 台灣時間 (UTC+8)
    utc_now = datetime.now(timezone.utc)
    tw_now = utc_now + timedelta(hours=8)
    current_hour = tw_now.hour

    # 判斷標題
    if current_hour < 12:
        title_prefix = "【盤中快報 10:00】"
    elif current_hour < 14:
        title_prefix = "【盤中快報 13:00】"
    else:
        title_prefix = "【盤後總結】"

    print(f"🚀 執行 {title_prefix} 掃描...")
    notify_list = []
    
    for symbol in TARGET_TICKERS:
        try:
            print(f"Analyzing {symbol}...")
            stock = yf.Ticker(symbol)
            df = stock.history(period="1y")
            
            if df.empty or len(df) < 60: continue
            
            pure_code = symbol.replace(".TW", "").replace(".TWO", "")
            ch_name = STOCK_NAMES.get(pure_code, symbol)
            
            status_list, need_notify, price, v60 = check_strategy(df)
            
            if need_notify:
                status_str = " | ".join(status_list)
                report_line = (f"【{ch_name} ({symbol})】\n"
                               f"現價: {price:.2f} (季線: {v60:.1f})\n"
                               f"訊號: {status_str}\n"
                               f"------------------------------\n")
                notify_list.append(report_line)
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

    if notify_list:
        chunk_size = 5
        chunks = [notify_list[i:i + chunk_size] for i in range(0, len(notify_list), chunk_size)]
        
        for i, chunk in enumerate(chunks):
            mail_body = f"{title_prefix} 股市戰略報告 - Part {i+1}\n\n" + "".join(chunk)
            send_email_batch(f"{title_prefix} 戰略訊號 ({i+1})", mail_body)
            time.sleep(1)
    else:
        print("✅ 無特殊訊號。")

if __name__ == "__main__":
    main()
