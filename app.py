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
st.set_page_config(page_title="股市戰略 - 最終原生版", layout="wide")

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

# 偽裝標頭
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
]

# --- Email 發送函數 ---
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

# --- 核心邏輯：快取抓取 ---
@st.cache_data(ttl=900, show_spinner=False)
def fetch_stock_data_batch(ticker_list):
    data_results = []
    
    for t in ticker_list:
        max_retries = 3 # 增加重試次數到 3
        success = False
        
        for attempt in range(max_retries):
            try:
                # 每次重試都換一個瀏覽器身分
                session = requests.Session()
                session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
                
                # 稍微延遲，模擬真人
                time.sleep(random.uniform(1.0, 2.0))
                
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
                break
                
            except Exception:
                time.sleep(1.5) # 失敗後多休息一下
        
        if not success:
            data_results.append({
                "code": t, "name": STOCK_NAMES.get(t, t),
                "price": 0, "ma60": 0, "error": "連線逾時 (請稍後重試)"
            })
            
    return data_results

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 最終原生版") 
# ^^^ 請確認網頁更新後，標題變成這個才算成功！

# 側邊欄
with st.sidebar.form(key='stock_form'):
    st.header("設定")
    email_input = st.text_input("通知 Email (選填)", placeholder="輸入 Email 以接收警示")
    ticker_input = st.text_area("股票清單", value=DEFAULT_LIST, height=300)
    
    col1, col2 = st.columns(2)
    with col1:
        submit_btn = st.form_submit_button(label='🚀 一般執行')
    with col2:
        refresh_btn = st.form_submit_button(label='🔄 強制重抓')

# 讀取 Secrets
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

if refresh_btn:
    st.cache_data.clear()
    st.toast("快取已清除，正在重新連線...", icon="🔄")

if submit_btn or refresh_btn:
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    user_tickers = list(dict.fromkeys(raw_tickers))
    
    progress_text = "正在分析中..."
    my_bar = st.progress(0, text=progress_text)
    
    with st.spinner("正在連線 Yahoo Finance (速度較慢以防封鎖)..."):
        stock_data = fetch_stock_data_batch(user_tickers)
    
    my_bar.progress(100, text="分析完成！")
    time.sleep(0.5)
    my_bar.empty()
    
    notify_list = []
    
    # 顯示結果
    st.subheader(f"📊 分析結果 ({len(stock_data)} 檔)")
    
    for item in stock_data:
        # 1. 處理錯誤
        if item['error']:
            with st.container(border=True):
                st.markdown(f"**{item['name']} ({item['code']})**")
                st.error(f"❌ {item['error']}")
            continue
            
        price = item['price']
        ma60 = item['ma60']
        
        # 2. 計算乖離
        if ma60 > 0:
            bias_val = ((price - ma60) / ma60) * 100
        else:
            bias_val = 0
            
        # 3. 判斷訊號
        trend_msg = ""
        bias_msg = ""
        is_alert = False
        
        # 趨勢
        if price > ma60:
            trend_msg = "🚀 多方行進(觀察)"
        else:
            trend_msg = "📉 空方整理"
            
        # 乖離 (疊加)
        if bias_val >= 30:
            bias_msg = f"🔥 乖離過大 (MA60: {ma60:.1f})"
            is_alert = True
        elif bias_val >= 15:
            bias_msg = f"🔸 乖離偏高 (MA60: {ma60:.1f})"
            is_alert = True
            
        # 4. 顯示卡片 (Native Container) - 這裡完全沒有 HTML 代碼
        with st.container(border=True):
            # 第一行：名稱與股價
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"#### {item['name']} `{item['code']}`")
            c2.markdown(f"#### ${price}")
            
            # 第二行：乖離率數值 (用 Streamlit 顏色語法)
            if bias_val >= 15:
                st.markdown(f"乖離率：:red[**{bias_val:.1f}%**]")
            else:
                st.markdown(f"乖離率：:green[**{bias_val:.1f}%**]")
            
            # 第三行：訊號區
            st.divider() # 分隔線
            
            # 趨勢
            if "多方" in trend_msg:
                st.markdown(f":green[{trend_msg}]")
            else:
                st.markdown(f":grey[{trend_msg}]")
                
            # 乖離警示
            if bias_msg:
                if "過大" in bias_msg:
                    st.error(bias_msg) # 紅色底框
                else:
                    st.warning(bias_msg) # 黃色底框
                    
        # 收集 Email
        if is_alert:
            full_msg = f"{trend_msg} | {bias_msg}"
            notify_list.append(f"【{item['name']}】${price} | 乖離{bias_val:.1f}% | {full_msg}")

    # 發信
    if notify_list and email_input and MY_GMAIL:
        st.info(f"📧 偵測到 {len(notify_list)} 則警示，正在發送 Email...")
        body = "\n\n".join(notify_list)
        if send_email_batch(MY_GMAIL, MY_PWD, [email_input], "股市戰略警示", body):
            st.success("✅ Email 發送成功！")
        else:
            st.error("❌ Email 發送失敗")
