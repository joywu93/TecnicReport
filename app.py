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
# 🔧 1. 系統設定與 112 檔對照表
# ==========================================
st.set_page_config(page_title="股市戰略指揮中心", layout="wide")

# 已根據您的指示修正 6996 為力領科技
STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2317": "鴻海", "2330": "台積電", "2404": "漢唐", "2454": "聯發科", "5225": "東科-KY",
    "6285": "啟碁", "6996": "力領科技", "8358": "金居", "9939": "宏全"
}

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    # 使用您指定的試算表 ID
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# ==========================================
# 🧠 2. 核心戰略判讀大腦 (依據《條件判讀.docx》)
# ==========================================
def analyze_strategy(df):
    try:
        close, volume = df['Close'], df['Volume']
        if len(close) < 240: return "資料不足", None, 0, False
        
        curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        pct_change = (curr_p - prev_p) / prev_p
        
        ma5, ma10, ma20 = close.rolling(5).mean(), close.rolling(10).mean(), close.rolling(20).mean()
        ma60, ma240 = close.rolling(60).mean(), close.rolling(240).mean()
        
        v5, v10, v20, v60, v240 = ma5.iloc[-1], ma10.iloc[-1], ma20.iloc[-1], ma60.iloc[-1], ma240.iloc[-1]
        p5, p60 = ma5.iloc[-2], ma60.iloc[-2]
        
        up_cnt = sum([v5 > ma5.iloc[-2], v10 > ma10.iloc[-2], v20 > ma20.iloc[-2]])
        dn_cnt = sum([v5 < ma5.iloc[-2], v10 < ma10.iloc[-2], v20 < ma20.iloc[-2]])

        msg, alert = [], False

        # 1. 季線轉折
        if prev_p < p60 and curr_p > v60:
            msg.append(f"🚀 轉多訊號：站上季線(60SMA) ({v60:.2f})"); alert = True
        elif prev_p > p60 and curr_p < v60:
            msg.append(f"📉 轉空警示：跌破季線(60SMA) ({v60:.2f})"); alert = True

        # 2. 強勢反彈 (漲>=5%且爆量1.5倍)
        if pct_change >= 0.05 and curr_v > prev_v * 1.5:
            msg.append(f"🔥 強勢反彈 (爆量) 慎防跌破 {close.iloc[-4]:.2f}"); alert = True

        # 3. 形態轉折
        if up_cnt >= 2 and curr_p < v60 and curr_p < v240:
            msg.append("✨ 底部轉折：均線翻揚"); alert = True
        elif dn_cnt >= 2 and curr_p > v60 and curr_p > v240 and curr_p < v5:
            msg.append("✨ 高檔轉整理：均線翻下"); alert = True

        # 4. 量價背離
        if curr_v > prev_v * 1.2 and curr_p < v5 and curr_p < prev_p:
            msg.append("⚠️ 量價背離：量增價跌"); alert = True

        # 5. 年線防守
        dist_240 = (curr_p - v240) / v240
        if abs(dist_240) < 0.05 and dn_cnt >= 3:
            msg.append("⚠️ 年線保衛戰：均線偏弱"); alert = True

        # 6. 均線糾結 (差距 < 2%)
        ma_diff = (max(v5, v10, v20) - min(v5, v10, v20)) / min(v5, v10, v20)
        if ma_diff < 0.02:
            msg.append("🌀 均線糾結：變盤在即"); alert = True

        # 7. 附加乖離標籤
        bias = ((curr_p - v60) / v60) * 100
        if curr_p > v60 * 1.3:
            msg.append(f"🚨 乖離率過高 60SMA({v60:.2f})"); alert = True

        if not msg:
            msg.append("🌊 多方行進" if curr_p > v60 else "☁️ 空方盤整")

        return " | ".join(msg), curr_p, bias, alert
    except:
        return None, None, None, False

# ==========================================
# 🖥️ 3. UI 介面與資料同步
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
            user_row = next((r for r in data if r['Email'] == email_in), None)
            if user_row: st.session_state["stocks"] = str(user_row['Stock_List'])
            else: st.warning("查無帳號")
        except Exception as e: st.error(f"連線失敗: {e}")

    ticker_input = st.text_area("自選股清單", value=st.session_state["stocks"], height=300)
    submit_btn = st.button("🚀 執行智能分析並同步")

if st.session_state["stocks"]:
    count = len(re.findall(r'\d{4}', st.session_state["stocks"]))
    st.info(f"📋 聯合合作戰清單：已載入 {count} 檔個股")

if submit_btn:
    try:
        sheet = init_sheet()
        raw_tickers = re.findall(r'\d{4}', ticker_input)
        user_tickers = list(dict.fromkeys(raw_tickers))
        
        if user_tickers:
            st.session_state["stocks"] = ", ".join(user_tickers)
            notify_list = []
            
            dl_list = [f"{t}.TW" for t in user_tickers] + [f"{t}.TWO" for t in user_tickers]
            all_data = yf.download(dl_list, period="2y", group_by='ticker', progress=False)

            for t in user_tickers:
                df = all_data[f"{t}.TW"] if f"{t}.TW" in all_data.columns.levels[0] else all_data.get(f"{t}.TWO", pd.DataFrame())
                if not df.empty and not df['Close'].dropna().empty:
                    sig, price, bias, urgent = analyze_strategy(df)
                    if price is not None:
                        name = STOCK_NAMES.get(t, f"個股 {t}")
                        with st.container(border=True):
                            st.markdown(f"#### {name} `{t}` - ${price:.2f}")
                            st.write(f"戰略判讀：{sig}")
                            if urgent: notify_list.append(f"【{name} {t}】${price:.2f} | {sig}")

            # 雲端存檔更新
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = sheet.get_all_records()
            u_idx = next((i for i, r in enumerate(data) if r['Email'] == email_in), -1)
            if u_idx != -1:
                sheet.update_cell(u_idx + 2, 2, st.session_state["stocks"])
                sheet.update_cell(u_idx + 2, 3, now_str)
                st.success("✅ 雲端存檔與同步完成！")
    except Exception as e: st.error(f"系統錯誤: {e}")
