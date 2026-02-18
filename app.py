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
st.set_page_config(page_title="股市戰略 - 專業術語版", layout="wide")

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

# --- Email 發送與診斷函數 ---
def test_email_connection(sender, pwd, receiver):
    try:
        msg = MIMEText("這是一封測試信，代表您的 Streamlit 機器人發信功能正常！")
        msg['Subject'] = "✅ 股市戰略 - 連線測試成功"
        msg['From'] = f"股市小幫手 <{sender}>"
        msg['To'] = receiver
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, pwd)
            server.send_message(msg)
        return True, "發送成功！"
    except Exception as e:
        return False, str(e)

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

# --- 核心邏輯：戰略分析 (SMA正名版) ---
def analyze_strategy(df):
    close = df['Close']
    volume = df['Volume']
    # 至少需要 240 天
    if len(close) < 240: return "資料不足", 0, 0, "", False, ""
    
    # 取得最新與前一日數據
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price
    
    # 計算均線 (SMA)
    sma3 = close.rolling(3).mean().iloc[-1]
    sma5 = close.rolling(5).mean()
    sma10 = close.rolling(10).mean()
    sma20 = close.rolling(20).mean()
    sma60 = close.rolling(60).mean()
    sma240 = close.rolling(240).mean()
    
    # 取值 (v=今日, p=昨日)
    v5, v10, v20, v60, v240 = sma5.iloc[-1], sma10.iloc[-1], sma20.iloc[-1], sma60.iloc[-1], sma240.iloc[-1]
    p5, p10, p20, p60 = sma5.iloc[-2], sma10.iloc[-2], sma20.iloc[-2], sma60.iloc[-2]

    # === 年線高低點判讀 ===
    high_240 = close.rolling(240).max().iloc[-1]
    low_240 = close.rolling(240).min().iloc[-1]
    
    position_msg = ""
    if high_240 > low_240:
        pos_rank = (curr_price - low_240) / (high_240 - low_240)
        if pos_rank >= 0.95:
            position_msg = f"⚠️ 位階：年線高點區 (M頭風險) | 高: {high_240:.1f}"
        elif pos_rank <= 0.05:
            position_msg = f"✨ 位階：年線低點區 (W底機會) | 低: {low_240:.1f}"

    messages = []
    is_alert = False

    # --- 1. 乖離率 (修正為 60SMA) ---
    bias_val = ((curr_price - v60) / v60) * 100
    bias_msg = ""
    if bias_val >= 30:
        bias_msg = f"🔥 乖離過大 (60SMA: {v60:.1f})"
        is_alert = True 
    elif bias_val >= 15:
        # A項：修正提示詞為 60SMA, 5SMA, 10SMA
        bias_msg = f"🔸 乖離偏高 (60SMA: {v60:.1f}) | ✨ 短線提防跌破 5SMA({v5:.1f}) / 10SMA({v10:.1f})"
        # 不寄信

    # ====== 客製化戰略邏輯 (SMA正名) ======

    # C項：多方偏弱 / 年線保衛 (不寄信)
    is_weak_bull = False
    if curr_price < v60 and curr_price > v240:
        messages.append(f"☁️ 多方偏弱 (提防跌破年線轉空，240SMA({v240:.1f}))")
        is_weak_bull = True

    # B項：多方回檔防守 (不寄信)
    short_term_down_count = 0
    if v5 < p5: short_term_down_count += 1
    if v10 < p10: short_term_down_count += 1
    if v20 < p20: short_term_down_count += 1
    dist_60 = (curr_price - v60) / v60

    if not is_weak_bull and curr_price > v60 and short_term_down_count >= 2 and 0 < dist_60 <= 0.05:
        messages.append("🌊 多方行進(觀察) + ⚠️ 慎防跌破 60SMA")

    # D項：多方整理轉折-向上 (要寄信)
    # 修正提示詞：5MA -> 5SMA, 10MA -> 10SMA
    elif curr_price > v60 and v5 > p5 and v5 > v10:
        messages.append(f"✨ 多方整理轉折 (5SMA({v5:.1f})向上 > 10SMA({v10:.1f}))")
        is_alert = True

    # E項：多方整理轉折-向下 (要寄信)
    # 修正提示詞：5MA -> 5SMA, 10MA -> 10SMA
    elif curr_price > v60 and v5 < p5 and curr_price < v5 and v5 < v10:
        messages.append(f"✨ 多方整理轉折 (5SMA({v5:.1f})向下 < 10SMA({v10:.1f}))")
        is_alert = True

    # 4. 其他強勢防守 (SMA正名)
    elif curr_price > v60 and curr_price > v5 and curr_price > v10 and curr_price > v20 and v5 > p5 and v10 > p10 and v20 > p20:
        messages.append(f"🌊 多方行進 + ✨ 短線提防跌破 5SMA({v5:.1f}) / 10SMA({v10:.1f})")
        is_alert = True

    # ====== 通用邏輯 ======
    if not messages:
        if prev_price < p60 and curr_price > v60:
            messages.append("🚀 轉多訊號：站上季線(60SMA)")
            is_alert = True
        elif prev_price > p60 and curr_price < v60:
            messages.append("📉 轉空警示：跌破季線(60SMA)")
            is_alert = True
        elif pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > sma3:
            messages.append("🔥 強勢反彈 (漲>4%且爆量)")
            is_alert = True
        else:
            if curr_price > v60: messages.append("🌊 多方行進 (觀察)")
            else: messages.append("☁️ 空方盤整 (觀望)")

    return " | ".join(messages), curr_price, bias_val, bias_msg, is_alert, position_msg

