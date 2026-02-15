import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import re

# ==========================================
# 🔧 使用者設定區 (預設自選股)
# ==========================================
# 您的長名單直接設為預設值
DEFAULT_TICKERS = "2330, 2317, 2323, 2451, 6203, 4763, 1522, 2404, 6788, 2344, 2368, 4979, 3163, 1326, 3491, 6143, 2408, 2383, 2454, 5225, 3526, 6197, 3570, 3231, 8299, 8069, 3037, 8046, 4977, 3455"

# --- 1. 中文名稱對照表 (持續擴充) ---
STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "6203": "海韻電", "3570": "大塚", "4766": "南寶", "NVDA": "輝達",
    "2313": "華通", "2454": "聯發科", "2303": "聯電", "2603": "長榮", "2609": "陽明", "2615": "萬海",
    "2323": "中環", "2451": "創見", "6229": "研通", "4763": "材料-KY", "1522": "堤維西", "2404": "漢唐",
    "6788": "華景電", "2344": "華邦電", "1519": "華城", "1513": "中興電", "3231": "緯創", "3035": "智原",
    "2408": "南亞科", "3406": "玉晶光", "2368": "金像電", "4979": "華星光", "3163": "波若威", "1326": "台化",
    "3491": "昇達科", "6143": "振曜", "2383": "台光電", "5225": "東科-KY", "3526": "凡甲", "6197": "佳必琪",
    "8299": "群聯", "8069": "元太", "3037": "欣興", "8046": "南電", "4977": "眾達-KY", "3455": "由田"
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

st.set_page_config(page_title="全方位戰略監控系統", layout="wide")
st.title("📈 股市戰略轉折 & 自動容錯監控")

# 後台 Secrets 讀取
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

st.sidebar.header("👤 使用者設定")
friend_email = st.sidebar.text_input("接收通知信箱", placeholder="請輸入您的 Email")
ticker_input = st.sidebar.text_area("自選股清單", value=DEFAULT_TICKERS, height=150)
run_button = st.sidebar.button("立即執行判讀")

# --- 3. 核心判讀邏輯 ---
def check_strategy(df):
    close = df['Close']
    volume = df['Volume']
    
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price
    
    s5 = close.rolling(5).mean()
    s10 = close.rolling(10).mean()
    s20 = close.rolling(20).mean()
    s60 = close.rolling(60).mean() 
    
    v60 = s60.iloc[-1]
    p60 = s60.iloc[-2]
    
    v5, v10, v20 = s5.iloc[-1], s10.iloc[-1], s20.iloc[-1]
    p5, p10, p20 = s5.iloc[-2], s10.iloc[-2], s20.iloc[-2]

    # 均線趨勢判斷 (True=向上)
    trend_up = {5: v5 > p5, 10: v10 > p10, 20: v20 > p20, 60: v60 > p60}
    up_count = sum([trend_up[5], trend_up[10], trend_up[20], trend_up[60]])
    down_count = 4 - up_count
    
    status = []
    need_notify = False
    
    # --- A. 60SMA 多空轉折 ---
    if prev_price > p60 and curr_price < v60:
        msg = f"📉 轉空警示：跌破季線(60SMA)"
        status.append(msg)
        status.append("⚠️ 關鍵：短中多轉空，整理時間恐拉長")
        need_notify = True
        
    elif prev_price < p60 and curr_price > v60:
        msg = f"🚀 轉多訊號：站上季線(60SMA)"
        status.append(msg)
        status.append("✅ 關鍵：短中空轉多，波段轉強")
        need_notify = True

    # --- B. 低檔強勢反彈 ---
    if pct_change >= 0.04 and curr_vol > prev_vol * 1.5:
        status.append("🔥 強勢反彈 (漲>4%且爆量1.5倍)")
        need_notify = True

    # --- C. 底部出現向上轉折 ---
    if up_count >= 2:
        if up_count >= 3:
            status.append(f"✨ 強力轉折：3條均線同時向上")
        else:
            status.append(f"✨ 底部轉折：2條均線開始翻揚")
        if curr_price <= v60 * 1.1: need_notify = True 

    # --- D. 量價異常 ---
    if curr_vol > prev_vol * 1.5 and pct_change < 0:
        status.append("⚠️ 出貨警訊 (爆量收黑)")
        need_notify = True
        
    if curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
        status.append("⚠️ 量價背離 (量增價弱，破5SMA)")
        need_notify = True

    return status, need_notify, curr_price, up_count, down_count, v60

