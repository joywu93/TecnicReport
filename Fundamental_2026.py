import streamlit as st
import pandas as pd
import io
import altair as alt
import re

# ==========================================
# 網頁基本設定與深層 CSS 卷軸魔法
# ==========================================
st.set_page_config(page_title="2026 股市戰略指揮中心", layout="wide")

st.markdown("""
    <style>
    /* 強制放大全網頁與表格底層卷軸 */
    ::-webkit-scrollbar { width: 20px !important; height: 20px !important; }
    ::-webkit-scrollbar-track { background: #e0e0e0; border-radius: 10px; }
    ::-webkit-scrollbar-thumb { background: #888; border-radius: 10px; border: 3px solid #e0e0e0; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }
    
    /* 針對 Streamlit 內部容器強制套用 */
    div[data-testid="stDataFrame"] div {
        scrollbar-width: auto;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 股市戰略指揮中心 (V26 雙年均值大師版)")
st.markdown("💡 **核心邏輯全面升級：** 導入「Q2=Q1保守法則」與「近2年 H2/H1 均值比例」推算全年業績！")

# ==========================================
# 1. 核心大腦：完美復刻 VBA (導入雙年均值法)
# ==========================================
def auto_strategic_model(
    name, current_month,
    rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, 
    base_q_eps, non_op_ratio, base_q_avg_rev,                     
    ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev,                   
    y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, # 💡 新增前年(2024)的四個季度
    recent_payout_ratio, current_price
):
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

    # 💡 步驟 1：Q1 預估
    est_q1_rev_total = est_q1_avg * 3
    q1_yoy = ((est_q1_rev_total - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0
    est_q1_eps = base_q_eps * (1 - (non_op_ratio / 100)) * (est_q1_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0

    # 💡 步驟 2：您指定的最強邏輯 -> 預設 Q2 = Q1
    est_q2_rev_total = est_q1_rev_total
    est_q2_eps = est_q1_eps
    
    est_h1_rev_total = est_q1_rev_total + est_q2_rev_total
    est_h1_eps = est_q1_eps + est_q2_eps

    # 💡 步驟 3：計算近 2 年的 H1 與 H2 均值
    y1_h1 = y1_q1_rev + y1_q2_rev
    y1_h2 = y1_q3_rev + y1_q4_rev
    y2_h1 = ly_q1_rev + ly_q2_rev
    y2_h2 = ly_q3_rev + ly_q4_rev
    
    avg_2yr_h1 = (y1_h1 + y2_h1) / 2
    avg_2yr_h2 = (y1_h2 + y2_h2) / 2

    # 💡 步驟 4：用 2 年均值比例推算全年
    if avg_2yr_h1 > 0:
        multiplier = 1 + (avg_2yr_h2 / avg_2yr_h1)
        est_total_rev = est_h1_rev_total * multiplier
        est_full_year_eps = est_h1_eps * multiplier
        
        # 為了畫長條圖，將下半年營收分配給 Q3 和 Q4 (依照去年比例拆分)
        est_h2_rev_total = est_total_rev - est_h1_rev_total
        est_q3_rev_total = est_h2_rev_total * (ly_q3_rev / y2_h2) if y2_h2 > 0 else est_h2_rev_total / 2
        est_q4_rev_total = est_h2_rev_total * (ly_q4_rev / y2_h2) if y2_h2 > 0 else est_h2_rev_total / 2
    else:
        est_total_rev = est_h1_rev_total
        est_full_year_eps = est_h1_eps
        est_q3_rev_total = est_q4_rev_total = 0

    # 計算預估年成長率 (YoY)
    ly_total_rev = y2_h1 + y2_h2
    est_annual_yoy = ((est_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0

    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    forward_yield = (est_full_year_eps * (calc_payout_ratio / 100)) / current_price * 100 if current_price > 0 else 0

    pure_est_q1 = max(0, est_q1_rev_total - known_q1)

    return {
        "股票名稱": name, "最新股價": current_price, "套用公式": formula_note,
        "當季預估均營收": round(est_q1_avg, 2), 
        "季成長率(YoY)%": round(q1_yoy, 2),
        "前瞻殖利率(%)": round(forward_yield, 2), 
        "預估今年Q1_EPS": round(est_q1_eps, 2), 
        "預估今年度_EPS": round(est_full_year_eps, 2), 
        "本益比(PER)": round(est_per, 2),         
        "預估年成長率(%)": round(est_annual_yoy, 2), 
        "運算配息率(%)": calc_payout_ratio,
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

st.sidebar.divider()
st.sidebar.header("📌 核心關注名單 (VIP置頂)")
watch_list_input = st.sidebar.text_input("輸入代號 (支援空白、逗號、分號)", value="8358; 8383 8390")

# ==========================================
# 3. CSV 解析引擎 (自動辨識 前年 與 去年)
# ==========================================
if uploaded_file is not None:
    try:
        raw_bytes = uploaded_file.read()
        try: df_upload = pd.read_csv(io.StringIO(raw_bytes.decode('cp950')))
        except: df_upload = pd.read_csv(io.StringIO(raw_bytes.decode('utf-8-sig', errors='ignore')))
                
        cols = df_upload.columns.tolist()
        
        # 💡 自動找尋最新年份(去年)與前年
        q_cols = [c for c in cols if re.search(r'(\d{2})Q', c)]
        ly = max([re.search(r'(\d{2})Q', c).group(1) for c in q_cols]) if q_cols else "25"
        y1 = str(int(ly) - 1) # 推算前年 (例如 24)

        def get_col(kw1, kw2=""):
            for c in reversed(cols):
                if kw1 in c and kw2 in c: return c
            return None
            
        c_code, c_name, c_price = get_col("代號"), get_col("名稱"), get_col("成交")
        c_rev_last_11, c_rev_last_12 = get_col("11單月營收"), get_col("12單月營收")
        c_rev_this_1, c_rev_this_2, c_rev_this_3 = get_col("01單月營收"), get_col("02單月營收"), get_col("03單月營收")
        
        # 抓取去年(ly)
        c_ly_q1, c_ly_q2 = get_col(f"{ly}Q1", "營收"), get_col(f"{ly}Q2", "營收")
        c_ly_q3, c_ly_q4 = get_col(f"{ly}Q3", "營收"), get_col(f"{ly}Q4", "營收") 
        c_eps_q3, c_eps_q4 = get_col(f"{ly}Q3", "盈餘"), get_col(f"{ly}Q4", "盈餘")
        
        # 抓取前年(y1) 供2年均值使用
        c_y1_q1, c_y1_q2 = get_col(f"{y1}Q1", "營收"), get_col(f"{y1}Q2", "營收")
        c_y1_q3, c_y1_q4 = get_col(f"{y1}Q3", "營收"), get_col(f"{y1}Q4", "營收")
        
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
            
            # 去年營收
            rev_q1, rev_q2, rev_q3 = get_val(c_ly_q1), get_val(c_ly_q2), get_val(c_ly_q3)
            rev_q4 = get_val(c_ly_q4)
            if rev_q4 == 0: rev_q4 = get_val(c_rev_10) + get_val(c_rev_last_11) + get_val(c_rev_last_12)
            
            # 前年營收
            y1_r_q1, y1_r_q2 = get_val(c_y1_q1), get_val(c_y1_q2)
            y1_r_q3, y1_r_q4 = get_val(c_y1_q3), get_val(c_y1_q4)

            eps_q3, eps_q4 = get_val(c_eps_q3), get_val(c_eps_q4)
            if eps_q4 != 0: base_eps = eps_q4
            else: base_eps = eps_q3 * (rev_q4 / rev_q3) if rev_q3 > 0 else eps_q3

            base_rev_avg = rev_q4 / 3 if rev_q4 > 0 else 0

            stock_db[code] = {
                "name": str(row[c_name]) if c_name else "未知",
                "rev_last_11": get_val(c_rev_last_11), "rev_last_12": get_val(c_rev_last_12),
                "rev_this_1": get_val(c_rev_this_1), "rev_this_2": get_val(c_rev_this_2), "rev_this_3": get_val(c_rev_this_3),
                "base_q_eps": base_eps, "non_op": get_val(c_non_op), "base_q_avg_rev": base_rev_avg,
                "ly_q1_rev": rev_q1, "ly_q2_rev": rev_q2, "ly_q3_rev": rev_q3, "ly_q4_rev": rev_q4,
                "y1_q1_rev": y1_r_q1, "y1_q2_rev": y1_r_q2, "y1_q3_rev": y1_r_q3, "y1_q4_rev": y1_r_q4, # 傳入前年數據
                "payout": get_val(c_payout), "price": get_val(c_price)
            }
        
        st.session_state["stock_db_v26"] = stock_db
        st.success(f"✅ CSV 檔案讀取大成功！成功載入 {len(stock_db)} 檔股票之「近兩年度」財報。")

    except Exception as e:
        st.error(f"檔案解析發生錯誤：{e}")

# ==========================================
# 4. 執行運算與報表呈現
# ==========================================
if "stock_db_v26" in st.session_state:
    if st.button(f"🚀 開始執行 {simulated_month} 月份戰略分析", type="primary"):
        with st.spinner("大腦運算中 (套用 Q2=Q1 及 雙年均值法則)..."):
            results = []
            current_rule_note = ""
            for code, data in st.session_state["stock_db_v26"].items():
                res = auto_strategic_model(
                    name=f"{code} {data['name']}", current_month=simulated_month,
                    rev_last_11=data["rev_last_11"], rev_last_12=data["rev_last_12"], 
                    rev_this_1=data["rev_this_1"], rev_this_2=data["rev_this_2"], rev_this_3=data["rev_this_3"],
                    base_q_eps=data["base_q_eps"], non_op_ratio=data["non_op"], base_q_avg_rev=data["base_q_avg_rev"],
                    ly_q1_rev=data["ly_q1_rev"], ly_q2_rev=data["ly_q2_rev"], ly_q3_rev=data["ly_q3_rev"], ly_q4_rev=data["ly_q4_rev"],
                    y1_q1_rev=data["y1_q1_rev"], y1_q2_rev=data["y1_q2_rev"], y1_q3_rev=data["y1_q3_rev"], y1_q4_rev=data["y1_q4_rev"],
                    recent_payout_ratio=data["payout"], current_price=data["price"]
                )
                current_rule_note = res["套用公式"] 
                results.append(res)
            
            st.session_state["df_final_v26"] = pd.DataFrame(results)
            st.session_state["current_rule_note"] = current_rule_note
            st.success("✅ 運算完成！年成長率與季成長率已分離！")

if "df_final_v26" in st.session_state:
    df = st.session_state["df_final_v26"].copy()
    
    st.divider()
    st.subheader("📊 季營收動能對比 (同期並列柱狀圖)")
    
    selected_stock = st.selectbox("📌 請點擊此處並輸入代號或名稱：", sorted(df["股票名稱"].tolist()))
    stock_row = df[df["股票名稱"] == selected_stock].iloc[0]
    
    chart_data = pd.DataFrame({
        "季度": ["Q1", "Q2", "Q3", "Q4"],
        "1.去年實際(億)": stock_row["_ly_qs"],
        "2.今年已公布(億)": stock_row["_known_qs"],
        "3.今年純預估(億)": stock_row["_pure_est_qs"]
    })
    chart_data_melt = chart_data.melt(id_vars="季度", var_name="營收類別", value_name="營收(億)")
    
    bars = alt.Chart(chart_data_melt).mark_bar().encode(
        x=alt.X('營收類別:N', title=None, axis=alt.Axis(labels=False, ticks=False)),
        y=alt.Y('營收(億):Q', title='營收(億)'),
        color=alt.Color('營收類別:N', legend=alt.Legend(title="指標圖例", orient="bottom")),
        column=alt.Column('季度:N', header=alt.Header(title=None, labelOrient='bottom'))
    ).properties(width=150, height=350)
    
    st.altair_chart(bars, use_container_width=False)
    st.markdown(f"**【{selected_stock}】核心指標：** 預估全年度 EPS **{stock_row['預估今年度_EPS']} 元** ｜ 本益比 **{stock_row['本益比(PER)']} 倍** ｜ 前瞻殖利率 **{stock_row['前瞻殖利率(%)']}%** ｜ 預估年成長率 **{stock_row['預估年成長率(%)']}%**")
    
    st.divider()
    st.subheader("🧮 2026 戰略預估數據總表")
    
    st.info(f"⚙️ **當前預估邏輯：** {st.session_state['current_rule_note']}。Q2=Q1保守推算；下半年採用「近2年度 H2/H1均值比例」放大。")
    
    display_df = df.drop(columns=["_ly_qs", "_known_qs", "_pure_est_qs", "套用公式"])
    
    raw_list = re.split(r'[;,\s\t]+', watch_list_input)
    watch_list = list(dict.fromkeys([c.strip() for c in raw_list if c.strip()]))
    
    if watch_list:
        display_df['is_vip'] = display_df['股票名稱'].apply(lambda x: 1 if any(w in x for w in watch_list) else 0)
        display_df = display_df.sort_values(
            by=['is_vip', '季成長率(YoY)%', '前瞻殖利率(%)'], 
            ascending=[False, False, False]
        ).drop(columns=['is_vip'])
    else:
        display_df = display_df.sort_values(
            by=['季成長率(YoY)%', '前瞻殖利率(%)'], 
            ascending=[False, False]
        )
    
    cols_order = [
        "當季預估均營收", "季成長率(YoY)%", "前瞻殖利率(%)", 
        "預估今年Q1_EPS", "預估今年度_EPS", "本益比(PER)", 
        "預估年成長率(%)", "運算配息率(%)"
    ]
    display_df = display_df[["股票名稱", "最新股價"] + cols_order]
    
    display_df = display_df.set_index(["股票名稱", "最新股價"])
    
    def highlight_yield(val):
        color = '#ff4b4b' if isinstance(val, (int, float)) and val >= 4.0 else ''
        return f'color: {color}; font-weight: {"bold" if color else "normal"}'
    
    format_dict = {"當季預估均營收": "{:.2f}", "季成長率(YoY)%": "{:.2f}%", "前瞻殖利率(%)": "{:.2f}%", "預估今年Q1_EPS": "{:.2f}", "預估今年度_EPS": "{:.2f}", "本益比(PER)": "{:.2f}", "預估年成長率(%)": "{:.2f}%", "運算配息率(%)": "{:.2f}%"}
    st.dataframe(display_df.style.map(highlight_yield, subset=['前瞻殖利率(%)']).format(format_dict), use_container_width=True)
