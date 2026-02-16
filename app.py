import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import re
import requests

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 強力連線版", layout="wide")

# 偽裝成真人瀏覽器的 Header (這是破解封鎖的關鍵)
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://finance.yahoo.com/"
})

# --- 1. 中文名稱對照表 ---
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

# --- 2. 策略邏輯 ---
def check_strategy(df):
    try:
        close = df['Close']
        volume = df['Volume']
        if len(close) < 60: return [], "資料不足", 0
        
        curr_price = close.iloc[-1]
        prev_price = close.iloc[-2]
        v60 = close.rolling(60).mean().iloc[-1]
        p60 = close.rolling(60).mean().iloc[-2]
        
        status = []
        if curr_price >= v60 * 1.3: status.append("⚠️ 乖離過大")
        if prev_price > p60 and curr_price < v60: status.append("📉 跌破季線")
        elif prev_price < p60 and curr_price > v60: status.append("🚀 站上季線")
        
        trend = "多方" if curr_price > v60 else "空方"
        if not status: status.append(f"{trend}盤整")
        
        return status, trend, curr_price
    except Exception as e:
        return [f"計算錯誤: {e}"], "錯誤", 0

# --- 3. 診斷式抓取 ---
def fetch_stock(ticker):
    # 這裡使用我們偽裝過的 SESSION
    try:
        t = yf.Ticker(f"{ticker}.TW", session=SESSION)
        df = t.history(period="3mo")
        if not df.empty: return df, f"{ticker}.TW"
        
        t = yf.Ticker(f"{ticker}.TWO", session=SESSION)
        df = t.history(period="3mo")
        if not df.empty: return df, f"{ticker}.TWO"
    except Exception as e:
        st.error(f"連線錯誤 ({ticker}): {e}")
        return None, None
        
    return None, None

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("🚑 股市戰略 - 強力連線版")

# 1. 測試按鈕：先確定能不能連上 Yahoo
if st.button("🔴 先按這裡測試連線 (台積電 2330)"):
    st.info("正在嘗試連線到 Yahoo Finance...")
    try:
        df_test, sym = fetch_stock("2330")
        if df_test is not None and not df_test.empty:
            st.success(f"✅ 連線成功！抓到 {sym} 資料，共 {len(df_test)} 筆。IP 未被封鎖。")
        else:
            st.error("❌ 連線失敗。Yahoo 正在封鎖此 IP，請等待 1-2 小時後再試。")
    except Exception as e:
        st.error(f"❌ 發生嚴重錯誤: {e}")

st.divider()

# 2. 正常功能區
try:
    MY_GMAIL = st.secrets.get("GMAIL_USER", "")
    MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")
    MY_PRIVATE_LIST = st.secrets.get("MY_LIST", "2330")

    with st.form(key='main_form'):
        st.write("### 批量分析")
        friend_email = st.text_input("Email (選填)", placeholder="輸入 Email")
        
        default_val = "2330"
        if friend_email == MY_GMAIL: default_val = MY_PRIVATE_LIST
        
        ticker_input = st.text_area("股票清單", value=default_val, height=200)
        submit_btn = st.form_submit_button(label='🚀 開始執行')

    if submit_btn:
        raw_tickers = re.findall(r'\d{4}', ticker_input)
        tickers = list(dict.fromkeys(raw_tickers))
        
        st.write(f"📊 準備分析 {len(tickers)} 檔股票...")
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 這裡不使用 st.dataframe，改用 expander + columns 避免表格渲染失敗
        for i, t in enumerate(tickers):
            status_text.text(f"正在處理 ({i+1}/{len(tickers)}): {t} ...")
            
            df, final_symbol = fetch_stock(t)
            
            ch_name = STOCK_NAMES.get(t, t)
            
            if df is not None:
                status_list, trend, price = check_strategy(df)
                status_str = " | ".join(status_list)
                
                # 直接畫出卡片
                with st.expander(f"✅ {i+1}. {ch_name} ({final_symbol}) - ${round(price, 2)}", expanded=True):
                    c1, c2 = st.columns([1, 3])
                    c1.write(f"**狀態**: {trend}")
                    if "⚠️" in status_str or "📉" in status_str:
                        c2.error(status_str)
                    elif "🚀" in status_str or "🔥" in status_str:
                        c2.success(status_str)
                    else:
                        c2.info(status_str)
            else:
                st.error(f"❌ {i+1}. {ch_name} ({t}): 讀取失敗 (Yahoo 阻擋或無資料)")
            
            progress_bar.progress((i + 1) / len(tickers))
            time.sleep(0.5) # 必要休息
            
        st.success("執行結束")

except Exception as e:
    st.error(f"系統崩潰: {e}")
