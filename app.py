import streamlit as st
import twstock
import pandas as pd
import time
import re
import os

# ==========================================
# 🔧 系統設定
# ==========================================
st.set_page_config(page_title="股市戰略 - 證交所直連版", layout="wide")

# 中文對照表 (維持您的清單)
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

# 讀取環境變數 (Render / Local)
MY_PRIVATE_LIST = os.environ.get("MY_LIST", "2330") 

# --- 核心邏輯：改用 twstock 抓取 ---
def fetch_stock_data(ticker):
    try:
        # 1. 抓取即時股價 (Realtime)
        # twstock 的即時資料通常很快
        real = twstock.realtime.get(ticker)
        
        if not real['success']:
            return None, 0, 0, "❌ 代號錯誤"
            
        latest_price = real['realtime']['latest_trade_price']
        
        # 處理剛開盤或無成交價
        if not latest_price or latest_price == '-':
             if real['realtime']['best_bid_price']:
                 latest_price = real['realtime']['best_bid_price'][0]
             else:
                 latest_price = real['realtime']['open']
                 
        try:
            current_price = float(latest_price)
        except:
            return None, 0, 0, "❌ 價格解析失敗"

        # 2. 抓取歷史資料算 60MA (History)
        # 這是最花時間的部分，因為要連線去抓 CSV
        stock = twstock.Stock(ticker)
        # 抓過去 70 天，確保有足夠的 60 筆資料
        price_history = stock.price[-70:]
        
        ma60 = 0
        if len(price_history) < 60:
            # 如果是新上市或資料不足，就暫時用現價當均線 (乖離=0)
            ma60 = current_price
        else:
            # 取最後 60 筆平均
            ma60 = sum(price_history[-60:]) / 60
            
        # 3. 計算乖離率
        bias_pct = ((current_price - ma60) / ma60) * 100
        
        status = []
        # === 乖離率判斷 (您的指定標準) ===
        if bias_pct >= 30:
            status.append(f"🔥⚠️ 乖離過大 (+{bias_pct:.1f}%)")
        elif bias_pct >= 15:
            status.append(f"🔸 乖離偏高 (+{bias_pct:.1f}%)")
            
        # 均線趨勢
        if current_price > ma60:
            status.append("🚀 站上季線")
        else:
            status.append("📉 跌破季線")
            
        final_signal = " | ".join(status)
        return current_price, ma60, bias_pct, final_signal

    except Exception as e:
        return None, 0, 0, f"❌ 系統錯誤: {str(e)}"

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("📈 股市戰略 - 證交所直連版")
st.caption("改用 TWSE 證交所直連，避開 Yahoo 封鎖，速度可能稍慢請見諒。")

use_mobile_view = st.toggle("📱 手機卡片模式", value=True)

with st.sidebar.form(key='stock_form'):
    st.header("設定")
    # 如果環境變數有清單就用，沒有就用預設
    default_list = MY_PRIVATE_LIST if len(MY_PRIVATE_LIST) > 2 else "2330"
    ticker_input = st.text_area("股票清單", value=default_list, height=250)
    submit_btn = st.form_submit_button(label='🚀 開始執行')

if submit_btn:
    raw_tickers = re.findall(r'\d{4}', ticker_input)
    # 去重
    user_tickers = list(dict.fromkeys(raw_tickers))
    
    st.info(f"正在連線證交所分析 {len(user_tickers)} 檔股票...")
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(user_tickers):
        stock_name = STOCK_NAMES.get(t, t)
        status_text.text(f"正在抓取: {t} {stock_name} ...")
        
        # 呼叫抓取函數
        price, ma60, bias, signal = fetch_stock_data(t)
        
        row_data = {
            "代號": t,
            "名稱": stock_name,
            "現價": price if price else 0,
            "乖離": round(bias, 1),
            "訊號": signal
        }
        
        results.append(row_data)
        
        # 更新進度
        progress_bar.progress((i + 1) / len(user_tickers))
        
        # 稍微停頓，避免對證交所發出太快請求
        time.sleep(0.5)
        
    status_text.text("✅ 分析完成！")
    
    df_res = pd.DataFrame(results)
    
    # === 顯示結果 ===
    if use_mobile_view:
        for idx, row in df_res.iterrows():
            # 決定邊框顏色
            border = "1px solid #ddd" # 灰
            if "🔥" in row['訊號']: border = "2px solid #dc3545" # 紅
            elif "🔸" in row['訊號']: border = "2px solid #ffc107" # 黃
            elif "🚀" in row['訊號']: border = "2px solid #28a745" # 綠
            
            # 決定乖離率顏色
            bias_color = "black"
            if row['乖離'] >= 15: bias_color = "#dc3545"
            elif row['乖離'] <= -15: bias_color = "#28a745"

            with st.container():
                st.markdown(f"""
                <div style="border: {border}; padding: 12px; border-radius: 8px; margin-bottom: 12px; background-color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-size: 1.1em; font-weight: bold;">{row['序號'] if '序號' in row else ''} {row['名稱']}</span>
                            <span style="color: #666; font-size: 0.9em;"> ({row['代號']})</span>
                        </div>
                        <div style="font-size: 1.2em; font-weight: bold;">${row['現價']}</div>
                    </div>
                    <div style="margin-top: 8px; font-size: 0.9em; display: flex; justify-content: space-between; border-top: 1px solid #eee; padding-top: 8px;">
                        <span>乖離率：<span style="color: {bias_color}; font-weight: bold;">{row['乖離']}%</span></span>
                    </div>
                    <div style="margin-top: 5px; font-weight: bold; font-size: 0.95em;">
                        {row['訊號']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.dataframe(df_res, use_container_width=True)
