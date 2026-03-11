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
st.set_page_config(page_title="2026 戰略指揮", layout="wide", initial_sidebar_state="expanded")

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

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

# 💡 V182 標題確認法：只要這裡不是 V182，就代表雲端沒更新！
st.title("📊 2026 戰略指揮 (V182 雲端同步確認版)")

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

# ==========================================
# 📊 核心大腦一：一般/成長股預估引擎
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
    static_q1_est_total = ((rev_last_11 + rev_last_12) / 2) * 3
    q1_yoy = ((static_q1_est_total - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0
    est_q1_eps_display = base_q_eps * (1 - (non_op_ratio / 100)) * (((rev_last_11 + rev_last_12) / 2) / base_q_avg_rev) if base_q_avg_rev > 0 else 0

    if current_month <= 1: dynamic_base_avg, formula_note = (rev_last_11 + rev_last_12) / 2, "推演1月(全未知)"
    elif current_month == 2: dynamic_base_avg, formula_note = sim_rev_1 * 0.9 if sim_rev_1 > 0 else (rev_last_11 + rev_last_12) / 2, "推演2月(知1月)"
    elif current_month == 3: dynamic_base_avg, formula_note = (sim_rev_1 * 2 + sim_rev_2) / 3 if sim_rev_2 > 0 else sim_rev_1, "推演3月(知1,2月)"
    else: dynamic_base_avg, formula_note = (sim_rev_1 + sim_rev_2 + sim_rev_3) / 3, "推演4月+"

    est_q2_rev_total = dynamic_base_avg * 3
    est_h1_rev_total = dynamic_base_avg * 3 + est_q2_rev_total
    est_h1_eps = (base_q_eps * (1 - (non_op_ratio / 100)) * (dynamic_base_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0) * 2

    avg_2yr_h1 = ((y1_q1_rev + y1_q2_rev) + (ly_q1_rev + ly_q2_rev)) / 2
    avg_2yr_h2 = ((y1_q3_rev + y1_q4_rev) + (ly_q3_rev + ly_q4_rev)) / 2

    if avg_2yr_h1 > 0:
        multiplier = 1 + (avg_2yr_h2 / avg_2yr_h1)
        est_total_rev, est_full_year_eps = est_h1_rev_total * multiplier, est_h1_eps * multiplier
    else:
        est_total_rev, est_full_year_eps = est_h1_rev_total, est_h1_eps

    ly_total_rev = (ly_q1_rev + ly_q2_rev + ly_q3_rev + ly_q4_rev)
    est_annual_yoy = ((est_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0
    
    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio <= 0 else recent_payout_ratio)
    est_annual_dividend = est_full_year_eps * (calc_payout_ratio / 100)
    forward_yield = (max(declared_div, est_annual_dividend) / current_price) * 100 if current_price > 0 else 0

    return {
        "股票名稱": name, "最新股價": round(current_price, 2), 
        "_logic_note": formula_note, "_payout_note": "", 
        "當季預估均營收": round(dynamic_base_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "預估今年Q1_EPS": round(est_q1_eps_display, 2), 
        "預估今年度_EPS": round(est_full_year_eps, 2), "最新累季EPS": acc_eps, "本益比(PER)": round(est_per, 2),         
        "預估年成長率(%)": round(est_annual_yoy, 2), "運算配息率(%)": calc_payout_ratio,
        "最新季度流動合約負債(億)": contract_liab, "最新季度流動合約負債季增(%)": contract_liab_qoq,
        "_ly_qs": [round(ly_q1_rev, 2), round(ly_q2_rev, 2), round(ly_q3_rev, 2), round(ly_q4_rev, 2)], 
        "_known_qs": [round(actual_known_q1, 2), 0, 0, 0],
        "_known_q1_months": [round(max(0, sim_rev_1), 2), round(max(0, sim_rev_2), 2), round(max(0, sim_rev_3), 2)],
        "_total_est_qs": [round(static_q1_est_total, 2), round(est_q2_rev_total, 2), 0, 0]
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
