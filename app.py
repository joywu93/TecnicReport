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
st.set_page_config(page_title="股市戰略 - 實戰排序版", layout="wide")

# 112 檔全新對照表
STOCK_NAMES = {
    "1464": "得力", "1517": "利奇", "1522": "堤維西", "1597": "直得", "1616": "億泰",
    "2228": "劍麟", "2313": "華通", "2317": "鴻海", "2327": "國巨", "2330": "台積電",
    "2344": "華邦電", "2368": "金像電", "2376": "技嘉", "2377": "微星", "2379": "瑞昱",
    "2382": "廣達", "2383": "台光電", "2397": "友通", "2404": "漢唐", "2408": "南亞科",
    "2439": "美律", "2441": "超豐", "2449": "京元電子", "2454": "聯發科", "2493": "揚博",
    "2615": "萬海", "3005": "神基", "3014": "聯陽", "3017": "奇鋐", "3023": "信邦",
    "3030": "德律", "3037": "欣興", "3042": "晶技", "3078": "僑威", "3163": "波若威",
    "3167": "大量", "3217": "優群", "3219": "倚強科", "3227": "原相", "3231": "緯創",
    "3264": "欣銓", "3265": "台星科", "3303": "岱稜", "3357": "臺慶科", "3402": "漢科",
    "3406": "玉晶光", "3416": "融程電", "3441": "聯一光", "3450": "聯鈞", "3455": "由田",
    "3479": "安勤", "3483": "力致", "3484": "崧騰", "3515": "華擎", "3526": "凡甲",
    "3548": "兆利", "3570": "大塚", "3596": "智易", "3679": "新至陞", "3711": "日月光投控",
    "3712": "永崴投控", "4554": "橙的", "4760": "勤凱", "4763": "材料*-KY", "4766": "南寶",
    "4915": "致伸", "4953": "緯軟", "4961": "天鈺", "4979": "華星光", "5225": "東科-KY",
    "5236": "凌陽創新", "5284": "jpp-KY", "5388": "中磊", "5439": "高技", "5871": "中租-KY",
    "6104": "創惟", "6121": "新普", "6139": "亞翔", "6143": "振曜", "6158": "禾昌",
    "6176": "瑞儀", "6187": "萬潤", "6197": "佳必琪", "6203": "海韻電", "6221": "晉泰",
    "6227": "茂崙", "6257": "矽格", "6261": "久元", "6274": "台燿", "6278": "台表科",
    "6285": "啟碁", "6290": "良維", "6538": "倉和", "6579": "研揚", "6605": "帝寶",
    "6613": "朋億*", "6629": "泰金-KY", "6651": "全宇昕", "6667": "信紘科", "6768": "志強-KY",
    "6788": "華景電", "6894": "衛司特", "6951": "靑新-創", "6967": "汎瑋材料", "6996": "力領科技",
    "8081": "致新", "8358": "金居", "8432": "東生華", "8473": "山林水", "8938": "明安",
    "9914": "美利達", "9939": "宏全"
}

# 預設清單
DEFAULT_LIST = "1464, 1517, 1522, 1597, 1616, 2228, 2313, 2317, 2327, 2330, 2344, 2368, 2376, 2377, 2379, 2382, 2383, 2397, 2404, 2408, 2439, 2441, 2449, 2454, 2493, 2615, 3005, 3014, 3017, 3023, 3030, 3037, 3042, 3078, 3163, 3167, 3217, 3219, 3227, 3231, 3264, 3265, 3303, 3357, 3402, 3406, 3416, 3441, 3450, 3455, 3479, 3483, 3484, 3515, 3526, 3548, 3570, 3596, 3679, 3711, 3712, 4554, 4760, 4763, 4766, 4915, 4953, 4961, 4979, 5225, 5236, 5284, 5388, 5439, 5871, 6104, 6121, 6139, 6143, 6158, 6176, 6187, 6197, 6203, 6221, 6227, 6257, 6261, 6274, 6278, 6285, 6290, 6538, 6579, 6605, 6613, 6629, 6651, 6667, 6768, 6788, 6894, 6951, 6967, 6996, 8081, 8358, 8432, 8473, 8938, 9914, 9939"

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

