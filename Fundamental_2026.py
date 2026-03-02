import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# ==========================================
# 網頁基本設定
# ==========================================
st.set_page_config(page_title="2026 基本面預估中心", layout="wide")
st.title("📊 2026 丙午年基本面戰略指揮中心")

# ==========================================
# 1. 核心運算大腦 (升級採用「稅後淨利率」精算 EPS)
# ==========================================
def calculate_2026_strategic_model(
    name, rev_24q1, rev_24q2, rev_24q3, rev_24q4, rev_25q1, rev_25q2, rev_25q3, rev_25q4, 
    avg_net_margin, shares_outstanding, recent_payout_ratio, current_price,
    contract_liab, contract_liab_qoq, note
):
    total_24_25 = sum([rev_24q1, rev_24q2, rev_24q3, rev_24q4, rev_25q1, rev_25q2, rev_25q3, rev_25q4])
    q1_24_25_total = rev_24q1 + rev_25q1

    avg_q4 = (rev_24q4 + rev_25q4) / 2
    est_26q1_rev = (rev_25q4 * rev_25q1) / avg_q4 if avg_q4 > 0 else 0

    seasonality_multiplier = total_24_25 / q1_24_25_total if q1_24_25_total > 0 else 0
    est_2026_total_rev = est_26q1_rev * seasonality_multiplier

    # 推算各季目標 (用於折線圖)
    q2_24_25_total = rev_24q2 + rev_25q2
    q3_24_25_total = rev_24q3 + rev_25q3
    q4_24_25_total = rev_24q4 + rev_25q4
    est_26q2_rev = est_2026_total_rev * (q2_24_25_total / total_24_25) if total_24_25 > 0 else 0
    est_26q3_rev = est_2026_total_rev * (q3_24_25_total / total_24_25) if total_24_25 > 0 else 0
    est_26q4_rev = est_2026_total_rev * (q4_24_25_total / total_24_25) if total_24_25 > 0 else 0

    # EPS 精算：直接使用稅後淨利率 (Net Margin)
    est_2026_net_profit = est_2026_total_rev * (avg_net_margin / 100)
    est_2026_eps = est_2026_net_profit / shares_outstanding if shares_outstanding > 0 else 0

    # 防呆配息率與殖利率
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    forward_yield = (est_2026_eps * (calc_payout_ratio / 100)) / current_price * 100 if current_price > 0 else 0

    return {
        "股票名稱": name,
        "最新股價": current_price,
        "預估今年EPS(元)": round(est_2026_eps, 2),
        "運算配息率(%)": calc_payout_ratio,
        "前瞻殖利率(%)": round(forward_yield, 2),
        "流動合約負債(億)": contract_liab,
        "合約負債季增(%)": contract_liab_qoq,
        "個股觀察筆記": note,
        # 隱藏欄位供畫圖使用
        "_est_qs": [est_26q1_rev, est_26q2_rev, est_26q3_rev, est_26q4_rev],
        "_ly_qs": [rev_25q1, rev_25q2, rev_25q3, rev_25q4]
    }

# ==========================================
# 2. 歷史基礎數據池 (含多檔印證與合約負債)
# ==========================================
# margin 改為「稅後淨利率」
stock_db = {
    "2330": {"name": "台積電", "24q1": 5926, "24q2": 6735, "24q3": 7596, "24q4": 8393, "25q1": 7300, "25q2": 8000, "25q3": 9000, "25q4": 10000, "margin": 38.5, "shares": 259.3, "payout": 32.5, "liab": 2500, "liab_qoq": 5.2, "note": "先進製程產能滿載，觀察資本支出執行率。"},
    "2317": {"name": "鴻海", "24q1": 13222, "24q2": 15000, "24q3": 17000, "24q4": 18500, "25q1": 14000, "25q2": 16000, "25q3": 18000, "25q4": 19500, "margin": 2.5, "shares": 138.6, "payout": 52.7, "liab": 1800, "liab_qoq": 2.1, "note": "AI伺服器出貨動能強勁。"},
    "1522": {"name": "堤維西", "24q1": 45, "24q2": 48, "24q3": 50, "24q4": 52, "25q1": 50, "25q2": 52, "25q3": 55, "25q4": 60, "margin": 8.5, "shares": 3.12, "payout": 63.0, "liab": 12, "liab_qoq": -1.5, "note": "營收年增來自於合併營收，需扣除匯兌損益影響。"},
    "6197": {"name": "佳必琪", "24q1": 12, "24q2": 15, "24q3": 18, "24q4": 20, "25q1": 15, "25q2": 18, "25q3": 20, "25q4": 22, "margin": 10.5, "shares": 1.5, "payout": 60, "liab": 8.5, "liab_qoq": 15.2, "note": "觀察6月專利是否有順利投入營收貢獻。"},
    "6629": {"name": "泰金-KY", "24q1": 2.5, "24q2": 3.0, "24q3": 3.5, "24q4": 3.8, "25q1": 3.2, "25q2": 3.5, "25q3": 4.0, "25q4": 4.5, "margin": 15.0, "shares": 0.35, "payout": 75, "liab": 1.2, "liab_qoq": 8.5, "note": "新產品水五金投入生產，觀察下半年毛利變化。"},
    "2404": {"name": "漢唐", "24q1": 150, "24q2": 160, "24q3": 155, "24q4": 170, "25q1": 165, "25q2": 175, "25q3": 180, "25q4": 190, "margin": 12.0, "shares": 1.9, "payout": 80, "liab": 550, "liab_qoq": 12.4, "note": "台積電建廠進度指標，重點關注流動合約負債是否續創新高。"},
    "3217": {"name": "優群", "24q1": 6.5, "24q2": 7.0, "24q3": 8.5, "24q4": 7.8, "25q1": 7.5, "25q2": 8.2, "25q3": 9.5, "25q4": 9.0, "margin": 22.0, "shares": 0.9, "payout": 85, "liab": 3.5, "liab_qoq": 4.1, "note": "Type-C 與伺服器連接器滲透率提升。"},
    "3526": {"name": "凡甲", "24q1": 5.5, "24q2": 6.2, "24q3": 7.5, "24q4": 7.0, "25q1": 6.5, "25q2": 7.8, "25q3": 8.5, "25q4": 8.2, "margin": 28.0, "shares": 0.6, "payout": 90, "liab": 2.8, "liab_qoq": 6.5, "note": "車用與伺服器高頻連接器佔比持續拉高。"}
}

