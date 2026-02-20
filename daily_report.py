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

# 1. 名稱對照表 (確保截圖中的 6285、1522、8358 等都有名稱)
STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "6285": "啟碁", "6290": "良維", 
    "1522": "堤維西", "8358": "金居", "3406": "玉晶光", "2603": "長榮"
}

def analyze_strategy(df):
    try:
        close = df['Close']
        if len(close) < 60: return None
        curr_price = float(close.iloc[-1])
        sma60 = close.rolling(60).mean().iloc[-1]
        bias_val = ((curr_price - sma60) / sma60) * 100
        
        # 💡 戰略標記
        msg = "🚀 轉多訊號" if curr_price > sma60 else "📉 觀望"
        return f"{msg} (乖離 {bias_val:.1f}%)", curr_price
    except:
        return None

def run_batch():
    print(f"⏰ 啟動定時任務：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 讀取環境變數
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sender = os.environ.get("GMAIL_USER")
    pwd = os.environ.get("GMAIL_PASSWORD")
    
    if not all([creds_json, sender, pwd]):
        print("❌ 錯誤：GitHub Secrets 設定不完整！")
        return

    # 連線 Google Sheets
    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    
    all_data = sheet.get_all_records()
    print(f"📊 偵測到雲端帳號數量：{len(all_data)}") # 預期為 3 個

    for row in all_data:
        email = row.get('Email')
        stock_list_raw = str(row.get('Stock_List', ''))
        tickers = re.findall(r'\d{4}', stock_list_raw)
        
        if not email or not tickers:
            print(f"⏭️ 跳過無效行：{email}")
            continue
        
        print(f"🔎 正在處理帳號：{email} (共 {len(tickers)} 檔個股)")
        
        # 批次下載
        dl_list = [f"{t}.TW" for t in tickers] + [f"{t}.TWO" for t in tickers]
        data = yf.download(dl_list, period="1y", group_by='ticker', progress=False)
        
        report_content = []
        for t in tickers:
            df = data[f"{t}.TW"] if f"{t}.TW" in data.columns.levels[0] else data.get(f"{t}.TWO", pd.DataFrame())
            if not df.empty and not df['Close'].dropna().empty:
                res = analyze_strategy(df)
                if res:
                    status, price = res
                    name = STOCK_NAMES.get(t, f"個股 {t}")
                    report_content.append(f"【{name} {t}】${price:.2f} | {status}")
        
        # 💡 無論如何都發信，確保連線正常
        if report_content:
            subject = f"📈 股市戰略日報 - {datetime.now().strftime('%m/%d %H:%M')}"
            body = f"前輩您好，這是您的定時戰略分析報告：\n\n" + "\n".join(report_content)
            
            msg = MIMEText(body)
            msg['Subject'], msg['From'], msg['To'] = subject, sender, email
            
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(sender, pwd)
                    server.send_message(msg)
                print(f"✅ 信件已發送至：{email}")
            except Exception as e:
                print(f"❌ 寄信給 {email} 失敗：{e}")

if __name__ == "__main__":
    run_batch()
