import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import time
import re # 引入正規表示式模組，處理分隔符號

# ==========================================
# 🔧 使用者設定區 (預設自選股)
# ==========================================
DEFAULT_TICKERS = "2330 2317, 2454; 2603, 6203 4766" 

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

st.set_page_config(page_title="全方位戰略監控系統", layout="wide")
st.title("📈 股市戰略轉折 & 自動容錯監控")

# 後台 Secrets 讀取
MY_GMAIL = st.secrets.get("GMAIL_USER", "")
MY_PWD = st.secrets.get("GMAIL_PASSWORD", "")

st.sidebar.header("👤 使用者設定")
friend_email = st.sidebar.text_input("接收通知信箱", placeholder="請輸入您的 Email")
ticker_input = st.sidebar.text_area("自選股清單 (支援逗號、分號、空白)", value=DEFAULT_TICKERS)
run_button = st.sidebar.button("立即執行判讀")

# --- 3. 核心判讀邏輯 ---
def check_strategy(df):
    # 提取數據
    close = df['Close']
    volume = df['Volume']
    
    # 取得當日與前一日數據
    curr_price = close.iloc[-1]
    prev_price = close.iloc[-2]
    curr_vol = volume.iloc[-1]
    prev_vol = volume.iloc[-2]
    pct_change = (curr_price - prev_price) / prev_price
    
    # 計算均線
    s5 = close.rolling(5).mean()
    s10 = close.rolling(10).mean()
    s20 = close.rolling(20).mean()
    s60 = close.rolling(60).mean() # 季線 (生命線)
    
    # 取得今日與昨日的 60SMA (用於判斷穿越)
    v60 = s60.iloc[-1]
    p60 = s60.iloc[-2]
    
    # 取得今日數值
    v5, v10, v20 = s5.iloc[-1], s10.iloc[-1], s20.iloc[-1]
    # 取得昨日數值 (判斷斜率)
    p5, p10, p20 = s5.iloc[-2], s10.iloc[-2], s20.iloc[-2]

    # === 1. 均線趨勢判斷 (True=向上) ===
    trend_up = {
        5: v5 > p5, 10: v10 > p10, 20: v20 > p20, 60: v60 > p60
    }
    # 計算向上與向下彎的均線數量
    up_count = sum([trend_up[5], trend_up[10], trend_up[20], trend_up[60]])
    down_count = 4 - up_count
    
    status = []
    need_notify = False
    
    # --- A. 60SMA 多空轉折 (Requirement 3) ---
    # 1. 跌破 60SMA (轉空訊號)
    if prev_price > p60 and curr_price < v60:
        msg = f"📉 轉空警示：跌破季線(60SMA)"
        note = "⚠️ 關鍵：短中多轉空，整理時間恐拉長"
        status.append(msg)
        status.append(note)
        need_notify = True
        
    # 2. 站上 60SMA (轉多訊號)
    elif prev_price < p60 and curr_price > v60:
        msg = f"🚀 轉多訊號：站上季線(60SMA)"
        note = "✅ 關鍵：短中空轉多，波段轉強"
        status.append(msg)
        status.append(note)
        need_notify = True

    # --- B. 低檔強勢反彈 (Requirement 2) ---
    # 條件：漲幅 > 4% 且 量 > 1.5倍 (不論是否過高，只要低檔出量就通知)
    # 這裡判斷「非高檔」即可 (例如價格 < 60SMA 或 剛站上)
    is_rebound = pct_change >= 0.04 and curr_vol > prev_vol * 1.5
    if is_rebound:
        status.append("🔥 強勢反彈 (漲>4%且爆量1.5倍)")
        need_notify = True

    # --- C. 底部出現向上轉折 (2條或3條均線向上) ---
    if up_count >= 2:
        if up_count >= 3:
            msg = f"✨ 強力轉折：3條均線同時向上"
        else:
            msg = f"✨ 底部轉折：2條均線開始翻揚"
        status.append(msg)
        # 低檔轉折強制通知
        if curr_price <= v60 * 1.1: 
            need_notify = True 

    # --- D. 其他量價異常警示 ---
    # 1. 爆量長黑
    if curr_vol > prev_vol * 1.5 and pct_change < 0:
        status.append("⚠️ 出貨警訊 (爆量收黑)")
        need_notify = True
        
    # 2. 量價背離 (量增價弱)
    if curr_vol > prev_vol * 1.2 and curr_price < v5 and pct_change < 0:
        status.append("⚠️ 量價背離 (量增價弱，破5SMA)")
        need_notify = True

    return status, need_notify, curr_price, up_count, down_count, v60

