import twstock
import time
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone

# ==========================================
# 🔧 設定監控清單 (您的 32 檔股票)
# ==========================================
TARGET_TICKERS = [
    "2330", "2317", "2323", "2451", "6229", "4763", "1522", "2404", "6788", "2344",
    "2368", "4979", "3163", "1326", "3491", "6143", "2383", "2454", "5225", "3526",
    "6197", "6203", "3570", "3231", "8299", "8069", "3037", "8046", "4977", "3455",
    "2408", "8271", "5439"
]

# 取得環境變數 (GitHub Secrets)
MY_GMAIL = os.environ.get("GMAIL_USER")
MY_PWD = os.environ.get("GMAIL_PASSWORD")
RECEIVERS = [MY_GMAIL]

def send_email_batch(subject, body):
    if not MY_GMAIL or not MY_PWD:
        print("❌ 找不到帳號密碼，無法寄信")
        return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市戰略機器人 <{MY_GMAIL}>"
        msg['To'] = ", ".join(RECEIVERS)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MY_GMAIL, MY_PWD)
            server.send_message(msg)
        print("✅ 信件發送成功")
        return True
    except Exception as e:
        print(f"❌ 發信失敗: {e}")
        return False

def analyze_stock(ticker):
    try:
        # 1. 抓取即時股價 (Realtime)
        real = twstock.realtime.get(ticker)
        if not real['success']: return None
        
        name = real['info']['name']
        latest_price = real['realtime']['latest_trade_price']
        
        # 處理剛開盤無成交價的情況
        if not latest_price or latest_price == '-':
             if real['realtime']['best_bid_price']:
                 latest_price = real['realtime']['best_bid_price'][0]
             else:
                 latest_price = real['realtime']['open']

        try:
            current_price = float(latest_price)
        except:
            return None
        
        # 2. 抓取歷史資料 (History) 算 60MA
        stock = twstock.Stock(ticker)
        price_history = stock.price[-60:] 
        
        if len(price_history) < 60:
            ma60 = current_price 
        else:
            ma60 = sum(price_history) / 60
            
        status = []
        need_notify = False
        
        # === 乖離率計算 (您的核心要求) ===
        bias_pct = ((current_price - ma60) / ma60) * 100
        
        # A. 嚴重警示：1.3倍 (乖離 > 30%)
        if current_price >= ma60 * 1.3:
             status.append(f"🔥⚠️ 乖離過大 (+{bias_pct:.1f}%)")
             need_notify = True
             
        # B. 預警觀察：1.15倍 (乖離 > 15%)
        elif current_price >= ma60 * 1.15:
             status.append(f"🔸 乖離偏高 (+{bias_pct:.1f}%)")
             need_notify = True

        # 均線邏輯
        if current_price > ma60:
            trend = "多方"
        else:
            trend = "空方"
            status.append("📉 季線之下")
            need_notify = True 

        if not status:
            status.append(f"{trend}行進")

        return f"【{name} ({ticker})】${current_price} | MA60:{round(ma60,1)} | {' '.join(status)}", need_notify

    except Exception as e:
        print(f"處理 {ticker} 發生錯誤: {e}")
        return None, False

def main():
    # 取得台灣時間
    utc_now = datetime.now(timezone.utc)
    tw_now = utc_now + timedelta(hours=8)
    time_str = tw_now.strftime('%H:%M')
    
    print(f"🚀 開始執行 TWSE 掃描任務 {time_str} ...")
    
    report_lines = []
    
    for ticker in TARGET_TICKERS:
        result_text, is_urgent = analyze_stock(ticker)
        if result_text:
            print(result_text)
            report_lines.append(result_text)
            
        time.sleep(1) # 禮貌性停頓

    if report_lines:
        mail_body = f"股市戰略報告 ({time_str})\n\n" + "\n".join(report_lines)
        send_email_batch(f"【{time_str}】股市戰略通知", mail_body)
    else:
        print("無資料")

if __name__ == "__main__":
    main()
