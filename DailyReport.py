import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- (💡 請全選複製上方 app.py 裡的 STOCK_NAMES 與 analyze_strategy 函式到此處) ---

def run_batch():
    try:
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
        if not sender or not pwd: return
        client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
                 scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
        sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        
        for row in sheet.get_all_records():
            email = row.get('Email')
            tickers = re.findall(r'\d{4}', str(row.get('Stock_List', '')))
            if not email: continue
            
            # 💡 強制測試報告：確保您一定收到信確認電路正常
            notify_list = [f"✅ 戰略巡航連線成功！測試時間：{datetime.now().strftime('%H:%M:%S')}"]
            for t in tickers:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                if not df.empty:
                    sig, p, s60, b, im = analyze_strategy(df, t)
                    if im: notify_list.append(f"【{t}】${p:.2f} | {sig}")

            msg = MIMEText("\n\n".join(notify_list))
            msg['Subject'] = f"📈 戰略巡航回報 - {datetime.now().strftime('%m/%d')}"
            msg['From'], msg['To'] = sender, email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender, pwd); server.send_message(msg)
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_batch()
