# ==========================================
# 📂 檔案名稱： Fundamental_2026.py (V185 終極防爆版)
# 💡 更新內容： 修復圖表年份空集合報錯、盤後更新Bug、升級淡旺季預估引擎
# ==========================================

import streamlit as st
import pandas as pd
import altair as alt
import re
import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import urllib3
import time
import math
import yfinance as yf
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 網頁基本設定 & 響應式 CSS 
# ==========================================
st.set_page_config(page_title="2026 戰略指揮", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    h1 { font-size: 1.8rem !important; margin-bottom: 0px !important; }
    h2 { font-size: 1.4rem !important; margin-bottom: 0px !important; }
    h3 { font-size: 1.2rem !important; margin-bottom: 0.5rem !important; } 
    p { margin-bottom: 0.2rem !important; font-size: 0.95rem !important; }
    .block-container { padding-top: 2.5rem !important; padding-bottom: 1rem !important; }
    ::-webkit-scrollbar { width: 14px !important; height: 14px !important; }
    ::-webkit-scrollbar-track { background: #e0e0e0; border-radius: 6px; }
    ::-webkit-scrollbar-thumb { background: #888; border-radius: 6px; border: 2px solid #e0e0e0; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }
    div[data-testid="stDataFrame"] div { scrollbar-width: auto; }
    </style>
""", unsafe_allow_html=True)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

st.title("📊 2026 戰略指揮 (V185 終極防爆版)")

def force_rerun():
    try: st.rerun()
    except: st.experimental_rerun()

def clear_cache_and_session():
    st.cache_data.clear()
    for key in list(st.session_state.keys()):
        del st.session_state[key]

def get_gspread_client():
    if "google_key" not in st.secrets: raise ValueError("找不到 Google 金鑰")
    key_data = st.secrets["google_key"]
    creds = Credentials.from_service_account_info(json.loads(key_data) if isinstance(key_data, str) else dict(key_data), scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def get_realtime_price(code, default_price):
    try:
        p = yf.Ticker(f"{code}.TW").fast_info['last_price']
        if p > 0 and not math.isnan(p): return float(p)
    except: pass
    try:
        p = yf.Ticker(f"{code}.TWO").fast_info['last_price']
        if p > 0 and not math.isnan(p): return float(p)
    except: pass
    return default_price

# ==========================================
# 📊 核心大腦一：一般/成長股預估引擎 (升級版：納入淡旺季比例)
# ==========================================
def auto_strategic_model(name, current_month, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, base_q_eps, non_op_ratio, base_q_avg_rev, ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev, y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, recent_payout_ratio, current_price, contract_liab, contract_liab_qoq, acc_eps, declared_div):
    try:
        current_price = float(current_price)
        if math.isnan(current_price) or math.isinf(current_price): current_price = 0.0
    except: current_price = 0.0

    if current_month <= 1: sim_rev_1, sim_rev_2, sim_rev_3 = 0, 0, 0
    elif current_month == 2: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, 0, 0
    elif current_month == 3: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, 0
    else: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, rev_this_3

    actual_known_q1 = sum([v for v in [sim_rev_1, sim_rev_2, sim_rev_3] if v > 0])
    
    # --- 🌟 歷史淡旺季跳動比例計算 ---
    ratio_q1 = ly_q1_rev / y1_q4_rev if y1_q4_rev > 0 else 1.0
    sum_q2_history = y1_q2_rev + ly_q2_rev
    sum_q3_history = y1_q3_rev + ly_q3_rev
    sum_q4_history = y1_q4_rev + ly_q4_rev
    ratio_q3 = sum_q3_history / sum_q2_history if sum_q2_history > 0 else 1.0
    ratio_q4 = sum_q4_history / sum_q3_history if sum_q3_history > 0 else 1.0

    base_11_12_avg = (rev_last_11 + rev_last_12) / 2
    if current_month <= 1: dynamic_base_avg, formula_note = base_11_12_avg, "推演1月(全未知)"
    elif current_month == 2: dynamic_base_avg, formula_note = sim_rev_1 * 0.9 if sim_rev_1 > 0 else base_11_12_avg, "推演2月(知1月)"
    elif current_month == 3: dynamic_base_avg, formula_note = (sim_rev_1 * 2 + sim_rev_2) / 3 if sim_rev_2 > 0 else sim_rev_1, "推演3月(知1,2月)"
    else: dynamic_base_avg, formula_note = (sim_rev_1 + sim_rev_2 + sim_rev_3) / 3, "推演4月+"

    # --- 🎯 精準預估各季營收 ---
    est_q1_rev = dynamic_base_avg * 3
    est_q2_rev = est_q1_rev
    est_q3_rev = est_q2_rev * ratio_q3
    est_q4_rev = est_q3_rev * ratio_q4
    est_total_rev = est_q1_rev + est_q2_rev + est_q3_rev + est_q4_rev

    ly_total_rev = (ly_q1_rev + ly_q2_rev + ly_q3_rev + ly_q4_rev)
    est_annual_yoy = ((est_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0
    q1_yoy = ((est_q1_rev - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0

    base_q_total_rev = base_q_avg_rev * 3 if base_q_avg_rev > 0 else 1.0
    profit_margin_factor = (base_q_eps * (1 - (non_op_ratio / 100))) / base_q_total_rev 

    est_q1_eps_display = est_q1_rev * profit_margin_factor
    est_full_year_eps = est_total_rev * profit_margin_factor
    
    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    
    # --- 💰 配息率與殖利率計算 (完美整合表單) ---
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio <= 0 else recent_payout_ratio)
    est_annual_dividend = est_full_year_eps * (calc_payout_ratio / 100)
    # 取表單內的「2026合計股利」與「預估股利」兩者最高者
    forward_yield = (max(declared_div, est_annual_dividend) / current_price) * 100 if current_price > 0 else 0

    return {
        "股票名稱": name, "最新股價": round(current_price, 2), "logic_note": formula_note,
        "當季預估均營收": round(dynamic_base_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "預估今年Q1_EPS": round(est_q1_eps_display, 2), 
        "預估今年度_EPS": round(est_full_year_eps, 2), "最新累季EPS": acc_eps, "本益比(PER)": round(est_per, 2),         
        "預估年成長率(%)": round(est_annual_yoy, 2), "運算配息率(%)": calc_payout_ratio,
        "最新季度流動合約負債(億)": contract_liab, "最新季度流動合約負債季增(%)": contract_liab_qoq,
        "_ly_qs": [ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev], "_known_qs": [actual_known_q1, 0, 0, 0],
        "_known_q1_months": [max(0, sim_rev_1), max(0, sim_rev_2), max(0, sim_rev_3)],
        "_total_est_qs": [est_q1_rev, est_q2_rev, est_q3_rev, est_q4_rev]
    }

# ==========================================
# 🏦 核心大腦二：金融防禦存股專屬預估引擎 
# ==========================================
def financial_strategic_model(name, code, current_month, data, simulated_month):
    rev_this_1, rev_this_2, rev_this_3 = data.get("rev_this_1",0), data.get("rev_this_2",0), data.get("rev_this_3",0)
    if simulated_month <= 1: sim_rev_1, sim_rev_2, sim_rev_3 = 0, 0, 0
    elif simulated_month == 2: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, 0, 0
    elif simulated_month == 3: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, 0
    else: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, rev_this_3

    if simulated_month <= 1: dynamic_base_avg = (data["rev_last_11"] + data.get("rev_last_12",0)) / 2
    elif simulated_month == 2: dynamic_base_avg = sim_rev_1 * 0.9 if sim_rev_1 > 0 else (data["rev_last_11"] + data.get("rev_last_12",0)) / 2
    elif simulated_month == 3: dynamic_base_avg = (sim_rev_1 * 2 + sim_rev_2) / 3 if sim_rev_2 > 0 else sim_rev_1
    else: dynamic_base_avg = (sim_rev_1 + sim_rev_2 + sim_rev_3) / 3

    est_q1_eps = data["base_q_eps"] * (1 - (data.get("non_op", 0) / 100)) * (dynamic_base_avg / data["base_q_avg_rev"]) if data["base_q_avg_rev"] > 0 else 0
    
    ly_total_eps = data["eps_q1"] + data["eps_q2"] + data["eps_q3"] + data["eps_q4"]
    if data["eps_q1"] > 0 and ly_total_eps > 0: est_fy_eps = est_q1_eps * (ly_total_eps / data["eps_q1"])
    elif ly_total_eps > 0: est_fy_eps = est_q1_eps + data["eps_q2"] + data["eps_q3"] + data["eps_q4"] 
    else: est_fy_eps = est_q1_eps * 4
        
    current_price = float(data["price"]) if data["price"] else 0.0
    est_per = current_price / est_fy_eps if est_fy_eps > 0 else 0
    payout_ratio = 90 if data["payout"] > 100 else (data["payout"] if data["payout"] > 0 else 50)
    est_dividend = est_fy_eps * (payout_ratio / 100)
    forward_yield = (max(data.get("declared_div", 0), est_dividend) / current_price) * 100 if current_price > 0 else 0
        
    return {
        "股票名稱": f"{code} {data['name']}", "最新股價": round(current_price, 2), "PBR(股價淨值比)": round(data.get("pbr", 0), 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "年化殖利率(%)": round(data.get("annual_yield", 0), 2),
        "前瞻PER": round(est_per, 2), "原始PER": round(data.get("orig_per", 0), 2), "連續配息次數": int(data.get("div_years", 0)),
        "預估今年Q1_EPS": round(est_q1_eps, 2), "預估今年度_EPS": round(est_fy_eps, 2), "運算配息率(%)": payout_ratio, "當季預估均營收(億)": round(dynamic_base_avg, 2)
    }

# ==========================================
# 🌟 核心快取大腦 
# ==========================================
@st.cache_data(ttl=3600, show_spinner="連線至雙核大數據庫 (V185 終極防爆版)...")
def fetch_gsheet_data_v185():
    try:
        client = get_gspread_client()
        worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
        
        gen_dfs = []
        fin_dfs = []
        
        for ws in worksheets:
            if "個股總表" in ws.title:
                data = ws.get_all_values()
                if data and len(data) > 1: gen_dfs.append(pd.DataFrame(data[1:], columns=data[0]))
            elif "金融股" in ws.title:
                data = ws.get_all_values()
                if data and len(data) > 1: fin_dfs.append(pd.DataFrame(data[1:], columns=data[0]))
                    
        df_general = pd.concat(gen_dfs, ignore_index=True) if gen_dfs else pd.DataFrame()
        df_finance = pd.concat(fin_dfs, ignore_index=True) if fin_dfs else pd.DataFrame()

        def parse_df(df):
            if df is None or df.empty: return {}
            cols = df.columns.tolist()
            
            # --- 🛡️ 圖表消失 Bug 終極修復：強制把年份壓在 24 跟 25 (防爆版) ---
            q_cols = [str(c) for c in cols if re.search(r'(\d{2})Q', str(c))]
            valid_years = [int(re.search(r'(\d{2})Q', c).group(1)) for c in q_cols]
            filtered_years = [y for y in valid_years if y <= 25] # 篩選出 25 以前的
            ly = str(max(filtered_years)) if filtered_years else "25" # 如果篩選後有東西才取最大值，否則預設 25
            y1 = str(int(ly) - 1) 

            yp = [int(m.group(1)) for c in cols for m in [re.search(r'(\d{2})M\d{2}單月營收', str(c).replace(' ', ''))] if m and "增" not in str(c)]
            this_y, last_y = str(max(yp)) if yp else "", str(int(max(yp)) -
