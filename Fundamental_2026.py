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

st.title("📊 2026 戰略指揮 (V144 終極毛利救援版)")

def get_gspread_client():
    if "google_key" not in st.secrets: raise ValueError("找不到 Google 金鑰")
    key_data = st.secrets["google_key"]
    creds = Credentials.from_service_account_info(json.loads(key_data) if isinstance(key_data, str) else dict(key_data), scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def get_realtime_price(code, default_price):
    try:
        p = yf.Ticker(f"{code}.TW").fast_info['last_price']
        if p > 0: return float(p)
    except: pass
    try:
        p = yf.Ticker(f"{code}.TWO").fast_info['last_price']
        if p > 0: return float(p)
    except: pass
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    for sfx in ['.TW', '.TWO']:
        try:
            res = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{code}{sfx}", headers=headers, timeout=2, verify=False).json()
            p = res['chart']['result'][0]['meta']['regularMarketPrice']
            if p > 0: return float(p)
        except: pass
    return default_price

# 💡 V144 HTML 深度救援部隊：專門挖出 Open API 隱藏的毛利
def rescue_html_gp(y_roc, q_num):
    url = "https://mops.twse.com.tw/mops/web/ajax_t163sb04"
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = {}
    for typek in ['sii', 'otc']:
        try:
            r = requests.post(url, data={'encodeURIComponent': '1', 'step': '1', 'firstin': '1', 'off': '1', 'TYPEK': typek, 'year': str(y_roc), 'season': str(q_num)}, headers=headers, timeout=15)
            r.encoding = 'utf8'
            for df in pd.read_html(io.StringIO(r.text)):
                if isinstance(df.columns, pd.MultiIndex): df.columns = [str(c[-1]).strip() for c in df.columns]
                else: df.columns = [str(c).strip() for c in df.columns]
                if '公司代號' not in df.columns: continue
                for _, row in df.iterrows():
                    code = str(row['公司代號']).replace('.0', '').strip()
                    if len(code) != 4 or not code.isdigit(): continue
                    def ex(kws, exclude=[]):
                        bv = 0.0
                        for c in df.columns:
                            ck = str(c).replace(' ', '').replace('（', '(').replace('）', ')')
                            if any(kw in ck for kw in kws) and not any(e in ck for e in exclude):
                                v = str(row[c]).strip()
                                if v and v != 'nan':
                                    v = '-' + v[1:-1].replace(',', '') if v.startswith('(') else v.replace(',', '')
                                    try:
                                        num = float(v)
                                        if num != 0:
                                            bv = num
                                            if '淨額' in ck or '已實現' in ck: return num
                                    except: pass
                        return bv
                    rev = ex(['營業收入', '淨收益'])
                    gp = ex(['營業毛利', '毛損', '毛利'], exclude=['未實現'])
                    op = ex(['營業利益', '營業損失'])
                    # 合併財報防護：保留營收較大者
                    if code in res and rev <= res[code]['rev']: continue
                    res[code] = {'rev': rev, 'gp': gp, 'op': op}
        except: pass
    return res

# ==========================================
# 📊 核心大腦一：一般/成長股預估引擎
# ==========================================
def auto_strategic_model(name, current_month, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, base_q_eps, non_op_ratio, base_q_avg_rev, ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev, y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, recent_payout_ratio, current_price, contract_liab, contract_liab_qoq, acc_eps, declared_div):
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
@st.cache_data(ttl=3600, show_spinner="連線至雙核大數據庫，這只需兩秒鐘...")
def load_google_sheet_data():
    try:
        client = get_gspread_client()
        worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
        df_general = pd.concat([pd.DataFrame(ws.get_all_values()[1:], columns=ws.get_all_values()[0]) for ws in worksheets if "個股總表" in ws.title and len(ws.get_all_values()) > 0], ignore_index=True)
        df_finance = pd.concat([pd.DataFrame(ws.get_all_values()[1:], columns=ws.get_all_values()[0]) for ws in worksheets if "金融股" in ws.title and len(ws.get_all_values()) > 0], ignore_index=True)

        def parse_df(df):
            if df is None or df.empty: return {}
            cols = df.columns.tolist()
            q_cols = [c for c in cols if re.search(r'(\d{2})Q', c)]
            ly = max([re.search(r'(\d{2})Q', c).group(1) for c in q_cols]) if q_cols else "25"
            y1 = str(int(ly) - 1) 

            yp = [int(m.group(1)) for c in cols for m in [re.search(r'(\d{2})M\d{2}單月營收', c.replace(' ', ''))] if m and "增" not in c]
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
                    try: return float(str(row[c_name]).replace(',', '').strip() or d) if c_name and pd.notna(row[c_name]) else d
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
                if str(row.get('管理員', '')).strip() in ['是', '可', 'V', '1', 'true', 'yes', 'Y', 'y']: is_admin = True
                break
        if user_row_idx: st.sidebar.success(f"✅ 歡迎！{' (👑 管理員)' if is_admin else ''}")
        else: st.sidebar.info("👋 輸入清單後儲存即可建立帳號。")
    except Exception as e: st.sidebar.error("❌ 連線失敗。")

watch_list_input = st.sidebar.text_area("📌 您的專屬關注清單", value=user_vip_list if user_vip_list else "2330, 2317", height=100)
if user_email and st.sidebar.button("💾 儲存 / 更新清單", type="secondary") and sheet_auth:
    with st.spinner("寫入中..."):
        if user_row_idx: sheet_auth.update_cell(user_row_idx, 2, watch_list_input)
        else: sheet_auth.append_row([user_email.strip(), watch_list_input, "否"]) 
        st.rerun()

# ==========================================
# 🌟 引擎：官方自動更新專區 
# ==========================================
if is_admin:
    st.sidebar.divider()
    st.sidebar.markdown("### 🤖 官方大數據自動更新中心")
    
    # --- 1. 股價更新 ---
    st.sidebar.markdown("#### 1️⃣ 每日盤後股價")
    if st.sidebar.button("⚡ 一鍵更新全市場股價", type="primary", use_container_width=True):
        with st.status("連線官方伺服器...", expanded=True) as status:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=headers, verify=False, timeout=10).json()
                res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=headers, verify=False, timeout=10).json()
                price_dict = {str(i.get('Code', '')).strip(): float(i.get('ClosingPrice', '0').replace(',', '')) for i in res_twse if i.get('ClosingPrice')}
                price_dict.update({str(i.get('SecuritiesCompanyCode', '')).strip(): float(i.get('Close', '0').replace(',', '')) for i in res_tpex if i.get('Close')})
                
                if not price_dict: status.update(label="⚠️ 無法取得報價。", state="error")
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
                            if cells: ws.update_cells(cells); cnt += len(cells)
                    status.update(label=f"🎉 成功更新 {cnt} 檔！", state="complete")
                    st.cache_data.clear()
            except Exception as e: status.update(label="錯誤", state="error"); st.error(e)

    # --- 2. 月營收更新 ---
    st.sidebar.markdown("#### 2️⃣ 月營收更新")
    now = datetime.now()
    lm_month, lm_year = (now.month - 1) or 12, now.year if now.month > 1 else now.year - 1
    auto_ym = st.sidebar.text_input("設定營收標題 (如: 26M03)", value=f"{str(lm_year)[-2:]}M{str(lm_month).zfill(2)}")
    if st.sidebar.button("⚡ 一鍵更新官方月營收", type="primary", use_container_width=True):
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

                    st.write(f"讀取官方 HTML 與 CSV 資料...")
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
                        try:
                            r2 = requests.get(u+".csv", headers=headers, verify=False, timeout=8)
                            if r2.status_code == 200:
                                r2.encoding = 'big5' 
                                df_gov = pd.read_csv(io.StringIO(r2.text), on_bad_lines='skip', header=None, dtype=str)
                                h_idx = next((i for i in range(min(10, len(df_gov))) if '公司代號' in "".join([str(x) for x in df_gov.iloc[i]])), -1)
                                if h_idx != -1:
                                    df_gov.columns = [str(c).replace('\n', '').replace(' ', '').strip() for c in df_gov.iloc[h_idx]]
                                    for _, row in df_gov.iloc[h_idx+1:].iterrows():
                                        if '公司代號' in row and pd.notna(row['公司代號']):
                                            df_all_list.append({'公司代號': str(row['公司代號']).strip(), '當月營收': cln(row.get('當月營收', '')), '月增率': cln(row.get('上月比較增減(%)', '')), '年增率': cln(row.get('去年同月增減(%)', '')), '來源優先級': 1})
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
                            status.update(label=f"🎉 營收更新成功！已寫入 {cnt} 張分頁！", state="complete", expanded=False)
                            st.cache_data.clear(); st.balloons()
                        else: status.update(label=f"⚠️ 無法更新。請確保試算表中有欄位標題為『{tm_h}單月營收(億)』", state="error", expanded=True)
            except Exception as e: status.update(label="任務中斷", state="error", expanded=True); st.error(f"❌ 錯誤說明：{e}")

    # --- 3. 季報財報清洗 ---
    st.sidebar.markdown("#### 3️⃣ 季報大掃除清洗站")
    target_q = st.sidebar.text_input("季報前綴 (如: 25Q4)", value="25Q4")
    if st.sidebar.button("⚡ 啟動財報清洗防呆引擎", type="primary", use_container_width=True):
        with st.status("執行 V144 雙核驅動救援...", expanded=True) as status:
            try:
                y_roc, q_num = str((2000 + int(target_q[:2])) - 1911), int(target_q[3])
                headers = {'User-Agent': 'Mozilla/5.0'}
                
                st.write("1️⃣ [核心一] 正在從官方 Open API 極速抓取財報...")
                res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False, timeout=15).json()
                res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False, timeout=15).json()
                
                curr_dict = {}
                def ext_val(item, kws, ex=None):
                    if ex is None: ex = []
                    best_val = 0.0
                    for k, v in item.items():
                        ck = str(k).replace(' ', '').replace('（', '(').replace('）', ')')
                        if any(kw in ck for kw in kws) and not any(e in ck for e in ex):
                            v_str = str(v).strip()
                            if v_str and v_str not in ['None', '']:
                                v_str = '-' + v_str[1:-1].replace(',', '') if v_str.startswith('(') and v_str.endswith(')') else v_str.replace(',', '')
                                try:
                                    num = float(v_str)
                                    if num != 0:
                                        best_val = num
                                        if '淨額' in ck or '已實現' in ck: return num
                                except: pass
                    return best_val

                for item in (res_twse + res_tpex):
                    code = str(item.get('公司代號', '')).strip()
                    if not code or str(item.get('年度', '')).strip() != y_roc or str(item.get('季別', '')).strip() != str(q_num): continue
                        
                    eps_raw = ext_val(item, ['基本每股盈餘', '每股盈餘'])
                    has_eps = eps_raw != 0.0

                    rev = ext_val(item, ['營業收入', '淨收益', '營業收益'])
                    gp = ext_val(item, ['營業毛利', '毛損', '毛利'], ex=['未實現'])
                    op = ext_val(item, ['營業利益', '營業損失', '營業損益'])
                    nonop = ext_val(item, ['營業外'])
                    pretax = ext_val(item, ['稅前淨利', '稅前損益', '稅前'])

                    if code in curr_dict and rev <= curr_dict[code]["rev"]: continue
                    curr_dict[code] = {"rev": rev, "gp": gp, "op": op, "nonop": nonop, "pretax": pretax, "eps": eps_raw, "has_eps": has_eps}

                if not curr_dict: status.update(label="⚠️ 官方目前無此季資料", state="error")
                else:
                    st.write("2️⃣ [核心二] 啟動 HTML 深度救援部隊！挖出隱藏的毛利率...")
                    html_dict = rescue_html_gp(y_roc, q_num)
                    
                    # 💡 將救援到的真實毛利合併回主字典
                    for c_code, d_data in html_dict.items():
                        if c_code in curr_dict:
                            if curr_dict[c_code]["gp"] == 0: curr_dict[c_code]["gp"] = d_data["gp"]
                            if curr_dict[c_code]["op"] == 0: curr_dict[c_code]["op"] = d_data["op"]
                            if curr_dict[c_code]["rev"] == 0: curr_dict[c_code]["rev"] = d_data["rev"]

                    st.write("3️⃣ 正在精準寫入試算表並清空季增數殘骸...")
                    worksheets = get_gspread_client().open_by_url(MASTER_GSHEET_URL).worksheets()
                    target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]
                    cnt = 0
                    for ws in target_sheets:
                        data = ws.get_all_values()
                        if not data: continue
                        h = data[0]
                        i_c = next((i for i, x in enumerate(h) if "代號" in str(x)), -1)
                        i_e = next((i for i, x in enumerate(h) if f"{target_q}單季每股盈餘" in str(x).replace(' ','')), -1)
                        i_ae = next((i for i, x in enumerate(h) if "最新累季" in str(x).replace(' ','')), -1)
                        i_gm = next((i for i, x in enumerate(h) if "最新單季毛利率" in str(x).replace(' ','') and "增" not in str(x)), -1)
                        i_gm_q = next((i for i, x in enumerate(h) if "最新單季毛利率季增" in str(x).replace(' ','')), -1)
                        i_om = next((i for i, x in enumerate(h) if "最新單季營益率" in str(x).replace(' ','') and "增" not in str(x)), -1)
                        i_om_q = next((i for i, x in enumerate(h) if "最新單季營益率季增" in str(x).replace(' ','')), -1)
                        i_no = next((i for i, x in enumerate(h) if "業外損益佔" in str(x).replace(' ','')), -1)
                        i_q1 = next((i for i, x in enumerate(h) if f"{target_q[:2]}Q1單季每股盈餘" in str(x).replace(' ','')), -1)
                        i_q2 = next((i for i, x in enumerate(h) if f"{target_q[:2]}Q2單季每股盈餘" in str(x).replace(' ','')), -1)
                        i_q3 = next((i for i, x in enumerate(h) if f"{target_q[:2]}Q3單季每股盈餘" in str(x).replace(' ','')), -1)
                        
                        if i_c != -1 and i_e != -1:
                            cells = []
                            for r, row in enumerate(data):
                                if r == 0: continue
                                code = str(row[i_c]).split('.')[0].strip()
                                if code in curr_dict:
                                    curr = curr_dict[code]
                                    if curr["has_eps"]:
                                        f_eps = curr["eps"]
                                        try:
                                            if q_num == 4 and i_q1!=-1 and i_q2!=-1 and i_q3!=-1: f_eps -= (float(row[i_q1] or 0) + float(row[i_q2] or 0) + float(row[i_q3] or 0))
                                            elif q_num == 3 and i_q1!=-1 and i_q2!=-1: f_eps -= (float(row[i_q1] or 0) + float(row[i_q2] or 0))
                                            elif q_num == 2 and i_q1!=-1: f_eps -= float(row[i_q1] or 0)
                                        except: pass
                                        cells.append(gspread.Cell(row=r+1, col=i_e+1, value=round(f_eps, 2)))
                                        if i_ae != -1: cells.append(gspread.Cell(row=r+1, col=i_ae+1, value=round(curr["eps"], 2)))
                                        
                                    if curr["rev"] > 0:
                                        if curr["gp"] != 0 and i_gm != -1: cells.append(gspread.Cell(row=r+1, col=i_gm+1, value=round((curr["gp"]/curr["rev"])*100, 2)))
                                        elif i_gm != -1: cells.append(gspread.Cell(row=r+1, col=i_gm+1, value=""))
                                        if i_gm_q != -1: cells.append(gspread.Cell(row=r+1, col=i_gm_q+1, value=""))
                                        
                                        if curr["op"] != 0 and i_om != -1: cells.append(gspread.Cell(row=r+1, col=i_om+1, value=round((curr["op"]/curr["rev"])*100, 2)))
                                        elif i_om != -1: cells.append(gspread.Cell(row=r+1, col=i_om+1, value=""))
                                        if i_om_q != -1: cells.append(gspread.Cell(row=r+1, col=i_om_q+1, value=""))
                                        
                                    if curr["pretax"] != 0 and i_no != -1:
                                        cells.append(gspread.Cell(row=r+1, col=i_no+1, value=round((curr["nonop"]/curr["pretax"])*100, 2)))
                            if cells: ws.update_cells(cells); cnt += len(cells)
                    status.update(label=f"🎉 V144 終極雙核驅動完成！共更新 {cnt} 格！", state="complete")
                    st.cache_data.clear()
            except Exception as e: status.update(label="錯誤", state="error"); st.error(e)

