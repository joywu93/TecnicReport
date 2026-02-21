# ==========================================
# 📂 程式抬頭：DailyReport.py (自動發報系統)
# ==========================================
import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# 💡 此處 analyze_strategy 函數內容請複製上方 App.py 的版本，確保邏輯 100% 同步

def run_batch():
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
    if not creds_json: return
    
    client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
             scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
    sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    
    for row in sheet.get_all_records():
        email, stocks = row.get('Email'), str(row.get('Stock_List', ''))
        tickers = re.findall(r'\d{4}', stocks)
        if not email or not tickers: continue
        
        notify_list = []
        for t in tickers:
            df = yf.download(f"{t}.TW", period="2y", progress=False)
            if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
            
            if not df.empty and not df['Close'].dropna().empty:
                sig, p, s60, b, m_trig = analyze_strategy(df)
                # 💡 只有符合警示且非「單純糾結」時才發信 
                if m_trig and p is not None and p > 0:
                    notify_list.append(f"【{t}】${p:.2f} | 60SMA({s60:.2f}) 乖離{b:.1f}% | {sig}")
        
        if notify_list:
            msg = MIMEText("\n\n".join(notify_list))
            msg['Subject'] = f"📈 定時戰略通知 - {datetime.now().strftime('%m/%d %H:%M')}"
            msg['From'], msg['To'] = sender, email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender, pwd)
                server.send_message(msg)

if __name__ == "__main__":
    run_batch()
