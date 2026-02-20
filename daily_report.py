import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

def analyze_strategy(df):
    try:
        close, volume = df['Close'], df['Volume']
        if len(close) < 240: return None, None, None, False
        curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        sma60 = close.rolling(60).mean().iloc[-1]
        msg, alert = [], False
        if curr_p > sma60 and prev_p < close.rolling(60).mean().iloc[-2]:
            msg.append("🚀 轉多訊號"); alert = True
        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5:
            msg.append("🔥 強勢反彈"); alert = True
        if curr_p > sma60 * 1.3:
            msg.append("🚨 乖離率過高"); alert = True
        return " | ".join(msg), curr_p, 0, alert
    except: return None, None, None, False

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
                # 💡 修正核心：只有當 price 不是 None 且觸發警示時才格式化文字
                if res[3] and res[1] is not None:
                    notify_list.append(f"【{t}】${res[1]:.2f} | {res[0]}")
        if notify_list:
            msg = MIMEText("\n".join(notify_list))
            msg['Subject'] = f"📈 股市戰略警訊 - {datetime.now().strftime('%m/%d %H:%M')}"
            msg['From'], msg['To'] = sender, email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender, pwd)
                server.send_message(msg)

if __name__ == "__main__":
    run_batch()
