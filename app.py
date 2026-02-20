import streamlit as st
import gspread
import pandas as pd
import yfinance as yf
import json
import re
import smtplib
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="股市戰略指揮中心", layout="wide")

STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2317": "鴻海", "2330": "台積電", "2404": "漢唐", "2454": "聯發科", "5225": "東科-KY",
    "6285": "啟碁", "6996": "力領科技", "8358": "金居", "9939": "宏全", "2376": "技嘉"
}

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

def analyze_strategy(df):
    try:
        close, volume = df['Close'], df['Volume']
        if len(close) < 240: return "資料不足", 0, 0, False
        curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        sma5, sma60 = close.rolling(5).mean().iloc[-1], close.rolling(60).mean().iloc[-1]
        bias = ((curr_p - sma60) / sma60) * 100
        msg, alert = [], False
        if curr_p > sma60 and prev_p < close.rolling(60).mean().iloc[-2]:
            msg.append("🚀 轉多訊號：站上季線(60SMA)"); alert = True
        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5:
            msg.append("🔥 強勢反彈 (爆量)"); alert = True
        if curr_p > sma60 * 1.3:
            msg.append("🚨 乖離率過高"); alert = True
        if not msg: msg.append("🌊 多方行進" if curr_p > sma60 else "☁️ 空方盤整")
        return " | ".join(msg), curr_p, bias, alert
    except: return None, None, None, False

st.title("📈 股市戰略指揮中心")
if "stocks" not in st.session_state: st.session_state["stocks"] = ""

with st.sidebar:
    st.header("權限驗證")
    email = st.text_input("註冊 Email", value="joywu4093@gmail.com").strip()
    if st.button("🔄 讀取雲端清單"):
        try:
            sheet = init_sheet()
            data = sheet.get_all_records()
            row = next((r for r in data if r['Email'] == email), None)
            if row: st.session_state["stocks"] = str(row['Stock_List'])
        except Exception as e: st.error(f"連線失敗: {e}")
    tickers_in = st.text_area("自選股清單", value=st.session_state["stocks"], height=300)
    run_btn = st.button("🚀 執行智能分析")

if st.session_state["stocks"]:
    count = len(re.findall(r'\d{4}', st.session_state["stocks"]))
    st.info(f"📋 聯合合作戰清單：已載入 {count} 檔個股")

if run_btn:
    try:
        raw = re.findall(r'\d{4}', tickers_in)
        user_tk = list(dict.fromkeys(raw))
        if user_tk:
            st.session_state["stocks"] = ", ".join(user_tk)
            st.info(f"正在分析 {len(user_tk)} 檔標的...")
            data = yf.download([f"{t}.TW" for t in user_tk] + [f"{t}.TWO" for t in user_tk], period="2y", group_by='ticker', progress=False)
            for t in user_tk:
                df = data[f"{t}.TW"] if f"{t}.TW" in data.columns.levels[0] else data.get(f"{t}.TWO", pd.DataFrame())
                if not df.empty and not df['Close'].dropna().empty:
                    sig, p, b, urg = analyze_strategy(df)
                    if p:
                        with st.container(border=True):
                            st.markdown(f"#### {STOCK_NAMES.get(t, t)} `{t}` - ${p:.2f}")
                            st.write(f"戰略判讀：{sig}")
            st.success("✅ 分析與雲端同步完成！")
    except Exception as e: st.error(f"系統錯誤: {e}")
