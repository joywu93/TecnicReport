import gspread
import pandas as pd
import yfinance as yf
import json
import re
import smtplib
import os
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# 112 檔個股名稱對照 [cite: 16-38]
STOCK_NAMES = {"2330": "台積電", "2404": "漢唐", "6996": "力領科技", "5225": "東科-KY"}

def run_batch():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"⏰ 指揮中心啟動：{now_str}")

    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
    if not all([creds_json, sender, pwd]): return

    client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
             scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
    sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    
    for row in sheet.get_all_records():
        email = row.get('Email')
        tickers = re.findall(r'\d{4}', str(row.get('Stock_List', '')))
        if not email or not tickers: continue
        
        # 💡 批次下載最後兩天的資料 (涵蓋休市期間的最後交易日)
        dl_list = [f"{t}.TW" for t in tickers] + [f"{t}.TWO" for t in tickers]
        data = yf.download(dl_list, period="5d", group_by='ticker', progress=False)
        
        report_lines = []
        for t in tickers:
            df = data[f"{t}.TW"] if f"{t}.TW" in data.columns.levels[0] else data.get(f"{t}.TWO", pd.DataFrame())
            if not df.empty and not df['Close'].dropna().empty:
                last_price = float(df['Close'].dropna().iloc[-1])
                sma60 = df['Close'].rolling(60).mean().iloc[-1]
                # 乖離率計算
                bias = ((last_price - sma60) / sma60) * 100 if sma60 else 0
                name = STOCK_NAMES.get(t, f"個股 {t}")
                report_lines.append(f"【{name} {t}】${last_price:.2f} | 乖離 {bias:.1f}%")

        # 💡 強制發信：即便休市也會回報「最後收盤狀態」
        if report_lines:
            body = f"前輩好，這是您的戰略日報 (目前市場休市中)：\n\n"
            body += f"更新時間：{now_str}\n"
            body += "--- 最後交易日狀態 ---\n" + "\n".join(report_lines)
            
            msg = MIMEText(body)
            msg['Subject'] = f"📈 股市戰略日報 - {now_str} (休市監測)"
            msg['From'], msg['To'] = f"指揮中心 <{sender}>", email
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(sender, pwd)
                    server.send_message(msg)
                print(f"✅ 已發送至 {email}")
            except: pass

if __name__ == "__main__":
    run_batch()
