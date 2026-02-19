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

# 取得環境變數
MY_GMAIL = os.environ.get("GMAIL_USER")
MY_PWD = os.environ.get("GMAIL_PASSWORD")
GOOGLE_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

def main():
    print("🚀 啟動股市戰略旗艦版...")
    
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(json.loads(GOOGLE_JSON), scopes=scope)
        client = gspread.authorize(creds)
        # 使用您提供的試算表 ID
        SHEET_ID = '1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU'
        sheet = client.open_by_key(SHEET_ID).sheet1 
        users = sheet.get_all_records()
        print(f"✅ 成功讀取試算表，共有 {len(users)} 位使用者")
    except Exception as e:
        print(f"❌ 試算表連線失敗: {e}")
        raise e 

    for user in users:
        email = user.get('Email', '').strip()
        stocks_raw = str(user.get('Stock_List', ''))
        tickers = re.findall(r'\d{4}', stocks_raw)
        
        if not email or not tickers: continue
            
        print(f"🔍 正在分析 {email} 的股票...")
        report = [f"📊 股市戰略定時報\n" + "="*30]
        count = 0
        
        for t in tickers:
            df = yf.download(f"{t}.TW", period="3mo", progress=False)
            if df.empty:
                df = yf.download(f"{t}.TWO", period="3mo", progress=False)
            
            if not df.empty:
                # 💡 修復日誌中的 FutureWarning
                price = float(df['Close'].iloc[-1]) 
                report.append(f"【{t}】價位: ${price:.2f}")
                count += 1
                print(f"  📈 抓到 {t}: ${price:.2f}")

        if count > 0:
            print(f"📫 準備寄信至 {email}...")
            msg = MIMEText("\n".join(report))
            msg['Subject'] = f"📈 股市戰略通知 ({count} 檔分析完畢)"
            msg['From'] = MY_GMAIL
            msg['To'] = email
            
            try:
                # 💡 使用強化的 SMTP 連線
                server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
                server.login(MY_GMAIL, MY_PWD)
                server.send_message(msg)
                server.quit()
                print(f"🎉 成功！信件已送達 {email}")
            except Exception as e:
                print(f"❌ 郵件寄送失敗: {e}")
                raise e 
        else:
            print(f"⚠️ 找不到有效股票資料。")

if __name__ == "__main__":
    main()
