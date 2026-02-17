import streamlit as st
import yfinance as yf
import pandas as pd
import time
import re
import os
import requests
import random

st.set_page_config(page_title="股市戰略 - 網頁版", layout="wide")

# 偽裝標頭
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/123.0.0.0 Safari/537.36"
]

# 中文對照
STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "6203": "海韻電", "3570": "大塚", "4766": "南寶", "NVDA": "輝達",
    "2313": "華通", "2454": "聯發科", "2303": "聯電", "2603": "長榮", "2609": "陽明", "2615": "萬海",
    "2323": "中環", "2451": "創見", "6229": "研通", "4763": "材料-KY", "1522": "堤維西", "2404": "漢唐",
    "6788": "華景電", "2344": "華邦電", "1519": "華城", "1513": "中興電", "3231": "緯創", "3035": "智原",
    "2408": "南亞科", "3406": "玉晶光", "2368": "金像電", "4979": "華星光", "3163": "波若威", "1326": "台化",
    "3491": "昇達科", "6143": "振曜", "2383": "台光電", "5225": "東科-KY", "3526": "凡甲", "6197": "佳必琪",
    "8299": "群聯", "8069": "元太", "3037": "欣興", "8046": "南電", "4977": "眾達-KY", "3455": "由田",
    "8271": "宇瞻", "5439": "高技"
}

# 讀取 Render 環境變數
MY_PRIVATE_LIST = os.environ.get("MY_LIST", "2330") 

def check_strategy(df):
    try:
        close = df['Close'].dropna()
        if len(close) < 60: return [], 0, 0, "N/A"
        
        curr_price = close.iloc[-1]
        s60 = close.rolling(60).mean()
        v60 = s60.iloc[-1]
        
        status = []
        
        # === 乖離率同步邏輯 ===
        bias_pct = ((curr_price - v60) / v60) * 100
        
        # 條件 A: > 30%
        if bias_pct >= 30:
            status.append(f"🔥⚠️ 乖離過大 (+{bias_pct:.1f}%)")
        # 條件 B: > 15%
        elif bias_pct >= 15:
            status.append(f"🔸 乖離偏高 (+{bias_pct:.1f}%)")
            
        if curr_price < v60:
            status.append("📉 季線之下")
            
        if not status:
            status.append("多方行進")
            
        return status, curr_price, bias_pct, "N/A"
    except:
        return ["計算錯"], 0, 0, "N/A"

@st.cache_data(ttl=600)
def fetch_stock(ticker):
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
        t = yf.Ticker(f"{ticker}.TW", session=session)
        df = t.history(period="1y")
        if not df.empty and len(df) > 60: return df
        
        t = yf.Ticker(f"{ticker}.TWO", session=session)
        df = t.history(period="1y")
        if not df.empty and len(df) > 60: return df
    except:
        pass
    return None

st.title("📈 股市戰略 - 網頁版")
use_mobile_view = st.toggle("📱 手機卡片模式", value=True)

with st.sidebar.form(key='stock_form'):
    ticker_input = st.text_area("股票清單", value=MY_PRIVATE_LIST if len(MY_PRIVATE_LIST)>2 else "2330", height=250)
    submit_btn = st.form_submit_button(label='🚀 開始執行')

if submit_btn:
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    user_tickers = list(dict.fromkeys(raw_tickers))
    
    st.info(f"正在分析 {len(user_tickers)} 檔股票...")
    results = []
    progress_bar = st.progress(0)
    
    for i, t in enumerate(user_tickers):
        df = fetch_stock(t)
        
        row_data = {
            "代號": t,
            "名稱": STOCK_NAMES.get(t, t),
            "現價": 0,
            "乖離": 0,
            "訊號": "❌ 無法讀取 (被擋)"
        }
        
        if df is not None:
            status_list, price, bias, _ = check_strategy(df)
            row_data["現價"] = round(price, 2)
            row_data["乖離"] = round(bias, 1)
            row_data["訊號"] = " | ".join(status_list)
        
        results.append(row_data)
        progress_bar.progress((i + 1) / len(user_tickers))
        time.sleep(random.uniform(0.5, 1.5)) # 隨機延遲防擋
        
    df_res = pd.DataFrame(results)
    
    if use_mobile_view:
        for idx, row in df_res.iterrows():
            border = "1px solid #ddd"
            if "🔥" in row['訊號']: border = "2px solid #dc3545"
            elif "🔸" in row['訊號']: border = "2px solid #ffc107"
            
            with st.container():
                st.markdown(f"""
                <div style="border: {border}; padding: 10px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between;">
                        <b>{row['名稱']} ({row['代號']})</b>
                        <b>${row['現價']}</b>
                    </div>
                    <div style="font-size: 0.9em; color: #555; margin-top: 5px;">
                        乖離率：{row['乖離']}%
                    </div>
                    <div style="margin-top: 5px; font-weight: bold;">{row['訊號']}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.dataframe(df_res)