# --- 下載函數 ---
@st.cache_data(ttl=600, show_spinner=False)
def fetch_all_data(user_tickers):
    download_list = []
    for t in user_tickers:
        download_list.append(f"{t}.TW")
        download_list.append(f"{t}.TWO")
    try:
        data = yf.download(download_list, period="2y", group_by='ticker', threads=True, progress=False)
    except: return []

    processed_results = []
    for t in user_tickers:
        df = pd.DataFrame()
        if f"{t}.TW" in data.columns.levels[0]:
            temp = data[f"{t}.TW"]
            if not temp['Close'].dropna().empty: df = temp
        if df.empty and f"{t}.TWO" in data.columns.levels[0]:
            temp = data[f"{t}.TWO"]
            if not temp['Close'].dropna().empty: df = temp
        
        if df.empty:
            processed_results.append({"code": t, "name": STOCK_NAMES.get(t, t), "error": "無資料"})
            continue
        
        signal_str, price, bias, bias_str, is_urgent, pos_msg = analyze_strategy(df)
        processed_results.append({
            "code": t, "name": STOCK_NAMES.get(t, t), "price": float(price),
            "bias_val": float(bias), "bias_str": bias_str, "signal": signal_str,
            "is_urgent": is_urgent, "pos_msg": pos_msg, "error": None
        })
    return processed_results

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 專業術語版")

with st.sidebar.form(key='stock_form'):
    st.header("設定")
    email_input = st.text_input("通知 Email (必填)", placeholder="輸入 Email 以接收警示")
    ticker_input = st.text_area("股票清單", value=DEFAULT_LIST, height=300)
    
    col1, col2 = st.columns(2)
    with col1:
        submit_btn = st.form_submit_button(label='🚀 智能分析')
    with col2:
        test_email_btn = st.form_submit_button(label='📧 寄送測試信')

# 讀取 Secrets
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

if not MY_GMAIL or not MY_PWD:
    st.sidebar.error("⚠️ 未設定 Secrets，無法寄信！")

# 測試信按鈕
if test_email_btn:
    if not email_input: st.toast("❌ 請填寫 Email", icon="⚠️")
    elif not MY_GMAIL or not MY_PWD: st.toast("❌ Secrets 未設定", icon="🚫")
    else:
        with st.spinner("連線中..."):
            success, msg = test_email_connection(MY_GMAIL, MY_PWD, email_input)
            if success: st.success("✅ 測試成功，信件已發送！")
            else: st.error(f"❌ 發送失敗：{msg}")

# 主程式
if submit_btn:
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    user_tickers = list(dict.fromkeys(raw_tickers))
    
    st.info(f"正在掃描 {len(user_tickers)} 檔股票 (含年線位階)...")
    stock_data = fetch_all_data(user_tickers)
    st.success(f"分析完成！")
    
    notify_list = []
    
    st.subheader(f"📊 分析結果 ({len(stock_data)} 檔)")
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
            pos_msg = item['pos_msg']
            
            with st.container(border=True):
                c1, c2 = st.columns([2, 1])
                c1.markdown(f"#### {item['name']} `{item['code']}`")
                c2.markdown(f"#### ${price:.1f}")
                
                # 乖離率顏色
                if bias_val >= 15: st.markdown(f"乖離率：:red[**{bias_val:.1f}%**]")
                else: st.markdown(f"乖離率：:green[**{bias_val:.1f}%**]")
                
                st.divider()
                
                # 訊號顏色
                if "轉折" in signal or "反彈" in signal or "強勢" in signal: st.markdown(f":green[{signal}]")
                elif "偏弱" in signal or "轉空" in signal or "跌破" in signal: st.markdown(f":grey[{signal}]")
                else: st.markdown(signal)

                # 乖離警示
                if bias_str:
                    if "過大" in bias_str: st.error(bias_str)
                    else: st.warning(bias_str)
                
                # 年線位階提示
                if pos_msg:
                    st.info(pos_msg)

            # Email 清單收集
            if item['is_urgent']:
                full_msg = f"{signal} | {bias_str} | {pos_msg}"
                notify_list.append(f"【{item['name']}】${price} | {full_msg}")

    # 發信
    if notify_list and email_input and MY_GMAIL:
        st.info(f"📧 偵測到 {len(notify_list)} 則重要訊號，正在發送 Email...")
        body = "\n\n".join(notify_list)
        if send_email_batch(MY_GMAIL, MY_PWD, [email_input], "股市戰略通知", body):
            st.success("✅ Email 發送成功！")
        else:
            st.error("❌ Email 發送失敗")
