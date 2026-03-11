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
@st.cache_data(ttl=3600, show_spinner="連線至雙核大數據庫 (V182 強制突破版)...")
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
    st.error(f"檔案解析失敗，請確認連結與權限。錯誤：{cached_data['error']}")
    cached_data = None

# ==========================================
# 側邊欄：登入與動態權限判斷
# ==========================================
if st.sidebar.button("🔄 重新載入最新表單資料 (清除雲端暫存)", type="primary", use_container_width=True):
    clear_cache_and_session()
    st.sidebar.success("✅ 雲端記憶已清除！")
    time.sleep(1)
    force_rerun()

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
                if str(row.get('管理員', '')).strip() in ['是', '可', 'V', '1', 'true', 'yes', 'Y', 'y']: is_admin = True
                break
        if user_row_idx: st.sidebar.success(f"✅ 歡迎！{' (👑 管理員)' if is_admin else ''}")
        else: st.sidebar.info("👋 輸入清單後儲存即可建立帳號。")
    except Exception as e: st.sidebar.error("❌ 連線失敗。")

watch_list_input = st.sidebar.text_area("📌 您的專屬關注清單", value=user_vip_list if user_vip_list else "2330, 2317, 3023", height=100)
if user_email and st.sidebar.button("💾 儲存 / 更新清單", type="secondary") and sheet_auth:
    with st.spinner("寫入中..."):
        if user_row_idx: sheet_auth.update_cell(user_row_idx, 2, watch_list_input)
        else: sheet_auth.append_row([user_email.strip(), watch_list_input, "否"]) 
        clear_cache_and_session()
        force_rerun()

