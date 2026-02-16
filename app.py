import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import re
import os
import requests
import random

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 最終重試版", layout="wide")

# 更多樣化的偽裝身分
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1"
]

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

# --- 2. 安全讀取設定 ---
def get_config(key, default_value):
    val = os.environ.get(key)
    if val: return val
    try:
        return st.secrets[key]
    except:
        return default_value

MY_GMAIL = get_config("GMAIL_USER", "")
MY_PWD = get_config("GMAIL_PASSWORD", "")
MY_PRIVATE_LIST = get_config("MY_LIST", "2330") 

# --- 3. Email 發送函數 ---
def send_email_batch(sender, pwd, receivers, subject, body):
    if not sender or not pwd: return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市監控小幫手 <{sender}>"
        msg['To'] = ", ".join(receivers)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True
    except Exception:
        return False

# --- 4. 核心判讀邏輯 ---
def check_strategy(df):
    try:
        close = df['Close']
        volume = df['Volume']
        close = close.dropna()
        volume = volume.dropna()
        
        if len(close) < 60: return [], "資料不足", 0, "N/A", 0, False
        
        curr_price = close.iloc[-1]
        prev_price = close.iloc[-2]
        curr_vol = volume.iloc[-1]
        prev_vol = volume.iloc[-2]
        
        s3 = close.rolling(3).mean()
        s5 = close.rolling(5).mean()
        s10 = close.rolling(10).mean()
        s20 = close.rolling(20).mean()
        s60 = close.rolling(60).mean() # 60MA
        
        v60 = s60.iloc[-1]
        p60 = s60.iloc[-2]
        v5, v3 = s5.iloc[-1], s3.iloc[-1]
        
        # 均線狀態
        trend_up = {
            5: v5 > s5.iloc[-2],
            10: s10.iloc[-1] > s10.iloc[-2],
            20: s20.iloc[-1] > s20.iloc[-2],
            60: v60 > p60
        }
        up_count = sum(trend_up.values())
        down_count = 4 - up_count
        ma_status_str = f"⬆️{up_count} / ⬇️{down_count}"
        
        status = []
        need_notify = False
        
        # 乖離率
        bias_pct = ((curr_price - v60) / v60) * 100
        
        if bias_pct >= 30: 
            status.append(f"🔴 乖離率過大 (+{bias_pct:.1f}%)")
            need_notify = True
        elif bias_pct >= 20: 
            status.append(f"🔸 乖離率偏高 (+{bias_pct:.1f}%)")
            need_notify = True
            
        if prev_price > p60 and curr_price < v60:
            status.append("📉 跌破季線")
            need_notify = True
        elif prev_price < p60 and curr_price > v60:
            status.append("🚀 站上季線")
            need_notify = True
            
        pct_change = (curr_price - prev_price) / prev_price if prev_price != 0 else 0
        if pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > v3:
            status.append("🔥 強勢反彈")
            need_notify = True
            
        trend = "多方" if curr_price > v60 else "空方"
        if not status: status.append(f"{trend}盤整")

        return status, f"{trend}", curr_price, ma_status_str, bias_pct, need_notify
    except Exception as e:
        return [f"計算錯誤"], "錯誤", 0, "N/A", 0, False

# --- 5. 抓取函數 (含重試機制 + 快取) ---
# 使用 ttl=900 (15分鐘快取)，避免短時間重複抓取同一支股票
@st.cache_data(ttl=900, show_spinner=False)
def fetch_with_retry(ticker):
    max_retries = 3  # 最多試 3 次
    
    for attempt in range(max_retries):
        try:
            # 每次換一個 User-Agent
            session = requests.Session()
            session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
            
            # 嘗試 TW
            t = yf.Ticker(f"{ticker}.TW", session=session)
            df = t.history(period="1y")
            if not df.empty and len(df) > 60: return df, f"{ticker}.TW", ""
            
            # 嘗試 TWO
            t = yf.Ticker(f"{ticker}.TWO", session=session)
            df = t.history(period="1y")
            if not df.empty and len(df) > 60: return df, f"{ticker}.TWO", ""
            
            # 如果是空值，拋出例外以觸發重試
            raise ValueError("Empty Data")
            
        except Exception as e:
            # 失敗了，休息一下再試
            if attempt < max_retries - 1:
                wait_time = random.uniform(2, 5) # 失敗後等待 2~5 秒
                time.sleep(wait_time)
                continue # 繼續下一次迴圈
            else:
                return None, None, f"重試{max_retries}次失敗 ({str(e)})"
                
    return None, None, "未知錯誤"

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 最終重試版")
st.caption("啟動重試機制：若抓取失敗，系統將自動換身分重試 3 次，請耐心等候。")