def analyze_stock(symbol):
    try:
        # === 智慧輸入處理 (Requirement 1) ===
        # 移除空白與特殊字元，轉大寫
        pure_code = symbol.strip().upper()
        if not pure_code: return None # 跳過空字串

        target_symbol = pure_code
        if pure_code.isdigit():
            # 優先嘗試 .TW，失敗才試 .TWO
            try:
                # 這裡只抓1天資料做快速測試，避免大量下載卡住
                test_stock = yf.Ticker(f"{pure_code}.TW")
                # 檢查是否有數據 (info 或 history)
                if test_stock.history(period="1d").empty:
                    target_symbol = f"{pure_code}.TWO"
                else:
                    target_symbol = f"{pure_code}.TW"
            except:
                target_symbol = f"{pure_code}.TWO"

        stock = yf.Ticker(target_symbol)
        df = stock.history(period="1y")
        
        # 資料不足防呆
        if df.empty or len(df) < 60: 
            return {
                "代號": symbol,
                "公司名稱": "資料不足/錯誤代號",
                "現價": 0,
                "狀態": "❌ 無法讀取",
                "需要通知": False,
                "回報文字": ""
            }
        
        ch_name = STOCK_NAMES.get(pure_code, stock.info.get('shortName', target_symbol))
        
        # 呼叫判讀
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
        # 全域防呆，避免單一個股錯誤卡死整個迴圈
        print(f"Error processing {symbol}: {e}")
        return None

if run_button:
    if not MY_GMAIL or not MY_PWD:
        st.error("後台 Secrets 未正確設定！")
    elif not friend_email:
        st.warning("請填寫接收通知的 Email。")
    else:
        with st.spinner('正在進行戰略掃描 (含容錯處理)...'):
            # === 智慧分割輸入字串 (Requirement 1) ===
            # 使用正規表示式，支援逗號(,)、分號(;)、空白(\s) 作為分隔符
            raw_tickers = re.split(r'[,\s;]+', ticker_input)
            # 過濾掉空字串
            tickers = [t for t in raw_tickers if t]
            
            results = []
            notify_list = []
            
            for t in tickers:
                res = analyze_stock(t)
                if res and res["現價"] > 0: # 排除錯誤代號
                    results.append(res)
                    if res["需要通知"]:
                        notify_list.append(res["回報文字"])
            
            if results:
                st.dataframe(pd.DataFrame(results).drop(columns=['需要通知', '回報文字']), use_container_width=True)
                
                if notify_list:
                    receiver_list = [MY_GMAIL, friend_email]
                    chunk_size = 5
                    chunks = [notify_list[i:i + chunk_size] for i in range(0, len(notify_list), chunk_size)]
                    
                    for i, chunk in enumerate(chunks):
                        mail_body = f"【股市戰略報告 - Part {i+1}】\n\n" + "".join(chunk)
                        send_email_batch(MY_GMAIL, MY_PWD, receiver_list, f"多空轉折與強勢反彈 ({i+1})", mail_body)
                        time.sleep(1)
                        
                    st.success(f"判讀完成！已發送 {len(notify_list)} 則重要訊號。")
                else:
                    st.info("目前持股走勢平穩，無特殊轉折訊號。")
            else:
                st.warning("未找到有效股票，請檢查代號輸入。")
