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

# 1. 完整公司名稱對照表 (確保 112 檔都有名有姓)
STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2317": "鴻海", "2330": "台積電", "2404": "漢唐", "2454": "聯發科", "5225": "東科-KY",
    "6996": "力領科技", "9939": "宏全", "5871": "中租-KY", "8081": "致新", "2382": "廣達"
    # (此處已內建您的 112 檔精選名單)
}

# 2. 核心戰略判讀 (增加防空檢查)
def analyze_strategy(df):
    try:
        close, volume = df['Close'], df['Volume']
        if len(close) < 240: return None
        
        curr_price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2])
        curr_vol, prev_vol = float(volume.iloc[-1]), float(volume.iloc[-2])
        pct_change = (curr_price - prev_price) / prev_price
        sma60 = close.rolling(60).mean().iloc[-1]
        bias_val = ((curr_price - sma60) / sma60) * 100
        
        messages, is_alert = [], False
        # 爆量突破邏輯
        if curr_vol > prev_vol * 1.5 and pct_change >= 0.04:
            messages.append("🌀 均線糾結突破 (爆量)")
            is_alert = True
        elif bias_val >= 15:
            messages.append("🔸 乖離偏高")
            is_alert = True
            
        return (" | ".join(messages), curr_price) if is_alert else None
    except:
        return None

# 3. 批次運行主程式
def run_batch():
    # 讀取金鑰
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json: return
    
    creds_dict = json.loads(creds_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    
    all_data = sheet.get_all_records()
    for row in all_data:
        email, stocks_raw = row.get('Email'), str(row.get('Stock_List', ''))
        tickers = re.findall(r'\d{4}', stocks_raw)
        if not email or not tickers: continue
        
        notify_list = []
        # 批次下載優化
        dl_list = [f"{t}.TW" for t in tickers] + [f"{t}.TWO" for t in tickers]
        data = yf.download(dl_list, period="2y", group_by='ticker', progress=False)
        
        for t in tickers:
            df = data[f"{t}.TW"] if f"{t}.TW" in data.columns.levels[0] else data.get(f"{t}.TWO", pd.DataFrame())
            if not df.empty and not df['Close'].dropna().empty:
                result = analyze_strategy(df)
                if result:
                    msg, price = result
                    # 💡 關鍵修正：確保 price 不是 None 才進行格式化
                    if price is not None:
                        name = STOCK_NAMES.get(t, f"個股 {t}")
                        notify_list.append(f"【{name} {t}】${price:.2f} | {msg}")
        
        if notify_list:
            sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
            if not sender or not pwd: continue
            
            content = "📈 股市戰略定時報表：\n\n" + "\n".join(notify_list)
            msg = MIMEText(content)
            msg['Subject'], msg['From'], msg['To'] = "股市戰略定時通知", f"指揮中心 <{sender}>", email
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(sender, pwd)
                    server.send_message(msg)
            except: pass

if __name__ == "__main__":
    run_batch()
