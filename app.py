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
st.set_page_config(page_title="股市戰略 - 智能完全體", layout="wide")

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

# --- 核心邏輯：全方位戰略分析 ---
def analyze_strategy(df):
    # 準備數據
    close = df['Close']
    volume = df['Volume']
    
    # 至少需要 240 天 (年線)
    if len(close) < 240: return "資料不足 (上市未滿一年)", 0, 0, False

    # 取得最新與前一日數據
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    
    # 計算漲跌幅
    pct_change = (curr_price - prev_price) / prev_price
    
    # 計算均線 (SMA)
    sma3 = close.rolling(3).mean().iloc[-1]
    sma5 = close.rolling(5).mean()
    sma10 = close.rolling(10).mean()
    sma20 = close.rolling(20).mean()
    sma60 = close.rolling(60).mean()
    sma240 = close.rolling(240).mean()
    
    # 取值
    v5, v10, v20 = sma5.iloc[-1], sma10.iloc[-1], sma20.iloc[-1]
    v60 = sma60.iloc[-1]
    v240 = sma240.iloc[-1]
    
    # 前一日均線 (判斷趨勢向上/向下)
    p5, p10, p20 = sma5.iloc[-2], sma10.iloc[-2], sma20.iloc[-2]
    p60 = sma60.iloc[-2]

    messages = []
    is_alert = False # 是否為重要訊號 (Email用)

    # --- 1. 乖離率 (您的核心要求，優先顯示) ---
    bias_val = ((curr_price - v60) / v60) * 100
    bias_msg = ""
    if bias_val >= 30:
        bias_msg = f"🔥 乖離過大 (MA60: {v60:.1f})"
        is_alert = True
    elif bias_val >= 15:
        bias_msg = f"🔸 乖離偏高 (MA60: {v60:.1f})"
        is_alert = True

    # --- 2. 季線多空轉折 ---
    prev_60 = sma60.iloc[-2]
    if prev_price < prev_60 and curr_price > v60:
        messages.append("🚀 轉多訊號：站上季線")
        is_alert = True
    elif prev_price > prev_60 and curr_price < v60:
        messages.append("📉 轉空警示：跌破季線")
        is_alert = True

    # --- 3. 強勢反彈 (漲>4% 且 爆量1.5倍) ---
    # 條件：漲幅 >= 4% 且 量 > 昨日1.5倍 且 價 > 3MA
    if pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > sma3:
        messages.append("🔥 強勢反彈 (爆量長紅)")
        is_alert = True

    # --- 4. 底部轉折 (均線翻揚) ---
    # 條件：5/10/20/60 有 2條以上向上 且 股價在低檔 (<= 季線*1.1)
    up_count = 0
    if v5 > p5: up_count += 1
    if v10 > p10: up_count += 1
    if v20 > p20: up_count += 1
    if v60 > p60: up_count += 1
    
    if up_count >= 2 and curr_price <= v60 * 1.1:
        messages.append(f"✨ 底部轉折 ({up_count}條均線翻揚)")
        is_alert = True

    # --- 5. 量價異常 (出貨/背離) ---
    # 出貨：量 > 1.3倍 且 收黑
    if curr_vol > prev_vol * 1.3 and pct_change < 0:
        messages.append("⚠️ 出貨警訊 (爆量收黑)")
        is_alert = True
    # 背離：量 > 1.2倍 且 破5日線 且 收黑
    elif curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
        messages.append("⚠️ 量價背離 (量增價弱)")
        is_alert = True

    # --- 6. 年線保衛/空方弱勢 ---
    # 距離年線 < 5% 且 3條均線向下
    down_count = 0
    if v5 < p5: down_count += 1
    if v10 < p10: down_count += 1
    if v20 < p20: down_count += 1
    
    dist_240 = abs(curr_price - v240) / v240
    if dist_240 < 0.05 and down_count >= 3:
        messages.append("⚠️ 年線保衛戰 (均線偏弱)")
        is_alert = True
    elif curr_price < v240 and down_count >= 3:
        messages.append("❄️ 空方弱勢整理 (均線蓋頭)")
    
    # --- 7. 均線糾結 ---
    # 5/10/20 差距 < 2%
    max_ma = max(v5, v10, v20)
    min_ma = min(v5, v10, v20)
    if (max_ma - min_ma) / min_ma < 0.02:
        messages.append("🌀 均線糾結 (變盤在即)")
        is_alert = True

    # --- 8. 預設狀態 (如果上面都沒觸發) ---
    if not messages:
        if curr_price > v60:
            messages.append("🌊 多方行進 (觀察)")
        else:
            messages.append("☁️ 空方盤整 (觀望)")

    return " | ".join(messages), curr_price, bias_val, bias_msg, is_alert


