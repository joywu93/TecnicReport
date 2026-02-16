import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import re
import random

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 慢速穩健版", layout="wide")

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
    try:
        # 簡單化處理
        close = df['Close']
        volume = df['Volume']
        
        # 移除 NaN
        close = close.dropna()
        volume = volume.dropna()
        
        if len(close) < 60: return [], "資料不足", 0
        
        curr_price = close.iloc[-1]
        prev_price = close.iloc[-2]
        curr_vol = volume.iloc[-1]
        prev_vol = volume.iloc[-2]
        
        s3 = close.rolling(3).mean()
        s5 = close.rolling(5).mean()
        s60 = close.rolling(60).mean() 
        
        v60 = s60.iloc[-1]
        p60 = s60.iloc[-2]
        v5, v3 = s5.iloc[-1], s3.iloc[-1]
        
        status = []
        need_notify = False
        
        # === 乖離率警示 ===
        if curr_price >= v60 * 1.3:
            status.append("⚠️ 乖離過大")
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
        
        if not status:
            status.append(f"{trend}盤整")

        return status, f"{trend}", curr_price, need_notify
    except Exception as e:
        return [f"計算錯: {e}"], "錯誤", 0, False

# --- 4. 慢速穩定抓取 ---
def fetch_one_by_one(ticker):
    # 先試 TW
    full_symbol = f"{ticker}.TW"
    try:
        t = yf.Ticker(full_symbol)
        df = t.history(period="3mo")
        
        if not df.empty:
            return df, full_symbol
            
        # 再試 TWO
        full_symbol = f"{ticker}.TWO"
        t = yf.Ticker(full_symbol)
        df = t.history(period="3mo")
        
        if not df.empty:
            return df, full_symbol
            
    except:
        pass
        
    return None, None

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 慢速穩健版")
st.caption("此模式會逐一掃描，速度較慢但保證不漏單。")

# 手機版切換
use_mobile_view = st.toggle("📱 手機卡片模式", value=True)

try:
    MY_GMAIL = st.secrets.get("GMAIL_USER", "")
    MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")
    MY_PRIVATE_LIST = st.secrets.get("MY_LIST", "2330")

    # 輸入表單
    with st.sidebar.form(key='stock_form'):
        st.header("設定")
        friend_email = st.text_input("Email (選填)", placeholder="輸入 Email 以接收通知")
        
        default_val = "2330"
        if friend_email == MY_GMAIL:
            default_val = MY_PRIVATE_LIST
            
        ticker_input = st.text_area("股票清單", value=default_val, height=250)
        submit_btn = st.form_submit_button(label='🚀 開始執行 (約需30秒)')

    if submit_btn:
        # 1. 解析輸入
        raw_tickers = re.findall(r'\d{4}', ticker_input)
        user_tickers = list(dict.fromkeys(raw_tickers)) # 去重
        
        total_stocks = len(user_tickers)
        st.info(f"📊 偵測到 {total_stocks} 檔股票，正在逐一連線...")
        
        results = []
        notify_list = []
        
        # 進度條
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 2. 逐一處理 (不分批，就是一支一支來，確保穩定)
        for i, t in enumerate(user_tickers):
            status_text.text(f"正在分析 ({i+1}/{total_stocks}): {t} ...")
            
            df, final_symbol = fetch_one_by_one(t)
            
            row_data = {
                "序號": i + 1,
                "代號": t,
                "名稱": STOCK_NAMES.get(t, t),
                "現價": 0,
                "狀態": "❌",
                "訊號": "❌ 無法讀取 (可能被擋)"
            }
            
            if df is not None:
                status_list, trend, price, need_notify = check_strategy(df)
                
                row_data["代號"] = final_symbol
                row_data["名稱"] = STOCK_NAMES.get(t, final_symbol)
                row_data["現價"] = round(price, 2)
                row_data["狀態"] = trend
                row_data["訊號"] = " | ".join(status_list)
                
                if need_notify:
                    notify_list.append(f"【{row_data['名稱']}】{price} | {row_data['訊號']}\n")
            
            results.append(row_data)
            
            # 更新進度
            progress_bar.progress((i + 1) / total_stocks)
            
            # 休息 0.5 秒，這是關鍵！避免被 Yahoo 封鎖 IP
            time.sleep(0.5)
            
        st.success("✅ 全部掃描完成！")
        
        # 3. 顯示結果
        df_res = pd.DataFrame(results)
        
        if use_mobile_view:
            for idx, row in df_res.iterrows():
                color = "grey"
                if "🚀" in row['訊號'] or "🔥" in row['訊號']: color = "green"
                elif "⚠️" in row['訊號'] or "📉" in row['訊號']: color = "red"
                
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.markdown(f"**{row['序號']}. {row['名稱']}**")
                    c2.markdown(f"**${row['現價']}**")
                    st.caption(f"趨勢: {row['狀態']}")
                    
                    if "❌" not in row['訊號']:
                        if color == "red": st.error(row['訊號'])
                        elif color == "green": st.success(row['訊號'])
                        else: st.info(row['訊號'])
                    else:
                        st.write(row['訊號'])
        else:
            st.dataframe(df_res, use_container_width=True, hide_index=True)

        # 發信
        if notify_list and MY_GMAIL and friend_email:
            receiver_list = [MY_GMAIL, friend_email]
            chunks = [notify_list[i:i + 20] for i in range(0, len(notify_list), 20)]
            for i, chunk in enumerate(chunks):
                send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"戰略訊號 ({i+1})", "".join(chunk))
                time.sleep(1)
            st.success(f"已發送 {len(notify_list)} 則通知信。")

except Exception as e:
    st.error(f"系統錯誤: {e}")
