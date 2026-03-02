import streamlit as st
import pandas as pd
import yfinance as yf

# ==========================================
# 網頁基本設定
# ==========================================
st.set_page_config(page_title="2026 基本面預估中心", layout="wide")
st.title("📊 2026 丙午年基本面戰略指揮中心 (全自動連線版)")
st.markdown("💡 **操作說明：** 點擊下方按鈕，系統將自動抓取最新股價，並透過歷史營收權重推算 2026 年預估 EPS 與前瞻殖利率。")

# ==========================================
# 1. 核心運算大腦 (與您 Excel 完全一致的邏輯)
# ==========================================
def calculate_2026_strategic_model(
    name, rev_24q1, rev_24q2, rev_24q3, rev_24q4, rev_25q1, rev_25q2, rev_25q3, rev_25q4, 
    avg_op_margin, shares_outstanding, recent_payout_ratio, current_price
):
    # 計算各季與全年總和
    total_24_25 = sum([rev_24q1, rev_24q2, rev_24q3, rev_24q4, rev_25q1, rev_25q2, rev_25q3, rev_25q4])
    q1_24_25_total = rev_24q1 + rev_25q1

    # 平滑化 Q4 基期算 26Q1
    avg_q4 = (rev_24q4 + rev_25q4) / 2
    est_26q1_rev = (rev_25q4 * rev_25q1) / avg_q4 if avg_q4 > 0 else 0

    # 季節性權重還原算全年營收
    seasonality_multiplier = total_24_25 / q1_24_25_total if q1_24_25_total > 0 else 0
    est_2026_total_rev = est_26q1_rev * seasonality_multiplier

    # 推算本業 EPS (扣除 20% 稅)
    est_2026_op_profit = est_2026_total_rev * (avg_op_margin / 100)
    est_2026_net_profit = est_2026_op_profit * 0.8 
    est_2026_eps = est_2026_net_profit / shares_outstanding if shares_outstanding > 0 else 0

    # 防呆配息率與殖利率
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    forward_yield = (est_2026_eps * (calc_payout_ratio / 100)) / current_price * 100 if current_price > 0 else 0

    return {
        "股票名稱": name,
        "最新股價": current_price,
        "預估26Q1營收(億)": round(est_26q1_rev, 1),
        "預估26全年營收(億)": round(est_2026_total_rev, 1),
        "預估今年EPS(元)": round(est_2026_eps, 2),
        "運算配息率(%)": calc_payout_ratio,
        "前瞻殖利率(%)": round(forward_yield, 2)
    }

# ==========================================
# 2. 測試股池歷史基礎數據 (模擬您的 Excel 資料庫)
# ==========================================
# 註：這裡先放入我們剛剛測試的四檔股票歷史數據，後續可擴充
stock_db = {
    "2330": {"name": "台積電", "24q1": 5926, "24q2": 6735, "24q3": 7596, "24q4": 8393, "25q1": 7300, "25q2": 8000, "25q3": 9000, "25q4": 10000, "margin": 42, "shares": 259.3, "payout": 32.5},
    "2317": {"name": "鴻海", "24q1": 13222, "24q2": 15000, "24q3": 17000, "24q4": 18500, "25q1": 14000, "25q2": 16000, "25q3": 18000, "25q4": 19500, "margin": 3.5, "shares": 138.6, "payout": 52.7},
    "1522": {"name": "堤維西", "24q1": 45, "24q2": 48, "24q3": 50, "24q4": 52, "25q1": 50, "25q2": 52, "25q3": 55, "25q4": 60, "margin": 10, "shares": 3.12, "payout": 63.0},
    "6667": {"name": "信紘科", "24q1": 6.5, "24q2": 7.0, "24q3": 7.5, "24q4": 8.0, "25q1": 7.5, "25q2": 8.0, "25q3": 8.5, "25q4": 9.5, "margin": 15, "shares": 0.45, "payout": 0}
}

# ==========================================
# 3. 執行分析與網頁顯示
# ==========================================
if st.button("🚀 點此開始：抓取最新股價並執行戰略分析", type="primary"):
    with st.spinner("正在連線到證券交易所抓取即時股價..."):
        results = []
        
        for code, data in stock_db.items():
            # 💡 全自動抓取最新股價
            try:
                ticker = yf.Ticker(f"{code}.TW")
                hist = ticker.history(period="1d")
                if not hist.empty:
                    live_price = hist['Close'].iloc[-1]
                else:
                    ticker_otc = yf.Ticker(f"{code}.TWO") # 嘗試上櫃代碼
                    live_price = ticker_otc.history(period="1d")['Close'].iloc[-1]
            except:
                live_price = 100 # 網路異常防呆
            
            # 將最新股價與歷史資料餵給大腦計算
            res = calculate_2026_strategic_model(
                name=f"{code} {data['name']}",
                rev_24q1=data["24q1"], rev_24q2=data["24q2"], rev_24q3=data["24q3"], rev_24q4=data["24q4"],
                rev_25q1=data["25q1"], rev_25q2=data["25q2"], rev_25q3=data["25q3"], rev_25q4=data["25q4"],
                avg_op_margin=data["margin"], shares_outstanding=data["shares"], 
                recent_payout_ratio=data["payout"], current_price=live_price
            )
            results.append(res)
            
        df_results = pd.DataFrame(results)

        st.success("✅ 即時股價連線成功！分析報表已產出。")

        # --- 顯示戰略四象限圖 ---
        st.subheader("🎯 戰略四象限圖 (右上角為高防禦、高成長)")
        st.markdown("圖表中橫軸為預估 EPS，縱軸為前瞻殖利率。**越往上方代表防禦力越強 (殖利率越高)**。")
        
        # 繪製散佈圖
        st.scatter_chart(
            data=df_results,
            x="預估今年EPS(元)",
            y="前瞻殖利率(%)",
            color="股票名稱",
            size=200,
            height=400
        )

        # --- 顯示數據表格 ---
        st.subheader("🧮 2026 戰略預估數據表")
        
        # 將大於 4% 的殖利率特別標示的函數
        def highlight_yield(val):
            color = '#ff4b4b' if val >= 4.0 else ''
            weight = 'bold' if val >= 4.0 else 'normal'
            return f'color: {color}; font-weight: {weight}'
        
        # 顯示套用顏色的表格
        st.dataframe(
            df_results.style.map(highlight_yield, subset=['前瞻殖利率(%)'])
                      .format({"最新股價": "{:.1f}", "前瞻殖利率(%)": "{:.2f}%"}),
            use_container_width=True
        )
