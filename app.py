import streamlit as st
import yfinance as yf
import pandas as pd
import time
import re
import smtplib
from email.mime.text import MIMEText

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 極速團購版", layout="wide")

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

# --- 核心邏輯：一次打包下載 (Batch Download) ---
@st.cache_data(ttl=600, show_spinner=False)
def fetch_all_data(user_tickers):
    # 1. 準備清單：因為不知道是上市(.TW)還是上櫃(.TWO)，我們兩個都猜！
    # 這樣一次下載 66 支，對 Yahoo 來說只是一次請求，非常快。
    download_list = []
    for t in user_tickers:
        download_list.append(f"{t}.TW")
        download_list.append(f"{t}.TWO")
    
    # 2. 發送超級請求 (Magic Happens Here)
    try:
        # group_by='ticker' 讓資料結構變成 data['2330.TW']['Close']
        data = yf.download(download_list, period="1y", group_by='ticker', threads=True, progress=False)
    except Exception:
        return []

    processed_results = []
    
    # 3. 整理資料
    for t in user_tickers:
        df = pd.DataFrame()
        valid_symbol = ""
        
        # 先找 TW
        if f"{t}.TW" in data.columns.levels[0]: # 檢查是否在第一層索引
            temp = data[f"{t}.TW"]
            # 檢查是否全是空值 (Yahoo有時候會回傳空表格)
            if not temp['Close'].dropna().empty:
                df = temp
                valid_symbol = "TW"
        
        # 如果 TW 沒資料，找 TWO
        if df.empty and f"{t}.TWO" in data.columns.levels[0]:
            temp = data[f"{t}.TWO"]
            if not temp['Close'].dropna().empty:
                df = temp
                valid_symbol = "TWO"
        
        # 還是空的？那就是真的抓不到
        if df.empty:
            processed_results.append({"code": t, "name": STOCK_NAMES.get(t, t), "error": "無資料"})
            continue

        # 計算
        close = df['Close'].dropna()
        if len(close) < 60:
            processed_results.append({"code": t, "name": STOCK_NAMES.get(t, t), "error": "資料不足"})
            continue
            
        curr_price = close.iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]
        
        processed_results.append({
            "code": t,
            "name": STOCK_NAMES.get(t, t),
            "price": float(curr_price),
            "ma60": float(ma60),
            "error": None
        })
        
    return processed_results

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 極速團購版")

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
    st.toast("快取已清除，正在重新下載...", icon="🔄")

if submit_btn or refresh_btn:
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    user_tickers = list(dict.fromkeys(raw_tickers))
    
    st.info(f"正在向 Yahoo 請求 {len(user_tickers)} 檔股票資料 (批次模式)...")
    
    # 執行批次下載
    stock_data = fetch_all_data(user_tickers)
    
    st.success(f"分析完成！")
    
    notify_list = []
    
    # 顯示結果
    st.subheader(f"📊 分析結果 ({len(stock_data)} 檔)")
    
    # 使用 2 欄排列，讓畫面更緊湊
    cols = st.columns(2) if len(stock_data) > 1 else [st]
    
    for i, item in enumerate(stock_data):
        with cols[i % 2]: # 左右輪流放
            if item.get('error'):
                with st.container(border=True):
                    st.markdown(f"#### {item['name']} `{item['code']}`")
                    st.error(f"❌ {item['error']}")
                continue
                
            price = item['price']
            ma60 = item['ma60']
            
            # 計算乖離
            if ma60 > 0:
                bias_val = ((price - ma60) / ma60) * 100
            else:
                bias_val = 0
                
            # 判斷訊號
            msgs = []
            is_alert = False
            
            # 趨勢
            trend_msg = "🚀 多方行進(觀察)" if price > ma60 else "📉 空方整理"
            
            # 乖離 (疊加)
            bias_msg = ""
            if bias_val >= 30:
                bias_msg = f"🔥 乖離過大 (MA60: {ma60:.1f})"
                is_alert = True
            elif bias_val >= 15:
                bias_msg = f"🔸 乖離偏高 (MA60: {ma60:.1f})"
                is_alert = True
                
            # 顯示卡片
            with st.container(border=True):
                c1, c2 = st.columns([2, 1])
                c1.markdown(f"#### {item['name']} `{item['code']}`")
                c2.markdown(f"#### ${price:.1f}")
                
                if bias_val >= 15:
                    st.markdown(f"乖離率：:red[**{bias_val:.1f}%**]")
                else:
                    st.markdown(f"乖離率：:green[**{bias_val:.1f}%**]")
                
                st.divider()
                
                if "多方" in trend_msg:
                    st.markdown(f":green[{trend_msg}]")
                else:
                    st.markdown(f":grey[{trend_msg}]")
                    
                if bias_msg:
                    if "過大" in bias_msg:
                        st.error(bias_msg)
                    else:
                        st.warning(bias_msg)

            # 收集 Email
            if is_alert:
                full_msg = f"{trend_msg} | {bias_msg}"
                notify_list.append(f"【{item['name']}】${price} | 乖離{bias_val:.1f}% | {full_msg}")

    # 發信
    if notify_list and email_input and MY_GMAIL:
        st.info(f"📧 偵測到警示，正在發送 Email...")
        body = "\n\n".join(notify_list)
        if send_email_batch(MY_GMAIL, MY_PWD, [email_input], "股市戰略警示", body):
            st.success("✅ Email 發送成功！")
