import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time

# --- 1. 中文名稱對照表 ---
STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "6203": "海韻電", 
    "3570": "大塚", "4766": "南寶", "NVDA": "輝達",
    "2313": "華通", "2454": "聯發科", "2303": "聯電",
    "2603": "長榮", "2609": "陽明", "2615": "萬海",
    "2323": "中環", "2451": "創見", "6229": "研通",
    "4763": "材料-KY", "1522": "堤維西", "2404": "漢唐",
    "6788": "華景電", "2344": "華邦電", "1519": "華城",
    "1513": "中興電", "3231": "緯創", "3035": "智原",
    "2408": "南亞科", "3406": "玉晶光"
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
        print(f"Error sending email: {e}")
        return False

st.set_page_config(page_title="量價位階戰略系統", layout="wide")
st.title("📈 股市量價位階 & 戰略判讀系統")

# 後台 Secrets 讀取
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

st.sidebar.header("👤 使用者設定")
friend_email = st.sidebar.text_input("接收通知信箱", placeholder="請輸入您的 Email")
ticker_input = st.sidebar.text_area("自選股清單 (輸入完請按 Enter)", "2330, 2317, 2451, 2344, 6203")
run_button = st.sidebar.button("立即執行判讀")

# --- 3. 核心判讀邏輯 ---
def check_strategy(df, symbol):
    # 提取數據 (需確保至少有 60 筆數據)
    close = df['Close']
    volume = df['Volume']
    
    # 取得當日與前一日數據
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    
    # 計算漲跌幅
    pct_change = (curr_price - prev_price) / prev_price
    
    # 均線計算
    sma5 = close.rolling(5).mean().iloc[-1]
    sma60 = close.rolling(60).mean().iloc[-1]
    sma240 = close.rolling(240).mean().iloc[-1]
    
    # === 位階定義 (Requirement 3) ===
    # 計算近 60 日最高與最低 (含今日)
    high_60 = close.rolling(60).max().iloc[-1]
    low_60 = close.rolling(60).min().iloc[-1]
    
    # 計算近 3 日最高與最低 (不含今日，用於比較突破)
    # 取 -4 到 -1，代表昨天、前天、大前天
    high_3days = close.iloc[-4:-1].max()
    low_3days = close.iloc[-4:-1].min()

    status = []
    need_notify = False
    
    # --- 1. 判斷位階 (高檔/低檔/波段) ---
    position_msg = ""
    # 若今日收盤創近 60 日新高 (或極其接近，例如 > 99%)
    if curr_price >= high_60 * 0.995:
        position_msg = "🏰 高檔整理 (創60日新高)"
    # 若今日收盤創近 60 日新低
    elif curr_price <= low_60 * 1.005:
        position_msg = "💧 低檔整理 (創60日新低)"
    else:
        # 未創新高低，判斷波段趨勢 (以年線 240SMA 為多空分界)
        if curr_price > sma240:
            position_msg = "🌊 波段中長多 (整理中)"
        else:
            position_msg = "❄️ 波段中長空 (整理中)"
    
    status.append(position_msg)

    # --- 2. 量價配合 (Requirement 4) ---
    # 單日量 > 前日1.5倍 且 漲幅 > 4%
    if curr_vol > prev_vol * 1.5 and pct_change >= 0.04:
        msg = "🚀 短期底部訊號 (爆量長紅)"
        # 備註：程式無法預知未來3日，故改為「提示後續觀察」
        note = "⚠️ 關鍵：未來3日需守住今日低點不破底"
        status.append(msg)
        status.append(note)
        need_notify = True

    # --- 3. 量價背離 (Requirement 5) ---
    # 單日量 > 前日1.2倍 (但漲幅不大或下跌)
    elif curr_vol > prev_vol * 1.2:
        # 這裡的邏輯是：出量了，但要觀察價格是否站上 5日線
        # 由於是當日判讀，我們提示使用者觀察 5SMA
        if curr_price < sma5:
            msg = "⚠️ 量價背離 (量增價弱)"
            note = "⚠️ 關鍵：未來3日股價需突破5SMA，否則需整理"
            status.append(msg)
            status.append(note)
            need_notify = True
        else:
            status.append("📈 量增價穩 (站上5SMA)")

    # --- 4. 強勢反轉訊號 (Requirement 6) ---
    # a) 底部出現：漲 > 6% 且 過近3日高
    if pct_change >= 0.06 and curr_price > high_3days:
        status.append("🔥 底部強勢反轉 (漲>6%且過3日高)")
        need_notify = True
    
    # b) 高點出現：跌 > 6% 且 破近3日低
    elif pct_change <= -0.06 and curr_price < low_3days:
        status.append("📉 頭部成形警示 (跌>6%且破3日低)")
        need_notify = True

    return status, need_notify, curr_price, position_msg

def analyze_stock(symbol):
    try:
        pure_code = symbol.strip().upper()
        target_symbol = pure_code
        if pure_code.isdigit():
            temp_stock = yf.download(f"{pure_code}.TW", period="5d", progress=False)
            target_symbol = f"{pure_code}.TW" if not temp_stock.empty else f"{pure_code}.TWO"

        stock = yf.Ticker(target_symbol)
        # 抓取 1 年數據 (足夠計算 240SMA)
        df = stock.history(period="1y")
        if len(df) < 60: return None
        
        ch_name = STOCK_NAMES.get(pure_code, stock.info.get('shortName', target_symbol))
        
        # 呼叫判讀
        status_list, need_notify, price, pos_msg = check_strategy(df, target_symbol)
        
        # 組合文字
        status_text = " | ".join(status_list)
        
        report_text = ""
        if need_notify:
            report_text = (f"【{ch_name} ({target_symbol})】\n"
                           f"現價: {price:.2f} ({pos_msg})\n"
                           f"訊號: {status_text}\n"
                           f"------------------------------\n")

        return {
            "代號": target_symbol,
            "公司名稱": ch_name,
            "現價": round(price, 2),
            "位階判讀": pos_msg,
            "戰略訊號": status_text,
            "需要通知": need_notify,
            "回報文字": report_text
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

if run_button:
    if not MY_GMAIL or not MY_PWD:
        st.error("後台 Secrets 未正確設定！")
    elif not friend_email:
        st.warning("請填寫接收通知的 Email。")
    else:
        with st.spinner('正在分析量價結構與60日位階...'):
            tickers = [t.strip() for t in ticker_input.split(',')]
            results = []
            notify_list = []
            
            for t in tickers:
                res = analyze_stock(t)
                if res:
                    results.append(res)
                    if res["需要通知"]:
                        notify_list.append(res["回報文字"])
            
            if results:
                # 顯示表格 (去除內部欄位)
                st.dataframe(pd.DataFrame(results).drop(columns=['需要通知', '回報文字']), use_container_width=True)
                
                if notify_list:
                    receiver_list = [MY_GMAIL, friend_email]
                    chunk_size = 5
                    chunks = [notify_list[i:i + chunk_size] for i in range(0, len(notify_list), chunk_size)]
                    
                    for i, chunk in enumerate(chunks):
                        mail_body = f"【股市戰略報告 - Part {i+1}】\n\n" + "".join(chunk)
                        send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"量價戰略訊號 ({i+1})", mail_body)
                        time.sleep(1)
                        
                    st.success(f"判讀完成！已發送 {len(notify_list)} 則重要訊號。")
                else:
                    st.info("目前持股量價結構穩健，無須發送警示。")
