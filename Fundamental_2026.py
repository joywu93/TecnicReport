# ==========================================
# 📂 檔案名稱： Fundamental_2026.py (主網頁程式)
# 💡 更新內容： 加入終極防彈機制，無視快取錯誤，永不當機
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

st.title("📊 2026 戰略指揮 (防彈穩定版)")

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

    est_q1_rev = (base_11_12_avg * 3) * ratio_q1
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
        "_total_est_qs": [round(est_q1_rev, 2), round(est_q2_rev, 2), round(est_q3_rev, 2), round(est_q4_rev, 2)]
    }

# ==========================================
# 🏦 核心大腦二：金融防禦存股專屬預估引擎 (🛡️ 終極防彈版)
# ==========================================
def financial_strategic_model(name, code, current_month, data, simulated_month):
    # 使用 .get() 確保就算欄位不見，也自動當作 0，絕不當機！
    rev_this_1, rev_this_2, rev_this_3 = data.get("rev_this_1",0), data.get("rev_this_2",0), data.get("rev_this_3",0)
    if simulated_month <= 1: sim_rev_1, sim_rev_2, sim_rev_3 = 0, 0, 0
    elif simulated_month == 2: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, 0, 0
    elif simulated_month == 3: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, 0
    else: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, rev_this_3

    if simulated_month <= 1: dynamic_base_avg = (data.get("rev_last_11",0) + data.get("rev_last_12",0)) / 2
    elif simulated_month == 2: dynamic_base_avg = sim_rev_1 * 0.9 if sim_rev_1 > 0 else (data.get("rev_last_11",0) + data.get("rev_last_12",0)) / 2
    elif simulated_month == 3: dynamic_base_avg = (sim_rev_1 * 2 + sim_rev_2) / 3 if sim_rev_2 > 0 else sim_rev_1
    else: dynamic_base_avg = (sim_rev_1 + sim_rev_2 + sim_rev_3) / 3

    base_q_avg_rev = data.get("base_q_avg_rev", 1)
    if base_q_avg_rev == 0: base_q_avg_rev = 1
    
    est_q1_eps = data.get("base_q_eps",0) * (1 - (data.get("non_op", 0) / 100)) * (dynamic_base_avg / base_q_avg_rev)
    
    # 這裡就是解決 KeyError 的關鍵！
    eps_q1 = data.get("eps_q1", 0)
    eps_q2 = data.get("eps_q2", 0)
    eps_q3 = data.get("eps_q3", 0)
    eps_q4 = data.get("eps_q4", 0)
    
    ly_total_eps = eps_q1 + eps_q2 + eps_q3 + eps_q4
    if eps_q1 > 0 and ly_total_eps > 0: est_fy_eps = est_q1_eps * (ly_total_eps / eps_q1)
    elif ly_total_eps > 0: est_fy_eps = est_q1_eps + eps_q2 + eps_q3 + eps_q4 
    else: est_fy_eps = est_q1_eps * 4
        
    current_price = float(data.get("price", 0)) if data.get("price") else 0.0
    est_per = current_price / est_fy_eps if est_fy_eps > 0 else 0
    payout = data.get("payout", 50)
    payout_ratio = 90 if payout > 100 else (payout if payout > 0 else 50)
    est_dividend = est_fy_eps * (payout_ratio / 100)
    
    forward_yield = (max(data.get("declared_div", 0), est_dividend) / current_price) * 100 if current_price > 0 else 0
        
    return {
        "股票名稱": f"{code} {data.get('name', '')}", "最新股價": round(current_price, 2), "PBR(股價淨值比)": round(data.get("pbr", 0), 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "年化殖利率(%)": round(data.get("annual_yield", 0), 2),
        "前瞻PER": round(est_per, 2), "原始PER": round(data.get("orig_per", 0), 2), "連續配息次數": int(data.get("div_years", 0)),
        "預估今年Q1_EPS": round(est_q1_eps, 2), "預估今年度_EPS": round(est_fy_eps, 2), "運算配息率(%)": payout_ratio, "當季預估均營收(億)": round(dynamic_base_avg, 2)
    }

# ==========================================
# 🌟 核心快取大腦 
# ==========================================
@st.cache_data(ttl=3600, show_spinner="連線至大數據庫...")
def fetch_gsheet_data_v182():
    try:
        client = get_gspread_client()
        worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
        
        gen_dfs = []
        fin_dfs = []
        
        for ws in worksheets:
            if "個股總表" in ws.title:
                data = ws.get_all_values()
                if data and len(data) > 1:
                    gen_dfs.append(pd.DataFrame(data[1:], columns=data[0]))
            elif "金融股" in ws.title:
                data = ws.get_all_values()
                if data and len(data) > 1:
                    fin_dfs.append(pd.DataFrame(data[1:], columns=data[0]))
                    
        df_general = pd.concat(gen_dfs, ignore_index=True) if gen_dfs else pd.DataFrame()
        df_finance = pd.concat(fin_dfs, ignore_index=True) if fin_dfs else pd.DataFrame()

        def parse_df(df):
            if df is None or df.empty: return {}
            cols = df.columns.tolist()
            q_cols = [str(c) for c in cols if re.search(r'(\d{2})Q', str(c))]
            ly = max([re.search(r'(\d{2})Q', c).group(1) for c in q_cols]) if q_cols else "25"
            y1 = str(int(ly) - 1) 

            yp = [int(m.group(1)) for c in cols for m in [re.search(r'(\d{2})M\d{2}單月營收', str(c).replace(' ', ''))] if m and "增" not in str(c)]
            this_y, last_y = str(max(yp)) if yp else "", str(int(max(yp)) - 1) if yp else ""

            def get_col(k1, k2="", ex=[]):
                for c in cols:
                    cc = str(c).replace('\n', '').replace(' ', '')
                    if k1 in cc and k2 in cc and not any(e in cc for e in ex): return c
                return None
                
            c_code, c_name = get_col("代號"), get_col("名稱")
            db = {}
            for idx, row in df.iterrows():
                code = str(row[c_code]).split('.')[0].strip() if c_code and pd.notna(row[c_code]) else ""
                if len(code) < 3: continue 
                
                def v(c_name, d=0.0):
                    if not c_name or pd.isna(row[c_name]): return d
                    val_str = str(row[c_name]).replace(',', '').strip()
                    if not val_str or val_str.lower() in ['-', 'nan', 'inf', '-inf', 'infinity', '-infinity', '#n/a', 'n/a', '#div/0!']: return d
                    try: 
                        val = float(val_str)
                        if math.isnan(val) or math.isinf(val): return d
                        return val
                    except: return d
                 
                rev_q4 = v(get_col(f"{ly}Q4", "營收", ex=["增", "率", "%"])) or (v(get_col("10單月營收", ex=["增", "%"])) + v(get_col(f"{last_y}M11", "營收", ex=["增", "%"])) + v(get_col(f"{last_y}M12", "營收", ex=["增", "%"])))
                eps_q3, eps_q4 = v(get_col(f"{ly}Q3", "盈餘")), v(get_col(f"{ly}Q4", "盈餘"))
                rev_q3 = v(get_col(f"{ly}Q3", "營收", ex=["增", "率", "%"]))
                base_eps = eps_q4 if eps_q4 != 0 else (eps_q3 * (rev_q4 / rev_q3) if rev_q3 > 0 else eps_q3)

                db[code] = {
                    "name": str(row[c_name]) if c_name else "未知", 
                    "industry": str(row[get_col("產業") or get_col("類別")]).strip() if (get_col("產業") or get_col("類別")) else "未分類",
                    "rev_last_11": v(get_col(f"{last_y}M11", "營收", ex=["增", "率", "%"])), "rev_last_12": v(get_col(f"{last_y}M12", "營收", ex=["增", "率", "%"])),
                    "rev_this_1": v(get_col(f"{this_y}M01", "營收", ex=["增", "率", "%"])), "rev_this_2": v(get_col(f"{this_y}M02", "營收", ex=["增", "率", "%"])), "rev_this_3": v(get_col(f"{this_y}M03", "營收", ex=["增", "率", "%"])),
                    "base_q_eps": base_eps, "non_op": v(get_col("業外損益")), "base_q_avg_rev": rev_q4 / 3 if rev_q4 > 0 else 0,
                    "ly_q1_rev": v(get_col(f"{ly}Q1", "營收", ex=["增", "%"])), "ly_q2_rev": v(get_col(f"{ly}Q2", "營收", ex=["增", "%"])), "ly_q3_rev": rev_q3, "ly_q4_rev": rev_q4,
                    "y1_q1_rev": v(get_col(f"{y1}Q1", "營收", ex=["增", "%"])), "y1_q2_rev": v(get_col(f"{y1}Q2", "營收", ex=["增", "%"])), "y1_q3_rev": v(get_col(f"{y1}Q3", "營收", ex=["增", "%"])), "y1_q4_rev": v(get_col(f"{y1}Q4", "營收", ex=["增", "%"])),
                    "eps_q1": v(get_col(f"{ly}Q1", "盈餘")), "eps_q2": v(get_col(f"{ly}Q2", "盈餘")), "eps_q3": eps_q3, "eps_q4": eps_q4,
                    "pbr": v(get_col("PBR") or get_col("淨值比")), "div_years": v(get_col("連配次數") or get_col("連續配發")),
                    "orig_per": v(get_col("PER", ex=["前瞻", "預估"])), "annual_yield": v(get_col("年化合計殖利率") or get_col("年化", "殖利率")),
                    "payout": v(get_col("分配率")), "price": v(get_col("成交", ex=["量", "值", "比"])), "acc_eps": v(get_col("累季", "盈餘")),
                    "contract_liab": v(get_col("合約負債", ex=["季增"])), "contract_liab_qoq": v(get_col("合約負債季增") or get_col("季增", "負債")), "declared_div": v(get_col("合計股利"))
                }
            return db
        return {"general": parse_df(df_general), "finance": parse_df(df_finance)}
    except Exception as e: return {"error": str(e)}

cached_data = fetch_gsheet_data_v182()
if cached_data and "error" in cached_data:
    st.error(f"檔案解析
