import streamlit as st
import pandas as pd
import numpy as np

# 設定網頁標題與寬度
st.set_page_config(page_title="2026 基本面預估中心", layout="wide")
st.title("📊 2026 丙午年基本面預估中心 (概念驗證版)")

st.write("目前測試標的：2330 台積電、2317 鴻海")
st.info("這是一個測試網頁，確認 GitHub 與 Streamlit 連結成功，後續將匯入真實連線數據。")

# 建立一個測試用的資料表 (對應您的欄位邏輯)
data = {
    "代號": ["2330", "2317"],
    "名稱": ["台積電", "鴻海"],
    "去年12月營收(億)": [2500, 4600],
    "歷年Q1淨利率(%)": [38.5, 2.5],
    "預估Q1營收(億)": [7100, 13000],
    "預估今年EPS(元)": [38.5, 11.2],
    "預估配息率(%)": [50, 50],
}
df = pd.DataFrame(data)

# 測試計算：前瞻殖利率 (假設目前股價 2330=850, 2317=150)
current_price = [850, 150]
df["前瞻殖利率(%)"] = (df["預估今年EPS(元)"] * (df["預估配息率(%)"]/100)) / current_price * 100
df["前瞻殖利率(%)"] = df["前瞻殖利率(%)"].round(2)

st.dataframe(df)

# 畫個簡單的折線圖示意 (預估 vs 實際營收)
st.subheader("📈 預估與實際營收軌跡圖 (版面測試)")
chart_data = pd.DataFrame(
    np.random.randn(12, 2) * 100 + 1000,
    columns=['實際營收線', '模型預估線']
)
st.line_chart(chart_data)

st.success("✅ 系統連線成功！第一步網頁介面與基礎資料表建置完畢。")