def analyze_stock(symbol):
    try:
        pure_code = symbol.strip().upper()
        if not pure_code: return None 

        target_symbol = pure_code
        # 自動判斷上市櫃 (先試 .TW, 失敗則試 .TWO)
        if pure_code.isdigit():
            try:
                # 這裡使用 yfinance 的 Ticker 物件直接抓取，若抓不到 info 會報錯
                test_ticker = yf.Ticker(f"{pure_code}.TW")
                # 快速檢查是否有歷史數據
                hist = test_ticker.history(period="1d")
                if hist.empty:
                    target_symbol = f"{pure_code}.TWO"
                else:
                    target_symbol = f"{pure_code}.TW"
            except:
                target_symbol = f"{pure_code}.TWO"

        stock = yf.Ticker(target_symbol)
        df = stock.history(period="1y")
        
        if df.empty or len(df) < 60: 
            return {"代號": symbol, "公司名稱": "資料不足", "現價": 0, "狀態": "❌", "需要通知": False, "回報文字": ""}
        
        ch_name = STOCK_NAMES.get(pure_code, stock.info.get('shortName', target_symbol))
        
        status_list, need_notify, price, up_cnt, down_cnt, v60 = check_strategy(df)
        status_text = " | ".join(status_list)
        
        report_text = ""
        if need_notify:
            report_text = (f"【{ch_name} ({target_symbol})】\n"
                           f"現價: {price:.2f} (季線: {v60:.1f})\n"
                           f"訊號: {status_text}\n"
                           f"------------------------------\n")

        return {
            "代號": target_symbol,
            "公司名稱": ch_name,
            "現價": round(price, 2),
            "均線狀態": f"⬆️{up_cnt} / ⬇️{down_cnt}",
            "戰略訊號": status_text,
            "需要通知": need_notify,
            "回報文字": report_text
        }
    except Exception as e:
        return {"代號": symbol, "公司名稱": "讀取錯誤", "現價": 0, "狀態": "❌", "需要通知": False, "回報文字": ""}

if run_button:
    if not MY_GMAIL or not MY_PWD:
        st.error("後台 Secrets 未正確設定！")
    elif not friend_email:
        st.warning("請填寫接收通知的 Email。")
    else:
        # === 智慧輸入與去重複 ===
        raw_tickers = re.split(r'[,\s;]+', ticker_input)
        tickers = list(dict.fromkeys([t for t in raw_tickers if t])) # 去除重複並保持順序
        
        results = []
        notify_list = []
        
        # === 進度條設定 ===
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_tickers = len(tickers)
        for i, t in enumerate(tickers):
            # 更新進度條文字
            status_text.text(f"正在分析 ({i+1}/{total_tickers}): {t} ...")
            
            res = analyze_stock(t)
            
            # 只有抓到資料且現價 > 0 才加入結果
            if res and res["現價"] > 0:
                results.append(res)
                if res["需要通知"]:
                    notify_list.append(res["回報文字"])
            
            # 更新進度條
            progress_bar.progress((i + 1) / total_tickers)
            time.sleep(0.1) # 稍微暫停，避免被 Yahoo 封鎖
            
        status_text.text("分析完成！")
        
        if results:
            st.dataframe(pd.DataFrame(results).drop(columns=['需要通知', '回報文字']), use_container_width=True)
            
            if notify_list:
                receiver_list = [MY_GMAIL, friend_email]
                chunk_size = 5
                chunks = [notify_list[i:i + chunk_size] for i in range(0, len(notify_list), chunk_size)]
                
                for i, chunk in enumerate(chunks):
                    mail_body = f"【股市戰略報告 - Part {i+1}】\n\n" + "".join(chunk)
                    send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"監控報告 ({i+1})", mail_body)
                    time.sleep(1)
                    
                st.success(f"已發送 {len(notify_list)} 則重要訊號。")
            else:
                st.info("目前持股走勢平穩。")
        else:
            st.warning("未找到有效股票，請檢查代號。")
