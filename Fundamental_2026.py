import streamlit as st
import pandas as pd
import io
import altair as alt

# ==========================================
# 網頁基本設定
# ==========================================
st.set_page_config(page_title="2026 股市戰略指揮中心", layout="wide")
st.title("📊 股市戰略指揮中心 (V23 並列柱狀圖滿配版)")
st.markdown("💡 **圖表大升級：** 季營收改採「3 根柱子並列」呈現，並新增「預估年成長率」核心指標！")

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
        known_q1 = 0
    elif current_month == 2:
        est_q1_avg = rev_this_1 * 0.9  
        formula_note = "採當年1月營收×0.9"
        known_q1 = rev_this_1
    elif current_month == 3:
        est_q1_avg = (rev_this_1 + rev_this_2) / 2
        formula_note = "採當年1、2月均值"
        known_q1 = rev_this_1 + rev_this_2
    else:
        est_q1_avg = (rev_this_1 + rev_this_2 + rev_this_3) / 3
        formula_note = "採當年Q1實際均值"
        known_q1 = rev_this_1 + rev_this_2 + rev_this_3

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

    # 計算預估年成長率 (YoY)
    ly_total_rev = ly_q1_rev + ly_q2_rev + ly_q3_rev + ly_q4_rev
    est_total_rev = est_q1_rev_total + est_q2_rev_total + est_q3_rev_total + est_q4_rev_total
    est_annual_yoy = ((est_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0

    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    forward_yield = (est_full_year_eps * (calc_payout_ratio / 100)) / current_price * 100 if current_price > 0 else 0

    # 計算純預估值 (總預估 扣除 已公布)
    pure_est_q1 = max(0, est_q1_rev_total - known_q1)

    return {
        "股票名稱": name, "最新股價": current_price, "套用公式": formula_note,
        "當季預估均營收": round(est_q1_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "預估今年Q1_EPS": round(est_q1_eps, 2), "預估今年度_EPS": round(est_full_year_eps, 2), 
        "預估年成長率(%)": round(est_annual_yoy, 2), # 💡 新增的年成長率指標
        "本益比(PER)": round(est_per, 2), "前瞻殖利率(%)": round(forward_yield, 2), "運算配息率(%)": calc_payout_ratio,
        "_ly_qs": [ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev],
        "_known_qs": [known_q1, 0, 0, 0],
        "_pure_est_qs": [pure_est_q1, est_q2_rev_total, est_q3_rev_total, est_q4_rev_total]
    }

# ==========================================
# 2. 側邊欄：檔案上傳與設定
# ==========================================
st.sidebar.header("📥 資料庫匯入區")
uploaded_file = st.sidebar.file_uploader("上傳 個股營收表 (僅限 CSV)", type=["csv"])

st.sidebar.divider()
st.sidebar.header("⚙️ 系統參數設定")
simulated_month = st.sidebar.slider("目前月份", 1, 12, 2)

# ==========================================
# 3. CSV 專屬直連解析引擎
# ==========================================
if uploaded_file is not None:
    try:
        raw_bytes = uploaded_file.read()
        try: df_upload = pd.read_csv(io.StringIO(raw_bytes.decode('cp950')))
        except: df_upload = pd.read_csv(io.StringIO(raw_bytes.decode('utf-8-sig', errors='ignore')))
                
        cols = df_upload.columns.tolist()
        
        def get_col(kw1, kw2=""):
            for c in reversed(cols):
                if kw1 in c and kw2 in c: return c
            return None
            
        c_code, c_name, c_price = get_col("代號"), get_col("名稱"), get_col("成交")
        c_rev_last_11, c_rev_last_12 = get_col("11單月營收"), get_col("12單月營收")
        c_rev_this_1, c_rev_this_2, c_rev_this_3 = get_col("01單月營收"), get_col("02單月營收"), get_col("03單月營收")
        
        c_ly_q1, c_ly_q2 = get_col("Q1", "營收"), get_col("Q2", "營收")
        c_ly_q3, c_ly_q4 = get_col("Q3", "營收"), get_col("Q4", "營收") 
        c_eps_q3, c_eps_q4 = get_col("Q3", "盈餘"), get_col("Q4", "盈餘")
        
        c_rev_10 = get_col("10單月營收")
        c_non_op, c_payout = get_col("業外損益"), get_col("分配率")

        stock_db = {}
        for idx, row in df_upload.iterrows():
            code = str(row[c_code]).split('.')[0].strip() if c_code and pd.notna(row[c_code]) else ""
            if len(code) < 3: continue 
            
            def get_val(col_name, default=0.0):
                if col_name and pd.notna(row[col_name]):
                    try: 
                        val_str = str(row[col_name]).replace(',', '').replace(' ', '').strip()
                        if val_str in ['-', '']: return default
                        return float(val_str)
                    except: return default
                return default
            
            rev_q1, rev_q2, rev_q3 = get_val(c_ly_q1), get_val(c_ly_q2), get_val(c_ly_q3)
            rev_q4 = get_val(c_ly_q4)
            eps_q3, eps_q4 = get_val(c_eps_q3), get_val(c_eps_q4)
            
            if rev_q4 == 0: rev_q4 = get_val(c_rev_10) + get_val(c_rev_last_11) + get_val(c_rev_last_12)
            if eps_q4 != 0: base_eps = eps_q4
            else: base_eps = eps_q3 * (rev_q4 / rev_q3) if rev_q3 > 0 else eps_q3

            base_rev_avg = rev_q4 / 3 if rev_q4 > 0 else 0

            stock_db[code] = {
                "name": str(row[c_name]) if c_name else "未知",
                "rev_last_11": get_val(c_rev_last_11), "rev_last_12": get_val(c_rev_last_12),
                "rev_this_1": get_val(c_rev_this_1), "rev_this_2": get_val(c_rev_this_2), "rev_this_3": get_val(c_rev_this_3),
                "base_q_eps": base_eps, "non_op": get_val(c_non_op), "base_q_avg_rev": base_rev_avg,
                "ly_q1_rev": rev_q1, "ly_q2_rev": rev_q2, "ly_q3_rev": rev_q3, "ly_q4_rev": rev_q4,
                "payout": get_val(c_payout), "price": get_val(c_price)
            }
        
        st.session_state["stock_db_v23"] = stock_db
        st.success(f"✅ CSV 檔案讀取大成功！已抓取 {len(stock_db)} 檔股票。請點擊下方按鈕執行運算。")

    except Exception as e:
        st.error(f"檔案解析發生錯誤：{e}")

# ==========================================
# 4. 執行運算與報表呈現
# ==========================================
if "stock_db_v23" in st.session_state:
    if st.button(f"🚀 開始執行 {simulated_month} 月份戰略分析", type="primary"):
        with st.spinner("正在執行 VBA 核心運算，請稍候..."):
            results = []
            for code, data in st.session_state["stock_db_v23"].items():
                res = auto_strategic_model(
                    name=f"{code} {data['name']}", current_month=simulated_month,
                    rev_last_11=data["rev_last_11"], rev_last_12=data["rev_last_12"], 
                    rev_this_1=data["rev_this_1"], rev_this_2=data["rev_this_2"], rev_this_3=data["rev_this_3"],
                    base_q_eps=data["base_q_eps"], non_op_ratio=data["non_op"], base_q_avg_rev=data["base_q_avg_rev"],
                    ly_q1_rev=data["ly_q1_rev"], ly_q2_rev=data["ly_q2_rev"], ly_q3_rev=data["ly_q3_rev"], ly_q4_rev=data["ly_q4_rev"],
                    recent_payout_ratio=data["payout"], current_price=data["price"]
                )
                results.append(res)
            st.session_state["df_final_v23"] = pd.DataFrame(results)
            st.success("✅ 分析完成！")

if "df_final_v23" in st.session_state:
    df = st.session_state["df_final_v23"]
    
    st.divider()
    st.subheader("📊 季營收動能對比 (同期並列柱狀圖)")
    selected_stock = st.selectbox("📌 請選擇要查看的個股：", sorted(df["股票名稱"].tolist()))
    stock_row = df[df["股票名稱"] == selected_stock].iloc[0]
    
    # 💡 視覺大變身：利用 Altair 產生 3 根柱子並排的群組長條圖
    chart_data = pd.DataFrame({
        "季度": ["Q1", "Q2", "Q3", "Q4"],
        "1.去年實際(億)": stock_row["_ly_qs"],
        "2.今年已公布(億)": stock_row["_known_qs"],
        "3.今年純預估(億)": stock_row["_pure_est_qs"]
    })
    # 資料轉換以符合 Altair 格式
    chart_data_melt = chart_data.melt(id_vars="季度", var_name="營收類別", value_name="營收(億)")
    
    bars = alt.Chart(chart_data_melt).mark_bar().encode(
        x=alt.X('營收類別:N', title=None, axis=alt.Axis(labels=False, ticks=False)), # 隱藏底下的副標籤
        y=alt.Y('營收(億):Q', title='營收(億)'),
        color=alt.Color('營收類別:N', legend=alt.Legend(title="指標圖例", orient="bottom")),
        column=alt.Column('季度:N', header=alt.Header(title=None, labelOrient='bottom'))
    ).properties(width=150, height=350)
    
    st.altair_chart(bars, use_container_width=False)
    
    # 💡 新增「預估年成長率(%)」於核心指標
    st.markdown(f"**【{selected_stock}】核心指標：** 預估全年度 EPS **{stock_row['預估今年度_EPS']} 元** ｜ 本益比 **{stock_row['本益比(PER)']} 倍** ｜ 前瞻殖利率 **{stock_row['前瞻殖利率(%)']}%** ｜ 預估年成長率 **{stock_row['預估年成長率(%)']}%**")
    
    st.divider()
    st.subheader("🧮 2026 戰略預估數據總表 (左側名稱與股價已凍結)")
    display_df = df.drop(columns=["_ly_qs", "_known_qs", "_pure_est_qs"])
    
    # 凍結欄位
    display_df = display_df.set_index(["股票名稱", "最新股價"])
    
    def highlight_yield(val):
        color = '#ff4b4b' if isinstance(val, (int, float)) and val >= 4.0 else ''
        return f'color: {color}; font-weight: {"bold" if color else "normal"}'
    
    format_dict = {"當季預估均營收": "{:.2f}", "季成長率(YoY)%": "{:.2f}%", "預估今年Q1_EPS": "{:.2f}", "預估今年度_EPS": "{:.2f}", "預估年成長率(%)": "{:.2f}%", "本益比(PER)": "{:.2f}", "運算配息率(%)": "{:.2f}%", "前瞻殖利率(%)": "{:.2f}%"}
    st.dataframe(display_df.style.map(highlight_yield, subset=['前瞻殖利率(%)']).format(format_dict), use_container_width=True)
