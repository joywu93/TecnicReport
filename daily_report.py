import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# 此處 analyze_strategy 函數請貼入與上方 app.py 相同的內容

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
        data = yf.download([f"{t}.TW" for t in tickers] + [f"{t}.TWO" for t in tickers], period="2y", group_by='ticker', progress=False)
        
        for t in tickers:
            df = data[f"{t}.TW"] if f"{t}.TW" in data.columns.levels[0] else data.get(f"{t}.TWO", pd.DataFrame())
            if not df.empty and not df['Close'].dropna().empty:
                res = analyze_strategy(df)
                # 💡 修正關鍵：只有價格不是空值才發信
                if res[3] and res[1] is not None:
                    notify_list.append(f"【{t}】${res[1]:.2f} | {res[0]}")
        
        if notify_list:
            msg = MIMEText("\n".join(notify_list))
            msg['Subject'] = f"📈 戰略警報 - {datetime.now().strftime('%m/%d %H:%M')}"
            msg['From'], msg['To'] = sender, email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender, pwd)
                server.send_message(msg)

if __name__ == "__main__":
    run_batch()