# ==========================================
# 4. 執行與呈現
# ==========================================
def render_dataframe(df_source, is_finance=False):
    if df_source.empty: return
    df = df_source.copy()
    if is_finance:
        df = df[["股票名稱", "最新股價", "PBR(股價淨值比)", "前瞻殖利率(%)", "年化殖利率(%)", "前瞻PER", "原始PER", "連續配息次數", "預估今年Q1_EPS", "預估今年度_EPS", "運算配息率(%)", "當季預估均營收(億)"]]
        f_dict = {"最新股價": "{:.2f}", "PBR(股價淨值比)": "{:.2f}", "前瞻殖利率(%)": "{:.2f}%", "年化殖利率(%)": "{:.2f}%", "前瞻PER": "{:.2f}", "原始PER": "{:.2f}", "預估今年Q1_EPS": "{:.2f}", "預估今年度_EPS": "{:.2f}", "運算配息率(%)": "{:.2f}%", "當季預估均營收(億)": "{:.2f}"}
        st.dataframe(df.set_index("股票名稱").style.map(lambda v: 'color: #ff4b4b; font-weight: bold' if isinstance(v, (int, float)) and v >= 5.0 else '', subset=['前瞻殖利率(%)', '年化殖利率(%)']).format(f_dict), height=800, use_container_width=True)
    else:
        df = df.drop(columns=["_ly_qs", "_known_qs", "_pure_est_qs", "_known_q1_months", "_total_est_qs", "logic_note", "payout_note", "套用公式"], errors='ignore')
        df = df[["股票名稱", "最新股價", "當季預估均營收", "季成長率(YoY)%", "前瞻殖利率(%)", "預估今年Q1_EPS", "預估今年度_EPS", "最新累季EPS", "本益比(PER)", "預估年成長率(%)", "運算配息率(%)", "最新季度流動合約負債(億)", "最新季度流動合約負債季增(%)"]]
        f_dict = {"最新股價": "{:.2f}", "當季預估均營收": "{:.2f}", "季成長率(YoY)%": "{:.2f}%", "前瞻殖利率(%)": "{:.2f}%", "預估今年Q1_EPS": "{:.2f}", "預估今年度_EPS": "{:.2f}", "最新累季EPS": "{:.2f}", "本益比(PER)": "{:.2f}", "預估年成長率(%)": "{:.2f}%", "運算配息率(%)": "{:.2f}%", "最新季度流動合約負債(億)": "{:.2f}", "最新季度流動合約負債季增(%)": "{:.2f}%"}
        st.dataframe(df.set_index("股票名稱").style.map(lambda v: 'color: #ff4b4b; font-weight: bold' if isinstance(v, (int, float)) and v >= 4.0 else '', subset=['前瞻殖利率(%)']).format(f_dict), height=600, use_container_width=True)

