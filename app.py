import streamlit as st
import yfinance as yf
import pandas as pd
import time
import re

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 底層診斷版", layout="wide")

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

# --- 2. 核心判讀邏輯 ---
def check_strategy(df):
    try:
        # 簡單化處理
        close = df['Close']
        volume = df['Volume']
        
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
        
        # 乖離率
        if curr_price >= v60 * 1.3:
            status.append("⚠️ 乖離過大")

        # 策略訊號
        if prev_price > p60 and curr_price < v60:
            status.append("📉 跌破季線")
        elif prev_price < p60 and curr_price > v60:
            status.append("🚀 站上季線")
            
        pct_change = (curr_price - prev_price) / prev_price if prev_price != 0 else 0
        if pct_change >= 0.04 and curr_vol > prev_vol * 1.5 and curr_price > v3:
            status.append("🔥 強勢反彈")
            
        # 均線排列
        trend = "多方" if curr_price > v60 else "空方"
        
        if not status:
            status.append(f"{trend}盤整")

        return status, f"{trend}", curr_price
    except Exception as e:
        return [f"計算錯: {e}"], "錯誤", 0

# --- 3. 診斷式抓取 (絕不隱藏錯誤) ---
def fetch_diagnostic(ticker):
    # 這裡不使用 try-except，讓錯誤直接顯示在 log 裡
    # 先試 TW
    full_symbol = f"{ticker}.TW"
    t = yf.Ticker(full_symbol)
    df = t.history(period="3mo")
    
    if df.empty:
        # 再試 TWO
        full_symbol = f"{ticker}.TWO"
        t = yf.Ticker(full_symbol)
        df = t.history(period="3mo")
    
    return df, full_symbol

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("🚑 股市戰略 - 底層診斷版")
st.caption("此模式會顯示詳細執行過程，若還是空白，代表網路完全被阻擋。")

# 側邊欄
with st.sidebar.form(key='debug_form'):
    st.header("設定")
    # 預設一些好抓的股票，確保測試能跑
    default_input = "2330, 2317, 2454"
    ticker_input = st.text_area("股票清單", value=default_input, height=200)
    submit_btn = st.form_submit_button(label='🚀 開始診斷')

if submit_btn:
    # 1. 解析
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    tickers = list(dict.fromkeys(raw_tickers))
    
    st.write(f"📋 準備分析清單：{tickers}")
    st.write("---")
    
    results = []
    
    # 2. 逐一執行並即時顯示 Log
    log_area = st.empty()
    logs = []
    
    progress_bar = st.progress(0)
    
    for i, t in enumerate(tickers):
        logs.append(f"🔄 正在處理：{t} ...")
        log_area.text("\n".join(logs[-5:])) # 只顯示最近 5 行 log
        
        try:
            df, final_symbol = fetch_diagnostic(t)
            
            if not df.empty:
                status_list, trend, price = check_strategy(df)
                logs.append(f"✅ {t} 成功抓取！現價：{price}")
                
                results.append({
                    "代號": t,
                    "實際代號": final_symbol,
                    "名稱": STOCK_NAMES.get(t, t),
                    "現價": round(price, 2),
                    "狀態": trend,
                    "訊號": " | ".join(status_list)
                })
            else:
                logs.append(f"❌ {t} 抓取失敗 (Yahoo 回傳空值)")
                # 即使失敗，也要加入表格！
                results.append({
                    "代號": t,
                    "實際代號": "N/A",
                    "名稱": STOCK_NAMES.get(t, t),
                    "現價": 0,
                    "狀態": "❌",
                    "訊號": "無法連線 (IP Blocked)"
                })
                
        except Exception as e:
            logs.append(f"❌ {t} 發生程式錯誤：{str(e)}")
            results.append({
                "代號": t,
                "實際代號": "Error",
                "名稱": STOCK_NAMES.get(t, t),
                "現價": 0,
                "狀態": "Error",
                "訊號": str(e)
            })
            
        progress_bar.progress((i + 1) / len(tickers))
        # 慢一點，比較穩
        time.sleep(0.5)

    log_area.text("🏁 執行結束！")
    
    # 3. 顯示結果 (強制顯示)
    st.write("### 📊 分析結果報告")
    if results:
        df_res = pd.DataFrame(results)
        st.dataframe(df_res, use_container_width=True)
    else:
        st.error("⚠️ 結果列表為空，這代表迴圈根本沒有執行。")
