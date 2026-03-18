# ==========================================
# 📂 檔案名稱： Fundamental_2026.py (主網頁程式 - V01 版)
# 💡 更新內容： 新增「配息基準」狀態標示欄位，修復季成長率/年成長率低估 Bug
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
st.set_page_config(page_title="2026 戰略指揮 (V01版)", layout="wide", initial_sidebar_state="expanded")

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

st.title("📊 2026 戰略指揮 (V01版)")

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
    
    ratio_q1 = ly_q1_rev / y1_q4_rev if y1_q4_rev > 0 else 1.0
    
    sum_q2_history = y1_q2_rev + ly_q2_rev
    sum_q3_history = y1_q3_rev + ly_q3_rev
    sum_q4_history = y1_q4_rev + ly_q4_rev
    
    ratio_q3 = sum_q3_history / sum_q2_history if sum_q2_history > 0 else 1.0
    ratio_q4 = sum_q4_history / sum_q3_history if sum_q3_history > 0 else 1.0

    base_11_12_avg = (rev_last_11 + rev_last_12) / 2
    
    # 🌟 【重大修正區塊】：強制 est_q1_rev 必須使用最新的動態真實營收！解決季成長率與年成長率低估問題
    if current_month <= 1: 
        dynamic_base_avg, formula_note = base_11_12_avg, "推演1月(全未知)"
        est_q1_rev = (base_11_12_avg * 3) * ratio_q1 # 只有在全未知時，才依賴去年Q4與歷史轉換率
    elif current_month == 2: 
        dynamic_base_avg, formula_note = sim_rev_1 * 0.9 if sim_rev_1 > 0 else base_11_12_avg, "推演2月(知1月)"
        est_q1_rev = dynamic_base_avg * 3  # ✅ 乘上最新動態均值
    elif current_month == 3: 
        dynamic_base_avg, formula_note = (sim_rev_1 * 2 + sim_rev_2) / 3 if sim_rev_2 > 0 else sim_rev_1, "推演3月(知1,2月)"
        est_q1_rev = dynamic_base_avg * 3  # ✅ 完美對應您手算的精準數字
    else: 
        dynamic_base_avg, formula_note = (sim_rev_1 + sim_rev_2 + sim_rev_3) / 3, "推演4月+"
        est_q1_rev = dynamic_base_avg * 3  # ✅ 乘上最新動態均值

    est_q2_rev = est_q1_rev
    est_q3_rev = est_q2_rev * ratio_q3
    est_q4_rev = est_q3_rev * ratio_q4

    est_total_rev = est_q1_rev + est_q2_rev + est_q3_rev + est_q4_rev
    ly_total_rev = (ly_q1_rev + ly_q2_rev + ly_q3_rev + ly_q4_rev)
    est_annual_yoy = ((est_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0
    q1_yoy = ((est_q1_rev - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0

    base_q_total_rev = base_q_avg_rev * 3 if base_q_avg_rev > 0 else 1.0
    profit_margin_factor = base_q_eps * (1 - (non_op_ratio / 100)) / base_q_total_rev 

    est_q1_eps_display = est_q1_rev * profit_margin_factor
    est_full_year_eps = est_total_rev * profit_margin_factor
    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    
    # 🌟 新版配息率強效防守邏輯 + 備註機制
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
            
    est_annual_dividend = est_full_year
