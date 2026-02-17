import streamlit as st
import yfinance as yf
import pandas as pd
import time
import re

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - Streamlit 專用版", layout="wide")

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

# --- 核心邏輯：快取抓取函數 (防止頻繁連線) ---
# ttl=900 代表資料會在記憶體存活 900秒 (15分鐘)
# 這期間內您重新整理網頁，程式會直接拿記憶體的資料，不會連線 Yahoo，所以不會被擋！
@st.cache_data(ttl=900, show_spinner=False)
def fetch_stock_data_batch(ticker_list):
    data_results = []
    
    for t in ticker_list:
        try:
            # 嘗試 TW
            stock_id = f"{t}.TW"
            ticker_obj = yf.Ticker(stock_id)
            df = ticker_obj.history(period="1y")
            
            # 如果 TW 沒資料，改試 TWO
            if df.empty:
                stock_id = f"{t}.TWO"
                ticker_obj = yf.Ticker(stock_id)
                df = ticker_obj.history(period="1y")
            
            if df.empty or len(df) < 60:
                data_results.append({
                    "code": t, "name": STOCK_NAMES.get(t, t),
                    "price": 0, "ma60": 0, "error": "資料不足"
                })
                continue

            # 計算數據
            close = df['Close']
            curr_price = close.iloc[-1]
            ma60 = close.rolling(60).mean().iloc[-1]
            
            data_results.append({
                "code": t,
                "name": STOCK_NAMES.get(t, t),
                "price": float(curr_price),
                "ma60": float(ma60),
                "error": None
            })
            
            # 稍微停頓一下，雖然有快取，但第一次抓還是溫柔點
            time.sleep(0.1)
            
        except Exception as e:
            data_results.append({
                "code": t, "name": STOCK_NAMES.get(t, t),
                "price": 0, "ma60": 0, "error": "讀取錯誤"
            })
            
    return data_results

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - Streamlit 快取版")
st.info("💡 系統已啟用「15分鐘快取」。第一次載入後，15分鐘內重新整理都不會被擋，且速度極快。")

# 側邊欄
with st.sidebar.form(key='stock_form'):
    st.header("設定")
    ticker_input = st.text_area("股票清單", value=DEFAULT_LIST, height=300)
    
    col1, col2 = st.columns(2)
    with col1:
        submit_btn = st.form_submit_button(label='🚀 開始分析')
    with col2:
        # 強制清除快取按鈕
        clear_btn = st.form_submit_button(label='🔄 強制更新')

if clear_btn:
    st.cache_data.clear()
    st.toast("已清除快取，將重新抓取最新資料！")

if submit_btn or clear_btn:
    # 解析代號
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    user_tickers = list(dict.fromkeys(raw_tickers)) # 去重
    
    with st.spinner(f"正在分析 {len(user_tickers)} 檔股票... (若為第一次執行需稍等)"):
        # 呼叫快取函數
        stock_data = fetch_stock_data_batch(user_tickers)
    
    st.success(f"分析完成！共 {len(stock_data)} 檔。")
    
    # 顯示卡片
    for item in stock_data:
        # 錯誤處理
        if item['error']:
            st.error(f"{item['name']} ({item['code']}): {item['error']}")
            continue
            
        price = item['price']
        ma60 = item['ma60']
        
        # === 乖離率計算 ===
        # 公式：(現價 - 季線) / 季線
        if ma60 > 0:
            bias_val = ((price - ma60) / ma60) * 100
        else:
            bias_val = 0
            
        # === 訊號判斷 (修正邏輯：優先權最高) ===
        status_text = ""
        border_style = "1px solid #ddd" # 預設灰框
        bias_color = "black"
        
        # 1. 優先檢查乖離 (紅燈 > 黃燈)
        if bias_val >= 30:
            status_text = f"🔥⚠️ 乖離過大 (+{bias_val:.1f}%)"
            border_style = "2px solid #dc3545" # 紅框
            bias_color = "#dc3545" # 紅字
        elif bias_val >= 15:
            status_text = f"🔸 乖離偏高 (+{bias_val:.1f}%)"
            border_style = "2px solid #ffc107" # 黃框
            bias_color = "#d39e00" # 黃字
        
        # 2. 如果沒有乖離警示，才顯示趨勢
        if status_text == "":
            if price > ma60:
                status_text = "🚀 多方行進 (季線之上)"
                border_style = "2px solid #28a745" # 綠框
            else:
                status_text = "📉 季線之下 (整理中)"
        
        # === 畫出卡片 ===
        with st.container():
            st.markdown(f"""
            <div style="border: {border_style}; padding: 12px; border-radius: 8px; margin-bottom: 12px; background-color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="font-size: 1.2em; font-weight: bold;">{item['name']}</span>
                        <span style="color: #666; font-size: 0.9em;"> ({item['code']})</span>
                    </div>
                    <div style="font-size: 1.3em; font-weight: bold;">${price}</div>
                </div>
                
                <div style="margin-top: 8px; display: flex; justify-content: space-between; font-size: 0.95em; color: #444; border-top: 1px solid #eee; padding-top: 8px;">
                    <span>季線(60MA): {ma60:.1f}</span>
                    <span>乖離率: <strong style="color: {bias_color};">{bias_val:.1f}%</strong></span>
                </div>
                
                <div style="margin-top: 8px; font-weight: bold; font-size: 1em;">
                    {status_text}
                </div>
            </div>
            """, unsafe_allow_html=True)
