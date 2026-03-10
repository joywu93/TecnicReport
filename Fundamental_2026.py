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

st.title("📊 2026 戰略指揮 (V140 終極透視與會計重構版)")

def get_gspread_client():
    if "google_key" not in st.secrets:
        raise ValueError("找不到 Google 金鑰 (google_key)")
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    key_data = st.secrets["google_key"]
    key_dict = json.loads(key_data) if isinstance(key_data, str) else dict(key_data)
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    return gspread.authorize(creds)

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
    
    headers = {'User-Agent': 'Mozilla/5.0'}
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
    try:
        client = get_gspread_client()
        if not client: return None
        
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
            
        return {"general": parse_df(df_general), "finance": parse_df(df_finance)}
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
        client = get_gspread_client()
        sheet_auth = client.open_by_url(MASTER_GSHEET_URL).worksheet("權限管理")
        auth_data = sheet_auth.get_all_records()
        
        for i, row in enumerate(auth_data):
            if str(row.get('Email', '')).strip().lower() == current_user:
                user_vip_list = str(row.get('VIP清單', ''))
                user_row_idx = i + 2
                admin_flag = str(row.get('管理員', '')).strip()
                if admin_flag in ['是', '可', 'V', 'O', '1', 'true', 'yes', 'Y', 'y']:
                    is_admin = True
                break
                
        if user_row_idx: 
            st.sidebar.success(f"✅ 歡迎回來！已載入專屬清單。{' (👑 管理員權限已解鎖)' if is_admin else ''}")
        else: 
            st.sidebar.info("👋 新朋友！輸入下方清單後按下儲存即可建立專屬帳號。")
            
    except Exception as e: st.sidebar.error("❌ 連線失敗，請確認是否建立「權限管理」分頁。")

watch_list_input = st.sidebar.text_area("📌 您的專屬關注清單 (用空白或逗號隔開)", value=user_vip_list if user_vip_list else "2330, 2317, 2382", height=100)

if user_email and "google_key" in st.secrets:
    if st.sidebar.button("💾 儲存 / 更新清單至雲端", type="secondary"):
        if sheet_auth:
            with st.spinner("正在將名單寫入雲端..."):
                try:
                    if user_row_idx: sheet_auth.update_cell(user_row_idx, 2, watch_list_input)
                    else: sheet_auth.append_row([user_email.strip(), watch_list_input, "否"]) 
                    st.sidebar.success("✅ 清單已成功更新！")
                    time.sleep(1)
                    st.rerun()
                except Exception as e: st.sidebar.error(f"寫入失敗：{e}")

