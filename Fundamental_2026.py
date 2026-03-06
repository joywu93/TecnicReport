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
# 網頁基本設定 & 響應式 CSS (手機版 RWD 美化)
# ==========================================
st.set_page_config(page_title="2026 戰略指揮", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    /* 🖥️ 電腦版基礎字體大小 */
    h1 { font-size: 1.8rem !important; margin-bottom: 0px !important; }
    h2 { font-size: 1.4rem !important; margin-bottom: 0px !important; }
    h3 { font-size: 1.2rem !important; margin-bottom: 0.5rem !important; } 
    p { margin-bottom: 0.2rem !important; font-size: 0.95rem !important; }
    .block-container { padding-top: 2.5rem !important; padding-bottom: 1rem !important; }
    
    /* 📱 手機版專屬縮放 (當螢幕寬度小於 768px 時自動觸發) */
    @media (max-width: 768px) {
        h1 { font-size: 1.5rem !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.05rem !important; margin-bottom: 0.2rem !important; } 
        p { font-size: 0.85rem !important; }
        .block-container { padding-top: 1.5rem !important; }
    }

    ::-webkit-scrollbar { width: 14px !important; height: 14px !important; }
    ::-webkit-scrollbar-track { background: #e0e0e0; border-radius: 6px; }
    ::-webkit-scrollbar-thumb { background: #888; border-radius: 6px; border: 2px solid #e0e0e0; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }
    div[data-testid="stDataFrame"] div { scrollbar-width: auto; }
    </style>
""", unsafe_allow_html=True)

# 🚨🚨🚨 系統核心參數 🚨🚨🚨
# 1. 寫死網址：已為您專屬綁定！
MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

# 2. 管理員信箱清單 (只有這些信箱登入，才能看到底層邏輯與更新按鈕)
ADMIN_EMAILS = ["joywu4093@gmail.com", "joywu93@gmail.com", "joywu93@kimo.com"]

st.title("📊 2026 戰略指揮 (V106 專屬綁定版)")

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
            res = requests.get(url, headers=headers, timeout=2).json()
            p = res['chart']['result'][0]['meta']['regularMarketPrice']
            if p and p > 0: return float(p)
        except: pass
    return default_price

# ==========================================
# 1. 核心大腦：完美復刻 VBA (滾動式預測雙軌引擎)
# ==========================================
def auto_strategic_model(name, current_month, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, base_q_eps, non_op_ratio, base_q_avg_rev, ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev, y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, recent_payout_ratio, current_price, contract_liab, contract_liab_qoq, acc_eps, declared_div):
    
    if current_month <= 1:
        sim_rev_1, sim_rev_2, sim_rev_3 = 0, 0, 0
    elif current_month == 2:
        sim_rev_1 = rev_this_1
        sim_rev_2, sim_rev_3 = 0, 0
    elif current_month == 3:
        sim_rev_1, sim_rev_2 = rev_this_1, rev_this_2
        sim_rev_3 = 0
    else:
        sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, rev_this_3

    actual_known_q1 = sum([v for v in [sim_rev_1, sim_rev_2, sim_rev_3] if v > 0])
    
    static_q1_avg = (rev_last_11 + rev_last_12) / 2
    static_q1_est_total = static_q1_avg * 3
    q1_yoy = ((static_q1_est_total - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0
    est_q1_eps_display = base_q_eps * (1 - (non_op_ratio / 100)) * (static_q1_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0

    if current_month <= 1:
        dynamic_base_avg = (rev_last_11 + rev_last_12) / 2
        formula_note = "推演1月(全未知)：Q1基準=上年11,12月均值；Q2後同此推算。"
    elif current_month == 2:
        dynamic_base_avg = sim_rev_1 * 0.9 if sim_rev_1 > 0 else (rev_last_11 + rev_last_12) / 2
        formula_note = "推演2月(知1月)：Q1基準=上年11,12月均值；Q2後採(1月×0.9)推算。"
    elif current_month == 3:
        if sim_rev_2 > 0:
            dynamic_base_avg = (sim_rev_1 * 2 + sim_rev_2) / 3
            formula_note = "推演3月(知1,2月)：Q1基準=上年11,12月均值；Q2後採(1月x2+2月)/3推算。"
        else:
            dynamic_base_avg = sim_rev_1
            formula_note = "推演3月(無2月資料)：Q1基準=上年11,12月均值；Q2後採1月推算。"
    else:
        dynamic_base_avg = (sim_rev_1 + sim_rev_2 + sim_rev_3) / 3
        formula_note = "推演4月+(知Q1全)：Q1基準=上年11,12月均值；Q2後採Q1實際均值推算。"

    est_q2_rev_total = dynamic_base_avg * 3
    dynamic_q1_total_for_calc = dynamic_base_avg * 3
    est_h1_rev_total = dynamic_q1_total_for_calc + est_q2_rev_total
    
    dynamic_q_eps = base_q_eps * (1 - (non_op_ratio / 100)) * (dynamic_base_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0
    est_h1_eps = dynamic_q_eps * 2

    y1_h1, y1_h2 = y1_q1_rev + y1_q2_rev, y1_q3_rev + y1_q4_rev
    y2_h1, y2_h2 = ly_q1_rev + ly_q2_rev, ly_q3_rev + ly_q4_rev
    avg_2yr_h1, avg_2yr_h2 = (y1_h1 + y2_h1) / 2, (y1_h2 + y2_h2) / 2
    avg_2yr_q3, avg_2yr_q4 = (y1_q3_rev + ly_q3_rev) / 2, (y1_q4_rev + ly_q4_rev) / 2
    avg_2yr_h2_calc = avg_2yr_q3 + avg_2yr_q4

    if avg_2yr_h1 > 0:
        multiplier = 1 + (avg_2yr_h2 / avg_2yr_h1)
        est_total_rev = est_h1_rev_total * multiplier
        est_full_year_eps = est_h1_eps * multiplier
        est_h2_rev_total = est_total_rev - est_h1_rev_total
        
        if avg_2yr_h2_calc > 0:
            est_q3_rev_total = est_h2_rev_total * (avg_2yr_q3 / avg_2yr_h2_calc)
            est_q4_rev_total = est_h2_rev_total * (avg_2yr_q4 / avg_2yr_h2_calc)
        else:
            est_q3_rev_total = est_h2_rev_total / 2
            est_q4_rev_total = est_h2_rev_total / 2
    else:
        est_total_rev, est_full_year_eps, est_q3_rev_total, est_q4_rev_total = est_h1_rev_total, est_h1_eps, 0, 0

    ly_total_rev = y2_h1 + y2_h2
    est_annual_yoy = ((est_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0
    
    current_price = float(current_price) if current_price else 0.0
    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    
    if recent_payout_ratio >= 100:
        calc_payout_ratio = 90
        payout_note = "(配息>100%，以90%計)"
    elif recent_payout_ratio <= 0:
        calc_payout_ratio = 50
        payout_note = "(無配息資料，以50%計)"
    else:
        calc_payout_ratio = recent_payout_ratio
        payout_note = ""
        
    est_annual_dividend = est_full_year_eps * (calc_payout_ratio / 100)
    
    if declared_div > 0 and current_price > 0:
        if declared_div < (est_annual_dividend * 0.45):
            forward_yield = (est_annual_dividend / current_price) * 100
            payout_note += "(多次配息，採預估EPS計算)"
        else:
            forward_yield = (declared_div / current_price) * 100
            payout_note += "(採宣告股利計算)"
    elif current_price > 0:
        forward_yield = (est_annual_dividend / current_price) * 100
    else:
        forward_yield = 0

    return {
        "股票名稱": name, "最新股價": round(current_price, 2), 
        "logic_note": formula_note, 
        "payout_note": payout_note, 
        "當季預估均營收": round(dynamic_base_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "預估今年Q1_EPS": round(est_q1_eps_display, 2), 
        "預估今年度_EPS": round(est_full_year_eps, 2), "最新累季EPS": acc_eps, "本益比(PER)": round(est_per, 2),         
        "預估年成長率(%)": round(est_annual_yoy, 2), "運算配息率(%)": calc_payout_ratio,
        "最新季度流動合約負債(億)": contract_liab, "最新季度流動合約負債季增(%)": contract_liab_qoq,
        "_ly_qs": [ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev], 
        "_known_qs": [actual_known_q1, 0, 0, 0],
        "_known_q1_months": [max(0, sim_rev_1), max(0, sim_rev_2), max(0, sim_rev_3)],
        "_total_est_qs": [static_q1_est_total, est_q2_rev_total, est_q3_rev_total, est_q4_rev_total]
    }

# ==========================================
# 2. 側邊欄：登入與自動記憶清單系統
# ==========================================
st.sidebar.header("⚙️ 系統參數")
current_real_month = datetime.now().month
simulated_month = st.sidebar.slider("月份推演 (檢視當下戰情)", 1, 12, current_real_month)

st.sidebar.divider()
st.sidebar.header("👤 帳號登入")
user_email = st.sidebar.text_input("請輸入您的 Email", placeholder="輸入信箱載入專屬清單...")

admin_list = []
if isinstance(ADMIN_EMAILS, list):
    admin_list = [str(e).strip().lower() for e in ADMIN_EMAILS]
elif isinstance(ADMIN_EMAILS, str):
    admin_list = [str(e).strip().lower() for e in ADMIN_EMAILS.split(',')]

current_user = user_email.strip().lower() if user_email else ""
is_admin = (current_user != "") and (current_user in admin_list)

user_vip_list = ""
user_row_idx = None
sheet_auth = None

if user_email and "google_key" in st.secrets:
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        key_dict = json.loads(st.secrets["google_key"]) if isinstance(st.secrets["google_key"], str) else dict(st.secrets["google_key"])
        creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        sheet_auth = client.open_by_url(MASTER_GSHEET_URL).worksheet("權限管理")
        auth_data = sheet_auth.get_all_records()
        
        for i, row in enumerate(auth_data):
            if str(row.get('Email', '')).strip().lower() == current_user:
                user_vip_list = str(row.get('VIP清單', ''))
                user_row_idx = i + 2 
                break
                
        if user_row_idx:
            st.sidebar.success(f"✅ 歡迎回來！已載入您的專屬清單。")
        else:
            st.sidebar.info("👋 新朋友！輸入下方清單後按下儲存即可建立專屬帳號。")
            
    except Exception as e:
        st.sidebar.error("❌ 連線失敗，請確認是否建立「權限管理」分頁。")

watch_list_input = st.sidebar.text_area(
    "📌 您的專屬關注清單 (用空白或逗號隔開)", 
    value=user_vip_list if user_vip_list else "2330, 2317, 2382", 
    height=100
)

if user_email and "google_key" in st.secrets:
    if st.sidebar.button("💾 儲存 / 更新清單至雲端", type="secondary"):
        if sheet_auth:
            with st.spinner("正在將名單寫入雲端..."):
                try:
                    if user_row_idx:
                        sheet_auth.update_cell(user_row_idx, 2, watch_list_input)
                        st.sidebar.success("✅ 清單已成功更新！下次登入將自動讀取。")
                    else:
                        sheet_auth.append_row([user_email.strip(), watch_list_input])
                        st.sidebar.success("✅ 帳號建立成功！您的清單已永久儲存。")
                        time.sleep(1)
                        st.rerun()
                except Exception as e:
                    st.sidebar.error(f"寫入失敗：{e}")

# ==========================================
# 🌟 引擎一：月營收自動更新 (僅管理員可見)
# ==========================================
if is_admin:
    st.sidebar.divider()
    with st.sidebar.expander("🤖 月營收自動更新 (僅管理員可用)"):
        now = datetime.now()
        lm_month = now.month - 1
        lm_year = now.year
        if lm_month == 0:
            lm_month = 12
            lm_year -= 1
        default_target_ym = f"{str(lm_year)
