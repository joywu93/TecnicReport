import streamlit as st
import pandas as pd
import altair as alt
import re
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import numpy as np
from datetime import datetime

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

st.title("📊 2026 戰略指揮 (V186 終極安息穩定版)")

def clear_cache_and_session():
    st.cache_data.clear()
    for key in list(st.session_state.keys()):
        del st.session_state[key]

def get_gspread_client():
    if "google_key" not in st.secrets: raise ValueError("找不到 Google 金鑰")
    key_data = st.secrets["google_key"]
    creds = Credentials.from_service_account_info(json.loads(key_data) if isinstance(key_data, str) else dict(key_data), scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

# ==========================================
# 📊 核心大腦一：一般/成長股預估引擎
# ==========================================
def auto_strategic_model(name, current_month, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, base_q_eps, non_op_ratio, base_q_avg_rev, ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev, y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, recent_payout_ratio, current_price, contract_liab, contract_liab_qoq, acc_eps, declared_div):
    try: current_price = float(current_price) if not math.isnan(float(current_price)) else 0.0
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
@st.cache_data(ttl=3600, show_spinner="🚀 讀取 Google Sheet 資料庫...")
def fetch_gsheet_data_v186():
    try:
        client = get_gspread_client()
        worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
        
        gen_dfs, fin_dfs = [], []
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
                    if not val_str or val_str.lower() in ['-', 'nan', 'inf', '-inf', 'infinity', '#n/a', 'n/a', '#div/0!']: return d
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

# 初始化載入快取資料
cached_data = fetch_gsheet_data_v186()
if cached_data and "error" in cached_data:
    st.error(f"檔案解析失敗，請確認連結與權限。錯誤：{cached_data['error']}")
    db_gen, db_fin = {}, {}
else:
    db_gen = cached_data.get("general", {}) if cached_data else {}
    db_fin = cached_data.get("finance", {}) if cached_data else {}

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
        if user_row_idx: st.sidebar.success(f"✅ 歡迎登入戰情室！")
        else: st.sidebar.info("👋 輸入清單後儲存即可建立帳號。")
    except Exception as e: st.sidebar.error("❌ 連線失敗。")

watch_list_input = st.sidebar.text_area("📌 您的專屬關注清單", value=user_vip_list if user_vip_list else "2330, 2317, 3023", height=100)
if user_email and st.sidebar.button("💾 儲存 / 更新清單", type="secondary") and sheet_auth:
    with st.spinner("寫入中..."):
        if user_row_idx: sheet_auth.update_cell(user_row_idx, 2, watch_list_input)
        else: sheet_auth.append_row([user_email.strip(), watch_list_input, "否"]) 
        try: st.rerun()
        except: st.experimental_rerun()

# ==========================================
# 4. 執行與呈現 (V186 物理級防爆矩陣渲染)
# ==========================================
def render_dataframe(df_source, is_finance=False, is_single=False):
    if df_source is None or df_source.empty: return
    
    # 清理資料與索引
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
    
    # 全面數值化排毒
    for c in df.columns:
        if c != "股票名稱":
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            
    calc_height = None if is_single else (800 if is_finance else 600)
    threshold = 5.0 if is_finance else 4.0
    
    f_dict = {c: "{:.2f}%" if "(%)" in c or "%" in c else ("{:.0f}" if "次數" in c else "{:.2f}") for c in df.columns if c != "股票名稱"}
    df_clean = df.set_index("股票名稱")
    
    # 🩸 核心手術：物理矩陣上色法！完全捨棄會當機的 applymap 和 subset
    def highlight_logic(x):
        # 建立一個全空的樣式矩陣
        df_style = pd.DataFrame('', index=x.index, columns=x.columns)
        if '前瞻殖利率(%)' in x.columns:
            # 只有大於條件的格子才會被填入紅色樣式
            mask = pd.to_numeric(x['前瞻殖利率(%)'], errors='coerce').fillna(0) >= threshold
            df_style.loc[mask, '前瞻殖利率(%)'] = 'color: #ff4b4b; font-weight: bold'
        return df_style

    try:
        # 將矩陣安全地覆蓋上去，保證 Streamlit 抓不到任何語法錯誤！
        styler = df_clean.style.apply(highlight_logic, axis=None).format(f_dict)
        st.dataframe(styler, height=calc_height, use_container_width=True)
    except Exception:
        # 即使天塌下來，最後的物理防護網依然存在
        df_safe = df_clean.copy()
        for c in df_safe.columns:
            if "(%)" in c or "%" in c: df_safe[c] = df_safe[c].apply(lambda x: f"{x:.2f}%")
            elif "次數" in c: df_safe[c] = df_safe[c].apply(lambda x: f"{int(x)}")
            else: df_safe[c] = df_safe[c].apply(lambda x: f"{x:.2f}")
        st.dataframe(df_safe, height=calc_height, use_container_width=True)

# ==========================================
# 5. 版面標籤與主程式
# ==========================================
if is_admin:
    t_vip, t_radar, t_fin = st.tabs(["🎯 專屬戰略指揮", "🔍 成長戰略雷達", "🏦 金融存股雷達"])
else:
    t_vip, t_fin = st.tabs(["🎯 專屬戰略指揮", "🏦 金融存股雷達"])
    t_radar = None

with t_vip:
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🚀 執行戰略分析", type="primary", use_container_width=True):
            with st.spinner("🔄 正在擷取 Google Sheet 最新數據..."):
                fetch_gsheet_data_v186.clear() # 強制清除快取
                fresh_data = fetch_gsheet_data_v186()
                db_gen = fresh_data.get("general", {}) if fresh_data else {}
                db_fin = fresh_data.get("finance", {}) if fresh_data else {}
            
            vips = list(dict.fromkeys([c.strip() for c in re.split(r'[;,\s\t]+', watch_list_input) if c.strip()]))
            bar = st.progress(0, "分析演算中...")
            res_list, found = [], 0
            for i, code in enumerate(vips):
                d = db_gen.get(code) or db_fin.get(code)
                if d:
                    found += 1
                    bar.progress((i+1)/len(vips), f"分析: {code}")
                    pr = float(d.get("price", 0.0)) if pd.notna(d.get("price")) and d.get("price") != "" else 0.0
                    res_list.append(auto_strategic_model(f"{code} {d['name']}", simulated_month, d.get("rev_last_11",0), d.get("rev_last_12",0), d.get("rev_this_1",0), d.get("rev_this_2",0), d.get("rev_this_3",0), d["base_q_eps"], d.get("non_op",0), d["base_q_avg_rev"], d["ly_q1_rev"], d["ly_q2_rev"], d["ly_q3_rev"], d["ly_q4_rev"], d["y1_q1_rev"], d["y1_q2_rev"], d["y1_q3_rev"], d["y1_q4_rev"], d.get("payout",0), pr, d.get("contract_liab",0), d.get("contract_liab_qoq",0), d.get("acc_eps",0), d.get("declared_div",0)))
            bar.empty()
            if not found: st.warning("未找到對應股票資料，請確認代號或表單內容。")
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
                    try: row_list = row_df.to_dict('records')
                    except Exception: row_list = []
                        
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
                            with st.expander("📝 點此查看預估邏輯"):
                                st.write(str(row.get('logic_note', '無紀錄')))
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
            with st.spinner("🔄 正在向 Google Sheet 抓取最新數據..."):
                fetch_gsheet_data_v186.clear()
                fresh_data = fetch_gsheet_data_v186()
                db_gen = fresh_data.get("general", {}) if fresh_data else {}
                db_fin = fresh_data.get("finance", {}) if fresh_data else {}
                
            kws = [k.strip() for k in re.split(r'[;,\s\t]+', ex_kws) if k.strip()]
            res_list = []
            for code, d in db_gen.items():
                if kws and any((k in d["name"] or code.startswith(k)) for k in kws): continue
                pr = float(d.get("price", 0.0)) if pd.notna(d.get("price")) and d.get("price") != "" else 0.0
                r = auto_strategic_model(f"{code} {d['name']}", simulated_month, d.get("rev_last_11",0), d.get("rev_last_12",0), d.get("rev_this_1",0), d.get("rev_this_2",0), d.get("rev_this_3",0), d["base_q_eps"], d.get("non_op",0), d["base_q_avg_rev"], d["ly_q1_rev"], d["ly_q2_rev"], d["ly_q3_rev"], d["ly_q4_rev"], d["y1_q1_rev"], d["y1_q2_rev"], d["y1_q3_rev"], d["y1_q4_rev"], d.get("payout",0), pr, d.get("contract_liab",0), d.get("contract_liab_qoq",0), d.get("acc_eps",0), d.get("declared_div",0))
                
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
        with st.spinner("🔄 正在向 Google Sheet 抓取最新數據..."):
            fetch_gsheet_data_v186.clear()
            fresh_data = fetch_gsheet_data_v186()
            db_gen = fresh_data.get("general", {}) if fresh_data else {}
            db_fin = fresh_data.get("finance", {}) if fresh_data else {}
            
        res_list = [financial_strategic_model(d["name"], c.strip(), simulated_month, d, simulated_month) for c, d in db_fin.items() if d.get("pbr",0) > 0]
        if not res_list: st.warning("無符合條件的金融股")
        else: render_dataframe(pd.DataFrame(res_list).sort_values(by=['PBR(股價淨值比)', '前瞻殖利率(%)', '連續配息次數'], ascending=[True, False, False]), is_finance=True)
