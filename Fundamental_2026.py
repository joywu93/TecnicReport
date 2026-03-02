import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime

# ==========================================
# 網頁基本設定
# ==========================================
st.set_page_config(page_title="2026 股市戰略指揮中心", layout="wide")
st.title("📊 股市戰略指揮中心 (大部隊速度測試版)")
st.markdown("💡 **測試說明：** 本次將模擬同時運算 150+ 檔個股。除漢唐與堤維西外，其餘個股將帶入模擬基礎數據，以測試系統連線抓取即時股價之效能。")

# ==========================================
# 1. 核心大腦 (完美復刻您的 VBA 疊加邏輯)
# ==========================================
def auto_strategic_model(
    name, current_month, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, 
    base_q_eps, non_op_ratio, base_q_avg_rev, ly_q1_rev, ly_q2_rev, ly_h1_rev, ly_h2_rev, 
    recent_payout_ratio, current_price
):
    # 自動判斷月份
    if current_month == 1: est_q1_avg = (rev_last_11 + rev_last_12) / 2
    elif current_month == 2: est_q1_avg = rev_this_1 * 0.9
    elif current_month == 3: est_q1_avg = (rev_this_1 + rev_this_2) / 2
    else: est_q1_avg = (rev_this_1 + rev_this_2 + rev_this_3) / 3

    # 估今年度 Q1 EPS
    est_q1_eps = base_q_eps * (1 - (non_op_ratio / 100)) * (est_q1_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0

    # 估今年度 EPS (疊加放大法)
    if ly_q1_rev > 0 and ly_h1_rev > 0:
        est_h1_eps = est_q1_eps + (est_q1_eps * (ly_q2_rev / ly_q1_rev))
        est_full_year_eps = est_h1_eps * (1 + (ly_h2_rev / ly_h1_rev))
    else:
        est_full_year_eps = 0

    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    forward_yield = (est_full_year_eps * (calc_payout_ratio / 100)) / current_price * 100 if current_price > 0 else 0

    return {
        "股票名稱": name, "最新股價": current_price,
        "預估今年Q1_EPS": round(est_q1_eps, 2), "預估今年度_EPS": round(est_full_year_eps, 2),
        "運算配息率(%)": calc_payout_ratio, "前瞻殖利率(%)": round(forward_yield, 2)
    }

# ==========================================
# 2. 建立百檔測試資料庫
# ==========================================
# 真實數據保留給漢唐與堤維西作驗證
stock_db = {
    "2404": {"name": "漢唐", "r11": 50, "r12": 55, "r1": 60.3, "r2": 60.3, "r3": 60.3, "b_eps": 16.1, "non_op": 16.2, "b_rev": 64.2, "lq1": 115, "lq2": 110.6, "lh1": 225.6, "lh2": 320.3, "pay": 85.0},
    "1522": {"name": "堤維西", "r11": 20, "r12": 20, "r1": 23.1, "r2": 23.1, "r3": 23.1, "b_eps": 1.1, "non_op": -21.9, "b_rev": 23.23, "lq1": 50, "lq2": 50, "lh1": 100, "lh2": 108.3, "pay": 63.0}
}

# 您圖片上的其餘 150 檔股票代號 (此處僅載入代號供系統連線測速，基本面數值皆帶入模擬預設值)
extra_tickers = [
    "3679", "6203", "1616", "6629", "6227", "6143", "6951", "4554", "3014", "6967", "3217", "6221", "3231", "8432", "4953", "3526", "6996", "6121", "3479", "4763", "2376", "9939", "5236", "8081", "2377", "6197", "3303", "3484", "3406", "2397", "3219", "5871", "6613", "3570", "2439", "3596", "8473", "6605", "3416", "6667", "3264", "3030", "8938", "4961", "3005", "2317", "6788", "6104", "5388", "4760", "6651", "1517", "4766", "6261", "5225", "2493", "3167", "3023", "6176", "6768", "6579", "3227", "5284", "6274", "2454", "6285", "3017", "6187", "2449", "2383", "1597", "3037", "3548", "3163", "1464", "6158", "9914", "3712", "8422", "3702", "2643", "5215", "6811", "1580", "6577", "5609", "3515", "5465", "3090", "1785", "2385", "6206", "3078", "4754", "4105", "1612", "4581", "2480", "6201", "6278", "4442", "6509", "1537", "4915", "5288", "6139", "8383", "5457", "1707", "6807", "6279", "8390", "3356", "3402", "2379", "6192", "8103", "6147", "3290", "4938", "1582", "6894", "7714", "6761", "3147", "6532", "5299", "3317", "3689", "6245", "4571", "2382", "2312", "3455", "2615", "3483", "3042", "3577", "3357", "2441", "4551", "6290"
]

# 批次匯入模擬財報數據
for code in extra_tickers:
    if code not in stock_db:
        stock_db[code] = {"name": f"個股_{code}", "r11": 10, "r12": 10, "r1": 10, "r2": 10, "r3": 10, "b_eps": 1.5, "non_op": 0, "b_rev": 30, "lq1": 30, "lq2": 30, "lh1": 60, "lh2": 65, "pay": 50.0}

# ==========================================
# 3. 網頁介面與測速引擎
# ==========================================
st.sidebar.header("⚙️ 系統時間模擬器")
simulated_month = st.sidebar.slider("目前月份", 1, 12, 2)

if st.button(f"🚀 開始測速：抓取 {len(stock_db)} 檔股價並運算", type="primary"):
    start_time = time.time() # 開始計時
    
    # 建立視覺化進度條
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    results = []
    total_stocks = len(stock_db)
    
    for i, (code, data) in enumerate(stock_db.items()):
        # 更新進度條
        progress = (i + 1) / total_stocks
        progress_bar.progress(progress)
        status_text.text(f"正在連線抓取：{code} ({i+1}/{total_stocks})...")
        
        # 抓取真實即時股價
        try:
            live_price = yf.Ticker(f"{code}.TW").history(period="1d")['Close'].iloc[-1]
        except:
            try: live_price = yf.Ticker(f"{code}.TWO").history(period="1d")['Close'].iloc[-1]
            except: live_price = 100 
            
        res = auto_strategic_model(
            name=f"{code} {data['name']}", current_month=simulated_month,
            rev_last_11=data["r11"], rev_last_12=data["r12"], rev_this_1=data["r1"], rev_this_2=data["r2"], rev_this_3=data["r3"],
            base_q_eps=data["b_eps"], non_op_ratio=data["non_op"], base_q_avg_rev=data["b_rev"],
            ly_q1_rev=data["lq1"], ly_q2_rev=data["lq2"], ly_h1_rev=data["lh1"], ly_h2_rev=data["lh2"],
            recent_payout_ratio=data["pay"], current_price=live_price
        )
        results.append(res)
        
    end_time = time.time() # 結束計時
    total_seconds = round(end_time - start_time, 2)
    
    # 清除進度條文字，顯示完成時間
    status_text.success(f"✅ 測速完成！共計處理 {total_stocks} 檔個股，耗時 {total_seconds} 秒 (約 {round(total_seconds/60, 1)} 分鐘)。")
    
    df_results = pd.DataFrame(results)
    
    def highlight_yield(val):
        color = '#ff4b4b' if isinstance(val, (int, float)) and val >= 4.0 else ''
        weight = 'bold' if isinstance(val, (int, float)) and val >= 4.0 else 'normal'
        return f'color: {color}; font-weight: {weight}'
    
    st.dataframe(
        df_results.style.map(highlight_yield, subset=['前瞻殖利率(%)'])
                  .format({"最新股價": "{:.2f}", "預估今年Q1_EPS": "{:.2f}", "預估今年度_EPS": "{:.2f}", 
                           "運算配息率(%)": "{:.2f}%", "前瞻殖利率(%)": "{:.2f}%"}),
        use_container_width=True
    )
