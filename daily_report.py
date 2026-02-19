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

# 1. 取得環境變數 (GitHub Secrets)
MY_GMAIL = os.environ.get("GMAIL_USER")
MY_PWD = os.environ.get("GMAIL_PASSWORD")
GOOGLE_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

def main():
    print("🚀 啟動股市戰略自動化診斷...")
    
    # 2. 透過 ID 精準連接 Google Sheets
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(json.loads(GOOGLE_JSON), scopes=scope)
        client = gspread.authorize(creds)
        
        # 使用您剛才提供的試算表 ID
        SHEET_ID = '1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU'
        sheet = client.open_by_key(SHEET_ID).sheet1 
        
        users = sheet.get_all_records()
        print(f"✅ 成功讀取試算表，名單中共有 {len(users)} 列資料")
    except Exception as e:
        print(f"❌ 無法讀取試算表，原因: {e}")
        raise e # 讓 GitHub 顯示紅叉 ❌

    # 3. 逐一分析個股並發信
    for user in users:
        email = user.get('Email')
        stocks_raw = str(user.get('Stock_List', ''))
        tickers = re.findall(r'\d{4}', stocks_raw)
        
        if not email or not tickers:
            continue
            
        report = [f"📊 股市戰略定時報\n" + "="*30]
        success_count = 0
        
        for t in tickers:
            try:
                # 抓取 3 個月歷史資料計算均線
                df = yf.download(f"{t}.TW", period="3mo", progress=False)
                if df.empty:
                    df = yf.download(f"{t}.TWO", period="3mo", progress=False)
                
                if not df.empty:
                    price = df['Close'].iloc[-1]
                    report.append(f"【{t}】價位: ${price:.2f}")
                    success_count += 1
            except:
                continue

        if success_count > 0:
            print(f"📫 正在發信給 {email}...")
            msg = MIMEText("\n".join(report))
            msg['Subject'] = "📈 股市戰略通知 (連線測試成功)"
            msg['From'] = MY_GMAIL
            msg['To'] = email
            
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
                    s.login(MY_GMAIL, MY_PWD)
                    s.send_message(msg)
                print(f"🎉 恭喜！{email} 的郵件已寄出")
            except Exception as e:
                print(f"❌ 寄信失敗: {e}")
                raise e # 若密碼錯誤，會在這裡報警 ❌

if __name__ == "__main__":
    main()