# ==========================================
# 🌟 引擎：官方自動更新專區 
# ==========================================
if is_admin:
    st.sidebar.divider()
    st.sidebar.markdown("### 🤖 大數據自動更新中心")
    
    if st.sidebar.button("⚡ 1️⃣ 盤後股價更新", type="secondary", use_container_width=True):
        with st.status("連線官方伺服器...", expanded=True) as status:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                try: res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=headers, verify=False, timeout=10).json()
                except: res_twse = []
                try: res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=headers, verify=False, timeout=10).json()
                except: res_tpex = []

                price_dict = {}
                if isinstance(res_twse, list):
                    price_dict.update({str(i.get('Code', '')).strip(): float(i.get('ClosingPrice', '0').replace(',', '')) for i in res_twse if i.get('ClosingPrice')})
                if isinstance(res_tpex, list):
                    price_dict.update({str(i.get('SecuritiesCompanyCode', '')).strip(): float(i.get('Close', '0').replace(',', '')) for i in res_tpex if i.get('Close')})
                
                if not price_dict: status.update(label="⚠️ 無法取得報價 (API無回應)。", state="error")
                else:
                    worksheets = get_gspread_client().open_by_url(MASTER_GSHEET_URL).worksheets()
                    target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]
                    cnt = 0
                    for ws in target_sheets:
                        data = ws.get_all_values()
                        if not data: continue
                        c_idx = next((i for i, h in enumerate(data[0]) if "代號" in h), -1)
                        p_idx = next((i for i, h in enumerate(data[0]) if "成交" in h and "量" not in h), -1)
                        if c_idx != -1 and p_idx != -1:
                            cells = [gspread.Cell(row=r+1, col=p_idx+1, value=price_dict[code]) for r, row in enumerate(data) if r > 0 and (code := str(row[c_idx]).split('.')[0].strip()) in price_dict]
                            if cells: ws.update_cells(cells);
                            cnt += len(cells)
                    status.update(label=f"🎉 成功更新 {cnt} 檔！", state="complete")
                    st.cache_data.clear()
            except Exception as e: status.update(label="錯誤", state="error"); st.error(e)

    now = datetime.now()
    lm_month, lm_year = (now.month - 1) or 12, now.year if now.month > 1 else now.year - 1
    auto_ym = st.sidebar.text_input("設定營收標題 (如: 26M03)", value=f"{str(lm_year)[-2:]}M{str(lm_month).zfill(2)}")
    if st.sidebar.button("⚡ 2️⃣ 官方月營收更新", type="secondary", use_container_width=True):
        with st.status(f"鎖定目標欄位【{auto_ym}】...", expanded=True) as status:
            try:
                worksheets = get_gspread_client().open_by_url(MASTER_GSHEET_URL).worksheets()
                target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]
                if not target_sheets: status.update(label="任務失敗：找不到分頁", state="error")
                else:
                    tm_h = auto_ym.strip().upper()
                    y_roc, q_m = (2000 + int(tm_h[:2])) - 1911, str(int(tm_h[-2:]))
                    df_all_list = []
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    def cln(val): return v if re.match(r'^-?\d+(\.\d+)?$', (v := str(val).replace(',', '').replace('%', '').strip())) else ""

                    urls = [f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{y_roc}_{q_m}_0", f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{y_roc}_{q_m}_1", f"https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{y_roc}_{q_m}_0", f"https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{y_roc}_{q_m}_1"]
                    for u in urls:
                        try:
                            r = requests.get(u+".html", headers=headers, verify=False, timeout=8)
                            if r.status_code == 200:
                                r.encoding = 'big5' 
                                for row in re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, flags=re.I|re.S):
                                    cs = [re.sub(r'<[^>]*>', '', c).replace('&nbsp;', '').replace('\u3000', '').strip() for c in re.findall(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', row, flags=re.I|re.S)]
                                    if len(cs) >= 7 and (m := re.search(r'(?<!\d)(\d{4})(?!\d)', cs[0])) and cln(cs[2]):
                                        df_all_list.append({'公司代號': m.group(1), '當月營收': cln(cs[2]), '月增率': cln(cs[5]), '年增率': cln(cs[6]), '來源優先級': 2})
                        except: pass
                    
                    if not df_all_list: status.update(label=f"⚠️ 目前尚未公佈 {tm_h} 營收", state="error", expanded=True)
                    else:
                        df_early = pd.DataFrame(df_all_list).sort_values('來源優先級').drop_duplicates(subset=['公司代號']) 
                        cnt = 0
                        for ws in target_sheets:
                            data = ws.get_all_values()
                            if not data: continue
                            h = data[0]
                            target_col_idx, mom_col_idx, yoy_col_idx, code_col_idx = -1, -1, -1, -1
                            for i, header in enumerate(h):
                                clean_h = str(header).replace('\n', '').replace(' ', '').replace('\r', '').strip()
                                if "代號" in clean_h: code_col_idx = i + 1
                                if tm_h in clean_h and "單月營收" in clean_h:
                                    if "月增" in clean_h: mom_col_idx = i + 1
                                    elif "年增" in clean_h: yoy_col_idx = i + 1
                                    elif "增" not in clean_h: target_col_idx = i + 1
                            
                            if target_col_idx != -1 and code_col_idx != -1:
                                row_map = {str(r[code_col_idx-1]).split('.')[0].strip(): idx + 1 for idx, r in enumerate(data) if idx > 0 and len(r) >= code_col_idx and str(r[code_col_idx-1]).strip()}
                                cells_to_update = []
                                for _, row in df_early.iterrows():
                                    code = str(row['公司代號']).strip()
                                    if code in row_map:
                                        row_idx = row_map[code]
                                        if row['當月營收']: cells_to_update.append(gspread.Cell(row=row_idx, col=target_col_idx, value=round(float(row['當月營收']) / 100000, 2)))
                                        if mom_col_idx != -1 and row['月增率']: cells_to_update.append(gspread.Cell(row=row_idx, col=mom_col_idx, value=float(row['月增率'])))
                                        if yoy_col_idx != -1 and row['年增率']: cells_to_update.append(gspread.Cell(row=row_idx, col=yoy_col_idx, value=float(row['年增率'])))
                                
                                if mom_col_idx != -1: cells_to_update.append(gspread.Cell(row=1, col=mom_col_idx, value=f"{tm_h}單月營收月增(%)"))
                                if yoy_col_idx != -1: cells_to_update.append(gspread.Cell(row=1, col=yoy_col_idx, value=f"{tm_h}單月營收年增(%)"))
                                if cells_to_update:
                                    ws.update_cells(cells_to_update)
                                    cnt += 1
                                    
                        if cnt > 0:
                            status.update(label=f"🎉 營收成功寫入 {cnt} 張分頁！", state="complete", expanded=False)
                            st.cache_data.clear()
                            st.balloons()
                        else: status.update(label=f"⚠️ 無法更新", state="error", expanded=True)
            except Exception as e: status.update(label="任務中斷", state="error", expanded=True); st.error(e)

# ==========================================
# 4. 執行與呈現
# ==========================================
def render_dataframe(df_source, is_finance=False, is_single=False):
    if df_source is None or df_source.empty: return
    
    try:
        df = df_source.copy().reset_index(drop=True)
        df = df.loc[:, ~df.columns.duplicated()]
        if "股票名稱" in df.columns:
            df["股票名稱"] = df["股票名稱"].astype(str).str.strip()
            df = df.drop_duplicates(subset=["股票名稱"], keep='first')
        
        if is_finance:
            cols = ["股票名稱", "最新股價", "PBR(股價淨值比)", "前瞻殖利率(%)", "年化殖利率(%)", "前瞻PER", "原始PER", "連續配息次數", "預估今年Q1_EPS", "預估今年度_EPS", "運算配息率(%)", "當季預估均營收(億)"]
        else:
            cols = ["股票名稱", "最新股價", "當季預估均營收", "季成長率(YoY)%", "前瞻殖利率(%)", "預估今年Q1_EPS", "預估今年度_EPS", "最新累季EPS", "本益比(PER)", "預估年成長率(%)", "運算配息率(%)", "最新季度流動合約負債(億)", "最新季度流動合約負債季增(%)"]
            
        df = df[[c for c in cols if c in df.columns]]
        
        for c in df.columns:
            if c != "股票名稱":
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
                
        calc_height = None if is_single else (800 if is_finance else 600)
        threshold = 5.0 if is_finance else 4.0
        
        f_dict = {}
        for c in df.columns:
            if c == "股票名稱": continue
            if "(%)" in c or "%" in c: f_dict[c] = "{:.2f}%"
            elif "次數" in c: f_dict[c] = "{:.0f}"
            else: f_dict[c] = "{:.2f}"
            
        def style_yield(s):
            styles = []
            for v in s:
                try:
                    if float(v) >= threshold: styles.append('color: #ff4b4b; font-weight: bold')
                    else: styles.append('')
                except: styles.append('')
            return styles

        df_clean = df.set_index("股票名稱")
        
        try:
            if '前瞻殖利率(%)' in df_clean.columns:
                styler = df_clean.style.apply(style_yield, subset=['前瞻殖利率(%)']).format(f_dict)
            else:
                styler = df_clean.style.format(f_dict)
            _ = styler.to_html() 
            st.dataframe(styler, height=calc_height, use_container_width=True)
        except Exception:
            df_safe = df_clean.copy()
            for c in df_safe.columns:
                if "(%)" in c or "%" in c: df_safe[c] = df_safe[c].apply(lambda x: f"{x:.2f}%")
                elif "次數" in c: df_safe[c] = df_safe[c].apply(lambda x: f"{int(x)}")
                else: df_safe[c] = df_safe[c].apply(lambda x: f"{x:.2f}")
            st.dataframe(df_safe, height=calc_height, use_container_width=True)
    
    except Exception:
        display_cols = [c for c in df_source.columns if not str(c).startswith('_')]
        st.dataframe(df_source[display_cols], use_container_width=True)

if cached_data:
    db_gen, db_fin = cached_data.get("general", {}), cached_data.get("finance", {})
    if is_admin:
        t_vip, t_radar, t_fin = st.tabs(["🎯 專屬戰略指揮", "🔍 成長戰略雷達", "🏦 金融存股雷達"])
    else:
        t_vip, t_fin = st.tabs(["🎯 專屬戰略指揮", "🏦 金融存股雷達"])
        t_radar = None
    
    with t_vip:
        c1, c2 = st.columns([1, 2])
        with c1:
            if st.button("🚀 執行戰略分析", type="primary", use_container_width=True):
                vips = list(dict.fromkeys([c.strip() for c in re.split(r'[;,\s\t]+', watch_list_input) if c.strip()]))
                bar = st.progress(0, "獲取報價...")
                res_list, found = [], 0
                for i, code in enumerate(vips):
                    d = db_gen.get(code) or db_fin.get(code)
                    if d:
                        found += 1
                        bar.progress((i+1)/len(vips), f"分析: {code}")
                        pr = get_realtime_price(code, d["price"])
                        res_list.append(auto_strategic_model(f"{code} {d['name']}", simulated_month, d.get("rev_last_11",0), d.get("rev_last_12",0), d.get("rev_this_1",0), d.get("rev_this_2",0), d.get("rev_this_3",0), d["base_q_eps"], d.get("non_op",0), d["base_q_avg_rev"], d["ly_q1_rev"], d["ly_q2_rev"], d["ly_q3_rev"], d["ly_q4_rev"], d["y1_q1_rev"], d["y1_q2_rev"], d["y1_q3_rev"], d["y1_q4_rev"], d.get("payout",0), pr, d.get("contract_liab",0), d.get("contract_liab_qoq",0), d.get("acc_eps",0), d.get("declared_div",0)))
                bar.empty()
                if not found: st.warning("未找到股票")
                elif res_list: st.session_state["df_vip"] = pd.DataFrame(res_list)
        
        if "df_vip" in st.session_state:
            df = st.session_state["df_vip"]
            if df is not None and not df.empty:
                valid_df = df[df["股票名稱"].astype(bool) & df["股票名稱"].notna() & (df["股票名稱"] != "")]
                opts = sorted([str(x) for x in valid_df["股票名稱"].unique() if str(x).strip()])
                vips = list(dict.fromkeys([c.strip() for c in re.split(r'[;,\s\t]+', watch_list_input) if c.strip()]))
                
                d_idx = 0
                if vips and opts:
                    try: d_idx = next((i for i, o in enumerate(opts) if str(o).startswith(vips[0])), 0)
                    except: pass
                
                with c1:
                    sel = st.selectbox("📌 搜尋關注個股：", opts, index=d_idx) if opts else None
                    if sel:
                        row_df = df[df["股票名稱"] == sel].copy()
                        
                        try:
                            row_list = row_df.to_dict('records')
                        except Exception:
                            row_list = []
                            
                        if row_list: 
                            try:
                                row = row_list[0] 
                                
                                def get_safe_float(val):
                                    if val is None: return 0.0
                                    if isinstance(val, (str, int, float)):
                                        try: return float(str(val).replace(',', '').replace('%', ''))
                                        except: return 0.0
                                    return 0.0
                                    
                                liab_value = get_safe_float(row.get('最新季度流動合約負債(億)', 0)) 
                                liab_qoq = get_safe_float(row.get('最新季度流動合約負債季增(%)', 0))
                                safe_price = get_safe_float(row.get('最新股價', 0))
                                safe_yield = get_safe_float(row.get('前瞻殖利率(%)', 0))
                                safe_per = get_safe_float(row.get('本益比(PER)', 0))
                                safe_eps = get_safe_float(row.get('預估今年度_EPS', 0))
                                safe_grow = get_safe_float(row.get('預估年成長率(%)', 0))
                                
                                st.markdown(
                                    f"**股價 {safe_price:.2f}元** ｜ "
                                    f"殖利率 **{safe_yield:.2f}%**<br>"
                                    f"PER **{safe_per:.2f}** ｜ "
                                    f"EPS **{safe_eps:.2f}元** ｜ "
                                    f"成長率 **{safe_grow:.2f}%** ｜ "
                                    f"📈 合約負債 **{liab_value:.2f}億 ({liab_qoq:.2f}%)**",
                                    unsafe_allow_html=True
                                )
                                if is_admin:
                                    with st.expander("📝 點此查看預估邏輯"):
                                        st.write(str(row.get('_logic_note', '無紀錄')))
                            except Exception: pass
                
                with c2:
                    if sel and row_list: 
                        try:
                            d_viz = []
                            for i, q in enumerate(["Q1", "Q2", "Q3", "Q4"]):
                                def clean_val_list(lst, idx):
                                    try:
                                        if not isinstance(lst, list): return 0.0
                                        v = lst[idx]
                                        fv = float(v)
                                        return fv if not math.isnan(fv) and not math.isinf(fv) else 0.0
                                    except: return 0.0
                                    
                                d_viz.append({"季度": q, "類別": "A.去年", "項目": "去年實際", "營收(億)": clean_val_list(row.get("_ly_qs", [0,0,0,0]), i)})
                                
                                if q == "Q1":
                                    m_revs = [clean_val_list(row.get("_known_q1_months", [0,0,0]), x) for x in range(3)]
                                    if m_revs[0] > 0: d_viz.append({"季度": q, "類別": "B.今年", "項目": "1月營收", "營收(億)": m_revs[0]})
                                    if m_revs[1] > 0: d_viz.append({"季度": q, "類別": "B.今年", "項目": "2月營收", "營收(億)": m_revs[1]})
                                    if m_revs[2] > 0: d_viz.append({"季度": q, "類別": "B.今年", "項目": "3月營收", "營收(億)": m_revs[2]})
                                    if sum(m_revs) == 0: d_viz.append({"季度": q, "類別": "B.今年", "項目": "已公布", "營收(億)": 0}) 
                                else:
                                    d_viz.append({"季度": q, "類別": "B.今年", "項目": "已公布", "營收(億)": clean_val_list(row.get("_known_qs", [0,0,0,0]), i)})
                                    
                                d_viz.append({"季度": q, "類別": "C.預估", "項目": "預估標竿", "營收(億)": clean_val_list(row.get("_total_est_qs", [0,0,0,0]), i)})
                                
                            bars = alt.Chart(pd.DataFrame(d_viz)).mark_bar().encode(
                                x=alt.X('類別:N', axis=None), 
                                y=alt.Y('營收(億):Q', title=None), 
                                color=alt.Color('項目:N', legend=alt.Legend(title=None, orient="bottom"), 
                                                scale=alt.Scale(domain=["去年實際", "1月營收", "2月營收", "3月營收", "已公布", "預估標竿"], 
                                                                range=["#004c6d", "#cce6ff", "#66b2ff", "#0073e6", "#3399ff", "#ff4b4b"])),
                                order=alt.Order('項目:N', sort='ascending'),
                                tooltip=alt.value(None),
                                column=alt.Column('季度:N', header=alt.Header(title=None, labelOrient='bottom'))
                            ).properties(width=55, height=180)
                            st.altair_chart(bars, use_container_width=False) 
                        except: pass

                st.divider()
                if sel and not row_df.empty:
                    st.markdown(f"### 🎯 【{sel}】專屬戰情報表")
                    render_dataframe(row_df, is_single=True)
                    st.divider()
                
                st.markdown("### 📋 關注清單總表")
                render_dataframe(df.sort_values(by=['季成長率(YoY)%', '前瞻殖利率(%)'], ascending=[False, False]))

    if t_radar:
        with t_radar:
            st.markdown("##### 🚀 成長動能條件")
            s1 = st.checkbox("☑️ 策略一：年底升溫")
            s2 = st.checkbox("☑️ 策略二：淡季突破")
            s3 = st.checkbox("☑️ 策略三：Q2大爆發")
            c_r1, c_r2 = st.columns(2)
            with c_r1:
                f_grow = st.slider("穩健成長 (年增率 > %)", -10, 100, 10)
                f_per = st.slider("便宜價 (本益比 <)", 5, 50, 50)
            with c_r2: f_y = st.slider("高殖利率 (大於 %)", 0.0, 15.0, 4.0)
            
            ex_kws = st.text_input("🚫 排除關鍵字 (如: KY, 航運)")
            
            if st.button("📡 全市場掃描", type="primary"):
                with st.spinner("掃描中..."):
                    # ✅ V182 新增：自動過濾營建、金融、證券類股防線
                    exclude_codes = {
                        '1316', '1436', '1438', '1439', '1442', '1453', '1456', '1472', '1805', '1808', '2442', '2501', '2504', '2505', '2506', '2509', '2511', '2515', '2516', '2520', '2524', '2527', '2528', '2530', '2534', '2535', '2536', '2537', '2538', '2539', '2540', '2542', '2543', '2545', '2546', '2547', '2548', '2596', '2597', '2718', '2923', '3052', '3056', '3188', '3266', '3489', '3512', '3521', '3703', '4113', '4416', '4907', '5206', '5213', '5324', '5455', '5508', '5511', '5512', '5514', '5515', '5516', '5519', '5520', '5521', '5522', '5523', '5525', '5529', '5531', '5533', '5534', '5543', '5546', '5547', '5548', '6171', '6177', '6186', '6198', '6212', '6219', '6264', '8080', '8424', '9906', '9946',
                        '2880', '2881', '2882', '2883', '2884', '2885', '2886', '2887', '2889', '2890', '2891', '2892', '5880', '2816', '2832', '2850', '2851', '2852', '2867', '5878', '2801', '2812', '2820', '2834', '2836', '2838', '2845', '2849', '2897', '5876',
                        '6016', '6020', '2855', '6015', '6005', '6026', '6024', '6023', '6021', '5864'
                    }
                    
                    kws = [k.strip() for k in re.split(r'[;,\s\t]+', ex_kws) if k.strip()]
                    res_list = []
                    for code, d in db_gen.items():
                        # 若代碼在排除清單中，直接跳過不掃描
                        if code in exclude_codes: continue
                        if kws and any((k in d["name"] or code.startswith(k)) for k in kws): continue
                        
                        r = auto_strategic_model(f"{code} {d['name']}", simulated_month, d.get("rev_last_11",0), d.get("rev_last_12",0), d.get("rev_this_1",0), d.get("rev_this_2",0), d.get("rev_this_3",0), d["base_q_eps"], d.get("non_op",0), d["base_q_avg_rev"], d["ly_q1_rev"], d["ly_q2_rev"], d["ly_q3_rev"], d["ly_q4_rev"], d["y1_q1_rev"], d["y1_q2_rev"], d["y1_q3_rev"], d["y1_q4_rev"], d.get("payout",0), d["price"], d.get("contract_liab",0), d.get("contract_liab_qoq",0), d.get("acc_eps",0), d.get("declared_div",0))
                        
                        ly_q1_avg, ly_q2 = r["_ly_qs"][0]/3, r["_ly_qs"][1]
                        ly_11_12_avg = r["_total_est_qs"][0]/3 
                        est_q1 = r["當季預估均營收"] * 3
                        est_q2, est_q2_avg = r["_total_est_qs"][1], r["_total_est_qs"][1]/3
                        best_q1_avg = (r["_known_qs"][0] if simulated_month >= 4 else est_q1)/3

                        if s1 and not (ly_11_12_avg > ly_q1_avg): continue
                        if s2 and not (est_q1 > ly_q2): continue
                        if s3 and not (est_q2_avg >= best_q1_avg and est_q2 > ly_q2): continue
                        if r["預估年成長率(%)"] < f_grow or (f_y > 0 and r["前瞻殖利率(%)"] < f_y) or (f_per < 50 and (r["本益比(PER)"] <= 0 or r["本益比(PER)"] > f_per)): continue
                        res_list.append(r)
                    if not res_list: st.warning("無符合條件股票")
                    else: st.success(f"命中 {len(res_list)} 檔！");
                    render_dataframe(pd.DataFrame(res_list).sort_values(by=['前瞻殖利率(%)', '季成長率(YoY)%'], ascending=[False, False]))

    with t_fin:
        if st.button("🛡️ 啟推金融掃描", type="primary"):
            with st.spinner("篩選中..."):
                res_list = [financial_strategic_model(d["name"], c.strip(), simulated_month, d, simulated_month) for c, d in db_fin.items() if d.get("pbr",0) > 0]
                if not res_list: st.warning("無符合條件的金融股")
                else: render_dataframe(pd.DataFrame(res_list).sort_values(by=['PBR(股價淨值比)', '前瞻殖利率(%)', '連續配息次數'], ascending=[True, False, False]), is_finance=True)

# ✅ 程式碼完整結束
