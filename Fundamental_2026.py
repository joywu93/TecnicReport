import streamlit as st
import pandas as pd
import re
from datetime import datetime
import yfinance as yf

# ==========================================
# 網頁基本設定
# ==========================================
st.set_page_config(page_title="2026 股市戰略指揮中心", layout="wide")
st.title("📊 股市戰略指揮中心 (V14 終極防護裝甲版)")
st.markdown("💡 **新增資料透視鏡：** 上傳檔案後，系統會先讓您「預覽」抓到的基礎數據，確保 100% 能成功執行！")

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
        "股票名稱": name, "最新股價": current_price, "套用公式": formula_note,
        "當季預估均營收": round(est_q1_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "預估今年Q1_EPS": round(est_q1_eps, 2), "預估今年度_EPS": round(est_full_year_eps, 2), 
        "本益比(PER)": round(est_per, 2), "前瞻殖利率(%)": round(forward_yield, 2), "運算配息率(%)": calc_payout_ratio,
        "_est_qs": [est_q1_rev_total, est_q2_rev_total, est_q3_rev_total, est_q4_rev_total],
        "_ly_qs": [ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev]
    }

# ==========================================
# 2. 側邊欄：檔案上傳與設定
# ==========================================
st.sidebar.header("📥 資料庫匯入區")
uploaded_file = st.sidebar.file_uploader("上傳財報 CSV/Excel", type=["xlsx", "csv"])

st.sidebar.divider()
st.sidebar.header("⚙️ 系統參數設定")
simulated_month = st.sidebar.slider("目前月份", 1, 12, 2)
use_yahoo_price = st.sidebar.checkbox("🌐 連線 Yahoo 抓取即時股價 (不勾選則用表單股價瞬間完成)", value=False)

# ==========================================
# 3. 萬能資料解析引擎
# ==========================================
if uploaded_file is not None:
    try:
        uploaded_file.seek(0)
        file_name = uploaded_file.name.lower()
        
        # 💡 萬能解碼器：使用 python engine 自動判斷分隔符號
        if file_name.endswith('.xlsx'):
            df_upload = pd.read_excel(uploaded_file)
        else:
            try: df_upload = pd.read_csv(uploaded_file, encoding='utf-8-sig', sep=None, engine='python')
            except: 
                uploaded_file.seek(0)
                df_upload = pd.read_csv(uploaded_file, encoding='cp950', sep=None, engine='python')
                
        cols = df_upload.columns.tolist()
        
        def find_col(pattern):
            for c in reversed(cols):
                if re.search(pattern, c): return c
            return None
            
        c_code = find_col(r'代號')
        c_name = find_col(r'名稱')
        
        # 💡 防呆檢查：如果連「代號」都找不到，把所有欄位印出來方便除錯
        if not c_code:
            st.error(f"❌ 解析失敗：找不到「代號」欄位！請確認檔案內容。系統讀取到的前 10 個欄位為：{cols[:10]}")
            st.stop()

        c_price = find_col(r'成交')
        c_rev_10, c_rev_11, c_rev_12 = find_col(r'10單月營收'), find_col(r'11單月營收'), find_col(r'12單月營收')
        c_rev_1, c_rev_2, c_rev_3 = find_col(r'(01|1)單月營收'), find_col(r'(02|2)單月營收'), find_col(r'(03|3)單月營收')
        c_ly_q1, c_ly_q2, c_ly_q3, c_ly_q4 = find_col(r'Q1.*單季營收'), find_col(r'Q2.*單季營收'), find_col(r'Q3.*單季營收'), find_col(r'Q4.*單季營收')
        c_eps_q3, c_eps_q4 = find_col(r'Q3.*每股盈餘'), find_col(r'Q4.*每股盈餘')
        c_non_op, c_payout = find_col(r'業外損益'), find_col(r'盈餘總分配率')

        stock_db = {}
        for idx, row in df_upload.iterrows():
            code = str(row[c_code]).split('.')[0].strip() if pd.notna(row[c_code]) else ""
            if len(code) < 3: continue # 濾除無效空行
            
            def get_val(col_name, default=0.0):
                if col_name and pd.notna(row[col_name]):
                    try: 
                        val_str = str(row[col_name]).replace(',', '').replace(';', '').replace(' ', '').strip()
                        if val_str in ['-', '']: return default
                        return float(val_str)
                    except: return default
                return default
            
            eps_q4, eps_q3 = get_val(c_eps_q4), get_val(c_eps_q3)
            rev_q4, rev_q3 = get_val(c_ly_q4), get_val(c_ly_q3)
            
            if rev_q4 == 0: rev_q4 = get_val(c_rev_10) + get_val(c_rev_11) + get_val(c_rev_12)
            if eps_q4 != 0 and rev_q4 != 0: base_eps, base_rev_avg = eps_q4, rev_q4 / 3
            else: base_eps, base_rev_avg = eps_q3, (rev_q3 / 3 if rev_q3 != 0 else 0)

            stock_db[code] = {
                "name": str(row[c_name]) if c_name else "未知",
                "rev_last_11": get_val(c_rev_11), "rev_last_12": get_val(c_rev_12),
                "rev_this_1": get_val(c_rev_1), "rev_this_2": get_val(c_rev_2), "rev_this_3": get_val(c_rev_3),
                "base_q_eps": base_eps, "non_op": get_val(c_non_op), "base_q_avg_rev": base_rev_avg,
                "ly_q1_rev": get_val(c_ly_q1), "ly_q2_rev": get_val(c_ly_q2),
                "ly_q3_rev": get_val(c_ly_q3), "ly_q4_rev": rev_q4,
                "payout": get_val(c_payout), "price": get_val(c_price)
            }
        
        # 💡 將解析成功的資料鎖入記憶體 (防止按鈕失憶)
        st.session_state["stock_db"] = stock_db
        
        # 💡 資料透視鏡：顯示前 3 筆抓到的資料讓使用者安心
        st.success(f"✅ 檔案讀取成功！成功抓取 {len(stock_db)} 檔股票。 (以下為前 3 筆資料預覽)")
        preview_data = []
        for i, (k, v) in enumerate(stock_db.items()):
            if i >= 3: break
            preview_data.append({"股票代號": k, "名稱": v['name'], "基礎EPS": v['base_q_eps'], "基準均營收": round(v['base_q_avg_rev'], 2)})
        st.dataframe(pd.DataFrame(preview_data), use_container_width=True)

    except Exception as e:
        st.error(f"檔案解析發生嚴重錯誤：{e}")

