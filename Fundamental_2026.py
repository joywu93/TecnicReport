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
    p { margin-bottom: 0.2rem !important; font-size: 0.95rem !important; }
    .block-container { padding-top: 2.5rem !important; padding-bottom: 1rem !important; }
    ::-webkit-scrollbar { width: 14px !important; height: 14px !important; }
    ::-webkit-scrollbar-track { background: #e0e0e0; border-radius: 6px; }
    ::-webkit-scrollbar-thumb { background: #888; border-radius: 6px; border: 2px solid #e0e0e0; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }
    div[data-testid="stDataFrame"] div { scrollbar-width: auto; }
    </style>
""", unsafe_allow_html=True)

st.title("📊 2026 戰略指揮 (V90 視覺累計與優化版)")

# ==========================================
# 1. 核心大腦：完美復刻 VBA 
# ==========================================
def auto_strategic_model(name, current_month, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, base_q_eps, non_op_ratio, base_q_avg_rev, ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev, y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, recent_payout_ratio, current_price, contract_liab, contract_liab_qoq, acc_eps, declared_div):
    if current_month == 1:
        est_q1_avg, formula_note, known_q1 = (rev_last_11 + rev_last_12) / 2, "採上年11、12月均值", 0
    elif current_month == 2:
        est_q1_avg, formula_note, known_q1 = rev_this_1 * 0.9, "採當年1月營收×0.9", rev_this_1
    elif current_month == 3:
        est_q1_avg = (rev_this_1 * 2 + rev_this_2) / 3
        formula_note = "採春節權重(1月x2+2月)/3"
        known_q1 = rev_this_1 + rev_this_2
    else:
        est_q1_avg, formula_note, known_q1 = (rev_this_1 + rev_this_2 + rev_this_3) / 3, "採當年Q1實際均值", rev_this_1 + rev_this_2 + rev_this_3

    est_q1_rev_total = est_q1_avg * 3
    q1_yoy = ((est_q1_rev_total - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0
    est_q1_eps = base_q_eps * (1 - (non_op_ratio / 100)) * (est_q1_avg / base_q_avg_rev) if base_q_avg_rev > 0 else 0

    est_q2_rev_total, est_q2_eps = est_q1_rev_total, est_q1_eps
    est_h1_rev_total, est_h1_eps = est_q1_rev_total + est_q2_rev_total, est_q1_eps + est_q2_eps

    y1_h1, y1_h2 = y1_q1_rev + y1_q2_rev, y1_q3_rev + y1_q4_rev
    y2_h1, y2_h2 = ly_q1_rev + ly_q2_rev, ly_q3_rev + ly_q4_rev
    avg_2yr_h1, avg_2yr_h2 = (y1_h1 + y2_h1) / 2, (y1_h2 + y2_h2) / 2

    # 💡 V90：按照歷年 Q3、Q4 的佔比來精準預估下半年營收
    avg_2yr_q3 = (y1_q3_rev + ly_q3_rev) / 2
    avg_2yr_q4 = (y1_q4_rev + ly_q4_rev) / 2
    avg_2yr_h2_calc = avg_2yr_q3 + avg_2yr_q4

    if avg_2yr_h1 > 0:
        multiplier = 1 + (avg_2yr_h2 / avg_2yr_h1)
        est_total_rev = est_h1_rev_total * multiplier
        est_full_year_eps = est_h1_eps * multiplier
        est_h2_rev_total = est_total_rev - est_h1_rev_total
        
        # 依歷史比例拆分 Q3 與 Q4
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
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    
    est_annual_dividend = est_full_year_eps * (calc_payout_ratio / 100)
    if declared_div > 0 and current_price > 0:
        if declared_div < (est_annual_dividend * 0.45):
            forward_yield = (est_annual_dividend / current_price) * 100
            formula_note += " (多次配息，採預估EPS計算)"
        else:
            forward_yield = (declared_div / current_price) * 100
            formula_note += " (採宣告股利計算)"
    elif current_price > 0:
        forward_yield = (est_annual_dividend / current_price) * 100
    else:
        forward_yield = 0

    return {
        "股票名稱": name, "最新股價": round(current_price, 2), "套用公式": formula_note,
        "當季預估均營收": round(est_q1_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "預估今年Q1_EPS": round(est_q1_eps, 2), 
        "預估今年度_EPS": round(est_full_year_eps, 2), "最新累季EPS": acc_eps, "本益比(PER)": round(est_per, 2),         
        "預估年成長率(%)": round(est_annual_yoy, 2), "運算配息率(%)": calc_payout_ratio,
        "最新季度流動合約負債(億)": contract_liab, "最新季度流動合約負債季增(%)": contract_liab_qoq,
        "_ly_qs": [ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev], "_known_qs": [known_q1, 0, 0, 0],
        "_pure_est_qs": [max(0, est_q1_rev_total - known_q1), est_q2_rev_total, est_q3_rev_total, est_q4_rev_total]
    }

# ==========================================
# 2. 側邊欄：登入與自動記憶清單系統
# ==========================================
st.sidebar.header("⚙️ 系統參數")
simulated_month = st.sidebar.slider("月份推演", 1, 12, 2)

st.sidebar.divider()
st.sidebar.header("📥 資料庫對接與帳號")
gsheet_url = st.sidebar.text_input("🔗 Google 試算表連結 (必填)", placeholder="請貼上共用連結...")
user_email = st.sidebar.text_input("👤 Email 登入", placeholder="請輸入您的信箱...")

user_vip_list = ""
user_row_idx = None
sheet_auth = None

if gsheet_url and user_email and "google_key" in st.secrets:
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        key_dict = json.loads(st.secrets["google_key"]) if isinstance(st.secrets["google_key"], str) else dict(st.secrets["google_key"])
        creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        sheet_auth = client.open_by_url(gsheet_url).worksheet("權限管理")
        auth_data = sheet_auth.get_all_records()
        
        for i, row in enumerate(auth_data):
            if str(row.get('Email', '')).strip().lower() == user_email.strip().lower():
                user_vip_list = str(row.get('VIP清單', ''))
                user_row_idx = i + 2 
                break
                
        if user_row_idx:
            st.sidebar.success(f"✅ 歡迎回來！已載入您的專屬清單。")
        else:
            st.sidebar.info("👋 新朋友！輸入下方清單後按下儲存即可建立專屬帳號。")
            
    except Exception as e:
        st.sidebar.error("❌ 連結失敗，請確認試算表有建立「權限管理」分頁。")

watch_list_input = st.sidebar.text_area(
    "📌 您的專屬關注清單 (用空白或逗號隔開)", 
    value=user_vip_list if user_vip_list else "2330, 2317, 2382", 
    height=100
)

if user_email and gsheet_url and "google_key" in st.secrets:
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
# 🌟 引擎一：月營收自動更新 
# ==========================================
st.sidebar.divider()
with st.sidebar.expander("🤖 月營收自動更新 (政府官方)"):
    auto_month = st.text_input("設定欲更新的營收月份 (如: 01 或 02)", value="02")
    if st.button("⚡ 一鍵更新營收至試算表", type="primary"):
        if not gsheet_url: st.error("❌ 請先貼上您的 Google 試算表連結！")
        elif "google_key" not in st.secrets: st.error("❌ 找不到金鑰！")
        else:
            with st.status("啟動純淨官方引擎：鎖定台灣交易所數據...", expanded=True) as status:
                try:
                    scopes = ['https://www.googleapis.com/auth/spreadsheets']
                    key_dict = json.loads(st.secrets["google_key"]) if isinstance(st.secrets["google_key"], str) else dict(st.secrets["google_key"])
                    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
                    client = gspread.authorize(creds)
                    
                    sheet = client.open_by_url(gsheet_url).worksheet("個股總表")
                    all_data = sheet.get_all_values()
                    headers = all_data[0]
                    
                    target_col_idx, mom_col_idx, yoy_col_idx, code_col_idx = -1, -1, -1, -1
                    target_m_header = auto_month.zfill(2) 
                    
                    for i, header in enumerate(headers):
                        clean_h = str(header).replace('\n', '').replace(' ', '').replace('\r', '').strip()
                        if "代號" in clean_h: code_col_idx = i + 1
                        if target_m_header in clean_h and "單月營收" in clean_h:
                            if "月增" in clean_h: mom_col_idx = i + 1
                            elif "年增" in clean_h: yoy_col_idx = i + 1
                            elif "增" not in clean_h: target_col_idx = i + 1
                            
                    if target_col_idx == -1 or code_col_idx == -1:
                        status.update(label="任務失敗：找不到對應標題", state="error", expanded=True)
                    else:
                        row_map = {str(row[code_col_idx-1]).split('.')[0].strip(): i + 1 for i, row in enumerate(all_data) if i > 0 and len(row) >= code_col_idx and str(row[code_col_idx-1]).strip()}
                        roc_year = 115 if int(auto_month) <= 12 else 114 
                        query_m = str(int(auto_month))
                        df_all_list = []
                        headers_agent = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                        
                        def clean_num(val):
                            v = str(val).replace(',', '').replace('%', '').strip()
                            return v if re.match(r'^-?\d+(\.\d+)?$', v) else ""

                        st.write(f"讀取官方即時公佈榜 (HTML)...")
                        gov_html_count = 0
                        gov_urls = [
                            f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{roc_year}_{query_m}_0.html",
                            f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{roc_year}_{query_m}_1.html",
                            f"https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{roc_year}_{query_m}_0.html",
                            f"https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{roc_year}_{query_m}_1.html"
                        ]
                        for url in gov_urls:
                            try:
                                res = requests.get(url, headers=headers_agent, verify=False, timeout=8)
                                if res.status_code == 200 and len(res.text) > 50:
                                    res.encoding = 'big5' 
                                    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', res.text, flags=re.I|re.S)
                                    for r in rows:
                                        cols = re.findall(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', r, flags=re.I|re.S)
                                        clean_cols = [re.sub(r'<[^>]*>', '', c).replace('&nbsp;', '').replace('\u3000', '').strip() for c in cols]
                                        if len(clean_cols) >= 7:
                                            code_match = re.search(r'(?<!\d)(\d{4})(?!\d)', clean_cols[0])
                                            if code_match and clean_num(clean_cols[2]):
                                                code = code_match.group(1)
                                                if code in row_map:
                                                    df_all_list.append({'公司代號': code, '當月營收': clean_num(clean_cols[2]), '月增率': clean_num(clean_cols[5]), '年增率': clean_num(clean_cols[6]), '來源優先級': 2})
                                                    gov_html_count += 1
                            except: pass
                        
                        st.write(f"讀取官方結算總表 (CSV)...")
                        gov_csv_urls = [url.replace('.html', '.csv') for url in gov_urls]
                        for url in gov_csv_urls:
                            try:
                                res = requests.get(url, headers=headers_agent, verify=False, timeout=8)
                                if res.status_code == 200 and len(res.text) > 100:
                                    res.encoding = 'big5' 
                                    df_gov = pd.read_csv(io.StringIO(res.text), on_bad_lines='skip', header=None, dtype=str)
                                    header_idx = next((i for i in range(min(10, len(df_gov))) if '公司代號' in "".join([str(x) for x in df_gov.iloc[i]]) and '當月營收' in "".join([str(x) for x in df_gov.iloc[i]])), -1)
                                    if header_idx != -1:
                                        df_gov.columns = [str(c).replace('\n', '').replace(' ', '').strip() for c in df_gov.iloc[header_idx]]
                                        df_gov = df_gov.iloc[header_idx+1:].reset_index(drop=True)
                                        for idx, row in df_gov.iterrows():
                                            if '公司代號' in row and pd.notna(row['公司代號']):
                                                code = str(row['公司代號']).strip()
                                                if code in row_map: 
                                                    df_all_list.append({'公司代號': code, '當月營收': clean_num(row.get('當月營收', '')), '月增率': clean_num(row.get('上月比較增減(%)', '')), '年增率': clean_num(row.get('去年同月增減(%)', '')), '來源優先級': 1})
                            except: pass

                        if not df_all_list: status.update(label=f"⚠️ 目前官方尚未公佈 {auto_month} 月營收", state="error", expanded=True)
                        else:
                            df_early = pd.DataFrame(df_all_list).sort_values('來源優先級').drop_duplicates(subset=['公司代號'], keep='first') 
                            cells_to_update = []
                            for index, row in df_early.iterrows():
                                row_idx = row_map[str(row['公司代號']).strip()]
                                if row['當月營收']: cells_to_update.append(gspread.Cell(row=row_idx, col=target_col_idx, value=round(float(row['當月營收']) / 100000, 2)))
                                if mom_col_idx != -1 and row['月增率']: cells_to_update.append(gspread.Cell(row=row_idx, col=mom_col_idx, value=float(row['月增率'])))
                                if yoy_col_idx != -1 and row['年增率']: cells_to_update.append(gspread.Cell(row=row_idx, col=yoy_col_idx, value=float(row['年增率'])))
                            
                            year_prefix = str(roc_year + 1911)[-2:] 
                            new_header_prefix = f"{year_prefix}M{target_m_header}"
                            if mom_col_idx != -1: cells_to_update.append(gspread.Cell(row=1, col=mom_col_idx, value=f"{new_header_prefix}單月營收月增(%)"))
                            if yoy_col_idx != -1: cells_to_update.append(gspread.Cell(row=1, col=yoy_col_idx, value=f"{new_header_prefix}單月營收年增(%)"))

                            if cells_to_update:
                                sheet.update_cells(cells_to_update)
                                status.update(label=f"🎉 營收更新成功！寫入 {len(df_early)} 檔數據！", state="complete", expanded=False)
                                st.balloons()
                except Exception as e:
                    status.update(label="任務中斷", state="error", expanded=True)
                    st.error(f"❌ 錯誤說明：{e}")

# ==========================================
# 🛠️ 管理員工具：自動生成 Goodinfo 純個股清單
# ==========================================
st.sidebar.divider()
with st.sidebar.expander("🛠️ 管理員輔助工具 (Goodinfo 專用)"):
    st.info("此工具可一鍵提取全市場「純 4 碼公司代號」(排除 ETF/權證)，並切成每包 300 檔，方便您複製到 Goodinfo 查詢歷史財報。")
    if st.button("打包純個股清單", type="secondary"):
        with st.spinner("向政府資料庫請求最新名單中..."):
            try:
                res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=10)
                twse_codes = [item['Code'] for item in res_twse.json() if str(item['Code']).isdigit() and len(str(item['Code'])) == 4]
                res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", timeout=10)
                tpex_codes = [item['SecuritiesCompanyCode'] for item in res_tpex.json() if str(item['SecuritiesCompanyCode']).isdigit() and len(str(item['SecuritiesCompanyCode'])) == 4]
                
                all_pure_codes = sorted(list(set(twse_codes + tpex_codes)))
                st.success(f"成功撈取 {len(all_pure_codes)} 檔純公司股票！")
                
                chunk_size = 300
                chunks = [all_pure_codes[i:i + chunk_size] for i in range(0, len(all_pure_codes), chunk_size)]
                for idx, chunk in enumerate(chunks):
                    st.text_area(f"第 {idx+1} 包 (共 {len(chunk)} 檔)", value=",".join(chunk), height=100)
            except Exception as e:
                st.error(f"獲取名單失敗，請稍後再試。({e})")

# ==========================================
# 3. 讀取與解析引擎
# ==========================================
df_upload = None
try:
    if gsheet_url and "google_key" in st.secrets:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        key_dict = json.loads(st.secrets["google_key"]) if isinstance(st.secrets["google_key"], str) else dict(st.secrets["google_key"])
        creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        sheet_main = client.open_by_url(gsheet_url).worksheet("個股總表")
        all_data = sheet_main.get_all_values()
        
        if len(all_data) > 0:
            df_upload = pd.DataFrame(all_data[1:], columns=all_data[0])

    if df_upload is not None:
        cols = df_upload.columns.tolist()
        q_cols = [c for c in cols if re.search(r'(\d{2})Q', c)]
        ly = max([re.search(r'(\d{2})Q', c).group(1) for c in q_cols]) if q_cols else "25"
        y1 = str(int(ly) - 1) 

        def get_col(kw1, kw2="", excludes=[]):
            for c in cols:
                clean_c = str(c).replace('\n', '').replace(' ', '').replace('\r', '')
                if kw1 in clean_c and kw2 in clean_c:
                    if any(ex in clean_c for ex in excludes): continue
                    return c
            return None
            
        c_code = get_col("代號")
        c_name = get_col("名稱")
        c_price = get_col("成交", excludes=["量", "值", "比", "額", "金", "幅", "差", "均"])
        
        c_rev_last_11 = get_col("11單月營收", excludes=["增", "率", "%"])
        c_rev_last_12 = get_col("12單月營收", excludes=["增", "率", "%"])
        c_rev_this_1 = get_col("01單月營收", excludes=["增", "率", "%"])
        c_rev_this_2 = get_col("02單月營收", excludes=["增", "率", "%"])
        c_rev_this_3 = get_col("03單月營收", excludes=["增", "率", "%"])
        
        c_ly_q1 = get_col(f"{ly}Q1", "營收", excludes=["增", "率", "%"])
        c_ly_q2 = get_col(f"{ly}Q2", "營收", excludes=["增", "率", "%"])
        c_ly_q3 = get_col(f"{ly}Q3", "營收", excludes=["增", "率", "%"])
        c_ly_q4 = get_col(f"{ly}Q4", "營收", excludes=["增", "率", "%"]) 
        c_y1_q1 = get_col(f"{y1}Q1", "營收", excludes=["增", "率", "%"])
        c_y1_q2 = get_col(f"{y1}Q2", "營收", excludes=["增", "率", "%"])
        c_y1_q3 = get_col(f"{y1}Q3", "營收", excludes=["增", "率", "%"])
        c_y1_q4 = get_col(f"{y1}Q4", "營收", excludes=["增", "率", "%"])
        c_rev_10 = get_col("10單月營收", excludes=["增", "率", "%"])

        c_eps_q3 = get_col(f"{ly}Q3", "盈餘")
        c_eps_q4 = get_col(f"{ly}Q4", "盈餘")
        c_acc_eps = get_col("累季", "盈餘") 
        
        c_non_op = get_col("業外損益")
        c_payout = get_col("分配率")
        
        c_dec_div = get_col("合計股利")
        
        c_liab_qoq = get_col("合約負債季增")
        if not c_liab_qoq: c_liab_qoq = get_col("季增", "負債")
        c_liab = get_col("合約負債", excludes=["季增", "%", "比"])

        stock_db = {}
        for idx, row in df_upload.iterrows():
            code = str(row[c_code]).split('.')[0].strip() if c_code and pd.notna(row[c_code]) else ""
            if len(code) < 3: continue 
            
            def get_val(col_name, default=0.0):
                if col_name and pd.notna(row[col_name]):
                    try: return float(str(row[col_name]).replace(',', '').replace(' ', '').strip() or default)
                    except: return default
                return default
            
            rev_q4 = get_val(c_ly_q4) or (get_val(c_rev_10) + get_val(c_rev_last_11) + get_val(c_rev_last_12))
            eps_q3, eps_q4 = get_val(c_eps_q3), get_val(c_eps_q4)
            rev_q3 = get_val(c_ly_q3)
            base_eps = eps_q4 if eps_q4 != 0 else (eps_q3 * (rev_q4 / rev_q3) if rev_q3 > 0 else eps_q3)

            stock_db[code] = {
                "name": str(row[c_name]) if c_name else "未知", "rev_last_11": get_val(c_rev_last_11), "rev_last_12": get_val(c_rev_last_12),
                "rev_this_1": get_val(c_rev_this_1), "rev_this_2": get_val(c_rev_this_2), "rev_this_3": get_val(c_rev_this_3),
                "base_q_eps": base_eps, "non_op": get_val(c_non_op), "base_q_avg_rev": rev_q4 / 3 if rev_q4 > 0 else 0,
                "ly_q1_rev": get_val(c_ly_q1), "ly_q2_rev": get_val(c_ly_q2), "ly_q3_rev": rev_q3, "ly_q4_rev": rev_q4,
                "y1_q1_rev": get_val(c_y1_q1), "y1_q2_rev": get_val(c_y1_q2), "y1_q3_rev": get_val(c_y1_q3), "y1_q4_rev": get_val(c_y1_q4),
                "payout": get_val(c_payout), "price": get_val(c_price), "acc_eps": get_val(c_acc_eps),
                "contract_liab": get_val(c_liab), "contract_liab_qoq": get_val(c_liab_qoq),
                "declared_div": get_val(c_dec_div)
            }
        st.session_state["stock_db_v90"] = stock_db
except Exception as e:
    st.error(f"檔案解析失敗，請確認連結與權限。詳細錯誤訊息：{e}")

# ==========================================
# 4. 執行與呈現
# ==========================================
if "stock_db_v90" in st.session_state:
    if st.button(f"🚀 執行 {simulated_month} 月戰略分析", type="primary"):
        results, current_rule_note = [], ""
        
        vip_list_parsed = list(dict.fromkeys([c.strip() for c in re.split(r'[;,\s\t]+', watch_list_input) if c.strip()]))
        valid_vips = [code for code in st.session_state["stock_db_v90"].keys() if code in vip_list_parsed]
        
        if not valid_vips:
            st.warning("您關注的股票清單與試算表資料未能對應，請檢查代號是否正確。")
        else:
            # 💡 V90：加入超明顯的進度條，讓您知道股價正在更新
            progress_bar = st.progress(0, text="連線國際資料庫獲取最新報價...")
            
            for i, code in enumerate(valid_vips):
                data = st.session_state["stock_db_v90"][code]
                progress_bar.progress((i + 1) / len(valid_vips), text=f"正在分析並更新股價: {code} {data['name']}")
                
                price = data["price"]
                try: 
                    hist = yf.Ticker(f"{code}.TW").history(period="5d")
                    if not hist.empty: price = float(hist['Close'].dropna().iloc[-1])
                    else:
                        hist_otc = yf.Ticker(f"{code}.TWO").history(period="5d")
                        if not hist_otc.empty: price = float(hist_otc['Close'].dropna().iloc[-1])
                except: pass 
                
                res = auto_strategic_model(
                    name=f"{code} {data['name']}", current_month=simulated_month,
                    rev_last_11=data.get("rev_last_11",0), rev_last_12=data.get("rev_last_12",0), rev_this_1=data.get("rev_this_1",0), rev_this_2=data.get("rev_this_2",0), rev_this_3=data.get("rev_this_3",0),
                    base_q_eps=data["base_q_eps"], non_op_ratio=data["non_op"], base_q_avg_rev=data["base_q_avg_rev"],
                    ly_q1_rev=data["ly_q1_rev"], ly_q2_rev=data["ly_q2_rev"], ly_q3_rev=data["ly_q3_rev"], ly_q4_rev=data["ly_q4_rev"],
                    y1_q1_rev=data["y1_q1_rev"], y1_q2_rev=data["y1_q2_rev"], y1_q3_rev=data["y1_q3_rev"], y1_q4_rev=data["y1_q4_rev"],
                    recent_payout_ratio=data["payout"], current_price=price, 
                    contract_liab=data.get("contract_liab", 0), contract_liab_qoq=data.get("contract_liab_qoq", 0),
                    acc_eps=data.get("acc_eps", 0),
                    declared_div=data.get("declared_div", 0) 
                )
                current_rule_note = res["套用公式"] 
                results.append(res)
                
            progress_bar.empty() # 跑完後隱藏進度條
            
            if results:
                st.session_state["df_final_v90"] = pd.DataFrame(results)
                st.session_state["current_rule_note"] = current_rule_note

if "df_final_v90" in st.session_state:
    df = st.session_state["df_final_v90"].copy()

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown(f"⚙️ **預估邏輯：** {st.session_state['current_rule_note']}<br>(Q2=Q1保守推算；下半年採歷年H2/H1比例分配)", unsafe_allow_html=True)
        selected_stock = st.selectbox("📌 搜尋個股：", sorted(df["股票名稱"].tolist()))
        stock_row = df[df["股票名稱"] == selected_stock].iloc[0]
        
        liab_value = stock_row.get('最新季度流動合約負債(億)', 0)
        liab_qoq = stock_row.get('最新季度流動合約負債季增(%)', 0)
        
        st.markdown(
            f"**股價 {float(stock_row['最新股價']):.2f}元** ｜ "
            f"EPS **{stock_row['預估今年度_EPS']}元** ｜ "
            f"殖利率 **{stock_row['前瞻殖利率(%)']}%** ｜ "
            f"成長率 **{stock_row['預估年成長率(%)']}%** ｜ "
            f"📈 合約負債 **{liab_value}億 ({liab_qoq}%)**"
        )

    with col2:
        # 💡 V90：將今年已公布跟預估合併，視覺上更直觀！
        chart_data = pd.DataFrame({
            "季度": ["Q1", "Q2", "Q3", "Q4"], 
            "1.去年實際": stock_row["_ly_qs"],
            "2.今年預估(含已公布)": [
                stock_row["_known_qs"][0] + stock_row["_pure_est_qs"][0],
                stock_row["_pure_est_qs"][1],
                stock_row["_pure_est_qs"][2],
                stock_row["_pure_est_qs"][3]
            ]
        }).melt(id_vars="季度", var_name="營收類別", value_name="營收(億)")
        
        bars = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('營收類別:N', title=None, axis=alt.Axis(labels=False, ticks=False)),
            y=alt.Y('營收(億):Q', title=None), color=alt.Color('營收類別:N', legend=alt.Legend(title=None, orient="top")),
            column=alt.Column('季度:N', header=alt.Header(title=None, labelOrient='bottom'))
        ).properties(width=60, height=220)
        st.altair_chart(bars, use_container_width=False) 
    
    st.divider()
    st.markdown(f"### 🎯 【{selected_stock}】 數據特寫 (免受下方大表排序影響)")
    mini_df = df[df["股票名稱"] == selected_stock].drop(columns=["_ly_qs", "_known_qs", "_pure_est_qs", "套用公式"])
    mini_df = mini_df[["股票名稱", "最新股價", "當季預估均營收", "季成長率(YoY)%", "前瞻殖利率(%)", "預估今年Q1_EPS", "預估今年度_EPS", "最新累季EPS", "本益比(PER)", "預估年成長率(%)", "運算配息率(%)", "最新季度流動合約負債(億)", "最新季度流動合約負債季增(%)"]]
    mini_df = mini_df.set_index(["股票名稱", "最新股價"])
    format_dict = {"最新股價": "{:.2f}", "當季預估均營收": "{:.2f}", "季成長率(YoY)%": "{:.2f}%", "前瞻殖利率(%)": "{:.2f}%", "預估今年Q1_EPS": "{:.2f}", "預估今年度_EPS": "{:.2f}", "最新累季EPS": "{:.2f}", "本益比(PER)": "{:.2f}", "預估年成長率(%)": "{:.2f}%", "運算配息率(%)": "{:.2f}%", "最新季度流動合約負債(億)": "{:.2f}", "最新季度流動合約負債季增(%)": "{:.2f}%"}
    st.dataframe(mini_df.style.apply(lambda x: ['background-color: rgba(255, 235, 59, 0.2)']*len(x), axis=1).format(format_dict), use_container_width=True)
    
    st.markdown("### 🧮 個人專屬戰略數據總表 (💡 游標放在表內往下捲動，標題會自動凍結喔！)")
    display_df = df.drop(columns=["_ly_qs", "_known_qs", "_pure_est_qs", "套用公式"])
    display_df = display_df.sort_values(by=['季成長率(YoY)%', '前瞻殖利率(%)'], ascending=[False, False])
    display_df = display_df[["股票名稱", "最新股價", "當季預估均營收", "季成長率(YoY)%", "前瞻殖利率(%)", "預估今年Q1_EPS", "預估今年度_EPS", "最新累季EPS", "本益比(PER)", "預估年成長率(%)", "運算配息率(%)", "最新季度流動合約負債(億)", "最新季度流動合約負債季增(%)"]]
    display_df = display_df.set_index(["股票名稱", "最新股價"])
    def highlight_yield(val): return f'color: #ff4b4b; font-weight: bold' if isinstance(val, (int, float)) and val >= 4.0 else ''
    st.dataframe(display_df.style.map(highlight_yield, subset=['前瞻殖利率(%)']).format(format_dict), height=600, use_container_width=True)
