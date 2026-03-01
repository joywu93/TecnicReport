import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# 💡 補回發報機的大腦
def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return "不足", 0, 0, 0, False
        df.columns = df.columns.get_level_values(0)
        close, lows, highs = df['Close'].astype(float).dropna(), df['Low'].astype(float).dropna(), df['High'].astype(float).dropna()
        curr_p = float(close.iloc[-1])
        ma60 = float(close.rolling(60).mean().iloc[-1])
        # W底偵測
        r_l, r_h = lows.tail(60), highs.tail(60)
        t_a_v = float(r_l.min()); t_a_i = r_l.idxmin()
        post_a = r_h.loc[t_a_i:]
        if len(post_a) > 5:
            w_p_v = float(post_a.max()); w_p_i = post_a.idxmax()
            post_b = lows.loc[w_p_i:]
            if len(post_b) > 3:
                t_c_v = float(post_b.min())
                if t_c_v >= (t_a_v * 0.97) and (w_p_v - t_a_v)/t_a_v >= 0.10:
                    gap = ((w_p_v - curr_p) / w_p_v) * 100
                    status = "✨ W底突破" if curr_p > w_p_v else "✨ W底機會"
                    return f"{status}(距{gap:.1f}%)", curr_p, ma60, 0, True
        # 強制測試：只要站上季線就發信
        if curr_p > ma60: return "🌊 多方行進", curr_p, ma60, 0, True
        return "", curr_p, ma60, 0, False
    except: return "錯誤", 0, 0, 0, False

def run_batch():
    try:
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
        client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
                 scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
        sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        
        for row in sheet.get_all_records():
            email = row.get('Email')
            tickers = re.findall(r'\d{4}', str(row.get('Stock_List', '')))
            if not email: continue
            
            # 💡 強迫測試行，保證信件內容不為空
            notify_list = [f"✅ 通訊測試成功！執行時間：{datetime.now().strftime('%H:%M:%S')}"]
            for t in tickers:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                if not df.empty:
                    sig, p, s60, b, im = analyze_strategy(df)
                    if im: notify_list.append(f"【{t}】${p:.2f} | {sig}")

            msg = MIMEText("\n\n".join(notify_list))
            msg['Subject'] = f"📈 戰略巡航回報 - {datetime.now().strftime('%m/%d')}"
            msg['From'], msg['To'] = sender, email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender, pwd); server.send_message(msg)
                print(f"Mail sent to {email}")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_batch()
