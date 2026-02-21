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

# --- 1. 系統設定與 112 檔完整對照表 ---
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
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds).open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# --- 2. 核心大腦 (修正 ma240 定義與格式)  ---
def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return "資料不足", 0, 0, 0, False
        close, volume = df['Close'].dropna(), df['Volume'].dropna()
        curr_p, prev_p, p3_close = float(close.iloc[-1]), float(close.iloc[-2]), float(close.iloc[-4])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        
        # 均線計算
        ma5_s = close.rolling(5).mean()
        ma10_s = close.rolling(10).mean()
        ma20_s = close.rolling(20).mean()
        ma60_s = close.rolling(60).mean()
        ma240_s = close.rolling(240).mean()
        
        v5, v10, v20, v60, v240 = float(ma5_s.iloc[-1]), float(ma10_s.iloc[-1]), float(ma20_s.iloc[-1]), float(ma60_s.iloc[-1]), float(ma240_s.iloc[-1])
        p5, p10, p20, p60 = float(ma5_s.iloc[-2]), float(ma10_s.iloc[-2]), float(ma20_s.iloc[-2]), float(ma60_s.iloc[-2])

        up_cnt = sum([v5 > p5, v10 > p10, v20 > p20])
        dn_cnt = sum([v5 < p5, v10 < p10, v20 < p20])
        msg, is_mail = [], False
        bias = ((curr_p - v60) / v60) * 100

        # 戰略判讀文字優化 [cite: 370-381]
        if prev_p < p60 and curr_p > v60: msg.append("🚀 轉多訊號：站上季線(60SMA)"); is_mail = True
        elif prev_p > p60 and curr_p < v60: msg.append("📉 轉空警示：跌破季線(60SMA)"); is_mail = True

        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5:
            msg.append(f"🔥 強勢反彈 (爆量) 慎防未來3日跌破前3日收盤價({p3_close:.2f})"); is_mail = True

        if up_cnt >= 2 and curr_p < v60 and curr_p < v240:
            msg.append(f"✨ 底部轉折：均線翻揚 5SMA({v5:.2f}) 10SMA({v10:.2f})"); is_mail = True
        elif dn_cnt >= 2 and curr_p > v60 and curr_p > v240 and curr_p < v5:
            msg.append(f"✨ 高檔轉整理：均線翻下 5SMA({v5:.2f}) 10SMA({v10:.2f})"); is_mail = True

        if curr_v > prev_v * 1.2 and curr_p < v5 and curr_p < prev_p:
            msg.append(f"⚠️ 量價背離：未來3日的收盤價 > 前3日的收盤價({p3_close:.2f})"); is_mail = True

        ma_diff = (max(v5, v10, v20) - min(v5, v10, v20)) / min(v5, v10, v20)
        if ma_diff < 0.02: msg.append("🌀 均線糾結：變盤在即") # 糾結不發mail [cite: 372]

        if curr_p > v60 * 1.3: msg.append(f"🚨 乖離率過高 60SMA({v60:.2f})"); is_mail = True

        if not msg: msg.append("🌊 多方行進" if curr_p > v60 else "☁️ 空方盤整")
        return " | ".join(msg), curr_p, v60, bias, is_mail
    except: return "分析錯誤", 0, 0, 0, False

# --- 3. UI 介面 (加入遞增排序) ---
st.title("📈 股市戰略指揮中心")
if "stocks" not in st.session_state: st.session_state["stocks"] = ""

with st.sidebar:
    st.header("權限驗證")
    email_in = st.text_input("通知 Email", value="joywu4093@gmail.com").strip()
    if st.button("🔄 讀取雲端清單"):
        try:
            data = init_sheet().get_all_records()
            user = next((r for r in data if r['Email'] == email_in), None)
            if user: st.session_state["stocks"] = str(user['Stock_List'])
        except: st.error("連線失敗")
    ticker_input = st.text_area("自選股清單", value=st.session_state["stocks"], height=300)
    submit_btn = st.button("🚀 執行智能分析並同步")

if submit_btn:
    try:
        # 💡 關鍵：代號遞增排序
        raw_tk = re.findall(r'\d{4}', ticker_input)
        user_tk = sorted(list(dict.fromkeys(raw_tk)))
        st.session_state["stocks"] = ", ".join(user_tk)
        
        sheet = init_sheet()
        notify_list = []
        for t in user_tk:
            df = yf.download(f"{t}.TW", period="2y", progress=False)
            if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
            if not df.empty:
                sig, p, s60, b, m_trig = analyze_strategy(df)
                name = STOCK_NAMES.get(t, f"個股 {t}")
                with st.container(border=True):
                    # 💡 顯示格式對位 
                    st.markdown(f"#### {name} {t} - ${p:.2f} 乖離率 60SMA({s60:.2f}) {b:.1f}%")
                    st.write(f"📊 戰略判讀：{sig}")
                    if m_trig: notify_list.append(f"【{name} {t}】${p:.2f} | 60SMA({s60:.2f}) 乖離{b:.1f}% | {sig}")

        # 雲端同步
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = sheet.get_all_records()
        u_idx = next((i for i, r in enumerate(data) if r['Email'] == email_in), -1)
        if u_idx != -1:
            sheet.update_cell(u_idx + 2, 2, st.session_state["stocks"])
            sheet.update_cell(u_idx + 2, 3, now_str)
            st.success("✅ 雲端存檔同步完成！")
        
        if notify_list:
            s_u, s_p = st.secrets["GMAIL_USER"], st.secrets["GMAIL_PASSWORD"]
            msg = MIMEText("\n\n".join(notify_list))
            msg['Subject'] = f"📈 戰略警報 - {datetime.now().strftime('%m/%d %H:%M')}"
            msg['From'], msg['To'] = s_u, email_in
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(s_u, s_p)
                server.send_message(msg)
            st.toast("📧 警訊已寄出！")
    except Exception as e: st.error(f"系統錯誤: {e}")
