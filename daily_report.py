import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# 💡 這裡必須貼上跟 app.py 完全一樣的 analyze_strategy 函式代碼 
# (請將上方 analyze_strategy 內容複製到此處)

def run_batch():
    # 讀取 GitHub Secrets
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
    
    if not creds_json: return
    
    client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
             scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
    sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    
    all_data = sheet.get_all_records()
    for row in all_data:
        email = row.get('Email')
        tickers = re.findall(r'\d{4}', str(row.get('Stock_List', '')))
        if not email or not tickers: continue
        
        notify_list = []
        dl_list = [f"{t}.TW" for t in tickers] + [f"{t}.TWO" for t in tickers]
        data = yf.download(dl_list, period="2y", group_by='ticker', progress=False)
        
        for t in tickers:
            df = data[f"{t}.TW"] if f"{t}.TW" in data.columns.levels[0] else data.get(f"{t}.TWO", pd.DataFrame())
            if not df.empty and not df['Close'].dropna().empty:
                signal, price, bias, urgent = analyze_strategy(df)
                if urgent:
                    notify_list.append(f"【{t}】${price:.2f} | {signal}")
        
        # 發信邏輯：僅發送符合警示條件的個股 
        if notify_list:
            # (發信代碼...)
            print(f"✅ 已發送警訊至 {email}")

if __name__ == "__main__":
    run_batch()