# ==========================================
# 🌟 引擎：官方自動更新專區 
# ==========================================
if is_admin:
    st.sidebar.divider()
    
    with st.sidebar.expander("🤖 盤後股價自動更新 (官方資料)"):
        if st.button("⚡ 一鍵更新全市場股價", type="primary", use_container_width=True):
            with st.status("連線官方伺服器撈取今日全市場收盤價...", expanded=True) as status:
                try:
                    headers_agent = {'User-Agent': 'Mozilla/5.0'}
                    res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=headers_agent, verify=False, timeout=10).json()
                    res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=headers_agent, verify=False, timeout=10).json()
                    
                    price_dict = {}
                    for item in res_twse:
                        if item.get('ClosingPrice'):
                            try: price_dict[str(item.get('Code', '')).strip()] = float(item.get('ClosingPrice').replace(',', ''))
                            except: pass
                    for item in res_tpex:
                        if item.get('Close'):
                            try: price_dict[str(item.get('SecuritiesCompanyCode', '')).strip()] = float(item.get('Close').replace(',', ''))
                            except: pass
                    
                    if not price_dict:
                        status.update(label="⚠️ 無法取得報價。", state="error", expanded=True)
                    else:
                        client = get_gspread_client()
                        worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
                        target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]
                        
                        total_price_updated = 0
                        for ws in target_sheets:
                            all_data = ws.get_all_values()
                            if not all_data: continue
                            headers = all_data[0]
                            code_col_idx, price_col_idx = -1, -1
                            for i, h in enumerate(headers):
                                clean_h = str(h).replace('\n', '').replace(' ', '').strip()
                                if "代號" in clean_h: code_col_idx = i + 1
                                elif "成交" in clean_h and not any(ex in clean_h for ex in ["量", "值", "比", "額", "金", "幅", "差", "均"]): 
                                    price_col_idx = i + 1
                            
                            if code_col_idx != -1 and price_col_idx != -1:
                                cells_to_update = []
                                for row_i, row in enumerate(all_data):
                                    if row_i == 0: continue
                                    code = str(row[code_col_idx-1]).split('.')[0].strip()
                                    if code in price_dict:
                                        cells_to_update.append(gspread.Cell(row=row_i+1, col=price_col_idx, value=price_dict[code]))
                                
                                if cells_to_update:
                                    ws.update_cells(cells_to_update)
                                    total_price_updated += len(cells_to_update)
                                    
                        status.update(label=f"🎉 股價更新成功！共更新 {total_price_updated} 檔股票！", state="complete", expanded=False)
                        st.cache_data.clear() 
                        st.balloons()
                except Exception as e:
                    status.update(label="任務中斷", state="error", expanded=True)
                    st.error(f"❌ 錯誤說明：{e}")

    with st.sidebar.expander("🤖 月營收自動更新 (官方資料)"):
        now = datetime.now()
        lm_month, lm_year = now.month - 1, now.year
        if lm_month == 0: lm_month, lm_year = 12, lm_year - 1
        default_target_ym = f"{str(lm_year)[-2:]}M{str(lm_month).zfill(2)}"
        auto_ym = st.text_input("設定欲更新的營收年月標題 (如: 26M03)", value=default_target_ym)
        
        if st.button("⚡ 一鍵更新營收至試算表", type="primary"):
            with st.status(f"鎖定台灣交易所數據，尋找目標欄位【{auto_ym}】...", expanded=True) as status:
                try:
                    client = get_gspread_client()
                    worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
                    target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]
                    
                    if not target_sheets: status.update(label="任務失敗：找不到相關分頁", state="error", expanded=True)
                    else:
                        target_m_header = auto_ym.strip().upper()
                        y_prefix, m_suffix = int(target_m_header[:2]), int(target_m_header[-2:])
                        roc_year, query_m = (2000 + y_prefix) - 1911, str(m_suffix)
                        
                        df_all_list = []
                        headers_agent = {'User-Agent': 'Mozilla/5.0'}
                        def clean_num(val): return v if re.match(r'^-?\d+(\.\d+)?$', (v := str(val).replace(',', '').replace('%', '').strip())) else ""

                        st.write(f"讀取官方即時公佈榜 (HTML)...")
                        gov_urls = [f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{roc_year}_{query_m}_0.html", f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{roc_year}_{query_m}_1.html", f"https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{roc_year}_{query_m}_0.html", f"https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{roc_year}_{query_m}_1.html"]
                        for url in gov_urls:
                            try:
                                res = requests.get(url, headers=headers_agent, verify=False, timeout=8)
                                if res.status_code == 200 and len(res.text) > 50:
                                    res.encoding = 'big5' 
                                    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', res.text, flags=re.I|re.S):
                                        clean_cols = [re.sub(r'<[^>]*>', '', c).replace('&nbsp;', '').replace('\u3000', '').strip() for c in re.findall(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', r, flags=re.I|re.S)]
                                        if len(clean_cols) >= 7 and (m := re.search(r'(?<!\d)(\d{4})(?!\d)', clean_cols[0])) and clean_num(clean_cols[2]):
                                            df_all_list.append({'公司代號': m.group(1), '當月營收': clean_num(clean_cols[2]), '月增率': clean_num(clean_cols[5]), '年增率': clean_num(clean_cols[6]), '來源優先級': 2})
                            except: pass
                        
                        st.write(f"讀取官方結算總表 (CSV)...")
                        for url in [u.replace('.html', '.csv') for u in gov_urls]:
                            try:
                                res = requests.get(url, headers=headers_agent, verify=False, timeout=8)
                                if res.status_code == 200 and len(res.text) > 100:
                                    res.encoding = 'big5' 
                                    df_gov = pd.read_csv(io.StringIO(res.text), on_bad_lines='skip', header=None, dtype=str)
                                    header_idx = next((i for i in range(min(10, len(df_gov))) if '公司代號' in "".join([str(x) for x in df_gov.iloc[i]]) and '當月營收' in "".join([str(x) for x in df_gov.iloc[i]])), -1)
                                    if header_idx != -1:
                                        df_gov.columns = [str(c).replace('\n', '').replace(' ', '').strip() for c in df_gov.iloc[header_idx]]
                                        df_gov = df_gov.iloc[header_idx+1:].reset_index(drop=True)
                                        for _, row in df_gov.iterrows():
                                            if '公司代號' in row and pd.notna(row['公司代號']):
                                                df_all_list.append({'公司代號': str(row['公司代號']).strip(), '當月營收': clean_num(row.get('當月營收', '')), '月增率': clean_num(row.get('上月比較增減(%)', '')), '年增率': clean_num(row.get('去年同月增減(%)', '')), '來源優先級': 1})
                            except: pass

                        if not df_all_list: status.update(label=f"⚠️ 目前官方尚未公佈 {target_m_header} 月營收", state="error", expanded=True)
                        else:
                            df_early = pd.DataFrame(df_all_list).sort_values('來源優先級').drop_duplicates(subset=['公司代號'], keep='first') 
                            total_updated = 0
                            for ws in target_sheets:
                                all_data = ws.get_all_values()
                                if not all_data: continue
                                headers = all_data[0]
                                target_col_idx, mom_col_idx, yoy_col_idx, code_col_idx = -1, -1, -1, -1
                                for i, header in enumerate(headers):
                                    clean_h = str(header).replace('\n', '').replace(' ', '').replace('\r', '').strip()
                                    if "代號" in clean_h: code_col_idx = i + 1
                                    if target_m_header in clean_h and "單月營收" in clean_h:
                                        if "月增" in clean_h: mom_col_idx = i + 1
                                        elif "年增" in clean_h: yoy_col_idx = i + 1
                                        elif "增" not in clean_h: target_col_idx = i + 1
                                
                                if target_col_idx != -1 and code_col_idx != -1:
                                    row_map = {str(row[code_col_idx-1]).split('.')[0].strip(): i + 1 for i, row in enumerate(all_data) if i > 0 and len(row) >= code_col_idx and str(row[code_col_idx-1]).strip()}
                                    cells_to_update = []
                                    for _, row in df_early.iterrows():
                                        code = str(row['公司代號']).strip()
                                        if code in row_map:
                                            row_idx = row_map[code]
                                            if row['當月營收']: cells_to_update.append(gspread.Cell(row=row_idx, col=target_col_idx, value=round(float(row['當月營收']) / 100000, 2)))
                                            if mom_col_idx != -1 and row['月增率']: cells_to_update.append(gspread.Cell(row=row_idx, col=mom_col_idx, value=float(row['月增率'])))
                                            if yoy_col_idx != -1 and row['年增率']: cells_to_update.append(gspread.Cell(row=row_idx, col=yoy_col_idx, value=float(row['年增率'])))
                                    
                                    if mom_col_idx != -1: cells_to_update.append(gspread.Cell(row=1, col=mom_col_idx, value=f"{target_m_header}單月營收月增(%)"))
                                    if yoy_col_idx != -1: cells_to_update.append(gspread.Cell(row=1, col=yoy_col_idx, value=f"{target_m_header}單月營收年增(%)"))
                                    if cells_to_update:
                                        ws.update_cells(cells_to_update)
                                        total_updated += 1
                                        
                            if total_updated > 0:
                                status.update(label=f"🎉 營收更新成功！已寫入 {total_updated} 張分頁！", state="complete", expanded=False)
                                st.cache_data.clear()
                                st.balloons()
                            else: status.update(label=f"⚠️ 無法更新。請確保試算表中有欄位標題為『{target_m_header}單月營收(億)』", state="error", expanded=True)
                except Exception as e: status.update(label="任務中斷", state="error", expanded=True); st.error(f"❌ 錯誤說明：{e}")

    # ------------------
    # 💡 3. V140 終極季報清洗站 (黑名單過濾 + 會計學重構引擎)
    # ------------------
    with st.sidebar.expander("🤖 季報自動更新 (官方資料)"):
        st.markdown("💡 搭載 V140 黑名單防護網：強制跳過「未實現」假數據！輔以會計重構引擎反推隱藏毛利。")
        target_q = st.text_input("輸入欲更新的季報欄位前綴 (如: 25Q4)", value="25Q4")
        
        if st.button("⚡ 一鍵洗淨並更新季報", type="primary", use_container_width=True):
            with st.status("啟動 V140 終極透視與會計重構引擎...", expanded=True) as status:
                try:
                    try:
                        target_year_roc = str((2000 + int(target_q[:2])) - 1911) 
                        target_q_num = int(target_q[3])
                    except:
                        raise ValueError("欄位前綴格式錯誤，請輸入如 '25Q4' 的格式")

                    headers_agent = {'User-Agent': 'Mozilla/5.0'}
                    
                    st.write(f"1️⃣ 正在從官方 Open API 抓取 {target_year_roc}年 第{target_q_num}季 最新財報...")
                    res_twse_q = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers_agent, verify=False, timeout=15).json()
                    res_tpex_q = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers_agent, verify=False, timeout=15).json()
                    
                    curr_dict = {}
                    
                    # 💡 V140 最強工業級透視萃取函數
                    def extract_val(item_dict, keywords, excludes=None, default=0.0):
                        if excludes is None: excludes = []
                        def clean(s): return str(s).replace(' ', '').replace('（', '(').replace('）', ')')
                        
                        matched_kvs = []
                        for k, v in item_dict.items():
                            ck = clean(k)
                            # 1. 如果符合關鍵字
                            if any(kw in ck for kw in keywords):
                                # 2. 如果包含黑名單字眼 (如: 未實現)，直接拉黑跳過！
                                if any(ex in ck for ex in excludes): 
                                    continue
                                
                                val_str = str(v).strip()
                                # 3. 確保不是空包彈或無效 0
                                if val_str and val_str not in ['None', '']:
                                    val_str = val_str.replace(',', '')
                                    # 處理會計的負數括號 ()
                                    if val_str.startswith('(') and val_str.endswith(')'):
                                        val_str = '-' + val_str[1:-1]
                                    try: 
                                        matched_kvs.append((ck, float(val_str)))
                                    except: pass
                                    
                        if not matched_kvs: return default
                        
                        # 4. 如果找到多個欄位，優先選擇名稱包含「淨額」或「已實現」的終極數值
                        for ck, num in matched_kvs:
                            if '淨額' in ck or '已實現' in ck:
                                if num != 0: return num
                                
                        # 5. 退而求其次，選擇非 0 的數值
                        for ck, num in matched_kvs:
                            if num != 0: return num
                            
                        return 0.0

                    for item in (res_twse_q + res_tpex_q):
                        code = str(item.get('公司代號', '')).strip()
                        item_y = str(item.get('年度', '')).strip()
                        item_q = str(item.get('季別', '')).strip()
                        
                        if not code or item_y != target_year_roc or item_q != str(target_q_num):
                            continue
                            
                        eps_raw = extract_val(item, ['基本每股盈餘', '每股盈餘'])
                        has_eps = eps_raw != 0.0

                        # 💡 V140 嚴格定義會計欄位與黑名單
                        rev = extract_val(item, ['營業收入', '淨收益', '營業收益'])
                        gp = extract_val(item, ['營業毛利', '毛損', '毛利'], excludes=['未實現'])
                        cost = extract_val(item, ['營業成本', '業務成本'])
                        op = extract_val(item, ['營業利益', '營業損失', '營業損益'])
                        exp = extract_val(item, ['營業費用', '業務費用', '推銷費用', '管理費用'])
                        nonop = extract_val(item, ['營業外'])
                        pretax = extract_val(item, ['稅前淨利', '稅前損益', '稅前'])
                        
                        # 🧮 會計學重構引擎：官方沒給的，機器人自己推算出來！
                        if gp == 0:
                            if rev > 0 and cost != 0: gp = rev - cost
                            elif op != 0 and exp != 0: gp = op + exp
                            
                        if op == 0 and gp != 0 and exp != 0:
                            op = gp - exp

                        curr_dict[code] = {
                            "rev": rev, "gp": gp, "op": op, "nonop": nonop, "pretax": pretax,
                            "eps": eps_raw, "has_eps": has_eps
                        }

                    if not curr_dict:
                        status.update(label=f"⚠️ 官方目前尚無 {target_q} 的財報資料！", state="error", expanded=True)
                    else:
                        st.write("2️⃣ 啟動會計重構！正在精準寫入試算表...")
                        client = get_gspread_client()
                        worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
                        target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]
                        
                        total_cells_updated = 0
                        for ws in target_sheets:
                            all_data = ws.get_all_values()
                            if not all_data: continue
                            headers = all_data
