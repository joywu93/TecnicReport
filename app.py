import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import re
import random

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 超級團購版", layout="wide")

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
    # 確保資料是 Series (單一股票)
    try:
        close = df['Close']
        volume = df['Volume']
        
        # 移除 NaN
        close = close.dropna()
        volume = volume.dropna()
        
        if len(close) < 60: return [], False, 0, 0, 0, 0

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
    except Exception as e:
        return [f"計算錯誤: {str(e)}"], False, 0, 0, 0, 0

# --- 4. 超級團購下載 (Super Batch Fetch) ---
@st.cache_data(ttl=60) # 為了測試準確度，暫時縮短快取時間
def fetch_super_batch(tickers):
    if not tickers: return {}
    
    unique_tickers = list(set(tickers))
    
    # 策略：分兩批下載 (.TW 和 .TWO)
    list_tw = [f"{t}.TW" for t in unique_tickers]
    list_two = [f"{t}.TWO" for t in unique_tickers]
    
    valid_data = {}
    
    # 定義下載並處理的內部函式
    def download_and_parse(symbol_list):
        if not symbol_list: return
        
        # 關鍵修正：強制 group_by='ticker' 確保結構統一
        data = yf.download(symbol_list, period="1y", group_by='ticker', progress=False, threads=True)
        
        # 處理單支股票的情況 (Yahoo 會回傳單層 DataFrame)
        if len(symbol_list) == 1:
            ticker = symbol_list[0]
            if not data.empty:
                # 把它包裝成類似多層的結構方便統一處理
                valid_data[ticker] = data
        else:
            # 多支股票 (Yahoo 回傳多層 DataFrame)
            for ticker in symbol_list:
                try:
                    # 嘗試提取該 ticker 的數據
                    df = data[ticker]
                    # 檢查是否有數據 (且不是全空)
                    if not df.empty and not df['Close'].isna().all():
                        valid_data[ticker] = df
                except KeyError:
                    continue

    # 執行下載
    st.write("📥 正在下載上市股票資料...")
    download_and_parse(list_tw)
    
    st.write("📥 正在下載上櫃股票資料...")
    download_and_parse(list_two)
    
    return valid_data

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 超級團購版")

if st.button("🧹 清除暫存 (若資料卡住請按我)"):
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
        # === 1. 解析輸入 ===
        raw_tickers = re.split(r'[,\s;，、]+', ticker_input)
        # 過濾空字串，但保留順序與重複
        user_tickers = [t.strip() for t in raw_tickers if t.strip()]
        
        st.write(f"📊 收到 {len(user_tickers)} 個代號，準備分析...")
        
        # === 2. 執行超級團購 ===
        data_map = fetch_super_batch(user_tickers)
        
        results = []
        notify_list = []
        
        # === 3. 建立報表 (嚴格按照輸入順序) ===
        for i, t in enumerate(user_tickers):
            # 尋找數據 (先找 .TW，再找 .TWO)
            full_tw = f"{t}.TW"
            full_two = f"{t}.TWO"
            
            df = None
            final_symbol = t
            
            if full_tw in data_map:
                df = data_map[full_tw]
                final_symbol = full_tw
            elif full_two in data_map:
                df = data_map[full_two]
                final_symbol = full_two
            
            # 預設值
            row_data = {
                "序號": i + 1,
                "輸入代號": t,
                "公司名稱": STOCK_NAMES.get(t, "未知"),
                "現價": 0,
                "均線狀態": "❌",
                "戰略訊號": "❌ 查無資料 (或代號錯誤)"
            }
            
            if df is not None:
                try:
                    ch_name = STOCK_NAMES.get(t, final_symbol)
                    status_list, need_notify, price, up_cnt, down_cnt, v60 = check_strategy(df)
                    status_str = " | ".join(status_list)
                    
                    row_data["公司名稱"] = ch_name
                    row_data["現價"] = round(price, 2)
                    row_data["均線狀態"] = f"⬆️{up_cnt} / ⬇️{down_cnt}"
                    row_data["戰略訊號"] = status_str
                    
                    if need_notify:
                        report = f"【{ch_name}】{price} | {status_str}\n"
                        notify_list.append(report)
                        
                except Exception as e:
                    row_data["戰略訊號"] = f"計算錯誤: {str(e)}"
            
            results.append(row_data)
        
        st.success("✅ 分析完成！")
        
        if results:
            df_res = pd.DataFrame(results)
            st.dataframe(df_res, use_container_width=True, hide_index=True)
            
            if notify_list and MY_GMAIL:
                receiver_list = [MY_GMAIL, friend_email]
                chunks = [notify_list[i:i + 15] for i in range(0, len(notify_list), 15)]
                for i, chunk in enumerate(chunks):
                    send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"戰略訊號 ({i+1})", "".join(chunk))
                st.success(f"已發送 {len(notify_list)} 則通知信。")

except Exception as e:
    st.error(f"系統錯誤: {e}")
