# ==========================================
# 📂 檔案名稱： Fundamental_2026.py (主網頁程式 - 雙星融合防彈版)
# 💡 更新內容： 
#    1. 移植 API 版「最強預估大腦」，具備 Q1~Q4 全動態推演與財報開獎校準功能！
#    2. 堅守防彈原則：廢除自作聰明的業外計算，直接抓取「最新單季業外損益佔稅前淨利(%)」！
# ==========================================

import streamlit as st
import pandas as pd
import io
import altair as alt
import re
import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import urllib3
import time
import math
import numpy as np
import yfinance as yf
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 網頁基本設定 & 響應式 CSS 
# ==========================================
st.set_page_config(page_title="2026 戰略指揮 (完美同步版)", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    h1 { font-size: 1.8rem !important; margin-bottom: 0px !important; }
    h2 { font-size: 1.4rem !important; margin-bottom: 0px !important; }
    h3 { font-size: 1.2rem !important; margin-bottom: 0.5rem !important; } 
    p { margin-bottom: 0.2rem !important; font-size: 0.95rem !important; }
    .block-container { padding-top: 2.5rem !important; padding-bottom: 1rem !important; }
    @media (max-width: 768px) {
        h1 { font-size: 1.5rem !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.05rem !important; margin-bottom: 0.2rem !important; } 
        .block-container { padding-top: 1.5rem !important; }
    }
    ::-webkit-scrollbar { width: 14px !important; height: 14px !important; }
    ::-webkit-scrollbar-track { background: #e0e0e0; border-radius: 6px; }
    ::-webkit-scrollbar-thumb { background: #888; border-radius: 6px; border: 2px solid #e0e0e0; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }
    div[data-testid="stDataFrame"] div { scrollbar-width: auto; }
    </style>
""", unsafe_allow_html=True)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit"

def force_rerun():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()

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
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    for sfx in ['.TW', '.TWO']:
        try:
            res = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{code}{sfx}", headers=headers, timeout=2, verify=False).json()
            p = res['chart']['result'][0]['meta']['regularMarketPrice']
            if p > 0 and not math.isnan(p): return float(p)
        except: pass
    return default_price

st.title("📊 2026 戰略指揮 (完美同步版)")

# ==========================================
# 📊 核心大腦一：一般/成長股預估引擎 (🌟 已換上 API 版最強大腦)
# ==========================================
def auto_strategic_model(name, current_month, rev_last_10, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, rev_this_4, rev_this_5, rev_this_6, base_q_eps, non_op_ratio, base_q_total_rev, ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev, y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, recent_payout_ratio, current_price, contract_liab, contract_liab_qoq, acc_eps, declared_div, actual_q1_eps):
    try:
        current_price = float(current_price)
        if math.isnan(current_price) or math.isinf(current_price): current_price = 0.0
    except: current_price = 0.0

    if current_month <= 1: sim_rev_1, sim_rev_2, sim_rev_3 = 0, 0, 0
    elif current_month == 2: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, 0, 0
    elif current_month == 3: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, 0
    else: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, rev_this_3

    actual_known_q1 = sum([v for v in [sim_rev_1, sim_rev_2, sim_rev_3] if v > 0])
    
    ratio_q1 = ly_q1_rev / y1_q4_rev if y1_q4_rev > 0 else 1.0
    sum_q2_history = y1_q2_rev + ly_q2_rev
    sum_q3_history = y1_q3_rev + ly_q3_rev
    sum_q4_history = y1_q4_rev + ly_q4_rev
    
    ratio_q3 = sum_q3_history / sum_q2_history if sum_q2_history > 0 else 1.0
    ratio_q4 = sum_q4_history / sum_q3_history if sum_q3_history > 0 else 1.0

    # 🌟 靜態紅色標竿 (年初設定，全年不變)
    if rev_last_12 > 0:
        base_11_12_avg = (rev_last_11 + rev_last_12) / 2
    else:
        base_11_12_avg = (rev_last_10 + rev_last_11 + (rev_last_11 * 0.9)) / 3
        
    benchmark_q1_rev = (base_11_12_avg * 3) * ratio_q1 
    benchmark_q2_rev = benchmark_q1_rev # Q1 = Q2 靜態標竿
    benchmark_q3_rev = benchmark_q2_rev * ratio_q3
    benchmark_q4_rev = benchmark_q3_rev * ratio_q4

    # 🌟 動態推估 Q1
    if current_month <= 1: 
        dynamic_est_q1_rev = benchmark_q1_rev
        dynamic_base_avg = base_11_12_avg
        formula_note = "動態EPS推估 (全未知)"
    elif current_month == 2: 
        if sim_rev_1 > 0:
            dynamic_est_q1_rev = sim_rev_1 * 0.9 * 3
            dynamic_base_avg = dynamic_est_q1_rev / 3
            formula_note = "動態EPS推估 (1月x0.9x3)"
        else:
            dynamic_est_q1_rev = benchmark_q1_rev
            dynamic_base_avg = base_11_12_avg
            formula_note = "動態EPS推估 (無1月用標竿)"
    elif current_month == 3: 
        if sim_rev_2 > 0:
            dynamic_est_q1_rev = (sim_rev_1 * 2) + sim_rev_2
            dynamic_base_avg = dynamic_est_q1_rev / 3
            formula_note = "動態EPS推估 (1月x2+2月)"
        elif sim_rev_1 > 0:
            dynamic_est_q1_rev = sim_rev_1 * 0.9 * 3
            dynamic_base_avg = dynamic_est_q1_rev / 3
            formula_note = "動態EPS推估 (僅知1月x0.9x3)"
        else:
            dynamic_est_q1_rev = benchmark_q1_rev
            dynamic_base_avg = base_11_12_avg
            formula_note = "動態EPS推估 (無1,2月用標竿)"
    else: 
        if sim_rev_3 > 0:
            dynamic_est_q1_rev = sim_rev_1 + sim_rev_2 + sim_rev_3
            dynamic_base_avg = dynamic_est_q1_rev / 3
            formula_note = "動態EPS推估 (知Q1)"
        elif sim_rev_2 > 0:
            dynamic_est_q1_rev = (sim_rev_1 * 2) + sim_rev_2
            dynamic_base_avg = dynamic_est_q1_rev / 3
            formula_note = "動態EPS推估 (缺3月,退守1月x2+2月)"
        elif sim_rev_1 > 0:
            dynamic_est_q1_rev = sim_rev_1 * 0.9 * 3
            dynamic_base_avg = dynamic_est_q1_rev / 3
            formula_note = "動態EPS推估 (缺2,3月,退守1月x0.9x3)"
        else:
            dynamic_est_q1_rev = benchmark_q1_rev
            dynamic_base_avg = base_11_12_avg
            formula_note = "動態EPS推估 (全無,用標竿)"

    # 🌟 動態推估 Q2~Q4
    if current_month <= 3:
        dynamic_est_q2_rev = dynamic_est_q1_rev
    elif current_month == 4:
        if rev_this_4 > 0:
            dynamic_est_q2_rev = (rev_this_4 * 2) + (rev_this_4 * 0.9)
            formula_note += " (Q2:4月x2+0.9)"
        else:
            dynamic_est_q2_rev = dynamic_est_q1_rev
    else: 
        if rev_this_4 > 0 and rev_this_5 > 0:
            dynamic_est_q2_rev = rev_this_4 + rev_this_5 + (rev_this_5 * 0.9)
            formula_note += " (Q2:4+5+5月x0.9)"
        elif rev_this_4 > 0:
            dynamic_est_q2_rev = (rev_this_4 * 2) + (rev_this_4 * 0.9)
            formula_note += " (Q2:缺5月退守4月公式)"
        else:
            dynamic_est_q2_rev = dynamic_est_q1_rev

    if current_month <= 3:
        actual_known_q2 = 0
    elif current_month == 4:
        actual_known_q2 = max(0, rev_this_4)
    elif current_month == 5:
        actual_known_q2 = max(0, rev_this_4) + max(0, rev_this_5)
    else:
        actual_known_q2 = max(0, rev_this_4) + max(0, rev_this_5) + max(0, rev_this_6)

    dynamic_est_q3_rev = dynamic_est_q2_rev * ratio_q3
    dynamic_est_q4_rev = dynamic_est_q3_rev * ratio_q4
    dynamic_total_rev = dynamic_est_q1_rev + dynamic_est_q2_rev + dynamic_est_q3_rev + dynamic_est_q4_rev

    # 計算利潤因子 (⚠️ V01 防彈特色：完全信賴表單的 non_op_ratio)
    safe_base_rev = base_q_total_rev if base_q_total_rev > 0 else 1.0
    orig_profit_margin_factor = base_q_eps * (1 - (non_op_ratio / 100)) / safe_base_rev 
    
    # 🌟 動態 EPS 運算
    est_q1_eps_baseline = dynamic_est_q1_rev * orig_profit_margin_factor

    if actual_q1_eps > 0:
        est_q1_eps_display = actual_q1_eps
        formula_note += " ｜ 🎯 財報開獎(已重塑新體質)"
        
        safe_actual_q1_rev = dynamic_est_q1_rev if dynamic_est_q1_rev > 0 else 1.0 
        new_profit_margin_factor = actual_q1_eps / safe_actual_q1_rev
        
        est_q2_eps_forecast = dynamic_est_q2_rev * new_profit_margin_factor
        est_q3_eps_forecast = dynamic_est_q3_rev * new_profit_margin_factor
        est_q4_eps_forecast = dynamic_est_q4_rev * new_profit_margin_factor
    else:
        est_q1_eps_display = est_q1_eps_baseline
        est_q2_eps_forecast = dynamic_est_q2_rev * orig_profit_margin_factor
        est_q3_eps_forecast = dynamic_est_q3_rev * orig_profit_margin_factor
        est_q4_eps_forecast = dynamic_est_q4_rev * orig_profit_margin_factor

    est_full_year_eps = est_q1_eps_display + est_q2_eps_forecast + est_q3_eps_forecast + est_q4_eps_forecast

    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    q1_yoy = ((dynamic_est_q1_rev - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0
    ly_total_rev = (ly_q1_rev + ly_q2_rev + ly_q3_rev + ly_q4_rev)
    est_annual_yoy = ((dynamic_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0
    
    payout_note = ""
    if acc_eps > 0 and declared_div > 0:
        raw_payout = (declared_div / acc_eps) * 100
        if raw_payout >= 100:
            calc_payout_ratio = 90.0
            payout_note = "⚠️ 最新公告(壓回90%)"
        elif raw_payout <= 0:
            calc_payout_ratio = 50.0
            payout_note = "🛡️ 最新公告(異常補50%)"
        else:
            calc_payout_ratio = raw_payout
            payout_note = "✅ 最新公告股利推算"
    else:
        raw_payout = recent_payout_ratio
        if raw_payout >= 100:
            calc_payout_ratio = 90.0
            payout_note = "⚠️ 歷史配息(壓回90%)"
        elif raw_payout <= 0:
            calc_payout_ratio = 50.0
            payout_note = "🛡️ 無資料(防守填50%)"
        else:
            calc_payout_ratio = raw_payout
            payout_note = "🕒 歷史配息率"
            
    est_annual_dividend = est_full_year_eps * (calc_payout_ratio / 100)
    forward_yield = (max(declared_div, est_annual_dividend) / current_price) * 100 if current_price > 0 else 0

    return {
        "股票名稱": name, "最新股價": round(current_price, 2), 
        "_logic_note": formula_note, "_payout_note": "", 
        "當季預估均營收": round(dynamic_base_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "前瞻殖利率(%)": round(forward_yield, 2), 
        "預估今年Q1_EPS": round(est_q1_eps_display, 2), 
        "預估今年度_EPS": round(est_full_year_eps, 2), "最新累季EPS": acc_eps, "本益比(PER)": round(est_per, 2),         
        "預估年成長率(%)": round(est_annual_yoy, 2), "運算配息率(%)": calc_payout_ratio, "配息基準": payout_note,
        "最新業外佔比(%)": round(non_op_ratio, 2), 
        "最新季度流動合約負債(億)": contract_liab, "最新季度流動合約負債季增(%)": contract_liab_qoq,
        "_ly_qs": [round(ly_q1_rev, 2), round(ly_q2_rev, 2), round(ly_q3_rev, 2), round(ly_q4_rev, 2)], 
        "_known_qs": [round(actual_known_q1, 2), round(actual_known_q2, 2), 0, 0],
        "_known_q1_months": [round(max(0, sim_rev_1), 2), round(max(0, sim_rev_2), 2), round(max(0, sim_rev_3), 2)],
        "_known_q2_months": [round(max(0, rev_this_4), 2), round(max(0, rev_this_5), 2), round(max(0, rev_this_6), 2)],
        "_total_est_qs": [round(benchmark_q1_rev, 2), round(benchmark_q2_rev, 2), round(benchmark_q3_rev, 2), round(benchmark_q4_rev, 2)]
    }

# ==========================================
# 🏦 核心大腦二：金融防禦存股專屬預估引擎
# ==========================================
def financial_strategic_model(name, code, current_month, data, simulated_month, actual_q1_eps):
    rev_this_1, rev_this_2, rev_this_3 = data.get("rev_this_1",0), data.get("rev_this_2",0), data.get("rev_this_3",0)
    if simulated_month <= 1: sim_rev_1, sim_rev_2, sim_rev_3 = 0, 0, 0
    elif simulated_month == 2: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, 0, 0
    elif simulated_month == 3: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, 0
    else: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, rev_this_3

    r_11 = data.get("rev_last_11", 0)
    r_12 = data.get("rev_last_12", 0)
    base_11_12_avg = (r_11 + r_12) / 2

    if simulated_month <= 1: 
        dynamic_est_q1_rev = base_11_12_avg * 3
        dynamic_base_avg = base_11_12_avg
    elif simulated_month == 2: 
        dynamic_est_q1_rev = sim_rev_1 * 0.9 * 3 if sim_rev_1 > 0 else base_11_12_avg * 3
        dynamic_base_avg = dynamic_est_q1_rev / 3
    elif simulated_month == 3: 
        if sim_rev_2 > 0: 
            dynamic_est_q1_rev = (sim_rev_1 * 2) + sim_rev_2
            dynamic_base_avg = dynamic_est_q1_rev / 3
        else: 
            dynamic_est_q1_rev = sim_rev_1 * 0.9 * 3
            dynamic_base_avg = dynamic_est_q1_rev / 3
    else: 
        dynamic_est_q1_rev = sim_rev_1 + sim_rev_2 + sim_rev_3
        dynamic_base_avg = dynamic_est_q1_rev / 3

    non_op_ratio = data.get("non_op_ratio", 0)
    safe_base_rev = data["base_q_total_rev"] if data["base_q_total_rev"] > 0 else 1.0
    profit_margin_factor = data["base_q_eps"] * (1 - (non_op_ratio / 100)) / safe_base_rev 
    
    est_q1_eps_forecast = dynamic_est_q1_rev * profit_margin_factor
    ly_total_eps = data["eps_q1"] + data["eps_q2"] + data["eps_q3"] + data["eps_q4"]

    if actual_q1_eps > 0:
        est_q1_eps_display = actual_q1_eps
        if data["eps_q1"] > 0 and ly_total_eps > 0:
            est_fy_eps = actual_q1_eps * (ly_total_eps / data["eps_q1"])
        elif ly_total_eps > 0:
            est_fy_eps = actual_q1_eps + data["eps_q2"] + data["eps_q3"] + data["eps_q4"] 
        else:
            est_fy_eps = actual_q1_eps * 4
    else:
        est_q1_eps_display = est_q1_eps_forecast
        if data["eps_q1"] > 0 and ly_total_eps > 0: 
            est_fy_eps = est_q1_eps_forecast * (ly_total_eps / data["eps_q1"])
        elif ly_total_eps > 0: 
            est_fy_eps = est_q1_eps_forecast + data["eps_q2"] + data["eps_q3"] + data["eps_q4"] 
        else: 
            est_fy_eps = est_q1_eps_forecast * 4
        
    current_price = float(data["price"]) if data["price"] else 0.0
    est_per = current_price / est_fy_eps if est_fy_eps > 0 else 0
    
    f_acc_eps = data.get("acc_eps", 0)
    f_declared_div = data.get("declared_div", 0)
    payout_note = ""
    if f_acc_eps > 0 and f_declared_div > 0:
        raw_payout = (f_declared_div / f_acc_eps) * 100
        if raw_payout >= 100:
            payout_ratio = 90.0
            payout_note = "⚠️ 最新公告(壓回90%)"
        elif raw_payout <= 0:
            payout_ratio = 50.0
            payout_note = "🛡️ 最新公告(異常補50%)"
        else:
            payout_ratio = raw_payout
            payout_note = "✅ 最新公告股推算"
    else:
        raw_payout = data.get("payout", 0)
        if raw_payout >= 100:
            payout_ratio = 90.0
            payout_note = "⚠️ 歷史配息(壓回90%)"
        elif raw_payout <= 0:
            payout_ratio = 50.0
            payout_note = "🛡️ 無資料(防守填50%)"
        else:
            payout_ratio = raw_payout
            payout_note = "🕒 歷史配息率"
            
    est_dividend = est_fy_eps * (payout_ratio / 100)
    forward_yield = (max(data.get("declared_div", 0), est_dividend) / current_price) * 100 if current_price > 0 else 0
        
    return {
        "股票名稱": f"{code} {data['name']}", "最新股價": round(current_price, 2), "PBR(股價淨值比)": round(data.get("pbr", 0), 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "年化殖利率(%)": round(data.get("annual_yield", 0), 2),
        "前瞻PER": round(est_per, 2), "原始PER": round(data.get("orig_per", 0), 2), "連續配息次數": int(data.get("div_years", 0)),
        "預估今年Q1_EPS": round(est_q1_eps_display, 2), "預估今年度_EPS": round(est_fy_eps, 2), "運算配息率(%)": payout_ratio, "配息基準": payout_note, "當季預估均營收(億)": round(dynamic_base_avg, 2), "最新業外佔比(%)": round(non_op_ratio, 2)
    }

# ==========================================
# 🌟 核心快取大腦
# ==========================================
def deduplicate_cols(cols):
    """防撞過濾器：自動為重複或空白的欄位加上編號，防止程式當機"""
    seen = {}
    res = []
    for c in cols:
        c_str = str(c).strip()
        if not c_str: c_str = "未命名欄位"
        if c_str in seen:
            seen[c_str] += 1
            res.append(f"{c_str}_{seen[c_str]}")
        else:
            seen[c_str] = 0
            res.append(c_str)
    return res

@st.cache_data(ttl=3600, show_spinner="連線至大數據庫...")
def fetch_gsheet_data_v182():
    try:
        client = get_gspread_client()
        worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
        
        gen_dfs = []
        fin_dfs = []
        
        for ws in worksheets:
            clean_title = ws.title.replace(" ", "")
            if any(n in clean_title for n in ["當年度表", "歷史表單", "個股總表", "總表"]):
                data = ws.get_all_values()
                if data and len(data) > 1:
                    cols = deduplicate_cols(data[0])
                    gen_dfs.append(pd.DataFrame(data[1:], columns=cols))
            elif "金融股" in clean_title:
                data = ws.get_all_values()
                if data and len(data) > 1:
                    cols = deduplicate_cols(data[0])
                    fin_dfs.append(pd.DataFrame(data[1:], columns=cols))
                    
        df_general = pd.concat(gen_dfs, ignore_index=True) if gen_dfs else pd.DataFrame()
        df_finance = pd.concat(fin_dfs, ignore_index=True) if fin_dfs else pd.DataFrame()

        def parse_df(df):
            if df is None or df.empty: return {}
            cols = df.columns.tolist()
            q_cols = [str(c) for c in cols if re.search(r'(\d{2})Q',
