import yfinance as yf
import pandas as pd
import os
import re
import smtplib
import gspread
import json
from google.oauth2.service_account import Credentials
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone

# 設定區
MY_GMAIL = os.environ.get("GMAIL_USER")
MY_PWD = os.environ.get("GMAIL_PASSWORD")
GOOGLE_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

def analyze_strategy(df):
    close = df['Close']
    volume = df['Volume']
    if len(close) < 240: return "資料不足", 0, 0, "", False, ""
    
    curr_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    curr_vol = float(volume.iloc[-1])
    prev_vol = float(volume.iloc[-2])
    pct_change = (curr_price - prev_price) / prev_price
    
    # 均線計算
    sma5 = close.rolling(5).mean().iloc[-1]
    sma10 = close.rolling(10).mean().iloc[-1]
    sma20 = close.rolling(20).mean().iloc[-1]
    sma60 = close.rolling(60).mean().iloc[-1]
    
    messages = []
    is_alert = False
    
    # 1. 乖離率判斷
    bias_val = ((curr_price - sma60) / sma60) * 100
    bias_str = ""
    if bias_val >= 30:
        bias_str = f"🔥 乖離過大({sma60:.2f})"
        is_alert = True
    elif bias_val >= 15:
        bias_str = f"🔸 乖離偏高({sma60:.2f})"

    # 2. 爆量突破邏輯
    if pct_change >= 0.04 and curr_vol > prev_vol * 1.5:
        msg = "🔥 強勢反彈 (漲爆量)"
        if curr_price < sma60: msg += " | ⚠️ 上有60SMA壓力"
        messages.append(msg)
        is_alert = True
        
    final_signal = " | ".join(messages) if messages else "🌊 多方行進" if curr_price > sma60 else "☁️ 空方盤整"
    return final_signal, curr_price, bias_val, bias_str, is_alert

def main():
    if not GOOGLE_JSON:
        print("❌ 缺少 GOOGLE_SERVICE_ACCOUNT_JSON")
        return

    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(json.loads(GOOGLE_JSON), scopes=scope)
        client = gspread.authorize(creds)
        # ⚠️ 請確保與 Google Sheets 檔名完全一致
        sheet = client.open("Email list").sheet1 
        users = sheet.get_all_records()
    except Exception as e:
        print(f"❌ 連線 Google Sheets 失敗: {e}")
        return

    tw_now = datetime.now(timezone(timedelta(hours=8)))
    time_str = tw_now.strftime('%H:%M')

    for user in users:
        email = user.get('Email')
        stocks_raw = str(user.get('Stock_List', ''))
        if not email or not stocks_raw: continue
        
        tickers = re.findall(r'\d{4}', stocks_raw)
        if not tickers: continue
        
        report = [f"📊 股市戰略定時報 ({time_str})\n" + "="*30]
        has_alert_item = False
        
        for t in tickers:
            try:
                # 嘗試下載個股資料
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                if df.empty: continue
                
                sig, price, b_val, b_msg, alert = analyze_strategy(df)
                line = f"【{t}】${price:.2f} | {sig}"
                if b_msg: line += f" | {b_msg}"
                report.append(line)
                if alert: has_alert_item = True
            except: continue

        # 只要有資料就寄信
        if len(report) > 1:
            try:
                msg = MIMEText("\n".join(report))
                msg['Subject'] = f"📈 股市戰略通知 ({time_str})"
                msg['From'] = f"戰略機器人 <{MY_GMAIL}>"
                msg['To'] = email
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
                    s.login(MY_GMAIL, MY_PWD)
                    s.send_message(msg)
                print(f"✅ 已寄信給 {email}")
            except Exception as e:
                print(f"❌ 寄信失敗: {e}")

if __name__ == "__main__":
    main()
