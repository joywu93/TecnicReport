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

# ==========================================
# 🔧 1. 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")

# 112 檔完整名稱表
STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2313": "華通", "2317": "鴻海", "2330": "台積電", "2404": "漢唐", "2454": "聯發科",
    "3037": "欣興", "3406": "玉晶光", "5225": "東科-KY", "6285": "啟碁", "6996": "力領科技",
    "8358": "金居", "9939": "宏全", "3030": "德律"
}

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# ==========================================
# 🧠 2. 核心戰略判讀 (依照最新修正要求)
# ==========================================
def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return "資料不足", 0, 0, 0, False
        
        # 💡 關鍵修正：使用 .item() 或 float() 確保獲取純數值，解決 Ambiguous Error
        close = df['Close'].dropna()
        volume = df['Volume'].dropna()
        curr_p = float(close.iloc[-1])
        prev_p = float(close.iloc[-2])
        p3_close = float(close.iloc[-4]) # 前3日收盤價
        
        curr_v = float(volume.iloc[-1])
        prev_v = float(volume.iloc[-2])
        
        # 計算均線今日值 (scalar values)
        v5 = float(close.rolling(5).mean().iloc[-1])
        v10 = float(close.rolling(10).mean().iloc[-1])
        v20 = float(close.rolling(20).mean().iloc[-1])
        v60 = float(close.rolling(60).mean().iloc[-1])
        v240 = float(close.rolling(240).mean().iloc[-1])
        
        # 計算均線昨日值 (判斷趨勢)
        p5 = float(close.rolling(5).mean().iloc[-2])
        p10 = float(close.rolling(10).mean().iloc[-2])
        p20 = float(close.rolling(20).mean().iloc[-2])
        p60 = float(close.rolling(60).mean().iloc[-2])

        up_cnt = sum([v5 > p5, v10 > p10, v20 > p20])
        dn_cnt = sum([v5 < p5, v10 < p10, v20 < p20])
        
        msg, is_mail = [], False
        bias = ((curr_p - v60) / v60) * 100

        # 1. 季線轉多/轉空
        if prev_p < p60 and curr_p > v60:
            msg.append("🚀 轉多訊號：站上季線(60SMA)"); is_mail = True
        elif prev_p > p60 and curr_p < v60:
            msg.append("📉 轉空警示：跌破季線(60SMA)"); is_mail = True

        # 2. 強勢反彈
        if (curr_p - prev_p)/prev_p >= 0.05 and curr_v > prev_v * 1.5:
            msg.append(f"🔥 強勢反彈 (爆量) 慎防未來3日跌破前3日收盤價({p3_close:.2f})"); is_mail = True

        # 3. 形態轉折 (修正：顯示 SMA 價位)
        if up_cnt >= 2 and curr_p < v60 and curr_p < v240:
            msg.append(f"✨ 底部轉折：均線翻揚 5SMA({v5:.2f}) 10SMA({v10:.2f})"); is_mail = True
        elif dn_cnt >= 2 and curr_p > v60 and curr_p > v240 and curr_p < v5:
            msg.append(f"✨ 高檔轉整理：均線翻下 5SMA({v5:.2f}) 10SMA({v10:.2f})"); is_mail = True

        # 4. 量價背離 (修正：未來3日判斷)
        if curr_v > prev_v * 1.2 and curr_p < v5 and curr_p < prev_p:
            msg.append(f"⚠️ 量價背離：未來3日的收盤價 > 前3日的收盤價({p3_close:.2f})"); is_mail = True

        # 6. 均線糾結 (💡 標註不發 mail)
        ma_diff = (max(v5, v10, v20) - min(v5, v10, v20)) / min(v5, v10, v20)
        if ma_diff < 0.02:
            msg.append("🌀 均線糾結：變盤在即")

        # 7. 乖離附加
        if curr_p > v60 * 1.3:
            msg.append(f"🚨 乖離率過高 60SMA({v60:.2f})"); is_mail = True

        if not msg:
            msg.append("🌊 多方行進" if curr_p > v60 else "☁️ 空方盤整")

        return " | ".join(msg), curr_p, v60, bias, is_mail
    except Exception as e:
        return f"分析錯誤: {str(e)}", 0, 0, 0, False

# ==========================================
# 🖥️ 3. UI 介面與顯示
# ==========================================
st.title("📈 股市戰略指揮中心")
if "stocks" not in st.session_state: st.session_state["stocks"] = ""

with st.sidebar:
    st.header("權限驗證")
    email_in = st.text_input("註冊 Email", value="joywu4093@gmail.com").strip()
    if st.button("🔄 讀取雲端清單"):
        try:
            sheet = init_sheet()
            data = sheet.get_all_records()
            user = next((r for r in data if r['Email'] == email_in), None)
            if user: st.session_state["stocks"] = str(user['Stock_List'])
            else: st.warning("查無帳號")
        except Exception as e: st.error(f"連線失敗: {e}")

    ticker_input = st.text_area("自選股清單", value=st.session_state["stocks"], height=300)
    submit_btn = st.button("🚀 執行智能分析並同步")

if st.session_state["stocks"]:
    cnt = len(re.findall(r'\d{4}', st.session_state["stocks"]))
    st.info(f"📋 聯合合作戰清單：已載入 {cnt} 檔個股")

if submit_btn:
    try:
        sheet = init_sheet()
        raw_tk = re.findall(r'\d{4}', ticker_input)
        user_tk = list(dict.fromkeys(raw_tk))
        
        if user_tk:
            st.session_state["stocks"] = ", ".join(user_tk)
            st.info(f"正在分析 {len(user_tk)} 檔戰略標的...")
            notify_list = []
            
            for t in user_tk:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                
                if not df.empty and not df['Close'].dropna().empty:
                    sig, p, s60, b, is_mail = analyze_strategy(df)
                    name = STOCK_NAMES.get(t, f"個股 {t}")
                    with st.container(border=True):
                        # 💡 修正顯示格式：堤維西 1522 - $44.40 乖離率 60SMA(47.95) -8.0%
                        st.markdown(f"#### {name} {t} - ${p:.2f} 乖離率 60SMA({s60:.2f}) {b:.1f}%")
                        st.write(f"📊 戰略判讀：{sig}")
                        if is_mail:
                            notify_list.append(f"【{name} {t}】${p:.2f} | 60SMA({s60:.2f}) 乖離{b:.1f}% | {sig}")

            # 雲端同步更新
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = sheet.get_all_records()
            u_idx = next((i for i, r in enumerate(data) if r['Email'] == email_in), -1)
            if u_idx != -1:
                sheet.update_cell(u_idx + 2, 2, st.session_state["stocks"])
                sheet.update_cell(u_idx + 2, 3, now_str)
                st.success("✅ 雲端存檔同步成功！")
            
            # 寄信 (過濾糾結)
            if notify_list:
                s_u, s_p = st.secrets["GMAIL_USER"], st.secrets["GMAIL_PASSWORD"]
                msg = MIMEText("\n\n".join(notify_list))
                msg['Subject'] = f"📈 戰略警報 - {datetime.now().strftime('%m/%d %H:%M')}"
                msg['From'], msg['To'] = s_u, email_in
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(s_u, s_p)
                    server.send_message(msg)
                st.toast("📧 戰略警訊已寄出！")
    except Exception as e: st.error(f"系統錯誤: {e}")
