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

def main():
    print("🚀  開始執行股市戰略診斷...")
    
    # 1. 檢查 Google 試算表連線
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json.loads(GOOGLE_JSON), scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Email list").sheet1 
    users = sheet.get_all_records()
    print(f"✅ 成功讀取試算表，共有 {len(users)} 位使用者")

    for user in users:
        email = user.get('Email')
        stocks_raw = str(user.get('Stock_List', ''))
        tickers = re.findall(r'\d{4}', stocks_raw)
        
        if not tickers: continue
        
        report = [f"📊 股市戰略定時報\n" + "="*30]
        
        for t in tickers:
            # 💡 增加 User-Agent 防止被 Yahoo 拒絕
            df = yf.download(f"{t}.TW", period="3mo", progress=False)
            if df.empty:
                df = yf.download(f"{t}.TWO", period="3mo", progress=False)
            
            if not df.empty:
                price = df['Close'].iloc[-1]
                report.append(f"【{t}】目前價位: ${price:.2f}")
                print(f"📈 抓到股票 {t} 價格: {price:.2f}")

        # 只要有抓到一檔股票就寄信
        if len(report) > 1:
            print(f"📫 準備寄信給 {email}...")
            msg = MIMEText("\n".join(report))
            msg['Subject'] = "📈 股市戰略機器人測試"
            msg['From'] = MY_GMAIL
            msg['To'] = email
            
            # 這裡不使用 try...except，失敗要直接報警
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
                s.login(MY_GMAIL, MY_PWD)
                s.send_message(msg)
            print(f"🎉 郵件已成功寄出！")
        else:
            print(f"⚠️ {email} 的清單內沒有抓到任何股票資料")

if __name__ == "__main__":
    main()
