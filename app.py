import streamlit as st
import yfinance as yf
import pandas as pd
import time
import re
import random
import smtplib
from email.mime.text import MIMEText
import requests

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 最終完結版", layout="wide")

# 中文對照表
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

# 預設清單
DEFAULT_LIST = "2330, 2317, 2323, 2451, 6229, 4763, 1522, 2404, 6788, 2344, 2368, 4979, 3163, 1326, 3491, 6143, 2383, 2454, 5225, 3526, 6197, 6203, 3570, 3231, 8299, 8069, 3037, 8046, 4977, 3455, 2408, 8271, 5439"

# 偽裝標頭 (隨機切換，防擋專用)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0"
]

# --- Email 發送函數 (恢復功能) ---
def send_email_batch(sender, pwd, receivers, subject, body):
    if not sender or not pwd: return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市小幫手 <{sender}>"
        msg['To'] = ", ".join(receivers)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True
    except Exception:
        return False

# --- 核心邏輯：快取抓取 (含自動重試) ---
@st.cache_data(ttl=900, show_spinner=False)
def fetch_stock_data_batch(ticker_list):
    data_results = []
    
    for t in ticker_list:
        max_retries = 3 # 每支股票最多重試 3 次
        success = False
        
        for attempt in range(max_retries):
            try:
                # 每次連線換一個身分
                session = requests.Session()
                session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
                
                # 嘗試 TW
                stock_id = f"{t}.TW"
                ticker_obj = yf.Ticker(stock_id, session=session)
                df = ticker_obj.history(period="1y")
                
                # 嘗試 TWO
                if df.empty:
                    stock_id = f"{t}.TWO"
                    ticker_obj = yf.Ticker(stock_id, session=session)
                    df = ticker_obj.history(period="1y")
                
                if df.empty or len(df) < 60:
                    raise ValueError("Data Empty")

                # 計算數據
                close = df['Close']
                curr_price = close.iloc[-1]
                ma60 = close.rolling(60).mean().iloc[-1]
                
                data_results.append({
                    "code": t,
                    "name": STOCK_NAMES.get(t, t),
                    "price": float(curr_price),
                    "ma60": float(ma60),
                    "error": None
                })
                success = True
                time.sleep(random.uniform(0.1, 0.5)) # 成功後稍微休息
                break # 成功就跳出重試迴圈
                
            except Exception:
                # 失敗了，休息久一點再試
                time.sleep(random.uniform(1.0, 2.0))
        
        # 如果試了 3 次還是失敗
        if not success:
            data_results.append({
                "code": t, "name": STOCK_NAMES.get(t, t),
                "price": 0, "ma60": 0, "error": "連線失敗 (Yahoo阻擋)"
            })
            
    return data_results

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 最終完結版")

# 側邊欄
with st.sidebar.form(key='stock_form'):
    st.header("設定")
    
    # 恢復 Email 輸入框
    email_input = st.text_input("通知 Email (選填)", placeholder="輸入以接收通知")
    
    ticker_input = st.text_area("股票清單", value=DEFAULT_LIST, height=300)
    
    col1, col2 = st.columns(2)
    with col1:
        submit_btn = st.form_submit_button(label='🚀 一般執行')
    with col2:
        refresh_btn = st.form_submit_button(label='🔄 強制重抓')

# 讀取 Secrets (如果有設定的話)
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

if refresh_btn:
    st.cache_data.clear()
    st.toast("🧹 快取已清除，正在重新連線並嘗試突破封鎖...", icon="🔄")

if submit_btn or refresh_btn:
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    user_tickers = list(dict.fromkeys(raw_tickers))
    
    with st.spinner(f"正在分析 {len(user_tickers)} 檔股票 (啟動自動重試機制)..."):
        stock_data = fetch_stock_data_batch(user_tickers)
    
    st.success(f"分析完成！共 {len(stock_data)} 檔。")
    
    notify_list = []
    
    # 顯示卡片
    for item in stock_data:
        if item['error']:
            st.warning(f"⚠️ {item['name']} ({item['code']}): {item['error']}")
            continue
            
        price = item['price']
        ma60 = item['ma60']
        
        # 計算乖離
        if ma60 > 0:
            bias_val = ((price - ma60) / ma60) * 100
        else:
            bias_val = 0
            
        # === 訊號判斷 (疊加式邏輯) ===
        msgs = []
        border_style = "1px solid #ddd" 
        bias_color = "black"
        
        # 1. 趨勢
        if price > ma60:
            msgs.append("🚀 多方行進(觀察)")
            if bias_val < 15: 
                 border_style = "2px solid #28a745" # 綠框
        else:
            msgs.append("📉 空方整理")
        
        # 2. 乖離 (疊加在後)
        is_alert = False
        if bias_val >= 30:
            msgs.append(f"🔥 乖離過大60sma({ma60:.1f})")
            border_style = "2px solid #dc3545" # 紅框
            bias_color = "#dc3545" # 紅字
            is_alert = True
        elif bias_val >= 15:
            msgs.append(f"🔸 乖離偏高60sma({ma60:.1f})")
            border_style = "2px solid #ffc107" # 黃框
            bias_color = "#d39e00" # 黃字
            is_alert = True
            
        final_signal = " | ".join(msgs)
        
        # 收集要寄信的內容
        if is_alert:
            notify_list.append(f"【{item['name']}】${price} | {final_signal}")
        
        # === 修正 HTML 顯示 (解決亂碼問題) ===
        # 這裡改用單純的 string formatting，確保不會被誤判
        card_html = f"""
        <div style="border: {border_style}; padding: 12px; border-radius: 8px; margin-bottom: 12px; background-color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 1.2em; font-weight: bold;">{item['name']}</span>
                    <span style="color: #666; font-size: 0.9em;"> ({item['code']})</span>
                </div>
                <div style="font-size: 1.3em; font-weight: bold;">${price}</div>
            </div>
            <div style="margin-top: 8px; display: flex; justify-content: space-between; font-size: 0.95em; color: #444; border-top: 1px solid #eee; padding-top: 8px;">
                <span>乖離率: <strong style="color: {bias_color};">{bias_val:.1f}%</strong></span>
            </div>
            <div style="margin-top: 8px; font-weight: bold; font-size: 1em;">
                {final_signal}
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

    # 發信邏輯
    if notify_list and email_input and MY_GMAIL:
        st.info("📧 偵測到警示訊號，正在發送 Email...")
        body = "\n\n".join(notify_list)
        if send_email_batch(MY_GMAIL, MY_PWD, [email_input], "股市戰略警示", body):
            st.success("✅ Email 發送成功！")
        else:
            st.error("❌ Email 發送失敗 (請檢查 Secrets 設定)")
