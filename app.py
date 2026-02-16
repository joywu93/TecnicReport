import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import re
import os
import requests

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 專家校正版", layout="wide")

# 偽裝標頭
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

# --- 4. 核心判讀邏輯 (專家算式) ---
def check_strategy(df):
    try:
        # yfinance 的 df 索引已經排除假日，所以 rolling(60) 就是「過去60個交易日」
        close = df['Close']
        volume = df['Volume']
        close = close.dropna()
        volume = volume.dropna()
        
        # 再次確認資料長度 (雖然抓1年通常夠，但還是防呆一下)
        if len(close) < 60: return [], "資料不足", 0, "N/A", 0, False
        
        curr_price = close.iloc[-1]
        prev_price = close.iloc[-2]
        curr_vol = volume.iloc[-1]
        prev_vol = volume.iloc[-2]
        
        # 計算均線 (Rolling Window = 交易日K棒數)
        s3 = close.rolling(3).mean()
        s5 = close.rolling(5).mean()
        s10 = close.rolling(10).mean()
        s20 = close.rolling(20).mean()
        s60 = close.rolling(60).mean() # 這裡算出來就是真正的季線
        
        v60 = s60.iloc[-1]
        p60 = s60.iloc[-2]
        v5, v3 = s5.iloc[-1], s3.iloc[-1]
        
        # 計算均線狀態
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
        
        # === 乖離率計算 (Bias Rate) ===
        # 公式：(現價 - 季線) / 季線 * 100
        bias_pct = ((curr_price - v60) / v60) * 100
        
        # 顯示邏輯：
        # 1. 正常顯示：都會顯示目前乖離率，讓您參考
        # 2. 警示標準：
        #    - 超過 20% (1.2倍)：顯示 🔸 偏高
        #    - 超過 30% (1.3倍)：顯示 🔴 過大 (您的原始標準)
        
        bias_info = f"乖離 {bias_pct:.1f}%" # 預設字串
        
        if bias_pct >= 30: # 原始嚴格標準
            status.append(f"🔴 乖離率過大 (+{bias_pct:.1f}%)")
            need_notify = True
        elif bias_pct >= 20: # 警戒區
            status.append(f"🔸 乖離率偏高 (+{bias_pct:.1f}%)")
            need_notify = True
            
        # === 策略訊號 ===
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
        return [f"計算錯"], "錯誤", 0, "N/A", 0, False

# --- 5. 抓取函數 ---
def fetch_one_by_one(ticker):
    try:
        # 抓取 1 年資料，保證交易日數量 > 60
        t = yf.Ticker(f"{ticker}.TW", session=SESSION)
        df = t.history(period="1y") 
        if not df.empty and len(df) > 60: return df, f"{ticker}.TW"
        
        t = yf.Ticker(f"{ticker}.TWO", session=SESSION)
        df = t.history(period="1y")
        if not df.empty and len(df) > 60: return df, f"{ticker}.TWO"
    except:
        pass
    return None, None

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 專家校正版")
use_mobile_view = st.toggle("📱 手機卡片模式", value=True)

with st.sidebar.form(key='stock_form'):
    st.header("設定")
    friend_email = st.text_input("Email (選填)", placeholder="輸入 Email 以接收通知")
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
    
    for i, t in enumerate(user_tickers):
        df, final_symbol = fetch_one_by_one(t)
        
        row_data = {
            "序號": i + 1,
            "代號": t,
            "名稱": STOCK_NAMES.get(t, t),
            "現價": 0,
            "均線": "N/A",
            "乖離": 0,
            "訊號": "❌ 無法讀取"
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
        time.sleep(0.5) 
        
    st.success("✅ 分析完成")
    
    df_res = pd.DataFrame(results)
    
    if use_mobile_view:
        for idx, row in df_res.iterrows():
            # 視覺化邏輯
            border = "1px solid #ddd" # 預設灰
            bg_color = "#ffffff"
            
            # 訊號顏色
            if "🔴" in row['訊號']: border = "2px solid #dc3545" # 紅框(危險)
            elif "🔸" in row['訊號']: border = "2px solid #ffc107" # 黃框(警告)
            elif "🚀" in row['訊號'] or "🔥" in row['訊號']: border = "2px solid #28a745" # 綠框(多方)
            
            # 乖離率文字顏色
            bias_color = "black"
            if row['乖離'] >= 20: bias_color = "#dc3545" # 紅字
            elif row['乖離'] <= -20: bias_color = "#28a745" # 綠字(負乖離過大)

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
