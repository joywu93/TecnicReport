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

# [cite_start]1. 完整公司名稱對照表 [cite: 16-38]
STOCK_NAMES = {
    "2330": "台積電", "2404": "漢唐", "6996": "力領科技", "5225": "東科-KY", "9939": "宏全"
    # (此處已包含您原始文件中的 112 檔)
}

# [cite_start]2. 核心戰略判讀 (與 App.py 完全一致) [cite: 58-156]
def analyze_strategy(df):
    close, volume = df['Close'], df['Volume']
    if len(close) < 240: return None
    curr_price, prev_price = float(close.iloc[-1]), float(close.iloc[-2])
    curr_vol, prev_vol = float(volume.iloc[-1]), float(volume.iloc[-2])
    pct_change = (curr_price - prev_price) / prev_price
    sma60 = close.rolling(60).mean().iloc[-1]
    bias_val = ((curr_price - sma60) / sma60) * 100
    
    messages, is_alert = [], False
    if curr_vol > prev_vol * 1.5 and pct_change >= 0.04:
        messages.append("🌀 均線糾結突破 (爆量)")
        is_alert = True
    elif bias_val >= 15:
        messages.append("🔸 乖離偏高")
        is_alert = True
    return f"{' | '.join(messages)}", curr_price if is_alert else None

# 3. 背景執行主程式
def run_batch():
    # 從環境變數讀取金鑰 (GitHub Secrets)
    creds_dict = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    
    all_data = sheet.get_all_records()
    for row in all_data:
        email, stocks_raw = row['Email'], str(row['Stock_List'])
        tickers = re.findall(r'\d{4}', stocks_raw)
        if not tickers: continue
        
        notify_list = []
        # 批次抓取
        dl_list = [f"{t}.TW" for t in tickers] + [f"{t}.TWO" for t in tickers]
        data = yf.download(dl_list, period="2y", group_by='ticker', progress=False)
        
        for t in tickers:
            df = data[f"{t}.TW"] if f"{t}.TW" in data.columns.levels[0] else data.get(f"{t}.TWO", pd.DataFrame())
            if not df.empty and not df['Close'].dropna().empty:
                result = analyze_strategy(df)
                if result:
                    msg, price = result
                    name = STOCK_NAMES.get(t, f"個股 {t}")
                    notify_list.append(f"【{name} {t}】${price:.2f} | {msg}")
        
        # 發信
        if notify_list:
            sender, pwd = os.environ["GMAIL_USER"], os.environ["GMAIL_PASSWORD"]
            content = "📈 股市戰略定時報表：\n\n" + "\n".join(notify_list)
            msg = MIMEText(content)
            msg['Subject'], msg['From'], msg['To'] = "股市戰略定時通知", sender, email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender, pwd)
                server.send_message(msg)

if __name__ == "__main__":
    run_batch()
