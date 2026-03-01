import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# (STOCK_NAMES 字典請複製與上方 app.py 相同內容)

def run_batch():
    try:
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
        if not creds_json or not sender: return
        
        creds = Credentials.from_service_account_info(json.loads(creds_json), 
                 scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        
        for row in sheet.get_all_records():
            email, stocks = row.get('Email'), str(row.get('Stock_List', ''))
            tickers = re.findall(r'\d{4}', stocks)
            if not email or not tickers: continue
            
            notify_list = []
            # 💡 測試模式：強迫加入一條成功訊息，用來測試通訊
            notify_list.append(f"✅ 通訊測試：自動發報機已於 {datetime.now().strftime('%H:%M')} 啟動成功")
            
            for t in tickers:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                if not df.empty:
                    # 💡 呼叫與網頁版相同的 analyze_strategy
                    sig, p, v60, b, is_mail = analyze_strategy(df)
                    if is_mail:
                        notify_list.append(f"【{t}】${p:.2f} | {sig}")
            
            if len(notify_list) > 1: # 除了測試訊息外還有警報才寄出
                msg = MIMEText("\n\n".join(notify_list))
                msg['Subject'] = f"📈 戰略警報 - {datetime.now().strftime('%m/%d %H:%M')}"
                msg['From'], msg['To'] = sender, email
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(sender, pwd); server.send_message(msg)
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_batch()
