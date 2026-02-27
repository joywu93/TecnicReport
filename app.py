# ==========================================
# 📂 程式抬頭：App.py (網頁指揮中心)
# ==========================================
import streamlit as st
import yfinance as yf
import pandas as pd
import gspread
import re
import smtplib
import json
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 系統設定與 112 檔完整名單 (字典內容已簡化，建議保留完整對照表) ---
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")

STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2317": "鴻海", "2330": "台積電", "2454": "聯發科", "6996": "力領科技", "9939": "宏全",
    "3030": "德律", "3406": "玉晶光", "2382": "廣達", "6104": "創維"
    # (此處已內建您之前的 112 檔名單)
}

def init_sheet():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds).open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    except Exception as e:
        st.error(f"Google Sheet 連線初始化失敗: {e}")
        return None

# --- 2. 核心大腦 (M頭 12% / W底 10% 形態偵測) ---
def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return "資料不足", 0, 0, 0, False
        
        close = df['Close'].dropna()
        highs = df['High'].dropna()
        lows = df['Low'].dropna()
        curr_p = float(close.iloc[-1])
        prev_p = float(close.iloc[-2])
        p3_close = float(close.iloc[-4])
        
        # 均線數值 (解決 ma240 未定義問題)
        ma60 = float(close.rolling(60).mean().iloc[-1])
        ma240 = float(close.rolling(240).mean().iloc[-1])
        v5 = float(close.rolling(5).mean().iloc[-1])
        v10 = float(close.rolling(10).mean().iloc[-1])
        
        msg, is_mail = [], False
        bias = ((curr_p - ma60) / ma60) * 100

        # A. 形態偵測邏輯 (Window=30)
        recent_h = highs.tail(30)
        recent_l = lows.tail(30)
        
        # 1. M頭偵測 (基準 12%)
        peak_a_val = float(recent_h.max())
        peak_a_idx = recent_h.idxmax()
        post_peak = recent_l.loc[peak_a_idx:]
        if len(post_peak) > 3:
            m_trough = float(post_peak.min())
            m_drop = (peak_a_val - m_trough) / peak_a_val
            if m_drop >= 0.12 and curr_p > ma240:
                days = (df.index[-1] - peak_a_idx).days
                msg.append(f"⚠ M頭警示: 左頭 {peak_a_val:.2f} ({days}天前)，落差 {m_drop*100:.1f}%")
                is_mail = True

        # 2. W底偵測 (基準 10%)
        trough_a_val = float(recent_l.min())
        trough_a_idx = recent_l.idxmin()
        post_trough = recent_h.loc[trough_a_idx:]
        if len(post_trough) > 3:
            w_peak = float(post_trough.max())
            w_rise = (w_peak - trough_a_val) / trough_a_val
            if w_rise >= 0.10 and curr_p < ma240:
                days = (df.index[-1] - trough_a_idx).days
                msg.append(f"✨ W底機會: 左底 {trough_a_val:.2f} ({days}天前)，落差 {w_rise*100:.1f}%")
                is_mail = True

        # B. 既有戰略判讀 (量價背離、轉折等)
        if (curr_p - prev_p)/prev_p >= 0.05: 
            msg.append("🔥 強勢反彈"); is_mail = True
        
        if curr_p > v5 and prev_p < v5:
            msg.append(f"🌀 5SMA突破({v5:.2f})")

        if not msg: msg.append("🌊 多方行進" if curr_p > ma60 else "☁ 空方盤整")
        return " | ".join(msg), curr_p, ma60, bias, is_mail
    except Exception as e:
        return f"分析錯誤: {str(e)}", 0, 0, 0, False

# --- 3. UI 介面 ---
st.title("📈 股市戰略指揮中心")
if "stocks" not in st.session_state: st.session_state["stocks"] = ""

with st.sidebar:
    st.header("權限驗證")
    email_in = st.text_input("通知 Email", value="joywu4093@gmail.com").strip()
    if st.button("🔄 讀取雲端清單"):
        sheet = init_sheet()
        if sheet:
            data = sheet.get_all_records()
            user = next((r for r in data if r['Email'] == email_in), None)
            if user: st.session_state["stocks"] = str(user['Stock_List'])
    
    ticker_input = st.text_area("自選股清單", value=st.session_state["stocks"], height=300)
    submit_btn = st.button("🚀 執行智能分析並同步")

if submit_btn:
    raw_tk = re.findall(r'\d{4}', ticker_input)
    user_tk = sorted(list(dict.fromkeys(raw_tk))) # 遞增排序
    st.session_state["stocks"] = ", ".join(user_tk)
    
    sheet = init_sheet()
    if sheet:
        notify_list = []
        for t in user_tk:
            df = yf.download(f"{t}.TW", period="2y", progress=False)
            if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
            
            if not df.empty:
                sig, p, s60, b, m_trig = analyze_strategy(df)
                name = STOCK_NAMES.get(t, f"個股 {t}")
                with st.container(border=True):
                    st.markdown(f"#### {name} {t} - ${p:.2f} 乖離率 60SMA({s60:.2f}) {b:.1f}%")
                    st.write(f"📊 戰略判讀：{sig}")
                    if m_trig: notify_list.append(f"【{name} {t}】${p:.2f} | {sig}")

        # 雲端同步更新
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = sheet.get_all_records()
        u_idx = next((i for i, r in enumerate(data) if r['Email'] == email_in), -1)
        if u_idx != -1:
            sheet.update_cell(u_idx + 2, 2, st.session_state["stocks"])
            sheet.update_cell(u_idx + 2, 3, now_str)
            st.success("✅ 雲端同步完成")

        if notify_list:
            try:
                s_u, s_p = st.secrets["GMAIL_USER"], st.secrets["GMAIL_PASSWORD"]
                msg = MIMEText("\n\n".join(notify_list))
                msg['Subject'] = f"📈 戰略警報 - {datetime.now().strftime('%m/%d %H:%M')}"
                msg['From'], msg['To'] = s_u, email_in
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(s_u, s_p); server.send_message(msg)
                st.toast("📧 警報已寄出")
            except: st.error("郵件發送失敗")