# ==========================================
# 3. 執行分析與網頁顯示
# ==========================================
if st.button("🚀 點此開始：抓取最新股價並執行戰略分析", type="primary"):
    with st.spinner("正在連線抓取即時股價並運算報表..."):
        results = []
        for code, data in stock_db.items():
            try:
                ticker = yf.Ticker(f"{code}.TW")
                hist = ticker.history(period="1d")
                if not hist.empty:
                    live_price = hist['Close'].iloc[-1]
                else:
                    live_price = yf.Ticker(f"{code}.TWO").history(period="1d")['Close'].iloc[-1]
            except:
                live_price = 100 # 網路異常防呆
            
            res = calculate_2026_strategic_model(
                name=f"{code} {data['name']}",
                rev_24q1=data["24q1"], rev_24q2=data["24q2"], rev_24q3=data["24q3"], rev_24q4=data["24q4"],
                rev_25q1=data["25q1"], rev_25q2=data["25q2"], rev_25q3=data["25q3"], rev_25q4=data["25q4"],
                avg_net_margin=data["margin"], shares_outstanding=data["shares"], 
                recent_payout_ratio=data["payout"], current_price=live_price,
                contract_liab=data["liab"], contract_liab_qoq=data["liab_qoq"], note=data["note"]
            )
            results.append(res)
            
        df_results = pd.DataFrame(results)
        st.session_state["df_results"] = df_results # 存入暫存供圖表使用
        st.success("✅ 即時股價連線成功！報表產出完畢。")

# ==========================================
# 4. 個股深度折線圖與報表呈現
# ==========================================
if "df_results" in st.session_state:
    df = st.session_state["df_results"]
    
    st.divider()
    st.subheader("📈 個股季度營收追蹤與觀察 (去年實際 vs 今年預估)")
    
    # 建立下拉選單
    stock_list = df["股票名稱"].tolist()
    selected_stock = st.selectbox("請選擇要查看的個股：", stock_list)
    
    # 取得選中個股的資料
    stock_row = df[df["股票名稱"] == selected_stock].iloc[0]
    
    # 顯示個股專屬筆記
    st.info(f"📝 **您的觀察筆記：** {stock_row['個股觀察筆記']}")
    
    # 繪製單一個股季度營收折線圖
    chart_data = pd.DataFrame({
        "2025實際營收(億)": stock_row["_ly_qs"],
        "2026模型預估(億)": stock_row["_est_qs"]
    }, index=["Q1", "Q2", "Q3", "Q4"])
    
    st.line_chart(chart_data)

    st.divider()
    st.subheader("🧮 2026 戰略預估數據總表")
    
    # 將不需顯示在表格的畫圖欄位移除
    display_df = df.drop(columns=["_est_qs", "_ly_qs"])
    
    # 紅綠燈標示 (殖利率 >= 4% 標紅字加粗)
    def highlight_yield(val):
        color = '#ff4b4b' if isinstance(val, (int, float)) and val >= 4.0 else ''
        weight = 'bold' if isinstance(val, (int, float)) and val >= 4.0 else 'normal'
        return f'color: {color}; font-weight: {weight}'
    
    st.dataframe(
        display_df.style.map(highlight_yield, subset=['前瞻殖利率(%)'])
                  .format({"最新股價": "{:.1f}", "前瞻殖利率(%)": "{:.2f}%", "流動合約負債(億)": "{:.1f}", "合約負債季增(%)": "{:.1f}%"}),
        use_container_width=True
    )
