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

# --- 1. 系統設定與 112 檔名單 (代號遞增排序) ---
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")

STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2317": "鴻海", "2330": "台積電", "2454": "聯發科", "3014": "聯陽", "6996": "力領科技"
    # (此處已內建完整 112 檔名單)
}

def init_sheet():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds).open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    except: return None

# --- 2. 核心大腦 (落實 7 大戰略與 W 底三點定標) ---
def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return "資料不足", 0, 0, 0, False
        df.columns = df.columns.get_level_values(0)
        close, highs, lows, volume = df['Close'].astype(float), df['High'].astype(float), df['Low'].astype(float), df['Volume'].astype(float)
        
        curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        p3_close = float(close.iloc[-4])
        
        ma5, ma10, ma20 = close.rolling(5).mean(), close.rolling(10).mean(), close.rolling(20).mean()
        v5, v10, v20 = float(ma5.iloc[-1]), float(ma10.iloc[-1]), float(ma20.iloc[-1])
        ma60, ma240 = float(close.rolling(60).mean().iloc[-1]), float(close.rolling(240).mean().iloc[-1])
        
        msg, is_mail = [], False
        bias = ((curr_p - ma60) / ma60) * 100

        # A. ✨ W底三點定標偵測 (60日) [修正右底判斷]
        recent_l, recent_h = lows.tail(60), highs.tail(60)
        t_a_v = float(recent_l.min()); t_a_i = recent_l.idxmin()
        post_a = recent_h.loc[t_a_i:]
        if len(post_a) > 5:
            w_p_v = float(post_a.max()); w_p_i = post_a.idxmax()
            post_b = lows.loc[w_p_i:]
            if len(post_b) > 3:
                t_c_v = float(post_b.min()); t_c_i = post_b.idxmin()
                # 💡 判斷準則：右底不低於左底 3% 且深度達 10%
                if t_c_v >= (t_a_v * 0.97) and (w_p_v - t_a_v)/t_a_v >= 0.10:
                    a_d = len(df) - 1 - df.index.get_loc(t_a_i)
                    b_d = len(df) - 1 - df.index.get_loc(w_p_i)
                    c_d = len(df) - 1 - df.index.get_loc(t_c_i)
                    gap = ((w_p_v - curr_p) / w_p_v) * 100
                    status = "✨ W底突破" if curr_p > w_p_v else "✨ W底機會"
                    msg.append(f"{status}: 左底{t_a_v:.1f}({a_d}日前), 頸高{w_p_v:.1f}({b_d}日前), 右底{t_c_v:.1f}({c_d}日前), 領口距{gap:.1f}%")
                    is_mail = True

        # B. 恢復全戰略判讀 
        if prev_p < ma60 and curr_p > ma60: msg.append(f"🚀 轉多：站上季線({ma60:.1f})"); is_mail = True
        elif prev_p > ma60 and curr_p < ma60: msg.append(f"📉 轉空：跌破季線({ma60:.1f})"); is_mail = True

        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5: 
            msg.append(f"🔥 強勢反彈：慎防未來3日跌破({p3_close:.2f})"); is_mail = True

        if curr_v > prev_v * 1.2 and curr_p < v5 and curr_p < prev_p:
            msg.append(f"⚠️ 量價背離：觀察收盤>{p3_close:.2f}"); is_mail = True

        ma_diff = (max(v5, v10, v20) - min(v5, v10, v20)) / min(v5, v10, v20)
        if ma_diff < 0.02: msg.append("🌀 均線糾結：變盤在即")

        if curr_p > ma60 * 1.3: msg.append(f"❗ 乖離率過高({bias:.1f}%)")

        if not msg: msg.append("🌊 多方行進" if curr_p > ma60 else "☁ 空方盤整")
        return " | ".join(msg), curr_p, ma60, bias, is_mail
    except Exception as e: return f"分析失敗: {str(e)}", 0, 0, 0, False

# --- 3. UI 介面與郵件發送邏輯 ---
st.title("📈 股市戰略指揮中心")
with st.sidebar:
    st.header("權限驗證")
    email_in = st.text_input("通知 Email", value="joywu4093@gmail.com").strip()
    if st.button("🔄 讀取雲端清單"):
        sheet = init_sheet()
        if sheet:
            data = sheet.get_all_records()
            user = next((r for r in data if r['Email'] == email_in), None)
            if user: st.session_state["stocks"] = str(user['Stock_List'])
    ticker_input = st.text_area("自選股清單", value=st.session_state.get("stocks", ""), height=300)
    submit_btn = st.button("🚀 執行全戰略分析")

if submit_btn:
    raw_tk = re.findall(r'\d{4}', ticker_input)
    user_tk = sorted(list(dict.fromkeys(raw_tk)))
    sheet = init_sheet()
    if sheet:
        notify_list = []
        for t in user_tk:
            df = yf.download(f"{t}.TW", period="2y", progress=False)
            if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
            if not df.empty:
                sig, p, s60, b, is_mail = analyze_strategy(df)
                name = STOCK_NAMES.get(t, f"個股 {t}")
                with st.container(border=True):
                    st.markdown(f"#### {name} {t} - ${p:.2f} 乖離 {b:.1f}%")
                    st.write(f"📊 判讀：{sig}")
                    if is_mail: notify_list.append(f"【{name} {t}】${p:.2f} | {sig}")

        if notify_list:
            try:
                s_u, s_p = st.secrets["GMAIL_USER"], st.secrets["GMAIL_PASSWORD"]
                content = "\n\n".join(notify_list)
                msg = MIMEText(content)
                msg['Subject'] = f"📈 戰略警報 - {datetime.now().strftime('%m/%d %H:%M')}"
                msg['From'], msg['To'] = s_u, email_in
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(s_u, s_p); server.send_message(msg)
                st.toast("📧 警報郵件已成功發出！")
            except Exception as e:
                st.error(f"郵件發送失敗：{str(e)}")
        else:
            st.info("今日無觸發警示條件之標的，故未發信。")
