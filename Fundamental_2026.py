import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from io import StringIO
from datetime import datetime

# ==========================================
# 網頁基本設定
# ==========================================
st.set_page_config(page_title="2026 基本面預估中心", layout="wide")
st.title("📊 股市戰略指揮中心 (常青樹傳承版)")
st.markdown("💡 **系統已導入 VBA 核心邏輯：** 自動偵測當前月份，套用對應的營收預估與 EPS 疊加公式。")

# ==========================================
# 0. 爬蟲模組 (加入防阻擋提示)
# ==========================================
def fetch_mops_contract_liability(stock_id, year_roc=114, season=3):
    url = "https://mops.twse.com.tw/mops/web/ajax_t164sb03"
    payload = {
        "encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1",
        "TYPEK": "all", "queryName": "co_id", "inpuType": "co_id", "isnew": "false",
        "co_id": str(stock_id), "year": str(year_roc), "season": str(season)
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://mops.twse.com.tw/mops/web/t164sb03"
    }
    try:
        res = requests.post(url, data=payload, headers=headers, timeout=5)
        res.encoding = 'utf-8'
        dfs = pd.read_html(StringIO(res.text))
        for df in dfs:
            if df.empty: continue
            df_str = df.astype(str)
            mask = df_str.apply(lambda x: x.str.contains('合約負債', na=False))
            if mask.any().any():
                row_idx = mask.any(axis=1).idxmax()
                raw_value = df.iloc[row_idx, 1] 
                if pd.notna(raw_value) and str(raw_value).replace('.','',1).isdigit():
                    return float(raw_value) / 100000  # 轉億元
        return "無資料"
    except:
        return "API阻擋" # 雲端主機被擋時的防呆提示

# ==========================================
# 1. 核心大腦：完全復刻您的 VBA 疊加邏輯
# ==========================================
def auto_strategic_model(
    name, rev_last_11, rev_last_12, rev_this_1, rev_this_2, # 用於預估Q1
    rev_ly_q1, rev_ly_q2, rev_ly_q3, rev_ly_q4,             # 去年各季營收
    eps_ly_q4, non_op_ratio,                                # 去年Q4 EPS 與 業外佔比
    recent_payout_ratio, current_price
):
    current_month = datetime.now().month

    # 1. 自動判斷月份，預估當年 Q1 均值
    if current_month == 1:
        est_q1_avg = (rev_last_11 + rev_last_12) / 2
    elif current_month == 2:
        est_q1_avg = rev_this_1 * 0.9  # 簡化春節邏輯
    elif current_month == 3:
        est_q1_avg = (rev_this_1 + rev_this_2) / 2
    else:
        # 4月以後 Q1 已成定局，可直接用實際值，此處先以常態估算代替
        est_q1_avg = (rev_this_1 + rev_this_2) / 2 

    # 2. 忠實還原 Excel 公式：估今年度 Q1 EPS
    est_q1_rev_total = est_q1_avg * 3
    ly_q4_rev_total = rev_ly_q4
    
    # 估今年度Q1EPS = 近期季EPS × (1-業外佔比%) × (當年Q1營收 / 去年度Q4營收)
    est_q1_eps = eps_ly_q4 * (1 - (non_op_ratio / 100)) * (est_q1_rev_total / ly_q4_rev_total) if ly_q4_rev_total > 0 else 0

    # 3. 忠實還原 Excel 公式：估今年度每股盈餘 (EPS)
    ly_h1_rev = rev_ly_q1 + rev_ly_q2
    ly_h2_rev = rev_ly_q3 + rev_ly_q4
    
    # (Q1EPS + Q1EPS × 去年Q2營收/去年Q1營收)
    q2_growth_ratio = rev_ly_q2 / rev_ly_q1 if rev_ly_q1 > 0 else 1
    est_h1_eps = est_q1_eps + (est_q1_eps * q2_growth_ratio)
    
    # × (1 + 估去年下半度營收值/去年上半年營收值)
    h2_h1_ratio = ly_h2_rev / ly_h1_rev if ly_h1_rev > 0 else 1
    est_full_year_eps = est_h1_eps * (1 + h2_h1_ratio)

    # 4. 防呆配息與前瞻殖利率
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    forward_yield = (est_full_year_eps * (calc_payout_ratio / 100)) / current_price * 100 if current_price > 0 else 0

    return {
        "股票名稱": name,
        "最新股價": current_price,
        "預估今年Q1_EPS(元)": round(est_q1_eps, 2),
        "預估今年度EPS(元)": round(est_full_year_eps, 2),
        "運算配息率(%)": calc_payout_ratio,
        "前瞻殖利率(%)": round(forward_yield, 2)
    }

