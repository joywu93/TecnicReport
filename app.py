import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import re
import random
import requests

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 終極穩定版", layout="wide")

# 偽裝瀏覽器標頭
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

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
    if len(df) < 60: return [], False, 0, 0, 0, 0

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

# --- 4. 穩定抓取 (不使用快取，避免狀態鎖死) ---
def fetch_data_stable(symbol):
    # 建立一個新的 Session
    session = requests.Session()
    session.headers.update(HEADERS)
    
    suffixes = [".TW", ".TWO"]
    
    for suffix in suffixes:
        full_symbol = f"{symbol}{suffix}"
        try:
            # 這裡不使用 download，改用 Ticker 物件，有時候比較不會被擋
            t = yf.Ticker(full_symbol, session=session)
            # 只抓最近 3 個月的資料，減少數據量，加快速度
            df = t.history(period="3mo")
            
            if not df.empty and len(df) > 50:
                return df, full_symbol
                
            time.sleep(0.2) # 稍微休息
        except:
            continue
            
    return None, None

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 終極穩定版")

if st.button("🧹 清除暫存 (若卡住請按我)"):
    st.cache_data.clear()
    st.rerun()

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
        # === 1. 雷射精準解析 (Regex) ===
        # 直接抓取所有「4個數字」的組合，忽略所有逗號、頓號、換行
        tickers = re.findall(r'[0-9]{4}', ticker_input)
        # 去除重複並保持順序
        tickers = list(dict.fromkeys(tickers))
        
        st.info(f"🔍 系統識別出 {len(tickers)} 檔股票代號： {', '.join(tickers)}")
        
        results = []
        notify_list = []
        
        # 建立一個進度顯示區 (Placeholder)
        status_table = st.empty()
        progress_bar = st.progress(0)
        
        # 初始化顯示表格 (讓您先看到有哪些股票在排隊)
        current_df = pd.DataFrame({
            "代號": tickers,
            "狀態": ["⏳ 等待中"] * len(tickers),
            "公司名稱": [STOCK_NAMES.get(t, "") for t in tickers]
        })
        status_table.dataframe(current_df, use_container_width=True, hide_index=True)
        
        # === 2. 逐一執行 (穩定模式) ===
        for i, t in enumerate(tickers):
            # 抓取資料
            df, final_symbol = fetch_data_stable(t)
            
            # 更新狀態
            if df is not None:
                try:
                    ch_name = STOCK_NAMES.get(t, final_symbol)
                    status_list, need_notify, price, up_cnt, down_cnt, v60 = check_strategy(df)
                    status_str = " | ".join(status_list)
                    
                    results.append({
                        "代號": t, # 顯示原始輸入代號，方便對照
                        "實際代號": final_symbol,
                        "公司名稱": ch_name,
                        "現價": price,
                        "均線狀態": f"⬆️{up_cnt} / ⬇️{down_cnt}",
                        "戰略訊號": status_str
                    })
                    
                    if need_notify:
                        notify_list.append(f"【{ch_name}】{price} | {status_str}\n")
                        
                    # 更新暫存表格的狀態 (視覺回饋)
                    current_df.loc[i, "狀態"] = "✅ 完成"
                    current_df.loc[i, "公司名稱"] = ch_name
                    
                except Exception as e:
                    results.append({"代號": t, "公司名稱": "計算錯", "現價": 0, "均線狀態": "❌", "戰略訊號": str(e)})
                    current_df.loc[i, "狀態"] = "❌ 錯誤"
            else:
                results.append({"代號": t, "公司名稱": "未知", "現價": 0, "均線狀態": "❌", "戰略訊號": "❌ 連線失敗 (Yahoo擋)"})
                current_df.loc[i, "狀態"] = "❌ 失敗"
            
            # 即時更新表格
            status_table.dataframe(current_df, use_container_width=True, hide_index=True)
            progress_bar.progress((i + 1) / len(tickers))
            
            # 隨機休息，避免封鎖
            time.sleep(random.uniform(0.1, 0.5))

        # === 3. 最終結果整理 ===
        st.success("✅ 全部掃描完成！詳細報告如下：")
        
        if results:
            final_df = pd.DataFrame(results)
            # 重新渲染最終表格
            status_table.dataframe(final_df, use_container_width=True, hide_index=True)
            
            if notify_list and MY_GMAIL:
                receiver_list = [MY_GMAIL, friend_email]
                chunks = [notify_list[i:i + 15] for i in range(0, len(notify_list), 15)]
                for i, chunk in enumerate(chunks):
                    send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"戰略訊號 ({i+1})", "".join(chunk))
                st.success(f"已發送 {len(notify_list)} 則通知信。")

except Exception as e:
    st.error(f"系統嚴重錯誤: {e}")