if cached_data:
    db_gen, db_fin = cached_data.get("general", {}), cached_data.get("finance", {})
    if is_admin:
        t_vip, t_radar, t_fin = st.tabs(["🎯 專屬戰略指揮", "🔍 成長戰略雷達", "🏦 金融存股雷達"])
    else:
        t_vip, t_fin = st.tabs(["🎯 專屬戰略指揮", "🏦 金融存股雷達"])
        t_radar = None
    
    with t_vip:
        if st.button("🚀 執行戰略分析", type="primary"):
            vips = list(dict.fromkeys([c.strip() for c in re.split(r'[;,\s\t]+', watch_list_input) if c.strip()]))
            bar = st.progress(0, "獲取報價...")
            res_list, found = [], 0
            for i, code in enumerate(vips):
                d = db_gen.get(code) or db_fin.get(code)
                if d:
                    found += 1
                    bar.progress((i+1)/len(vips), f"分析: {code} {d['name']}")
                    pr = get_realtime_price(code, d["price"])
                    res_list.append(auto_strategic_model(f"{code} {d['name']}", simulated_month, d.get("rev_last_11",0), d.get("rev_last_12",0), d.get("rev_this_1",0), d.get("rev_this_2",0), d.get("rev_this_3",0), d["base_q_eps"], d.get("non_op",0), d["base_q_avg_rev"], d["ly_q1_rev"], d["ly_q2_rev"], d["ly_q3_rev"], d["ly_q4_rev"], d["y1_q1_rev"], d["y1_q2_rev"], d["y1_q3_rev"], d["y1_q4_rev"], d.get("payout",0), pr, d.get("contract_liab",0), d.get("contract_liab_qoq",0), d.get("acc_eps",0), d.get("declared_div",0)))
            bar.empty()
            if not found: st.warning("未找到股票")
            elif res_list: st.session_state["df_vip"] = pd.DataFrame(res_list)

        if "df_vip" in st.session_state:
            df = st.session_state["df_vip"]
            opts = sorted(df["股票名稱"].tolist())
            vips = list(dict.fromkeys([c.strip() for c in re.split(r'[;,\s\t]+', watch_list_input) if c.strip()]))
            d_idx = next((i for i, o in enumerate(opts) if vips and o.startswith(vips[0])), 0)
            sel = st.selectbox("📌 搜尋：", opts, index=d_idx)
            row = df[df["股票名稱"] == sel].iloc[0]
            st.markdown(f"**股價 {float(row['最新股價']):.2f}** ｜ 殖利率 **{row['前瞻殖利率(%)']}%** ｜ EPS **{row['預估今年度_EPS']}元** ｜ 成長率 **{row['預估年成長率(%)']}%**", unsafe_allow_html=True)
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
                    kws = [k.strip() for k in re.split(r'[;,\s\t]+', ex_kws) if k.strip()]
                    res_list = []
                    for code, d in db_gen.items():
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
                    else: st.success(f"命中 {len(res_list)} 檔！"); render_dataframe(pd.DataFrame(res_list).sort_values(by=['前瞻殖利率(%)', '季成長率(YoY)%'], ascending=[False, False]))

    with t_fin:
        if st.button("🛡️ 啟動金融掃描", type="primary"):
            with st.spinner("篩選中..."):
                res_list = [financial_strategic_model(d["name"], c.strip(), simulated_month, d, simulated_month) for c, d in db_fin.items() if d.get("pbr",0) > 0]
                if not res_list: st.warning("無符合條件的金融股")
                else: render_dataframe(pd.DataFrame(res_list).sort_values(by=['PBR(股價淨值比)', '前瞻殖利率(%)', '連續配息次數'], ascending=[True, False, False]), is_finance=True)

# ✅ 程式碼完整結束