# --- 批次下載函數 ---
@st.cache_data(ttl=600, show_spinner=False)
def fetch_all_data(user_tickers):
    download_list = []
    for t in user_tickers:
        download_list.append(f"{t}.TW")
        download_list.append(f"{t}.TWO")
    
    try:
        # 下載 2 年資料以計算年線
        data = yf.download(download_list, period="2y", group_by='ticker', threads=True, progress=False)
    except Exception:
        return []

    processed_results = []
    
    for t in user_tickers:
        df = pd.DataFrame()
        
        # 尋找資料 (TW 或 TWO)
        if f"{t}.TW" in data.columns.levels[0]:
            temp = data[f"{t}.TW"]
            if not temp['Close'].dropna().empty: df = temp
        
        if df.empty and f"{t}.TWO" in data.columns.levels[0]:
            temp = data[f"{t}.TWO"]
            if not temp['Close'].dropna().empty: df = temp
        
        if df.empty:
            processed_results.append({"code": t, "name": STOCK_NAMES.get(t, t), "error": "無資料"})
            continue

        # 執行戰略分析
        signal_str, price, bias, bias_str, is_urgent = analyze_strategy(df)
        
        processed_results.append({
            "code": t,
            "name": STOCK_NAMES.get(t, t),
            "price": float(price),
            "bias_val": float(bias),
            "bias_str": bias_str,
            "signal": signal_str,
            "is_urgent": is_urgent,
            "error": None
        })
        
    return processed_results

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 智能完全體")

# 側邊欄
with st.sidebar.form(key='stock_form'):
    st.header("設定")
    email_input = st.text_input("通知 Email (選填)", placeholder="輸入 Email 以接收警示")
    ticker_input = st.text_area("股票清單", value=DEFAULT_LIST, height=300)
    
    col1, col2 = st.columns(2)
    with col1:
        submit_btn = st.form_submit_button(label='🚀 智能分析')
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
    
    st.info(f"正在進行 6 大戰略分析，掃描 {len(user_tickers)} 檔股票...")
    
    stock_data = fetch_all_data(user_tickers)
    
    st.success(f"分析完成！")
    
    notify_list = []
    
    st.subheader(f"📊 分析結果 ({len(stock_data)} 檔)")
    
    # 雙欄排版
    cols = st.columns(2) if len(stock_data) > 1 else [st]
    
    for i, item in enumerate(stock_data):
        with cols[i % 2]:
            if item.get('error'):
                with st.container(border=True):
                    st.markdown(f"#### {item['name']} `{item['code']}`")
                    st.error(f"❌ {item['error']}")
                continue
                
            price = item['price']
            bias_val = item['bias_val']
            bias_str = item['bias_str']
            signal = item['signal']
            
            # 顯示卡片
            with st.container(border=True):
                c1, c2 = st.columns([2, 1])
                c1.markdown(f"#### {item['name']} `{item['code']}`")
                c2.markdown(f"#### ${price:.1f}")
                
                # 乖離率 (顏色判斷)
                if bias_val >= 15:
                    st.markdown(f"乖離率：:red[**{bias_val:.1f}%**]")
                else:
                    st.markdown(f"乖離率：:green[**{bias_val:.1f}%**]")
                
                st.divider()
                
                # 顯示戰略訊號 (綠色/灰色)
                if "多方" in signal or "轉多" in signal or "反彈" in signal or "翻揚" in signal:
                     st.markdown(f":green[{signal}]")
                elif "空方" in signal or "轉空" in signal or "出貨" in signal or "弱勢" in signal:
                     st.markdown(f":grey[{signal}]")
                else:
                     st.markdown(signal)

                # 疊加顯示乖離警示 (如果有)
                if bias_str:
                    if "過大" in bias_str:
                        st.error(bias_str)
                    else:
                        st.warning(bias_str)

            # 收集 Email (只有重要訊號或有乖離警示才寄)
            if item['is_urgent']:
                full_msg = f"{signal} | {bias_str}"
                notify_list.append(f"【{item['name']}】${price} | 乖離{bias_val:.1f}% | {full_msg}")

    # 發信
    if notify_list and email_input and MY_GMAIL:
        st.info(f"📧 偵測到 {len(notify_list)} 則重要訊號，正在發送 Email...")
        body = "\n\n".join(notify_list)
        if send_email_batch(MY_GMAIL, MY_PWD, [email_input], "股市戰略警示", body):
            st.success("✅ Email 發送成功！")
