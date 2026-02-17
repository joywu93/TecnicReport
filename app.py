import streamlit as st
import yfinance as yf
import pandas as pd
import time
import re
import os
import requests
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 極速並行版", layout="wide")

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

# 讀取環境變數
MY_PRIVATE_LIST = os.environ.get("MY_LIST", "2330") 

# 偽裝標頭 (隨機切換)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

# --- 核心邏輯：單支股票分析函數 ---
def analyze_stock(ticker):
    try:
        # 隨機延遲一點點，避免多線程同時撞牆
        time.sleep(random.uniform(0.1, 0.5))
        
        session = requests.Session()
        session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
        
        # 優先嘗試 .TW，失敗試 .TWO
        stock_id = f"{ticker}.TW"
        df = yf.Ticker(stock_id, session=session).history(period="1y")
        
        if df.empty:
            stock_id = f"{ticker}.TWO"
            df = yf.Ticker(stock_id, session=session).history(period="1y")
        
        # 如果還是空的，直接回傳錯誤，不要硬算
        if df.empty:
            return {
                "代號": ticker, "名稱": STOCK_NAMES.get(ticker, ticker),
                "現價": "N/A", "乖離": "N/A", "訊號": "❌ 無法讀取 (IP被擋)"
            }

        # 確保資料長度足夠
        close = df['Close']
        if len(close) < 60:
             return {
                "代號": ticker, "名稱": STOCK_NAMES.get(ticker, ticker),
                "現價": round(close.iloc[-1], 2), "乖離": "N/A", "訊號": "⚠️ 資料不足60天"
            }
            
        # === 計算數值 ===
        curr_price = close.iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]
        
        # 防呆：如果 MA60 是 NaN (例如停牌剛恢復)
        if pd.isna(ma60):
             return {
                "代號": ticker, "名稱": STOCK_NAMES.get(ticker, ticker),
                "現價": round(curr_price, 2), "乖離": "N/A", "訊號": "⚠️ 季線計算錯誤"
            }

        # === 乖離率與策略 ===
        bias_pct = ((curr_price - ma60) / ma60) * 100
        
        status = []
        # 1. 乖離率警示
        if bias_pct >= 30:
            status.append(f"🔥⚠️ 乖離過大 (+{bias_pct:.1f}%)")
        elif bias_pct >= 15:
            status.append(f"🔸 乖離偏高 (+{bias_pct:.1f}%)")
            
        # 2. 季線趨勢
        if curr_price > ma60:
            # 如果乖離率沒有過高，就顯示多方行進
            if not status: status.append("🚀 多方行進 (季線之上)")
        else:
            status.append("📉 跌破季線")
            
        return {
            "代號": ticker,
            "名稱": STOCK_NAMES.get(ticker, ticker),
            "現價": round(curr_price, 2),
            "乖離": round(bias_pct, 1),
            "訊號": " | ".join(status)
        }

    except Exception as e:
        return {
            "代號": ticker, "名稱": STOCK_NAMES.get(ticker, ticker),
            "現價": "N/A", "乖離": "N/A", "訊號": "❌ 系統錯誤"
        }

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 極速並行版")
st.caption("啟用多執行緒 (Multi-threading) 加速運算，大幅縮短等待時間。")

use_mobile_view = st.toggle("📱 手機卡片模式", value=True)

with st.sidebar.form(key='stock_form'):
    st.header("設定")
    default_list = MY_PRIVATE_LIST if len(MY_PRIVATE_LIST) > 2 else "2330"
    ticker_input = st.text_area("股票清單", value=default_list, height=250)
    submit_btn = st.form_submit_button(label='🚀 開始極速分析')

if submit_btn:
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    user_tickers = list(dict.fromkeys(raw_tickers))
    
    st.info(f"啟動 5 核心引擎，正在平行分析 {len(user_tickers)} 檔股票...")
    
    results = []
    progress_bar = st.progress(0)
    
    # === 關鍵：多執行緒並行處理 ===
    # max_workers=5 代表同時查 5 支，速度提升 5 倍
    with ThreadPoolExecutor(max_workers=5) as executor:
        # 送出所有任務
        future_to_ticker = {executor.submit(analyze_stock, t): t for t in user_tickers}
        
        count = 0
        for future in as_completed(future_to_ticker):
            data = future.result()
            results.append(data)
            
            count += 1
            progress_bar.progress(count / len(user_tickers))
    
    # 排序：依照原始輸入順序重新排列，不然多執行緒會亂掉
    results.sort(key=lambda x: user_tickers.index(x['代號']) if x['代號'] in user_tickers else 999)
    
    st.success("✅ 分析完成！")
    
    df_res = pd.DataFrame(results)
    
    # === 顯示結果 ===
    if use_mobile_view:
        for idx, row in df_res.iterrows():
            # 樣式邏輯
            border = "1px solid #ddd" # 灰
            bg_color = "white"
            
            signal_str = str(row['訊號'])
            
            if "🔥" in signal_str: 
                border = "2px solid #dc3545" # 紅框
            elif "🔸" in signal_str: 
                border = "2px solid #ffc107" # 黃框
            elif "無法讀取" in signal_str or "系統錯誤" in signal_str:
                bg_color = "#f8f9fa" # 錯誤變灰底
            elif "🚀" in signal_str: 
                border = "2px solid #28a745" # 綠框

            # 乖離率顏色
            bias_val = row['乖離']
            bias_color = "black"
            if isinstance(bias_val, (int, float)):
                if bias_val >= 15: bias_color = "#dc3545"
                elif bias_val <= -15: bias_color = "#28a745"

            with st.container():
                st.markdown(f"""
                <div style="border: {border}; padding: 12px; border-radius: 8px; margin-bottom: 12px; background-color: {bg_color}; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-size: 1.1em; font-weight: bold;">{idx+1}. {row['名稱']}</span>
                            <span style="color: #666; font-size: 0.9em;"> ({row['代號']})</span>
                        </div>
                        <div style="font-size: 1.2em; font-weight: bold;">${row['現價']}</div>
                    </div>
                    <div style="margin-top: 8px; font-size: 0.9em; display: flex; justify-content: space-between; border-top: 1px solid #eee; padding-top: 8px;">
                        <span>乖離率：<span style="color: {bias_color}; font-weight: bold;">{row['乖離']}%</span></span>
                    </div>
                    <div style="margin-top: 5px; font-weight: bold; font-size: 0.95em; color: #333;">
                        {row['訊號']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.dataframe(df_res, use_container_width=True)
