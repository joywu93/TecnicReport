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

# 1. 取得環境變數
MY_GMAIL = os.environ.get("GMAIL_USER")
MY_PWD = os.environ.get("GMAIL_PASSWORD")
GOOGLE_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

def main():
    print("🚀 啟動診斷程序...")
    
    # 2. 連接試算表 (使用您提供的 ID)
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(json.loads(GOOGLE_JSON), scopes=scope)
        client = gspread.authorize(creds)
        SHEET_ID = '1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU'
        sheet = client.open_by_key(SHEET_ID).sheet1 
        users = sheet.get_all_records()
        print(f"✅ 成功開啟試算表！名單中共有 {len(users)} 筆資料")
    except Exception as e:
        print(f"❌ 試算表連線失敗: {e}")
        raise e 

    # 3. 處理每一位使用者
    for user in users:
        email = user.get('Email', '').strip()
        stocks_raw = str(user.get('Stock_List', ''))
        # 抓取 4 位數代號
        tickers = re.findall(r'\d{4}', stocks_raw)
        
        if not email or not tickers:
            print(f"⚠️ 跳過空白資料: Email={email}, 股票數={len(tickers)}")
            continue
            
        print(f"🔍 正在為 {email} 分析 {len(tickers)} 檔股票...")
        report = [f"📊 股市戰略定時報\n" + "="*30]
        count = 0
        
        for t in tickers:
            # 嘗試下載資料 (增加重試邏輯)
            df = yf.download(f"{t}.TW", period="3mo", progress=False)
            if df.empty:
                df = yf.download(f"{t}.TWO", period="3mo", progress=False)
            
            if not df.empty:
                price = df['Close'].iloc[-1]
                report.append(f"【{t}】價位: ${price:.2f}")
                count += 1
                print(f"  📈 抓到 {t}: ${price:.2f}")
            else:
                print(f"  ❌ 抓不到 {t} 的價格")

        # 4. 寄信 (如果抓到至少一檔股票)
        if count > 0:
            print(f"📫 準備發信給 {email}...")
            msg = MIMEText("\n".join(report))
            msg['Subject'] = f"📈 股市戰略通知 ({count} 檔分析完畢)"
            msg['From'] = MY_GMAIL
            msg['To'] = email
            
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
                    s.login(MY_GMAIL, MY_PWD)
                    s.send_message(msg)
                print(f"🎉 成功！信件已送達 {email}")
            except Exception as e:
                print(f"❌ 郵件寄送失敗，請檢查密碼: {e}")
                raise e 
        else:
            print(f"⚠️ 找不到任何有效的股票價格，所以不發信。")

if __name__ == "__main__":
    main()
