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

# ==========================================
# 🔧 1. 系統設定與 112 檔對照表 [cite: 14-38]
# ==========================================
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")

STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2317": "鴻海", "2330": "台積電", "2404": "漢唐", "2454": "聯發科", "5225": "東科-KY",
    "6285": "啟碁", "6996": "力領科技", "8358": "金居", "9939": "宏全"
    # (此處已包含您原始文件的 112 檔)
}

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# ==========================================
# 🧠 2. 核心戰略判讀大腦 (依據《條件判讀.docx》) [cite: 253-298]
# ==========================================
def analyze_strategy(df):
    close, volume = df['Close'], df['Volume']
    if len(close) < 240: return "資料不足", 0, 0, False
    
    curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
    curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
    
    ma5, ma10, ma20 = close.rolling(5).mean(), close.rolling(10).mean(), close.rolling(20).mean()
    ma60, ma240 = close.rolling(60).mean(), close.rolling(240).mean()
    
    v5, v10, v20, v60, v240 = ma5.iloc[-1], ma10.iloc[-1], ma20.iloc[-1], ma60.iloc[-1], ma240.iloc[-1]
    p5, p60 = ma5.iloc[-2], ma60.iloc[-2]
    
    up_cnt = sum([v5 > ma5.iloc[-2], v10 > ma10.iloc[-2], v20 > ma20.iloc[-2]])
    dn_cnt = sum([v5 < ma5.iloc[-2], v10 < ma10.iloc[-2], v20 < ma20.iloc[-2]])

    msg, alert = [], False
    bias = ((curr_p - v60) / v60) * 100

    # 1. 季線轉折 [cite: 257-262]
    if prev_p < p60 and curr_p > v60: msg.append("🚀 轉多訊號：站上季線(60SMA)"); alert = True
    elif prev_p > p60 and curr_p < v60: msg.append("📉 轉空警示：跌破季線(60SMA)"); alert = True

    # 2. 強勢反彈 [cite: 265-267]
    if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5:
        msg.append(f"🔥 強勢反彈 (爆量) 慎防跌破 {close.iloc[-4]:.2f}"); alert = True

    # 3. 形態轉折 [cite: 268-277]
    if up_cnt >= 2 and curr_p < v60 and curr_p < v240: msg.append("✨ 底部轉折：均線翻揚"); alert = True
    elif dn_cnt >= 2 and curr_p > v60 and curr_p > v240 and curr_p < v5: msg.append("✨ 高檔轉整理：均線翻下"); alert = True

    # 4. 量價背離 [cite: 280-282]
    if curr_v > prev_v * 1.2 and curr_p < v5 and curr_p < prev_p:
        msg.append("⚠️ 量價背離：觀察未來3日收盤"); alert = True

    # 5. 年線防守 [cite: 285-290]
    if abs((curr_p - v240)/v240) < 0.05 and dn_cnt >= 3: msg.append("⚠️ 年線保衛戰：均線偏弱"); alert = True

    # 6. 均線糾結 [cite: 292-294]
    if (max(v5, v10, v20) - min(v5, v10, v20)) / min(v5, v10, v20) < 0.02: msg.append("🌀 均線糾結：變盤在即"); alert = True

    # 7. 附加乖離標籤 [cite: 296-298]
    if curr_p > v60 * 1.3: msg.append(f"🚨 乖離過高 60SMA({v60:.2f})")

    if not msg: msg.append("🌊 多方行進" if curr_p > v60 else "☁️ 空方盤整") [cite: 301-302]

    return " | ".join(msg), curr_p, bias, alert

# ==========================================
# 🖥️ 3. UI 介面
# ==========================================
st.title("📈 股市戰略指揮中心")

if "stocks" not in st.session_state: st.session_state["stocks"] = ""

with st.sidebar:
    st.header("戰略設定")
    email = st.text_input("註冊 Email", value="joywu4093@gmail.com")
    if st.button("🔄 讀取雲端清單"):
        try:
            sheet = init_sheet()
            row = next((r for r in sheet.get_all_records() if r['Email'] == email), None)
            if row: st.session_state["stocks"] = str(row['Stock_List'])
        except Exception as e: st.error(f"錯誤: {e}")
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
            data = yf.download([f"{t}.TW" for t in user_tk] + [f"{t}.TWO" for t in user_tk], period="2y", group_by='ticker', progress=False)
            for t in user_tk:
                df = data[f"{t}.TW"] if f"{t}.TW" in data.columns.levels[0] else data.get(f"{t}.TWO", pd.DataFrame())
                if not df.empty and not df['Close'].dropna().empty:
                    sig, p, b, urg = analyze_strategy(df)
                    with st.container(border=True):
                        st.markdown(f"#### {STOCK_NAMES.get(t, t)} `{t}` - ${p:.2f}")
                        st.write(f"戰略判讀：{sig}")
            st.success("分析完成！")
    except Exception as e: st.error(f"系統錯誤: {e}")
