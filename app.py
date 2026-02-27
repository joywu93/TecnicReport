# ==========================================
# 📂 程式抬頭：App.py (網頁指揮中心 - 形態精準版)
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

# --- 1. 系統設定與 112 檔完整名單 [來自 image_505042.png] ---
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")

STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2228": "劍麟", "2313": "華通", "2317": "鴻海", "2327": "國巨", "2330": "台積電",
    "2344": "華邦電", "2368": "金像電", "2376": "技嘉", "2377": "微星", "2379": "瑞昱",
    "2382": "廣達", "2383": "台光電", "2397": "友通", "2404": "漢唐", "2408": "南亞科",
    "2439": "美律", "2441": "超豐", "2449": "京元電子", "2454": "聯發科", "2493": "揚博",
    "2615": "萬海", "3005": "神基", "3014": "聯陽", "3017": "奇鋐", "3023": "信邦",
    "3030": "德律", "3037": "欣興", "3042": "晶技", "3078": "僑威", "3163": "波若威",
    "3167": "大量", "3217": "優群", "3219": "倚強科", "3227": "原相", "3231": "緯創",
    "3264": "欣銓", "3265": "台星科", "3303": "岱稜", "3357": "臺慶科", "3402": "漢科",
    "3406": "玉晶光", "3416": "融程電", "3441": "聯一光", "3450": "聯鈞", "3455": "由田",
    "3479": "安勤", "3483": "力致", "3484": "崧騰", "3515": "華擎", "3526": "凡甲",
    "3548": "兆利", "3570": "大塚", "3596": "智易", "3679": "新至陞", "3711": "日月光投控",
    "3712": "永崴投控", "4554": "橙的", "4760": "勤凱", "4763": "材料*-KY", "4766": "南寶",
    "4915": "致伸", "4953": "緯軟", "4961": "天鈺", "4979": "華星光", "5225": "東科-KY",
    "5236": "凌陽創新", "5284": "jpp-KY", "5388": "中磊", "5439": "高技", "5871": "中租-KY",
    "6104": "創維", "6121": "新普", "6139": "亞翔", "6143": "振曜", "6158": "禾昌",
    "6176": "瑞儀", "6187": "萬潤", "6197": "佳必琪", "6203": "海韻電", "6221": "晉泰",
    "6227": "茂崙", "6257": "矽格", "6261": "久元", "6274": "台燿", "6278": "台表科",
    "6285": "啟碁", "6290": "良維", "6538": "倉和", "6579": "研揚", "6605": "帝寶",
    "6613": "朋億*", "6629": "泰金-KY", "6651": "全宇昕", "6667": "信紘科", "6768": "志強-KY",
    "6788": "華景電", "6894": "衛司特", "6951": "靑新-創", "6967": "汎瑋材料", "6996": "力領科技",
    "8081": "致新", "8358": "金居", "8432": "東生華", "8473": "山林水", "8938": "明安",
    "9914": "美利達", "9939": "宏全"
}

def init_sheet():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds).open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
    except: return None

# --- 2. 核心大腦 (修正交易日算法與關鍵點顯示) ---
def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return "資料不足", 0, 0, 0, False
        df.columns = df.columns.get_level_values(0)
        close, highs, lows = df['Close'].astype(float), df['High'].astype(float), df['Low'].astype(float)
        
        curr_p = float(close.iloc[-1])
        ma60 = float(close.rolling(60).mean().iloc[-1])
        ma240 = float(close.rolling(240).mean().iloc[-1])
        
        msg, is_mail = [], False
        bias = ((curr_p - ma60) / ma60) * 100

        # A. 形態偵測 (Window=30 交易日)
        recent_h = highs.tail(30)
        recent_l = lows.tail(30)

        # 1. M頭偵測 (基準 12%) [修正華邦電需求：標註中間底]
        if curr_p > ma240:
            peak_a_val = float(recent_h.max())
            peak_a_idx = recent_h.idxmax()
            post_peak = recent_l.loc[peak_a_idx:]
            if len(post_peak) > 3:
                m_trough_val = float(post_peak.min())
                m_drop = (peak_a_val - m_trough_val) / peak_a_val
                if m_drop >= 0.12:
                    # 💡 修正為交易日算法 (K線根數)
                    bars_ago = len(df) - 1 - df.index.get_loc(peak_a_idx)
                    msg.append(f"⚠ M頭警戒: 左頭 {peak_a_val:.2f} ({bars_ago}根前), 中間底 {m_trough_val:.2f}, 落差 {m_drop*100:.1f}%")
                    is_mail = True

        # 2. W底偵測 (基準 10%) [修正原相需求：修正天數與頸線]
        elif curr_p < ma240:
            trough_a_val = float(recent_l.min())
            trough_a_idx = recent_l.idxmin()
            post_trough = recent_h.loc[trough_a_idx:]
            if len(post_trough) > 3:
                w_peak_val = float(post_trough.max())
                w_rise = (w_peak_val - trough_a_val) / trough_a_val
                if w_rise >= 0.10:
                    # 💡 修正為交易日算法 (K線根數)
                    bars_ago = len(df) - 1 - df.index.get_loc(trough_a_idx)
                    msg.append(f"✨ W底機會: 左底 {trough_a_val:.2f} ({bars_ago}根前), 頸線高 {w_peak_val:.2f}, 落差 {w_rise*100:.1f}%")
                    is_mail = True

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
    user_tk = sorted(list(dict.fromkeys(raw_tk)))
    st.session_state["stocks"] = ", ".join(user_tk)
    
    sheet = init_sheet()
    if sheet:
        for t in user_tk:
            df = yf.download(f"{t}.TW", period="2y", progress=False)
            if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
            if not df.empty:
                sig, p, s60, b, m_trig = analyze_strategy(df)
                name = STOCK_NAMES.get(t, f"個股 {t}")
                with st.container(border=True):
                    st.markdown(f"#### {name} {t} - ${p:.2f} 乖離率 60SMA({s60:.2f}) {b:.1f}%")
                    st.write(f"📊 戰略判讀：{sig}")
        st.success("✅ 分析與同步完成")
