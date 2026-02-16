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
# 🔧 系統設定與偽裝
# ==========================================
st.set_page_config(page_title="股市戰略 - 救援模式", layout="wide")

# 偽裝成瀏覽器的 Header (這是破解封鎖的關鍵)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 建立專屬連線 Session
session = requests.Session()
session.headers.update(HEADERS)

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
    close = df['Close']
    volume = df['Volume']
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price
    
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
    
    # 策略條件
    if prev_price > p60 and curr_price < v60:
        status.append("📉 轉空警示：跌破季線(60SMA)")
        need_notify = True
    elif prev_price < p60 and curr_price > v60:
        status.append("🚀 轉多訊號：站上季線(60SMA)")
        need_notify = True
    if pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > v3:
        status.append("🔥 強勢反彈 (漲>4%, 爆量1.5倍, 站上3SMA)")
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
        
    dist_240 = abs(curr_price - s60.iloc[-1]) / s60.iloc[-1] # 簡化用季線代替年線做防呆
    if dist_240 < 0.05 and down_count >= 3:
        status.append("⚠️ 年線保衛戰：均線偏弱")
        need_notify = True 
    elif curr_price < v60 and down_count >= 3:
        status.append("❄️ 空方弱勢整理：均線蓋頭")
    
    avg_price = (s5.iloc[-1] + s10.iloc[-1] + s20.iloc[-1]) / 3
    if abs(s5.iloc[-1]-avg_price)/avg_price < 0.02 and abs(s20.iloc[-1]-avg_price)/avg_price < 0.02:
        status.append("🌀 均線糾結：變盤在即")
        
    if not status:
        if curr_price > v60: status.append("🌊 多方行進 (觀察)")
        else: status.append("☁️ 空方盤整 (觀望)")

    return status, need_notify, curr_price, up_count, down_count, v60

# --- 4. 資料抓取 (使用快取 + 偽裝) ---
@st.cache_data(ttl=600, show_spinner=False)
def fetch_data_safe(symbol):
    try:
        # 嘗試 .TW
        t = yf.Ticker(f"{symbol}.TW", session=session)
        df = t.history(period="1y")
        if not df.empty: return df, f"{symbol}.TW"
        
        # 嘗試 .TWO
        t = yf.Ticker(f"{symbol}.TWO", session=session)
        df = t.history(period="1y")
        if not df.empty: return df, f"{symbol}.TWO"
        
        return None, None
    except Exception as e:
        return None, str(e)

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 救援診斷版")

# 1. 救命按鈕：清除快取
if st.button("🧹 清除快取 (如果跑不出資料請按我)"):
    st.cache_data.clear()
    st.success("快取已清除！請重新點擊「立即執行判讀」。")

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
        
        st.write(f"🔍 準備分析 {len(tickers)} 檔股票...")
        
        results = []
        notify_list = []
        progress_bar = st.progress(0)
        status_box = st.empty()
        
        # 診斷計數器
        success_count = 0
        fail_count = 0
        
        for i, t in enumerate(tickers):
            status_box.text(f"正在連線: {t} ...")
            
            # 呼叫抓取
            df, final_symbol = fetch_data_safe(t)
            
            if df is not None and not df.empty and len(df) > 60:
                success_count += 1
                try:
                    ch_name = STOCK_NAMES.get(t, final_symbol)
                    status_list, need_notify, price, up_cnt, down_cnt, v60 = check_strategy(df)
                    status_str = " | ".join(status_list)
                    
                    report = f"【{ch_name}】{price} | {status_str}\n"
                    
                    results.append({
                        "代號": final_symbol,
                        "名稱": ch_name,
                        "現價": price,
                        "訊號": status_str,
                        "需通知": "✅" if need_notify else ""
                    })
                    
                    if need_notify:
                        notify_list.append(report)
                except Exception as e:
                    st.error(f"分析 {t} 時發生錯誤: {e}")
            else:
                fail_count += 1
                # 這裡不顯示錯誤，以免畫面太亂，只在最後統計
            
            progress_bar.progress((i + 1) / len(tickers))
            time.sleep(0.5) # 故意放慢速度，避免被鎖

        status_box.text("分析完成！")
        
        # 顯示統計結果
        st.info(f"📊 統計：成功 {success_count} 檔 / 失敗 {fail_count} 檔")
        
        if fail_count > 0 and success_count == 0:
            st.error("⚠️ 所有股票都無法讀取。可能原因：IP 仍被封鎖。請等待 1-2 小時後再試，或按上方的「清除快取」。")
        
        if results:
            st.dataframe(pd.DataFrame(results))
            
            if notify_list and MY_GMAIL:
                receiver_list = [MY_GMAIL, friend_email]
                chunks = [notify_list[i:i + 5] for i in range(0, len(notify_list), 5)]
                for i, chunk in enumerate(chunks):
                    send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"戰略訊號 ({i+1})", "".join(chunk))
                st.success(f"已發送 {len(notify_list)} 則通知信。")

except Exception as e:
    st.error(f"系統錯誤: {e}")
