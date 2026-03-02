import streamlit as st
import pandas as pd
from datetime import datetime

# ==========================================
# 網頁基本設定
# ==========================================
st.set_page_config(page_title="2026 股市戰略指揮中心", layout="wide")
st.title("📊 股市戰略指揮中心 (V12 終極匯入版)")
st.markdown("💡 **傳承無痛化：** 未來只需將整理好的 Excel 拖曳至左側，系統將自動套用 VBA 邏輯並計算全年度 EPS。")

# ==========================================
# 1. 核心大腦：完美復刻 VBA 
# ==========================================
def auto_strategic_model(
    name, current_month,
    rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, 
    base_q_eps, non_op_ratio, base_q_avg_rev,                     
    ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev,                   
    recent_payout_ratio, current_price
):
    ly_h1_rev = ly_q1_rev + ly_q2_rev
    ly_h2_rev = ly_q3_rev + ly_q4_rev

    if current_month == 1:
        est_q1_avg = (rev_last_11 + rev_last_12) / 2
        formula_note = "採上年11、12月均值"
    elif current_month == 2:
        est_q1_avg = rev_this_1 * 0.9  
        formula_note = "採當年1月營收×0.9"
    elif current_month == 3:
        est_q1_avg = (rev_this_1 + rev_this_2) / 2
        formula_note = "採當年1、2月均值"
    else:
        est_q1_avg = (rev_this_1 + rev_this_2 + rev_this_3) / 3
        formula_note = "採當年Q1實際均值"

    est_q1_rev_total = est_q1_avg * 3
    q1_yoy = ((est_q1_rev_total - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0
    est_q1_eps = base_q_eps * (1 - (non_op_ratio / 100)) * (est_q1_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0

    if ly_q1_rev > 0 and ly_h1_rev > 0:
        est_q2_rev_total = est_q1_rev_total * (ly_q2_rev / ly_q1_rev)
        est_h1_eps = est_q1_eps + (est_q1_eps * (ly_q2_rev / ly_q1_rev))
        est_full_year_eps = est_h1_eps * (1 + (ly_h2_rev / ly_h1_rev))
        
        est_h1_rev_total = est_q1_rev_total + est_q2_rev_total
        est_h2_rev_total = est_h1_rev_total * (ly_h2_rev / ly_h1_rev)
        est_q3_rev_total = est_h2_rev_total * (ly_q3_rev / ly_h2_rev) if ly_h2_rev > 0 else 0
        est_q4_rev_total = est_h2_rev_total * (ly_q4_rev / ly_h2_rev) if ly_h2_rev > 0 else 0
    else:
        est_full_year_eps = 0
        est_q2_rev_total = est_q3_rev_total = est_q4_rev_total = 0

    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    forward_yield = (est_full_year_eps * (calc_payout_ratio / 100)) / current_price * 100 if current_price > 0 else 0

    return {
        "股票名稱": name,
        "最新股價": current_price,
        "套用公式": formula_note,
        "當季預估均營收": round(est_q1_avg, 2),
        "季成長率(YoY)%": round(q1_yoy, 2),
        "預估今年Q1_EPS": round(est_q1_eps, 2),    
        "預估今年度_EPS": round(est_full_year_eps, 2), 
        "本益比(PER)": round(est_per, 2),
        "前瞻殖利率(%)": round(forward_yield, 2),
        "運算配息率(%)": calc_payout_ratio,
        "_est_qs": [est_q1_rev_total, est_q2_rev_total, est_q3_rev_total, est_q4_rev_total],
        "_ly_qs": [ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev]
    }

# ==========================================
# 2. 側邊欄：檔案上傳與時間模擬
# ==========================================
st.sidebar.header("📥 資料庫匯入區")
st.sidebar.info("未來晚輩只需將 Goodinfo 下載的 Excel 拖曳至此，即可瞬間分析百檔股票！")
uploaded_file = st.sidebar.file_uploader("上傳財報總表 (Excel/CSV)", type=["xlsx", "csv"])

st.sidebar.divider()
st.sidebar.header("⚙️ 系統時間模擬器")
simulated_month = st.sidebar.slider("目前月份", 1, 12, 2)

# ==========================================
# 3. 執行區塊 (若無上傳檔案，載入預設 2 檔測試)
# ==========================================
# 預設測試股池
stock_db = {
    "2404": {"name": "漢唐", "rev_last_11": 50, "rev_last_12": 55, "rev_this_1": 60.3, "rev_this_2": 60.3, "rev_this_3": 60.3, "base_q_eps": 16.1, "non_op": 16.2, "base_q_avg_rev": 64.2, "ly_q1_rev": 115, "ly_q2_rev": 110.6, "ly_q3_rev": 155, "ly_q4_rev": 170.3, "payout": 85.0, "price": 1130.0},
    "1522": {"name": "堤維西", "rev_last_11": 20, "rev_last_12": 20, "rev_this_1": 23.1, "rev_this_2": 23.1, "rev_this_3": 23.1, "base_q_eps": 1.17, "non_op": -21.9, "base_q_avg_rev": 23.23, "ly_q1_rev": 50, "ly_q2_rev": 50, "ly_q3_rev": 55, "ly_q4_rev": 53.3, "payout": 63.0, "price": 44.0}
}

if st.button(f"🚀 執行 {simulated_month} 月份戰略分析", type="primary"):
    with st.spinner("正在執行 VBA 核心運算..."):
        
        # 💡 未來這裡將加入讀取 uploaded_file 的邏輯
        if uploaded_file is not None:
            st.success(f"讀取到檔案：{uploaded_file.name} (即將開放自動解析功能)")
            # 這裡之後會寫自動模糊比對欄位的程式碼
        
        results = []
        for code, data in stock_db.items():
            res = auto_strategic_model(
                name=f"{code} {data['name']}", current_month=simulated_month,
                rev_last_11=data["rev_last_11"], rev_last_12=data["rev_last_12"], 
                rev_this_1=data["rev_this_1"], rev_this_2=data["rev_this_2"], rev_this_3=data["rev_this_3"],
                base_q_eps=data["base_q_eps"], non_op_ratio=data["non_op"], base_q_avg_rev=data["base_q_avg_rev"],
                ly_q1_rev=data["ly_q1_rev"], ly_q2_rev=data["ly_q2_rev"], ly_q3_rev=data["ly_q3_rev"], ly_q4_rev=data["ly_q4_rev"],
                recent_payout_ratio=data["payout"], current_price=data["price"]
            )
            results.append(res)
            
        st.session_state["df_v12"] = pd.DataFrame(results)
        st.success("✅ 分析完成！")

# ==========================================
# 4. 圖表與報表呈現
# ==========================================
if "df_v12" in st.session_state:
    df = st.session_state["df_v12"]
    
    st.divider()
    st.subheader("📈 個股營收軌跡對比 (去年度實際 vs 今年度預估)")
    
    sorted_stock_list = sorted(df["股票名稱"].tolist())
    selected_stock = st.selectbox("📌 請選擇要查看的個股：", sorted_stock_list)
    
    stock_row = df[df["股票名稱"] == selected_stock].iloc[0]
    chart_data = pd.DataFrame({
        "去年度實際營收(億)": stock_row["_ly_qs"],
        "今年度模型預估(億)": stock_row["_est_qs"]
    }, index=["Q1", "Q2", "Q3", "Q4"])
    
    st.line_chart(chart_data)

    st.markdown(f"**【{selected_stock}】核心指標：** 預估全年度 EPS **{stock_row['預估今年度_EPS']} 元** ｜ 本益比 **{stock_row['本益比(PER)']} 倍** ｜ 前瞻殖利率 **{stock_row['前瞻殖利率(%)']}%**")
    
    st.divider()
    st.subheader("🧮 2026 戰略預估數據總表")
    
    display_df = df.drop(columns=["_est_qs", "_ly_qs"])
    
    def highlight_yield(val):
        color = '#ff4b4b' if isinstance(val, (int, float)) and val >= 4.0 else ''
        weight = 'bold' if isinstance(val, (int, float)) and val >= 4.0 else 'normal'
        return f'color: {color}; font-weight: {weight}'
    
    format_dict = {
        "當季預估均營收": "{:.2f}", "季成長率(YoY)%": "{:.2f}%", 
        "預估今年Q1_EPS": "{:.2f}", "預估今年度_EPS": "{:.2f}", 
        "本益比(PER)": "{:.2f}", "運算配息率(%)": "{:.2f}%", "前瞻殖利率(%)": "{:.2f}%"
    }

    st.dataframe(display_df.style.map(highlight_yield, subset=['前瞻殖利率(%)']).format(format_dict), use_container_width=True)
