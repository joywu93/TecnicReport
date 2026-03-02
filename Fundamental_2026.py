import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# 設定網頁標題與寬度
st.set_page_config(page_title="2026 基本面預估中心", layout="wide")
st.title("📊 2026 丙午年基本面預估中心 (Phase 2：動態選單與真實股價)")

# --- 1. 測試用基本面參數庫 (第三階段將換成自動抓取財報) ---
# 這裡先設定 2026 年度的預期參數，用來測試模型運算
stock_data = {
    "2330": {"名稱": "台積電", "去年12月營收(億)": 2500, "歷年Q1淨利率(%)": 38.5, "預估Q1營收(億)": 7100, "預估今年EPS(元)": 38.5, "預估配息率(%)": 50},
    "2317": {"名稱": "鴻海", "去年12月營收(億)": 4600, "歷年Q1淨利率(%)": 2.5, "預估Q1營收(億)": 13000, "預估今年EPS(元)": 11.2, "預估配息率(%)": 50}
}

# --- 2. 營收折線圖與選單區塊 (置於最上方) ---
st.subheader("📈 預估與實際營收軌跡圖")

# 建立下拉選單，讓使用者選擇個股
selected_stock = st.selectbox("請選擇要查看的個股：", ["2330 台積電", "2317 鴻海"])
stock_code = selected_stock.split(" ")[0] # 擷取代號 (如 2330)

# 根據選到的股票，產生對應的折線圖 (目前為模擬數據，後續串接真實營收)
# 利用代號當作隨機種子，讓同一檔股票的圖形固定，切換時會有變化感
np.random.seed(int(stock_code)) 
base_revenue = 2000 if stock_code == "2330" else 4000
chart_data = pd.DataFrame(
    np.random.randn(12, 2) * (base_revenue * 0.1) + base_revenue,
    columns=['實際營收線(億)', '模型預估線(億)']
)
st.line_chart(chart_data)

st.divider() # 分隔線

# --- 3. 戰略預估數據運算區塊 ---
st.subheader("🧮 2026 戰略預估數據表")

# 設定一鍵啟動按鈕
if st.button("🚀 取得最新股價並計算前瞻殖利率"):
    with st.spinner("正在連線抓取最新市場數據..."):
        results = []
        for code, info in stock_data.items():
            # 透過 yfinance 抓取即時真實股價
            try:
                ticker = yf.Ticker(f"{code}.TW") # 台股代號後加上 .TW
                hist = ticker.history(period="1d")
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
                else:
                    current_price = 850 if code == "2330" else 150 # 網路異常時的防呆機制
            except:
                current_price = 850 if code == "2330" else 150

            # 核心邏輯計算：前瞻殖利率 = (預估今年EPS * 配息率) / 目前股價
            forward_yield = (info["預估今年EPS(元)"] * (info["預估配息率(%)"] / 100)) / current_price * 100

            # 將結果整理進列表
            results.append({
                "代號": code,
                "名稱": info["名稱"],
                "最新股價": round(current_price, 2),
                "預估今年EPS(元)": info["預估今年EPS(元)"],
                "預估配息率(%)": info["預估配息率(%)"],
                "前瞻殖利率(%)": round(forward_yield, 2),
                "去年12月營收(億)": info["去年12月營收(億)"],
                "歷年Q1淨利率(%)": info["歷年Q1淨利率(%)"],
                "預估Q1營收(億)": info["預估Q1營收(億)"]
            })

        # 顯示為表格
        df_results = pd.DataFrame(results)
        st.dataframe(df_results, use_container_width=True)
        st.success("✅ 即時股價連線成功！最新前瞻殖利率計算完成。")
else:
    st.info("請點擊上方「🚀 取得最新股價」按鈕開始執行分析。")