use_mobile_view = st.toggle("📱 手機卡片模式", value=True)

with st.sidebar.form(key='stock_form'):
    st.header("設定")
    friend_email = st.text_input("Email (選填)", placeholder="輸入 Email")
    default_val = MY_PRIVATE_LIST if len(MY_PRIVATE_LIST) > 2 else "2330"
    ticker_input = st.text_area("股票清單", value=default_val, height=250)
    submit_btn = st.form_submit_button(label='🚀 開始執行')

if submit_btn:
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    user_tickers = list(dict.fromkeys(raw_tickers))
    
    st.info(f"📊 正在分析 {len(user_tickers)} 檔股票...")
    
    results = []
    notify_list = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(user_tickers):
        status_text.text(f"正在分析 ({i+1}/{len(user_tickers)}): {t} ...")
        
        # 呼叫帶有快取和重試功能的抓取函數
        df, final_symbol, err_msg = fetch_with_retry(t)
        
        row_data = {
            "序號": i + 1,
            "代號": t,
            "名稱": STOCK_NAMES.get(t, t),
            "現價": 0,
            "均線": "N/A",
            "乖離": 0,
            "訊號": f"❌ {err_msg}" if err_msg else "❌ 無法讀取"
        }
        
        if df is not None:
            status_list, trend, price, ma_status, bias, need_notify = check_strategy(df)
            row_data["代號"] = final_symbol
            row_data["名稱"] = STOCK_NAMES.get(t, final_symbol)
            row_data["現價"] = round(price, 2)
            row_data["均線"] = ma_status
            row_data["乖離"] = round(bias, 1)
            row_data["訊號"] = " | ".join(status_list)
            
            if need_notify:
                notify_list.append(f"【{row_data['名稱']}】{price} | {row_data['訊號']}\n")
        
        results.append(row_data)
        progress_bar.progress((i + 1) / len(user_tickers))
        
        # 成功後也要稍微休息，避免太快打下一支
        if df is not None:
            time.sleep(random.uniform(0.5, 1.5))
        
    status_text.text("✅ 分析完成！")
    
    df_res = pd.DataFrame(results)
    
    if use_mobile_view:
        for idx, row in df_res.iterrows():
            border = "1px solid #ddd"
            bg_color = "#ffffff"
            
            if "🔴" in row['訊號']: border = "2px solid #dc3545" 
            elif "🔸" in row['訊號']: border = "2px solid #ffc107"
            elif "🚀" in row['訊號'] or "🔥" in row['訊號']: border = "2px solid #28a745"
            
            bias_color = "black"
            if row['乖離'] >= 20: bias_color = "#dc3545"
            elif row['乖離'] <= -20: bias_color = "#28a745"

            with st.container():
                st.markdown(f"""
                <div style="border: {border}; padding: 12px; border-radius: 8px; margin-bottom: 12px; background-color: {bg_color}; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div>
                            <span style="font-size: 1.1em; font-weight: bold;">{row['序號']}. {row['名稱']}</span>
                            <span style="color: #666; font-size: 0.9em;"> ({row['代號']})</span>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.2em; font-weight: bold;">${row['現價']}</div>
                        </div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.9em; color: #555; border-top: 1px solid #eee; padding-top: 8px;">
                        <span>均線：{row['均線']}</span>
                        <span style="color: {bias_color}; font-weight: bold;">乖離率：{row['乖離']}%</span>
                    </div>
                    <div style="margin-top: 8px; font-weight: bold; color: #333;">
                        {row['訊號']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.dataframe(df_res, use_container_width=True, hide_index=True)

    if notify_list and MY_GMAIL and friend_email:
        chunks = [notify_list[i:i + 20] for i in range(0, len(notify_list), 20)]
        for i, chunk in enumerate(chunks):
            send_email_batch(MY_GMAIL, MY_PWD, [MY_GMAIL, friend_email], f"戰略訊號 ({i+1})", "".join(chunk))
            time.sleep(1)
        st.success("📧 通知信已發送")