# ==========================================
# 2. 歷史資料庫 (晚輩未來只需更新此處的歷史財報)
# ==========================================
stock_db = {
    # 欄位對應：11月營收, 12月營收, 1月營收, 2月營收, 去年Q1~Q4營收, 去年Q4 EPS, 業外佔比(%)
    "2404": {"name": "漢唐", "rev_last_11": 50, "rev_last_12": 55, "rev_this_1": 60, "rev_this_2": 58, 
             "ly_q1": 150, "ly_q2": 160, "ly_q3": 155, "ly_q4": 170, 
             "eps_ly_q4": 6.5, "non_op": 5.0, "payout": 80, "note": "台積電建廠進度指標。"},
             
    "1522": {"name": "堤維西", "rev_last_11": 22, "rev_last_12": 23.1, "rev_this_1": 25, "rev_this_2": 20, 
             "ly_q1": 50, "ly_q2": 52, "ly_q3": 55, "ly_q4": 60, 
             "eps_ly_q4": 1.17, "non_op": -21.9, "payout": 63.0, "note": "AM車燈旺季，留意匯兌。"},

    "6613": {"name": "朋億*", "rev_last_11": 8.5, "rev_last_12": 9.0, "rev_this_1": 8.0, "rev_this_2": 8.2, 
             "ly_q1": 22, "ly_q2": 24, "ly_q3": 28, "ly_q4": 30, 
             "eps_ly_q4": 3.5, "non_op": 2.0, "payout": 65, "note": "半導體廠務設備。"}
}

# ==========================================
# 3. 執行分析與網頁顯示
# ==========================================
current_m = datetime.now().month
st.info(f"📅 **系統自動偵測：** 目前為 {current_m} 月，已自動切換對應之預估模型。")

if st.button("🚀 開始連線：執行跨年度全自動分析", type="primary"):
    with st.spinner("正在連線抓取即時股價與 MOPS 數據..."):
        results = []
        for code, data in stock_db.items():
            # 自動抓最新股價
            try:
                live_price = yf.Ticker(f"{code}.TW").history(period="1d")['Close'].iloc[-1]
            except:
                try: live_price = yf.Ticker(f"{code}.TWO").history(period="1d")['Close'].iloc[-1]
                except: live_price = 100 
            
            # 執行 VBA 疊加核心邏輯
            res = auto_strategic_model(
                name=f"{code} {data['name']}",
                rev_last_11=data["rev_last_11"], rev_last_12=data["rev_last_12"], 
                rev_this_1=data["rev_this_1"], rev_this_2=data["rev_this_2"],
                rev_ly_q1=data["ly_q1"], rev_ly_q2=data["ly_q2"], rev_ly_q3=data["ly_q3"], rev_ly_q4=data["ly_q4"],
                eps_ly_q4=data["eps_ly_q4"], non_op_ratio=data["non_op"], 
                recent_payout_ratio=data["payout"], current_price=live_price
            )
            
            # 去 MOPS 抓合約負債 (加入防阻擋機制)
            res["流動合約負債(億)"] = fetch_mops_contract_liability(code, year_roc=114, season=3)
            res["個股觀察筆記"] = data["note"]
            
            results.append(res)
            
        df_results = pd.DataFrame(results)
        st.success("✅ 分析完成！")

        def highlight_yield(val):
            color = '#ff4b4b' if isinstance(val, (int, float)) and val >= 4.0 else ''
            weight = 'bold' if isinstance(val, (int, float)) and val >= 4.0 else 'normal'
            return f'color: {color}; font-weight: {weight}'
        
        # 動態格式化 (因為合約負債可能是文字 "API阻擋")
        format_dict = {"最新股價": "{:.2f}", "預估今年Q1_EPS(元)": "{:.2f}", "預估今年度EPS(元)": "{:.2f}", 
                       "運算配息率(%)": "{:.2f}%", "前瞻殖利率(%)": "{:.2f}%"}

        st.dataframe(
            df_results.style.map(highlight_yield, subset=['前瞻殖利率(%)']).format(format_dict),
            use_container_width=True
        )