if "stock_db" not in st.session_state or not st.session_state["stock_db"]:
    st.info("請從左側上傳您的 CSV/Excel 檔案。")

# ==========================================
# 4. 執行運算區塊
# ==========================================
if "stock_db" in st.session_state and st.session_state["stock_db"]:
    if st.button(f"🚀 開始執行 {simulated_month} 月份戰略分析", type="primary"):
        with st.spinner("正在執行 VBA 核心運算，請稍候..."):
            results = []
            db = st.session_state["stock_db"]
            progress_bar = st.progress(0)
            
            for i, (code, data) in enumerate(db.items()):
                progress_bar.progress((i + 1) / len(db))
                
                if use_yahoo_price:
                    try: live_price = yf.Ticker(f"{code}.TW").history(period="1d")['Close'].iloc[-1]
                    except: 
                        try: live_price = yf.Ticker(f"{code}.TWO").history(period="1d")['Close'].iloc[-1]
                        except: live_price = data["price"] if data["price"] > 0 else 100
                else:
                    live_price = data["price"] if data["price"] > 0 else 100
                
                res = auto_strategic_model(
                    name=f"{code} {data['name']}", current_month=simulated_month,
                    rev_last_11=data["rev_last_11"], rev_last_12=data["rev_last_12"], 
                    rev_this_1=data["rev_this_1"], rev_this_2=data["rev_this_2"], rev_this_3=data["rev_this_3"],
                    base_q_eps=data["base_q_eps"], non_op_ratio=data["non_op"], base_q_avg_rev=data["base_q_avg_rev"],
                    ly_q1_rev=data["ly_q1_rev"], ly_q2_rev=data["ly_q2_rev"], ly_q3_rev=data["ly_q3_rev"], ly_q4_rev=data["ly_q4_rev"],
                    recent_payout_ratio=data["payout"], current_price=live_price
                )
                results.append(res)
                
            st.session_state["df_final"] = pd.DataFrame(results)
            progress_bar.empty()
            st.success("✅ 分析完成！請滾動至下方查看總表。")

# ==========================================
# 5. 圖表與報表呈現
# ==========================================
if "df_final" in st.session_state:
    df = st.session_state["df_final"]
    
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
        "最新股價": "{:.2f}", "當季預估均營收": "{:.2f}", "季成長率(YoY)%": "{:.2f}%", 
        "預估今年Q1_EPS": "{:.2f}", "預估今年度_EPS": "{:.2f}", 
        "本益比(PER)": "{:.2f}", "運算配息率(%)": "{:.2f}%", "前瞻殖利率(%)": "{:.2f}%"
    }
    st.dataframe(display_df.style.map(highlight_yield, subset=['前瞻殖利率(%)']).format(format_dict), use_container_width=True)