# --- 核心邏輯：戰略分析 ---
def analyze_strategy(df):
    close = df['Close']
    volume = df['Volume']
    if len(close) < 240: return "資料不足", 0, 0, "", False, ""
    
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price
    
    sma3 = close.rolling(3).mean().iloc[-1]
    sma5 = close.rolling(5).mean()
    sma10 = close.rolling(10).mean()
    sma20 = close.rolling(20).mean()
    sma60 = close.rolling(60).mean()
    sma240 = close.rolling(240).mean()
    
    v5, v10, v20, v60, v240 = sma5.iloc[-1], sma10.iloc[-1], sma20.iloc[-1], sma60.iloc[-1], sma240.iloc[-1]
    p5, p10, p20, p60 = sma5.iloc[-2], sma10.iloc[-2], sma20.iloc[-2], sma60.iloc[-2]

    # === 年線高低點判讀 ===
    high_240 = close.rolling(240).max().iloc[-1]
    low_240 = close.rolling(240).min().iloc[-1]
    
    position_msg = ""
    if high_240 > low_240:
        pos_rank = (curr_price - low_240) / (high_240 - low_240)
        if pos_rank >= 0.95:
            position_msg = f"⚠️ 位階：年線高點區 (M頭風險) | 高: {high_240:.2f}"
        elif pos_rank <= 0.05:
            position_msg = f"✨ 位階：年線低點區 (W底機會) | 低: {low_240:.2f}"

    messages = []
    is_alert = False

    # --- 1. 乖離率 ---
    bias_val = ((curr_price - v60) / v60) * 100
    bias_msg = ""
    if bias_val >= 30:
        bias_msg = f"🔥 乖離過大 (60SMA: {v60:.2f})"
        is_alert = True 
    elif bias_val >= 15:
        bias_msg = f"🔸 乖離偏高 (60SMA: {v60:.2f}) | ✨ 短線提防跌破 5SMA({v5:.2f}) / 10SMA({v10:.2f})"

    # === 戰略重構：爆量表態絕對優先 ===
    p_max_ma = max(p5, p10, p20)
    p_min_ma = min(p5, p10, p20)
    is_entangled_yesterday = (p_max_ma - p_min_ma) / p_min_ma < 0.02
    
    c_max_ma = max(v5, v10, v20)
    c_min_ma = min(v5, v10, v20)
    is_entangled_today = (c_max_ma - c_min_ma) / c_min_ma < 0.02

    # 優先權 1：大漲爆量型態 (無論是否糾結，一律置頂判斷)
    if is_entangled_yesterday and curr_vol > prev_vol * 1.5 and pct_change >= 0.05 and curr_price > v5:
        msg = f"🌀 均線糾結突破 (提防假突破，未來3日不跌破 {prev_price:.2f})"
        if curr_price < v60: msg += " | ⚠️ 上有60SMA壓力"
        messages.append(msg)
        is_alert = True
        
    elif pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > sma3:
        msg = "🔥 強勢反彈 (漲>4%且爆量)"
        if curr_price < v60: msg += " | ⚠️ 上有60SMA壓力"
        messages.append(msg)
        is_alert = True
        
    # 優先權 2：向下破線型態
    elif is_entangled_yesterday and curr_vol > prev_vol * 1.2 and pct_change <= -0.05 and curr_price < v5:
        messages.append(f"🌀 均線糾結跌破 (提防假跌破，未來3日反彈看 {prev_price:.2f})")
        is_alert = True
        
    # 優先權 3：糾結狀態 (即將變盤)
    elif is_entangled_today:
        messages.append("🌀 均線糾結：變盤在即 (請密切關注量能)")
        is_alert = True
        
    # ====== 其他客製化戰略邏輯 (若未觸發大漲大跌) ======
    else:
        # C項：多方偏弱 / 年線保衛 (不寄信)
        is_weak_bull = False
        if curr_price < v60 and curr_price > v240:
            messages.append(f"☁️ 多方偏弱 (提防跌破年線轉空，240SMA({v240:.2f}))")
            is_weak_bull = True

        # B項：多方回檔防守 (不寄信)
        short_term_down_count = sum([v5 < p5, v10 < p10, v20 < p20])
        dist_60 = (curr_price - v60) / v60

        if not is_weak_bull and curr_price > v60 and short_term_down_count >= 2 and 0 < dist_60 <= 0.05:
            messages.append("🌊 多方行進(觀察) + ⚠️ 慎防跌破 60SMA")

        # D項：多方整理轉折-向上 (要寄信)
        elif curr_price > v60 and v5 > p5 and v5 > v10:
            messages.append(f"✨ 多方整理轉折 (5SMA({v5:.2f})向上 > 10SMA({v10:.2f}))")
            is_alert = True

        # E項：多方整理轉折-向下 (要寄信)
        elif curr_price > v60 and v5 < p5 and curr_price < v5 and v5 < v10:
            messages.append(f"✨ 多方整理轉折 (5SMA({v5:.2f})向下 < 10SMA({v10:.2f}))")
            is_alert = True

        # 4. 其他強勢防守
        elif curr_price > v60 and curr_price > v5 and curr_price > v10 and curr_price > v20 and v5 > p5 and v10 > p10 and v20 > p20:
            messages.append(f"🌊 多方行進 + ✨ 短線提防跌破 5SMA({v5:.2f}) / 10SMA({v10:.2f})")
            is_alert = True

        # ====== 通用邏輯 ======
        if not messages:
            if prev_price < p60 and curr_price > v60:
                messages.append("🚀 轉多訊號：站上季線(60SMA)")
                is_alert = True
            elif prev_price > p60 and curr_price < v60:
                messages.append("📉 轉空警示：跌破季線(60SMA)")
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
            processed_results.append({"code": t, "name": STOCK_NAMES.get(t, t), "error": "無資料或未上市", "is_urgent": False})
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
st.title("📈 股市戰略 - 實戰排序版")

