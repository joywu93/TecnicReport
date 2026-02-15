import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time

# ==========================================
# 🔧 使用者設定區 (請在此修改您的預設股票)
# ==========================================
# 這裡修改後，每次打開網頁都會自動出現這些股票，不用重打
DEFAULT_TICKERS = "2330, 2317, 2451, 2344, 6203, 4766" 

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

st.set_page_config(page_title="均線戰略監控系統", layout="wide")
st.title("📈 股市均線戰略 & 轉折判讀系統")

# 後台 Secrets 讀取
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

st.sidebar.header("👤 使用者設定")
friend_email = st.sidebar.text_input("接收通知信箱", placeholder="請輸入您的 Email")

# 使用變數 DEFAULT_TICKERS 作為預設值，解決重複輸入問題
ticker_input = st.sidebar.text_area("自選股清單 (修改後請按 Ctrl+Enter)", value=DEFAULT_TICKERS)
run_button = st.sidebar.button("立即執行判讀")

# --- 3. 核心判讀邏輯 ---
def check_strategy(df, symbol):
    # 提取數據
    close = df['Close']
    volume = df['Volume']
    
    # 取得當日與前一日數據
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price
    
    # 計算均線 (Series)
    s5 = close.rolling(5).mean()
    s10 = close.rolling(10).mean()
    s20 = close.rolling(20).mean()
    s60 = close.rolling(60).mean()
    s240 = close.rolling(240).mean()

    # 取得今日數值
    v5, v10, v20, v60, v240 = s5.iloc[-1], s10.iloc[-1], s20.iloc[-1], s60.iloc[-1], s240.iloc[-1]
    # 取得昨日數值 (用於判斷下彎)
    p5, p10, p20, p60 = s5.iloc[-2], s10.iloc[-2], s20.iloc[-2], s60.iloc[-2]

    # === 關鍵：判斷均線趨勢 (True=向上, False=向下) ===
    trend_up = {
        5: v5 > p5,
        10: v10 > p10,
        20: v20 > p20,
        60: v60 > p60
    }
    # 計算向下彎的均線數量
    down_count = sum([not trend_up[5], not trend_up[10], not trend_up[20], not trend_up[60]])
    
    # 計算位階 (60日高低)
    high_60 = close.rolling(60).max().iloc[-1]
    low_60 = close.rolling(60).min().iloc[-1]
    
    # 計算近3日高低 (判斷突破/跌破)
    high_3days = close.iloc[-4:-1].max()
    low_3days = close.iloc[-4:-1].min()

    status = []
    need_notify = False
    
    # --- A. 位階與均線趨勢判讀 (解決 Issue 2) ---
    position_msg = ""
    
    # 1. 高檔震盪區 (接近60日高點 OR 在60SMA之上)
    if curr_price > v60:
        if curr_price >= high_60 * 0.98:
            position_msg = "🏰 高檔震盪"
        else:
            position_msg = "🌊 波段多方"

        # **均線下彎偵測邏輯**
        if down_count >= 3:
            # 3條以上均線下彎 (如 2451)
            msg = f"📉 空方持續修正：{down_count}條均線下彎，高檔壓力大"
            status.append(msg)
            need_notify = True
        elif down_count == 2:
            # 2條均線下彎 (如 2344)
            msg = "☁️ 高檔震盪整理：2條均線下彎，留意支撐"
            status.append(msg)
            # 若想讓2條下彎也通知，可設為 True，目前設為 False 僅顯示
            # need_notify = True 
        elif down_count <= 1:
            status.append("✅ 多方趨勢行進中")

    # 2. 低檔整理區
    elif curr_price <= v60:
        if curr_price <= low_60 * 1.02:
            position_msg = "💧 低檔整理"
        else:
            position_msg = "❄️ 波段空方"
            
        # 低檔轉強偵測
        if down_count <= 1: # 均線大多翻揚
            status.append("✨ 底部翻揚：均線開始向上")

    status.append(position_msg)

    # --- B. 量價強勢訊號 (維持前版邏輯) ---
    # 底部爆量長紅
    if curr_vol > prev_vol * 1.5 and pct_change >= 0.04:
        status.append("🚀 短期底部訊號 (爆量長紅)")
        status.append("⚠️ 關鍵：未來3日需守住今日低點")
        need_notify = True

    # 量價背離 (高檔出量不漲 / 低檔量增價跌)
    elif curr_vol > prev_vol * 1.2:
        if curr_price < v5: # 出量但破5日線
            status.append("⚠️ 量價背離 (量增價弱，破5SMA)")
            need_notify = True

    # 強勢反轉 (漲跌幅 > 6%)
    if pct_change >= 0.06 and curr_price > high_3days:
        status.append("🔥 強勢反轉 (漲>6%過前高)")
        need_notify = True
    elif pct_change <= -0.06 and curr_price < low_3days:
        status.append("📉 長黑破線 (跌>6%破前低)")
        need_notify = True

    return status, need_notify, curr_price, position_msg, down_count

def analyze_stock(symbol):
    try:
        pure_code = symbol.strip().upper()
        target_symbol = pure_code
        if pure_code.isdigit():
            temp_stock = yf.download(f"{pure_code}.TW", period="5d", progress=False)
            target_symbol = f"{pure_code}.TW" if not temp_stock.empty else f"{pure_code}.TWO"

        stock = yf.Ticker(target_symbol)
        df = stock.history(period="1y")
        if len(df) < 60: return None
        
        ch_name = STOCK_NAMES.get(pure_code, stock.info.get('shortName', target_symbol))
        
        # 呼叫判讀
        status_list, need_notify, price, pos_msg, down_cnt = check_strategy(df, target_symbol)
        
        status_text = " | ".join(status_list)
        
        report_text = ""
        if need_notify:
            report_text = (f"【{ch_name} ({target_symbol})】\n"
                           f"現價: {price:.2f} ({pos_msg})\n"
                           f"均線狀態: {down_cnt}條下彎\n"
                           f"訊號: {status_text}\n"
                           f"------------------------------\n")

        return {
            "代號": target_symbol,
            "公司名稱": ch_name,
            "現價": round(price, 2),
            "均線下彎數": f"{down_cnt} 條", # 新增欄位方便觀察
            "位階": pos_msg,
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
        with st.spinner('正在分析均線趨勢與量價結構...'):
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
                # 顯示表格
                st.dataframe(pd.DataFrame(results).drop(columns=['需要通知', '回報文字']), use_container_width=True)
                
                if notify_list:
                    receiver_list = [MY_GMAIL, friend_email]
                    chunk_size = 5
                    chunks = [notify_list[i:i + chunk_size] for i in range(0, len(notify_list), chunk_size)]
                    
                    for i, chunk in enumerate(chunks):
                        mail_body = f"【股市戰略報告 - Part {i+1}】\n\n" + "".join(chunk)
                        send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"均線戰略訊號 ({i+1})", mail_body)
                        time.sleep(1)
                        
                    st.success(f"判讀完成！已發送 {len(notify_list)} 則重要訊號。")
                else:
                    st.info("目前持股走勢穩健，無須發送警示。")
