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

STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2317": "鴻海", "2330": "台積電", "2404": "漢唐", "2454": "聯發科", "3014": "聯陽",
    "5225": "東科-KY", "6203": "海韻電", "6285": "啟碁", "6996": "力領科技", "8358": "金居"
    # (此處建議保留您原本代碼中完整的 112 檔清單) [cite: 15-37]
}

def init_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1

# ==========================================
# 🧠 2. 核心戰略判讀大腦 (2026 修正版) 
# ==========================================
def analyze_strategy(df):
    close, volume = df['Close'], df['Volume']
    if len(close) < 240: return "資料不足", 0, 0, False
    
    curr_price, prev_price = float(close.iloc[-1]), float(close.iloc[-2])
    curr_vol, prev_vol = float(volume.iloc[-1]), float(volume.iloc[-2])
    pct_change = (curr_price - prev_price) / prev_price
    
    # 均線計算 [cite: 66-71]
    sma5, sma10, sma20 = close.rolling(5).mean(), close.rolling(10).mean(), close.rolling(20).mean()
    sma60, sma240 = close.rolling(60).mean(), close.rolling(240).mean()
    
    v5, v10, v20, v60, v240 = sma5.iloc[-1], sma10.iloc[-1], sma20.iloc[-1], sma60.iloc[-1], sma240.iloc[-1]
    p5, p10, p20, p60 = sma5.iloc[-2], sma10.iloc[-2], sma20.iloc[-2], sma60.iloc[-2]
    
    # 均線趨勢判斷 [cite: 271-276]
    up_count = sum([v5 > p5, v10 > p10, v20 > p20])
    down_count = sum([v5 < p5, v10 < p10, v20 < p20])

    messages, is_alert = [], False

    # 1. 季線轉多/轉空 [cite: 257-262]
    if prev_price < p60 and curr_price > v60:
        messages.append(f"🚀 轉多訊號：站上季線(60SMA)")
        is_alert = True
    elif prev_price > p60 and curr_price < v60:
        messages.append(f"📉 轉空警示：跌破季線(60SMA)")
        is_alert = True

    # 2. 強勢反彈 [cite: 265-267]
    if pct_change >= 0.05 and curr_vol > prev_vol * 1.5:
        messages.append(f"🔥 強勢反彈 (漲>=5%且爆量1.5倍) 慎防未來3日跌破 {close.iloc[-4]:.2f}")
        is_alert = True

    # 3. 形態轉折 [cite: 268-277]
    if up_count >= 2 and curr_price < v60 and curr_price < v240:
        messages.append("✨ 底部轉折：均線翻揚")
        is_alert = True
    elif down_count >= 2 and curr_price > v60 and curr_price > v240 and curr_price < v5:
        messages.append("✨ 高檔轉整理：均線翻下")
        is_alert = True

    # 4. 量價背離 [cite: 280-282]
    if curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
        messages.append(f"⚠️ 量價背離：量增價跌，破5SMA")
        is_alert = True

    # 5. 年線防守 [cite: 285-290]
    dist_240 = (curr_price - v240) / v240
    if abs(dist_240) < 0.05 and down_count >= 3:
        messages.append("⚠️ 年線保衛戰：均線偏弱")
        is_alert = True

    # 6. 均線糾結 [cite: 292-294]
    ma_diff = (max(v5, v10, v20) - min(v5, v10, v20)) / min(v5, v10, v20)
    if ma_diff < 0.02:
        messages.append("🌀 均線糾結：變盤在即")
        is_alert = True

    # 7. 附加乖離標籤 [cite: 296-298]
    bias_val = ((curr_price - v60) / v60) * 100
    if curr_price > v60 * 1.3:
        messages.append(f"🚨 乖離率過高 60SMA({v60:.2f})")

    if not messages:
        messages.append("🌊 多方行進" if curr_price > v60 else "☁️ 空方盤整") [cite: 301-302]

    return " | ".join(messages), curr_price, bias_val, is_alert

# ==========================================
# 🖥️ 3. UI 介面程式碼 (解決空白問題) [cite: 188-251]
# ==========================================
st.title("📈 股市戰略指揮中心")

with st.sidebar.form(key='stock_form'):
    st.header("戰略設定")
    email_in = st.text_input("註冊 Email", value="joywu4093@gmail.com")
    ticker_input = st.text_area("自選股清單", height=300, placeholder="2330 2404")
    submit_btn = st.form_submit_button(label='🚀 啟動智能分析')

if submit_btn:
    try:
        sheet = init_sheet()
        raw_tickers = re.findall(r'\d{4}', ticker_input)
        user_tickers = list(dict.fromkeys(raw_tickers))
        
        if user_tickers:
            st.info(f"正在分析 {len(user_tickers)} 檔個股...")
            dl_list = [f"{t}.TW" for t in user_tickers] + [f"{t}.TWO" for t in user_tickers]
            all_data = yf.download(dl_list, period="2y", group_by='ticker', progress=False)

            for t in user_tickers:
                df = all_data[f"{t}.TW"] if f"{t}.TW" in all_data.columns.levels[0] else all_data.get(f"{t}.TWO", pd.DataFrame())
                if not df.empty and not df['Close'].dropna().empty:
                    sig, price, bias, urgent = analyze_strategy(df)
                    name = STOCK_NAMES.get(t, f"個股 {t}")
                    with st.container(border=True):
                        st.markdown(f"#### {name} `{t}` - ${price:.2f}")
                        st.write(f"戰略判讀：{sig}")
            st.success("分析完成！")
    except Exception as e:
        st.error(f"系統錯誤: {e}")
