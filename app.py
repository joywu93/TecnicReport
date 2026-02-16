import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import re
import os

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 極速團購版", layout="wide")

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

# --- 2. Email 發送函數 ---
def send_email_batch(sender, pwd, receivers, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"股市監控小幫手 <{sender}>"
        msg['To'] = ", ".join(receivers)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True
    except Exception as e:
        return False

# --- 3. 核心判讀邏輯 ---
def check_strategy(df):
    # 確保資料足夠
    if len(df) < 60:
        return [], False, 0, 0, 0, 0

    close = df['Close']
    volume = df['Volume']
    
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price if prev_price != 0 else 0
    
    price_4_days_ago = close.iloc[-5] 
    s3 = close.rolling(3).mean()
    s5 = close.rolling(5).mean()
    s10 = close.rolling(10).mean()
    s20 = close.rolling(20).mean()
    s60 = close.rolling(60).mean() 
    
    v60 = s60.iloc[-1]
    p60 = s60.iloc[-2]
    v5, v3 = s5.iloc[-1], s3.iloc[-1]

    trend_up = {5: v5 > s5.iloc[-2], 10: s10.iloc[-1] > s10.iloc[-2], 20: s20.iloc[-1] > s20.iloc[-2], 60: v60 > p60}
    up_count = sum(trend_up.values())
    down_count = 4 - up_count
    
    status = []
    need_notify = False
    
    # 策略
    if prev_price > p60 and curr_price < v60:
        status.append("📉 轉空警示：跌破季線")
        need_notify = True
    elif prev_price < p60 and curr_price > v60:
        status.append("🚀 轉多訊號：站上季線")
        need_notify = True
    if pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > v3:
        status.append("🔥 強勢反彈 (漲>4%, 爆量, 站上3SMA)")
        need_notify = True
    if up_count >= 2 and curr_price <= v60 * 1.1:
        status.append(f"✨ 底部轉折：{up_count}條均線翻揚")
        need_notify = True
    cond_sell_a = (curr_vol > prev_vol * 1.3 and pct_change < 0)
    cond_sell_b = (curr_price < price_4_days_ago)
    if cond_sell_a or cond_sell_b:
        reasons = []
        if cond_sell_a: reasons.append("爆量收黑")
        if cond_sell_b: reasons.append("跌破4日價")
        status.append(f"⚠️ 出貨警訊 ({'+'.join(reasons)})")
        need_notify = True
    if curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
        status.append("⚠️ 量價背離 (量增價弱，破5SMA)")
        need_notify = True
        
    dist_240 = abs(curr_price - s60.iloc[-1]) / s60.iloc[-1]
    if dist_240 < 0.05 and down_count >= 3:
        status.append("⚠️ 年線保衛戰：均線偏弱")
        need_notify = True 
    elif curr_price < v60 and down_count >= 3:
        status.append("❄️ 空方弱勢整理：均線蓋頭")
    
    if not status:
        if curr_price > v60: status.append("🌊 多方行進 (觀察)")
        else: status.append("☁️ 空方盤整 (觀望)")

    return status, need_notify, curr_price, up_count, down_count, v60

# --- 4. 團購式資料抓取 (Batch Download) ---
@st.cache_data(ttl=300) # 快取 5 分鐘
def fetch_batch_data(tickers):
    # 第一步：假設全部都是上市 (.TW)
    tw_tickers = [f"{t}.TW" for t in tickers]
    
    st.write("📥 正在進行大量下載 (上市)...")
    data_tw = yf.download(tw_tickers, period="1y", group_by='ticker', progress=False)
    
    # 第二步：檢查哪些失敗了 (沒有資料)
    failed_tickers = []
    valid_data = {}
    
    for t in tickers:
        full_symbol = f"{t}.TW"
        try:
            # 嘗試取得該股票資料
            if len(tickers) == 1:
                df = data_tw
            else:
                df = data_tw[full_symbol]
                
            # 檢查是否為空或全是 NaN
            if df.empty or df['Close'].isna().all():
                failed_tickers.append(t)
            else:
                valid_data[t] = (df, full_symbol)
        except KeyError:
            failed_tickers.append(t)
            
    # 第三步：失敗的改試上櫃 (.TWO)
    if failed_tickers:
        st.write(f"📥 正在重試 {len(failed_tickers)} 檔上櫃股票 (.TWO)...")
        two_tickers = [f"{t}.TWO" for t in failed_tickers]
        data_two = yf.download(two_tickers, period="1y", group_by='ticker', progress=False)
        
        for t in failed_tickers:
            full_symbol = f"{t}.TWO"
            try:
                if len(two_tickers) == 1:
                    df = data_two
                else:
                    df = data_two[full_symbol]
                
                if not df.empty and not df['Close'].isna().all():
                    valid_data[t] = (df, full_symbol)
                else:
                    valid_data[t] = (None, "失敗")
            except KeyError:
                valid_data[t] = (None, "失敗")
                
    return valid_data

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 極速團購版")

if st.button("🧹 清除暫存"):
    st.cache_data.clear()

try:
    MY_GMAIL = st.secrets.get("GMAIL_USER", "")
    MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")
    MY_PRIVATE_LIST = st.secrets.get("MY_LIST", "2330")

    st.sidebar.header("設定")
    friend_email = st.sidebar.text_input("Email", placeholder="輸入您的 Email")

    display_tickers = "2330"
    if friend_email.strip() == MY_GMAIL:
        display_tickers = MY_PRIVATE_LIST

    ticker_input = st.sidebar.text_area("股票清單", value=display_tickers, height=300)
    run_button = st.sidebar.button("立即執行判讀")

    if run_button:
        # 處理輸入
        raw_tickers = re.split(r'[,\s;，、]+', ticker_input)
        tickers = list(dict.fromkeys([t.strip() for t in raw_tickers if t.strip()]))
        
        st.write(f"🔍 開始處理 {len(tickers)} 檔股票...")
        
        # === 呼叫團購下載 ===
        stock_data_map = fetch_batch_data(tickers)
        
        results = []
        notify_list = []
        
        # 依照使用者輸入的順序建立報告 (確保不漏掉)
        for t in tickers:
            data_tuple = stock_data_map.get(t)
            
            if data_tuple and data_tuple[0] is not None:
                df = data_tuple[0]
                final_symbol = data_tuple[1]
                
                try:
                    ch_name = STOCK_NAMES.get(t, final_symbol)
                    status_list, need_notify, price, up_cnt, down_cnt, v60 = check_strategy(df)
                    status_str = " | ".join(status_list)
                    
                    report = f"【{ch_name}】{price} | {status_str}\n"
                    
                    results.append({
                        "代號": final_symbol,
                        "公司名稱": ch_name,
                        "現價": price,
                        "均線狀態": f"⬆️{up_cnt} / ⬇️{down_cnt}",
                        "戰略訊號": status_str
                    })
                    
                    if need_notify:
                        notify_list.append(report)
                except Exception as e:
                     results.append({
                        "代號": t,
                        "公司名稱": "計算錯誤",
                        "現價": 0,
                        "均線狀態": "❌",
                        "戰略訊號": str(e)
                    })
            else:
                # 即使沒抓到，也要顯示！
                results.append({
                    "代號": t,
                    "公司名稱": STOCK_NAMES.get(t, "未知"),
                    "現價": 0,
                    "均線狀態": "❌",
                    "戰略訊號": "❌ 查無資料 (可能下市或輸入錯誤)"
                })
        
        st.success("✅ 分析完成！")
        
        if results:
            df_res = pd.DataFrame(results)
            st.dataframe(df_res, use_container_width=True)
            
            if notify_list and MY_GMAIL:
                receiver_list = [MY_GMAIL, friend_email]
                chunks = [notify_list[i:i + 10] for i in range(0, len(notify_list), 10)] # 一封信塞多一點
                for i, chunk in enumerate(chunks):
                    send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"戰略訊號 ({i
