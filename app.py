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

# --- 1. 系統設定與 112 檔完整名單 ---
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
    "5236": "力領科技", "5284": "jpp-KY", "5388": "中磊", "5439": "高技", "5871": "中租-KY",
    "6104": "創惟", "6121": "新普", "6139": "亞翔", "6143": "振曜", "6158": "禾昌",
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

def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return "資料不足", 0, 0, 0, False
        df.columns = df.columns.get_level_values(0)
        close, highs, lows, volume = df['Close'].astype(float), df['High'].astype(float), df['Low'].astype(float), df['Volume'].astype(float)
        
        curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        
        ma60 = float(close.rolling(60).mean().iloc[-1])
        ma240 = float(close.rolling(240).mean().iloc[-1])
        
        msg, is_mail = [], False
        bias = ((curr_p - ma60) / ma60) * 100

        # A. 💡 長線趨勢線偵測 (修正為 120 日)
        recent_l_120 = lows.tail(120)
        l1_val = float(recent_l_120.min())
        l1_idx = recent_l_120.idxmin()
        # 尋找 L1 之後的局部低點
        post_l1 = recent_l_120.loc[l1_idx:].iloc[1:]
        if len(post_l1) > 10:
            l2_val = float(post_l1.min())
            l2_idx = post_l1.idxmin()
            
            # 兩點定一線
            dist = df.index.get_loc(l2_idx) - df.index.get_loc(l1_idx)
            if dist > 0 and l2_val > l1_val:
                slope = (l2_val - l1_val) / dist
                today_dist = len(df) - 1 - df.index.get_loc(l2_idx)
                support = l2_val + (slope * today_dist)
                gap = ((curr_p - support) / support) * 100
                if abs(gap) <= 2.5: 
                    msg.append(f"🛡️ 120日趨勢支撐: {support:.2f} (距 {gap:.1f}%)")
                    is_mail = True

        # B. 💡 中長線型態偵測 (修正為 60 日)
        recent_h, recent_l = highs.tail(60), lows.tail(60)
        
        # 1. M頭 (落差 12%)
        if curr_p > ma240:
            p_a_v = float(recent_h.max()); p_a_i = recent_h.idxmax()
            post_p_idx = df.index.get_loc(p_a_i)
            post_p_data = lows.iloc[post_p_idx:]
            if len(post_p_data) > 5:
                m_t_v = float(post_p_data.min())
                m_t_i = post_p_data.idxmin()
                if (p_a_v - m_t_v) / p_a_v >= 0.12:
                    a_d = len(df) - 1 - post_p_idx
                    b_d = len(df) - 1 - df.index.get_loc(m_t_i)
                    gap = ((curr_p - m_t_v) / m_t_v) * 100
                    status = "🚨 M頭跌破成立" if curr_p < m_t_v else "⚠ M頭警戒"
                    msg.append(f"{status}: 左頭 {p_a_v:.2f} ({a_d}日前), 中間底 {m_t_v:.2f} ({b_d}日前), 領口距 {gap:.1f}%")
                    is_mail = True

        # 2. W底 (落差 10%) [對位 image_63a264.png]
        elif curr_p < ma240:
            t_a_v = float(recent_l.min()); t_a_i = recent_l.idxmin()
            post_t_idx = df.index.get_loc(t_a_i)
            post_t_data = highs.iloc[post_t_idx:]
            if len(post_t_data) > 5:
                w_p_v = float(post_t_data.max())
                w_p_i = post_t_data.idxmax()
                if (w_p_v - t_a_v) / t_a_v >= 0.10:
                    a_d = len(df) - 1 - post_t_idx
                    b_d = len(df) - 1 - df.index.get_loc(w_p_i)
                    gap = ((w_p_v - curr_p) / w_p_v) * 100
                    # 💡 判斷突破成立
                    status = "✨ W底突破成立" if curr_p > w_p_v else "✨ W底機會"
                    msg.append(f"{status}: 左底 {t_a_v:.2f} ({a_d}日前), 頸線高 {w_p_v:.2f} ({b_d}日前), 領口距 {gap:.1f}%")
                    is_mail = True

        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5: 
            msg.append("🔥 強勢反彈"); is_mail = True
            
        if not msg: msg.append("🌊 多方行進" if curr_p > ma60 else "☁ 空方盤整")
        return " | ".join(msg), curr_p, ma60, bias, is_mail
    except Exception as e: return f"分析失敗: {str(e)}", 0, 0, 0, False

# --- UI 介面 ---
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
    submit_btn = st.button("🚀 執行長線型態分析")

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
        st.success("✅ 120日趨勢與型態突破分析完成")
