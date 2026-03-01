import os, gspread, json, re, smtplib
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 核心大腦 (解決 slice indexing 與 $0.00 問題) ---
def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return None, False
        # 💡 關鍵修正：拍平雙層標籤，確保索引不報錯
        df.columns = df.columns.get_level_values(0)
        close = df['Close'].astype(float).dropna()
        highs = df['High'].astype(float).dropna()
        lows = df['Low'].astype(float).dropna()
        volume = df['Volume'].astype(float).dropna()
        
        curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        p3_close = float(close.iloc[-4])
        
        ma5 = close.rolling(5).mean(); v5 = float(ma5.iloc[-1])
        ma60 = close.rolling(60).mean(); v60 = float(ma60.iloc[-1])
        
        msg, is_mail = [], False

        # W底偵測 (60日)
        r_l, r_h = lows.tail(60), highs.tail(60)
        t_a_v = float(r_l.min()); t_a_i = r_l.idxmin()
        post_a = r_h.loc[t_a_i:]
        if len(post_a) > 5:
            w_p_v = float(post_a.max()); w_p_i = post_a.idxmax()
            post_b = lows.loc[w_p_i:]
            if len(post_b) > 3:
                t_c_v = float(post_b.min())
                if t_c_v >= (t_a_v * 0.97) and (w_p_v - t_a_v)/t_a_v >= 0.10:
                    status = "✨ W底突破" if curr_p > w_p_v else "✨ W底機會"
                    msg.append(f"{status}: 領口距 {((w_p_v-curr_p)/w_p_v)*100:.1f}%")
                    is_mail = True

        # 戰略項
        if prev_p < v60 and curr_p > v60: msg.append("🚀 轉多：站上季線"); is_mail = True
        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5: msg.append("🔥 強勢反彈"); is_mail = True
        if curr_v > prev_v * 1.2 and curr_p < v5 and curr_p < prev_p: msg.append("⚠️ 量價背離"); is_mail = True

        return " | ".join(msg), is_mail
    except: return None, False

def run_batch():
    try:
        # A. 讀取 Secrets
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
        if not creds_json or not sender: return
        
        # B. 連線 Google Sheet
        creds = Credentials.from_service_account_info(json.loads(creds_json), 
                 scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        
        for row in sheet.get_all_records():
            email, stocks = row.get('Email'), str(row.get('Stock_List', ''))
            tickers = re.findall(r'\d{4}', stocks)
            if not email or not tickers: continue
            
            notify_list = []
            for t in tickers:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                
                sig, is_mail = analyze_strategy(df)
                if is_mail:
                    notify_list.append(f"【{t}】${df['Close'].iloc[-1].values[0]:.2f} | {sig}")
            
            if notify_list:
                msg = MIMEText("\n\n".join(notify_list))
                msg['Subject'] = f"📈 戰略警報 - {datetime.now().strftime('%m/%d %H:%M')}"
                msg['From'], msg['To'] = sender, email
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(sender, pwd); server.send_message(msg)
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_batch()