with st.sidebar.form(key='stock_form'):
    st.header("設定")
    email_input = st.text_input("通知 Email (必填)", placeholder="輸入 Email 以接收警示")
    ticker_input = st.text_area("股票清單", value=DEFAULT_LIST, height=300)
    
    submit_btn = st.form_submit_button(label='🚀 智能分析')

MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

if not MY_GMAIL or not MY_PWD:
    st.sidebar.error("⚠️ 未設定 Secrets，無法寄信！")

if submit_btn:
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    user_tickers = list(dict.fromkeys(raw_tickers))
    
    st.info(f"正在掃描 {len(user_tickers)} 檔股票...")
    stock_data = fetch_all_data(user_tickers)
    
    # ====== 置頂排序邏輯 ======
    # 排序規則：(0) 發信警示股 -> (1) 正常股 -> (2) 錯誤/無資料
    def sort_priority(item):
        if item.get('error'): return 2
        if item.get('is_urgent'): return 0
        return 1
        
    stock_data.sort(key=sort_priority)
    
    st.success(f"分析完成！(警示個股已為您置頂)")
    
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
                c2.markdown(f"#### ${price:.2f}") # 小數點 2 位
                
                if bias_val >= 15: st.markdown(f"乖離率：:red[**{bias_val:.1f}%**]")
                else: st.markdown(f"乖離率：:green[**{bias_val:.1f}%**]")
                
                st.divider()
                
                if "突破" in signal or "轉折" in signal or "反彈" in signal or "強勢" in signal: st.markdown(f":green[{signal}]")
                elif "跌破" in signal or "偏弱" in signal or "轉空" in signal: st.markdown(f":red[{signal}]")
                elif "糾結" in signal: st.markdown(f":blue[{signal}]")
                else: st.markdown(f":grey[{signal}]")

                if bias_str:
                    if "過大" in bias_str: st.error(bias_str)
                    else: st.warning(bias_str)
                
                if pos_msg:
                    st.info(pos_msg)

            if item['is_urgent']:
                full_msg = f"{signal} | {bias_str} | {pos_msg}".strip(" | ")
                notify_list.append(f"【{item['name']}】${price:.2f} | {full_msg}") # 小數點 2 位

    if notify_list and email_input and MY_GMAIL:
        st.info(f"📧 偵測到 {len(notify_list)} 則重要訊號，正在發送 Email...")
        body = "\n\n".join(notify_list)
        if send_email_batch(MY_GMAIL, MY_PWD, [email_input], "股市戰略通知", body):
            st.success("✅ Email 發送成功！")
        else:
            st.error("❌ Email 發送失敗")

