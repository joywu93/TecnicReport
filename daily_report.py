import os
import gspread
import json
import re
import smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==========================================
# 🧠 1. 核心戰略判讀大腦 (與 app.py 完全同步)
# ==========================================
def analyze_strategy(df):
    try:
        close, volume = df['Close'], df['Volume']
        if len(close) < 240: return None, None, None, False
        
        curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        pct_change = (curr_p - prev_p) / prev_p
        
        ma5, ma10, ma20 = close.rolling(5).mean(), close.rolling(10).mean(), close.rolling(20).mean()
        ma60, ma240 = close.rolling(60).mean(), close.rolling(240).mean()
        
        v5, v10, v20, v60, v240 = ma5.iloc[-1], ma10.iloc[-1], ma20.iloc[-1], ma60.iloc[-1], ma240.iloc[-1]
        p5, p60 = ma5.iloc[-2], ma60.iloc[-2]
        
        up_cnt = sum([v5 > ma5.iloc[-2], v10 > ma10.iloc[-2], v20 > ma20.iloc[-2]])
        dn_cnt = sum([v5 < ma5.iloc[-2], v10 < ma10.iloc[-2], v20 < ma20.iloc[-2]])

        msg, alert = [], False

        # 1. 季線轉折
        if prev_p < p60 and curr_p > v60:
            msg.append("🚀 轉多訊號：站上季線(60SMA)")
            alert = True
        elif prev_p > p60 and curr_p < v60:
            msg.append("📉 轉空警示：跌破季線(60SMA)")
            alert = True

        # 2. 強勢反彈
        if pct_change >= 0.05 and curr_v > prev_v * 1.5:
            msg.append(f"🔥 強勢反彈 (爆量) 觀察支撐：{close.iloc[-4]:.2f}")
            alert = True

        # 3. 形態轉折 (底部與高檔)
        if up_cnt >= 2 and curr_p < v60 and curr_p < v240:
            msg.append("✨ 底部轉折：均線翻揚")
            alert = True
        elif dn_cnt >= 2 and curr_p > v60 and curr_p > v240 and curr_p < v5:
            msg.append("✨ 高檔轉整理：均線翻下")
            alert = True

        # 4. 量價背離
        if curr_v > prev_v * 1.2 and curr_p < v5 and curr_p < prev_p:
            msg.append("⚠️ 量價背離：量增價跌")
            alert = True

        # 6. 均線糾結
        if (max(v5, v10, v20) - min(v5, v10, v20)) / min(v5, v10, v20) < 0.02:
            msg.append("🌀 均線糾結：變盤在即")
            alert = True

        # 7. 附加乖離標籤
        bias = ((curr_p - v60) / v60) * 100
        if curr_p > v60 * 1.3:
            msg.append(f"🚨 乖離率過高 60SMA({v60:.2f})")
            alert = True

        return " | ".join(msg), curr_p, bias, alert
    except:
        return None, None, None, False

# ==========================================
# 🛰️ 2. 自動執行與發信邏輯
# ==========================================
def run_batch():
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
    if not all([creds_json, sender, pwd]): return
    
    client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
             scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
    sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    
    for row in sheet.get_all_records():
        email, stocks = row.get('Email'), str(row.get('Stock_List', ''))
        tickers = re.findall(r'\d{4}', stocks)
        if not email or not tickers: continue
        
        notify_list = []
        dl_list = [f"{t}.TW" for t in tickers] + [f"{t}.TWO" for t in tickers]
        data = yf.download(dl_list, period="2y", group_by='ticker', progress=False)
        
        for t in tickers:
            df = data[f"{t}.TW"] if f"{t}.TW" in data.columns.levels[0] else data.get(f"{t}.TWO", pd.DataFrame())
            if not df.empty and not df['Close'].dropna().empty:
                res = analyze_strategy(df)
                if res[3]: # 💡 只有 alert 為 True 才發信
                    sig, price, bias, _ = res
                    # 💡 修正 TypeError：確保 price 不是 None 再格式化
                    if price is not None:
                        notify_list.append(f"【{t}】${price:.2f} | {sig}")
        
        if notify_list:
            body = "前輩好，股市戰略指揮中心偵測到以下警訊：\n\n" + "\n".join(notify_list)
            msg = MIMEText(body)
            msg['Subject'] = f"📈 股市戰略警報 - {datetime.now().strftime('%m/%d %H:%M')}"
            msg['From'], msg['To'] = sender, email
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(sender, pwd)
                    server.send_message(msg)
            except: pass

if __name__ == "__main__":
    run_batch()
