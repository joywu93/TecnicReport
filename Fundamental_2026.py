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
import yfinance as yf
from datetime import datetime

# 關閉 SSL 憑證警告
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
        p { font-size: 0.85rem !important; }
        .block-container { padding-top: 1.5rem !important; }
        button[data-baseweb="tab"] { font-size: 1rem !important; padding-top: 10px !important; padding-bottom: 10px !important; }
    }
    ::-webkit-scrollbar { width: 14px !important; height: 14px !important; }
    ::-webkit-scrollbar-track { background: #e0e0e0; border-radius: 6px; }
    ::-webkit-scrollbar-thumb { background: #888; border-radius: 6px; border: 2px solid #e0e0e0; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }
    div[data-testid="stDataFrame"] div { scrollbar-width: auto; }
    </style>
""", unsafe_allow_html=True)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

st.title("📊 2026 戰略指揮 (V137 終極會計重構版)")

def get_realtime_price(code, default_price):
    try:
        tkr = yf.Ticker(f"{code}.TW")
        p = tkr.fast_info['last_price']
        if p and p > 0: return float(p)
    except: pass
    try:
        tkr = yf.Ticker(f"{code}.TWO")
        p = tkr.fast_info['last_price']
        if p and p > 0: return float(p)
    except: pass
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    for sfx in ['.TW', '.TWO']:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}{sfx}"
            res = requests.get(url, headers=headers, timeout=2, verify=False).json()
            p = res['chart']['result'][0]['meta']['regularMarketPrice']
            if p and p > 0: return float(p)
        except: pass
    return default_price

# ==========================================
# 📊 核心大腦一：一般/成長股預估引擎
# ==========================================
def auto_strategic_model(name, current_month, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, base_q_eps, non_op_ratio, base_q_avg_rev, ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev, y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, recent_payout_ratio, current_price, contract_liab, contract_liab_qoq, acc_eps, declared_div):
    if current_month <= 1: sim_rev_1, sim_rev_2, sim_rev_3 = 0, 0, 0
    elif current_month == 2: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, 0, 0
    elif current_month == 3: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, 0
    else: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, rev_this_3

    actual_known_q1 = sum([v for v in [sim_rev_1, sim_rev_2, sim_rev_3] if v > 0])
    static_q1_avg = (rev_last_11 + rev_last_12) / 2
    static_q1_est_total = static_q1_avg * 3
    q1_yoy = ((static_q1_est_total - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0
    est_q1_eps_display = base_q_eps * (1 - (non_op_ratio / 100)) * (static_q1_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0

    if current_month <= 1: dynamic_base_avg, formula_note = (rev_last_11 + rev_last_12) / 2, "推演1月(全未知)：Q1基準=上年11,12月均值"
    elif current_month == 2: dynamic_base_avg, formula_note = sim_rev_1 * 0.9 if sim_rev_1 > 0 else (rev_last_11 + rev_last_12) / 2, "推演2月(知1月)：Q2後採(1月×0.9)推算"
    elif current_month == 3: dynamic_base_avg, formula_note = (sim_rev_1 * 2 + sim_rev_2) / 3 if sim_rev_2 > 0 else sim_rev_1, "推演3月(知1,2月)：Q2後採前月均值推算"
    else: dynamic_base_avg, formula_note = (sim_rev_1 + sim_rev_2 + sim_rev_3) / 3, "推演4月+(知Q1全)：Q2後採Q1實際均值推算"

    est_q2_rev_total = dynamic_base_avg * 3
    dynamic_q1_total_for_calc = dynamic_base_avg * 3
    est_h1_rev_total = dynamic_q1_total_for_calc + est_q2_rev_total
    dynamic_q_eps = base_q_eps * (1 - (non_op_ratio / 100)) * (dynamic_base_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0
    est_h1_eps = dynamic_q_eps * 2

    avg_2yr_h1 = ((y1_q1_rev + y1_q2_rev) + (ly_q1_rev + ly_q2_rev)) / 2
    avg_2yr_h2 = ((y1_q3_rev + y1_q4_rev) + (ly_q3_rev + ly_q4_rev)) / 2

    if avg_2yr_h1 > 0:
        multiplier = 1 + (avg_2yr_h2 / avg_2yr_h1)
        est_total_rev, est_full_year_eps = est_h1_rev_total * multiplier, est_h1_eps * multiplier
    else:
        est_total_rev, est_full_year_eps = est_h1_rev_total, est_h1_eps

    ly_total_rev = (ly_q1_rev + ly_q2_rev + ly_q3_rev + ly_q4_rev)
    est_annual_yoy = ((est_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0
    current_price = float(current_price) if current_price else 0.0
    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio <= 0 else recent_payout_ratio)
    est_annual_dividend = est_full_year_eps * (calc_payout_ratio / 100)
    forward_yield = (max(declared_div, est_annual_dividend) / current_price) * 100 if current_price > 0 else 0

    return {
        "股票名稱": name, "最新股價": round(current_price, 2), "logic_note": formula_note, "payout_note": "", 
        "當季預估均營收": round(dynamic_base_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "預估今年Q1_EPS": round(est_q1_eps_display, 2), 
        "預估今年度_EPS": round(est_full_year_eps, 2), "最新累季EPS": acc_eps, "本益比(PER)": round(est_per, 2),         
        "預估年成長率(%)": round(est_annual_yoy, 2), "運算配息率(%)": calc_payout_ratio,
        "最新季度流動合約負債(億)": contract_liab, "最新季度流動合約負債季增(%)": contract_liab_qoq,
        "_ly_qs": [ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev], "_known_qs": [actual_known_q1, 0, 0, 0],
        "_known_q1_months": [max(0, sim_rev_1), max(0, sim_rev_2), max(0, sim_rev_3)],
        "_total_est_qs": [static_q1_est_total, est_q2_rev_total, 0, 0]
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

    base_q_eps = data["base_q_eps"]
    base_q_avg_rev = data["base_q_avg_rev"]
    
    est_q1_eps = base_q_eps * (1 - (data.get("non_op", 0) / 100)) * (dynamic_base_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0
    
    ly_total_eps = data["eps_q1"] + data["eps_q2"] + data["eps_q3"] + data["eps_q4"]
    if data["eps_q1"] > 0 and ly_total_eps > 0:
        seasonality_ratio = ly_total_eps / data["eps_q1"]
        est_fy_eps = est_q1_eps * seasonality_ratio
    elif ly_total_eps > 0:
        est_fy_eps = est_q1_eps + data["eps_q2"] + data["eps_q3"] + data["eps_q4"] 
    else:
        est_fy_eps = est_q1_eps * 4
        
    current_price = float(data["price"]) if data["price"] else 0.0
    est_per = current_price / est_fy_eps if est_fy_eps > 0 else 0
    
    payout_ratio = data["payout"] if data["payout"] > 0 else 50
    if payout_ratio > 100: payout_ratio = 90
    
    est_dividend = est_fy_eps * (payout_ratio / 100)
    declared_div = data.get("declared_div", 0)
    
    if declared_div > 0 and current_price > 0:
        forward_yield = (max(declared_div, est_dividend) / current_price) * 100
    elif current_price > 0:
        forward_yield = (est_dividend / current_price) * 100
    else:
        forward_yield = 0
        
    return {
        "股票名稱": f"{code} {data['name']}",
        "最新股價": round(current_price, 2),
        "PBR(股價淨值比)": round(data.get("pbr", 0), 2),
        "前瞻殖利率(%)": round(forward_yield, 2),
        "年化殖利率(%)": round(data.get("annual_yield", 0), 2),
        "前瞻PER": round(est_per, 2),
        "原始PER": round(data.get("orig_per", 0), 2),
        "連續配息次數": int(data.get("div_years", 0)),
        "預估今年Q1_EPS": round(est_q1_eps, 2),
        "預估今年度_EPS": round(est_fy_eps, 2),
        "運算配息率(%)": payout_ratio,
        "當季預估均營收(億)": round(dynamic_base_avg, 2)
    }

# ==========================================
# 🌟 核心快取大腦 
# ==========================================
@st.cache_data(ttl=3600, show_spinner="連線至雙核大數據庫，這只需兩秒鐘...")
def load_google_sheet_data():
    if "google_key" not in st.secrets: return None
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        key_dict = json.loads(st.secrets["google_key"]) if isinstance(st.secrets["google_key"], str) else dict(st.secrets["google_key"])
        creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
        
        target_sheets = [ws for ws in worksheets if "個股總表" in ws.title]
        df_general = pd.concat([pd.DataFrame(ws.get_all_values()[1:], columns=ws.get_all_values()[0]) for ws in target_sheets if len(ws.get_all_values()) > 0], ignore_index=True) if target_sheets else pd.DataFrame()
        
        finance_sheets = [ws for ws in worksheets if "金融股" in ws.title]
        df_finance = pd.concat([pd.DataFrame(ws.get_all_values()[1:], columns=ws.get_all_values()[0]) for ws in finance_sheets if len(ws.get_all_values()) > 0], ignore_index=True) if finance_sheets else pd.DataFrame()

        def parse_df(df):
            if df is None or df.empty: return {}
            cols = df.columns.tolist()
            q_cols = [c for c in cols if re.search(r'(\d{2})Q', c)]
            ly = max([re.search(r'(\d{2})Q', c).group(1) for c in q_cols]) if q_cols else "25"
            y1 = str(int(ly) - 1) 

            year_prefixes = [int(m.group(1)) for c in cols for m in [re.search(r'(\d{2})M\d{2}單月營收', c.replace('\n', '').replace(' ', ''))] if m and "增" not in c]
            this_y = str(max(year_prefixes)) if year_prefixes else ""
            last_y = str(int(this_y) - 1) if this_y else ""

            def get_col(kw1, kw2="", excludes=[]):
                for c in cols:
                    clean_c = str(c).replace('\n', '').replace(' ', '').replace('\r', '')
                    if kw1 in clean_c and kw2 in clean_c and not any(ex in clean_c for ex in excludes): return c
                return None
            
            def get_col_exact(name):
                for c in cols:
                    if str(c).strip() == name: return c
                return None
                
            c_code, c_name = get_col("代號"), get_col("名稱")
            c_price = get_col("成交", excludes=["量", "值", "比", "額", "金", "幅", "差", "均"])
            c_industry = get_col("產業") or get_col("類別") or get_col("類股")
            
            c_pbr = get_col("PBR") or get_col("淨值比")
            c_div_years = get_col("連配次數") or get_col("連續配發") or get_col("次數")
            c_orig_per = get_col_exact("PER") or get_col("PER", excludes=["前瞻", "預估", "均"])
            c_annual_yield = get_col("年化合計殖利率") or get_col("年化", "殖利率") or get_col("成交價年化合計殖利率")
            
            ex_words = ["增", "率", "%", "去年", "上月"]
            c_rev_this_1 = get_col(f"{this_y}M01", "營收", excludes=ex_words) if this_y else get_col("01單月", "營收", excludes=ex_words)
            c_rev_this_2 = get_col(f"{this_y}M02", "營收", excludes=ex_words) if this_y else get_col("02單月", "營收", excludes=ex_words)
            c_rev_this_3 = get_col(f"{this_y}M03", "營收", excludes=ex_words) if this_y else get_col("03單月", "營收", excludes=ex_words)
            c_rev_last_11 = get_col(f"{last_y}M11", "營收", excludes=ex_words) if last_y else get_col("11單月", "營收", excludes=ex_words)
            c_rev_last_12 = get_col(f"{last_y}M12", "營收", excludes=ex_words) if last_y else get_col("12單月", "營收", excludes=ex_words)
            
            c_ly_q1, c_ly_q2, c_ly_q3, c_ly_q4 = get_col(f"{ly}Q1", "營收", excludes=["增", "率", "%"]), get_col(f"{ly}Q2", "營收", excludes=["增", "率", "%"]), get_col(f"{ly}Q3", "營收", excludes=["增", "率", "%"]), get_col(f"{ly}Q4", "營收", excludes=["增", "率", "%"])
            c_y1_q1, c_y1_q2, c_y1_q3, c_y1_q4 = get_col(f"{y1}Q1", "營收", excludes=["增", "率", "%"]), get_col(f"{y1}Q2", "營收", excludes=["增", "率", "%"]), get_col(f"{y1}Q3", "營收", excludes=["增", "率", "%"]), get_col(f"{y1}Q4", "營收", excludes=["增", "率", "%"])
            c_rev_10 = get_col("10單月營收", excludes=["增", "率", "%"])
            
            c_eps_q1, c_eps_q2, c_eps_q3, c_eps_q4, c_acc_eps = get_col(f"{ly}Q1", "盈餘"), get_col(f"{ly}Q2", "盈餘"), get_col(f"{ly}Q3", "盈餘"), get_col(f"{ly}Q4", "盈餘"), get_col("累季", "盈餘")
            c_non_op, c_payout, c_dec_div = get_col("業外損益"), get_col("分配率"), get_col("合計股利")
            c_liab_qoq = get_col("合約負債季增") or get_col("季增", "負債")
            c_liab = get_col("合約負債", excludes=["季增", "%", "比"])

            db = {}
            for idx, row in df.iterrows():
                code = str(row[c_code]).split('.')[0].strip() if c_code and pd.notna(row[c_code]) else ""
                if len(code) < 3: continue 
                
                def get_val(col_name, default=0.0):
                    if col_name and pd.notna(row[col_name]):
                        try: return float(str(row[col_name]).replace(',', '').replace(' ', '').strip() or default)
                        except: return default
                    return default
                
                rev_q4 = get_val(c_ly_q4) or (get_val(c_rev_10) + get_val(c_rev_last_11) + get_val(c_rev_last_12))
                eps_q3, eps_q4, rev_q3 = get_val(c_eps_q3), get_val(c_eps_q4), get_val(c_ly_q3)
                
                base_eps = eps_q4 if eps_q4 != 0 else (eps_q3 * (rev_q4 / rev_q3) if rev_q3 > 0 else eps_q3)

                db[code] = {
                    "name": str(row[c_name]) if c_name else "未知", 
                    "industry": str(row[c_industry]).strip() if c_industry and pd.notna(row[c_industry]) else "未分類",
                    "rev_last_11": get_val(c_rev_last_11), "rev_last_12": get_val(c_rev_last_12),
                    "rev_this_1": get_val(c_rev_this_1), "rev_this_2": get_val(c_rev_this_2), "rev_this_3": get_val(c_rev_this_3),
                    "base_q_eps": base_eps, "non_op": get_val(c_non_op), "base_q_avg_rev": rev_q4 / 3 if rev_q4 > 0 else 0,
                    "ly_q1_rev": get_val(c_ly_q1), "ly_q2_rev": get_val(c_ly_q2), "ly_q3_rev": rev_q3, "ly_q4_rev": rev_q4,
                    "y1_q1_rev": get_val(c_y1_q1), "y1_q2_rev": get_val(c_y1_q2), "y1_q3_rev": get_val(c_y1_q3), "y1_q4_rev": get_val(c_y1_q4),
                    "eps_q1": get_val(c_eps_q1), "eps_q2": get_val(c_eps_q2), "eps_q3": get_val(c_eps_q3), "eps_q4": get_val(c_eps_q4),
                    "pbr": get_val(c_pbr), "div_years": get_val(c_div_years),
                    "orig_per": get_val(c_orig_per), "annual_yield": get_val(c_annual_yield),
                    "payout": get_val(c_payout), "price": get_val(c_price), "acc_eps": get_val(c_acc_eps),
                    "contract_liab": get_val(c_liab), "contract_liab_qoq": get_val(c_liab_qoq), "declared_div": get_val(c_dec_div)
                }
            return db
            
        stock_db = parse_df(df_general)
        finance_db = parse_df(df_finance)
        
        return {"general": stock_db, "finance": finance_db}
        
    except Exception as e:
        return {"error": str(e)}

cached_data = load_google_sheet_data()
if cached_data and "error" in cached_data:
    st.error(f"檔案解析失敗，請確認連結與權限。錯誤：{cached_data['error']}")
    cached_data = None

# ==========================================
# 側邊欄：登入與動態權限判斷
# ==========================================
st.sidebar.header("⚙️ 系統參數")
current_real_month = datetime.now().month
simulated_month = st.sidebar.slider("月份推演 (檢視當下戰情)", 1, 12, current_real_month)

st.sidebar.divider()
st.sidebar.header("👤 帳號登入")
user_email = st.sidebar.text_input("請輸入您的 Email", placeholder="輸入信箱載入專屬清單...")

current_user = user_email.strip().lower() if user_email else ""
is_admin = False 
user_vip_list, user_row_idx, sheet_auth = "", None, None

if user_email and "google_key" in st.secrets:
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_info(json.loads(st.secrets["google_key"]) if isinstance(st.secrets["google_key"], str) else dict(
