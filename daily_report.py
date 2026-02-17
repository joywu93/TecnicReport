import twstock
import time
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone

# 監控清單
TARGET_TICKERS = [
    "2330", "2317", "2323", "2451", "6229", "4763", "1522", "2404", "6788", "2344",
    "2368", "4979", "3163", "1326", "3491", "6143", "2383", "2454", "5225", "3526",
    "6197", "6203", "3570", "3231", "8299", "8069", "3037", "8046", "4977", "3455",
    "2408", "8271", "5439"
]

MY_GMAIL = os.environ.get("GMAIL_USER")
MY_PWD = os.environ.get("GMAIL_PASSWORD")
RECEIVERS = [MY_GMAIL]

def send_email_batch(subject, body):
    if not MY_GMAIL or not MY_PWD:
        print("❌ 沒帳密")
        return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市戰略機器人 <{MY_GMAIL}>"
        msg['To'] = ", ".join(RECEIVERS)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MY_GMAIL, MY_PWD)
            server.send_message(msg)
        print("✅ 寄信成功")
        return True
    except Exception as e:
        print(f"❌ 寄信失敗: {e}")
        return False

def analyze_stock(ticker):
    try:
        # 1. 抓即時
        real = twstock.realtime.get(ticker)
        if not real['success']: return None
        
        name = real['info']['name']
        latest_price = real['realtime']['latest_trade_price']
        
        if not latest_price or latest_price == '-':
             if real['realtime']['best_bid_price']:
                 latest_price = real['realtime']['best_bid_price'][0]
             else:
                 latest_price = real['realtime']['open']

        try:
            current_price = float(latest_price)
        except:
            return None
        
        # 2. 抓歷史算 60MA
        stock = twstock.Stock(ticker)
        # 抓多一點確保夠算
        price_history = stock.price[-70:] 
        
        if len(price_history) < 60:
            ma60 = current_price 
        else:
            # 取最後60筆
            ma60 = sum(price_history[-60:]) / 60
            
        status = []
        
        # === 乖離率核心邏輯 (完全照您的要求) ===
        bias_pct = ((current_price - ma60) / ma60) * 100
        
        # 條件 A: > 30% (1.3倍)
        if bias_pct >= 30:
             status.append(f"🔥⚠️ 乖離過大 (+{bias_pct:.1f}%)")
             
        # 條件 B: > 15% (1.15倍)
        elif bias_pct >= 15:
             status.append(f"🔸 乖離偏高 (+{bias_pct:.1f}%)")

        # 均線趨勢
        if current_price > ma60:
            trend = "多方"
        else:
            trend = "空方"
            status.append("📉 季線之下")

        if not status:
            status.append(f"{trend}行進")

        return f"【{name} ({ticker})】${current_price} | MA60:{round(ma60,1)} | {' '.join(status)}"

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

def main():
    utc_now = datetime.now(timezone.utc)
    tw_now = utc_now + timedelta(hours=8)
    time_str = tw_now.strftime('%H:%M')
    
    print(f"🚀 開始執行 ({time_str}) ...")
    report_lines = []
    
    for ticker in TARGET_TICKERS:
        res = analyze_stock(ticker)
        if res:
            print(res)
            report_lines.append(res)
        time.sleep(1) 

    if report_lines:
        mail_body = "\n".join(report_lines)
        send_email_batch(f"【{time_str}】股市戰略通知", mail_body)

if __name__ == "__main__":
    main()
