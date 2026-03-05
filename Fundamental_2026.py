import streamlit as st
import pandas as pd
import io
import altair as alt
import re
import os
import yfinance as yf
import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import urllib3
import time

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

st.title("📊 2026 戰略指揮 (V80 國際數據庫直連版)")

# ==========================================
# 1. 核心大腦：完美復刻 VBA 
# ==========================================
def auto_strategic_model(name, current_month, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, base_q_eps, non_op_ratio, base_q_avg_rev, ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev, y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, recent_payout_ratio, current_price, contract_liab, contract_liab_qoq):
    if current_month == 1:
        est_q1_avg, formula_note, known_q1 = (rev_last_11 + rev_last_12) / 2, "採上年11、12月均值", 0
    elif current_month == 2:
        est_q1_avg, formula_note, known_q1 = rev_this_1 * 0.9, "採當年1月營收×0.9", rev_this_1
    elif current_month == 3:
        est_q1_avg, formula_note, known_q1 = (rev_this_1 + rev_this_2) / 2, "採當年1、2月均值", rev_this_1 + rev_this_2
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

    if avg_2yr_h1 > 0:
        multiplier = 1 + (avg_2yr_h2 / avg_2yr_h1)
        est_total_rev = est_h1_rev_total * multiplier
        est_full_year_eps = est_h1_eps * multiplier
        est_h2_rev_total = est_total_rev - est_h1_rev_total
        est_q3_rev_total = est_h2_rev_total * (ly_q3_rev / y2_h2) if y2_h2 > 0 else est_h2_rev_total / 2
        est_q4_rev_total = est_h2_rev_total * (ly_q4_rev / y2_h2) if y2_h2 > 0 else est_h2_rev_total / 2
    else:
        est_total_rev, est_full_year_eps, est_q3_rev_total, est_q4_rev_total = est_h1_rev_total, est_h1_eps, 0, 0

    ly_total_rev = y2_h1 + y2_h2
    est_annual_yoy = ((est_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0
    
    current_price = float(current_price) if current_price else 0.0
    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    calc_payout_ratio = 90 if recent_payout_ratio >= 100 else (50 if recent_payout_ratio == 0 else recent_payout_ratio)
    forward_yield = (est_full_year_eps * (calc_payout_ratio / 100)) / current_price * 100 if est_full_year_eps > 0 and current_price > 0 else 0

    return {
        "股票名稱": name, "最新股價": round(current_price, 2), "套用公式": formula_note,
        "當季預估均營收": round(est_q1_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "預估今年Q1_EPS": round(est_q1_eps, 2), 
        "預估今年度_EPS": round(est_full_year_eps, 2), "本益比(PER)": round(est_per, 2),         
        "預估年成長率(%)": round(est_annual_yoy, 2), "運算配息率(%)": calc_payout_ratio,
        "最新季度流動合約負債(億)": contract_liab, "最新季度流動合約負債季增(%)": contract_liab_qoq,
        "_ly_qs": [ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev], "_known_qs": [known_q1, 0, 0, 0],
        "_pure_est_qs": [max(0, est_q1_rev_total - known_q1), est_q2_rev_total, est_q3_rev_total, est_q4_rev_total]
    }

# ==========================================
# 2. 側邊欄設定 & 雲端資料庫對接
# ==========================================
st.sidebar.header("⚙️ 系統參數")
simulated_month = st.sidebar.slider("月份推演", 1, 12, 2)
watch_list_input = st.sidebar.text_input("📌 VIP 關注清單", value="8358, 8383, 8390")

st.sidebar.divider()
st.sidebar.header("📥 資料庫對接")
gsheet_url = st.sidebar.text_input("🔗 Google 試算表連結 (優先讀取)", placeholder="請貼上共用連結...")

# ==========================================
# 🌟 引擎一：月營收自動更新 (保持政府靜態頁面讀取，不受防火牆影響)
# ==========================================
st.sidebar.divider()
st.sidebar.header("🤖 月營收自動更新")
auto_month = st.sidebar.text_input("設定欲更新的營收月份 (如: 01 或 02)", value="02")

if st.sidebar.button("⚡ 一鍵更新營收至試算表", type="primary"):
    if not gsheet_url: st.sidebar.error("❌ 請先貼上您的 Google 試算表連結！")
    elif "google_key" not in st.secrets: st.sidebar.error("❌ 找不到金鑰！")
    else:
        with st.status("啟動純淨官方引擎：鎖定台灣交易所數據...", expanded=True) as status:
            try:
                scopes = ['https://www.googleapis.com/auth/spreadsheets']
                raw_key = st.secrets["google_key"]
                key_dict = json.loads(raw_key) if isinstance(raw_key, str) else dict(raw_key)
                creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
                client = gspread.authorize(creds)
                
                sheet = client.open_by_url(gsheet_url).sheet1
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
# 🌟 引擎二：季報/財報自動更新 (V80 國際數據庫 yfinance 版)
# ==========================================
st.sidebar.divider()
st.sidebar.header("💼 季報/財報自動更新")
q_year = st.sidebar.text_input("設定財報年份 (如: 25 或 2025)", value="25")
q_season = st.sidebar.selectbox("設定財報季度 (Q1~Q4)", ["1", "2", "3", "4"], index=2)

if st.sidebar.button("⚡ 一鍵更新季報至試算表", type="primary"):
    if not gsheet_url: st.sidebar.error("❌ 請先貼上您的 Google 試算表連結！")
    elif "google_key" not in st.secrets: st.sidebar.error("❌ 找不到金鑰！")
    else:
        with st.status(f"🚀 啟動國際財經數據庫，獲取 {q_year}Q{q_season} 綜合損益表...", expanded=True) as status:
            try:
                st.write("1. 連結 Google 試算表，定位財報欄位...")
                scopes = ['https://www.googleapis.com/auth/spreadsheets']
                raw_key = st.secrets["google_key"]
                key_dict = json.loads(raw_key) if isinstance(raw_key, str) else dict(raw_key)
                creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
                client = gspread.authorize(creds)
                
                sheet = client.open_by_url(gsheet_url).sheet1
                all_data = sheet.get_all_values()
                headers = all_data[0]
                
                c_code_idx, c_gm_idx, c_om_idx, c_eps_idx = -1, -1, -1, -1
                
                # 年份防呆換算 (25 -> 2025, 114 -> 2025)
                y_val = int(q_year)
                if y_val < 100: target_year = y_val + 2000
                elif y_val < 1000: target_year = y_val + 1911
                else: target_year = y_val
                
                target_q = int(q_season)
                roc_year_str = str(target_year - 1911 - 100) # 2025 -> 114 -> "14" -> "25" (民國114年即為表格標題25)
                eps_header_target = f"{(target_year-2000)}Q{target_q}單季每股盈餘(元)" 
                
                for i, header in enumerate(headers):
                    clean_h = str(header).replace('\n', '').replace(' ', '').replace('\r', '').strip()
                    if "代號" in clean_h: c_code_idx = i + 1
                    if "最新單季毛利率(%)" in clean_h: c_gm_idx = i + 1
                    if "最新單季營益率(%)" in clean_h: c_om_idx = i + 1
                    if eps_header_target in clean_h: c_eps_idx = i + 1
                        
                if c_code_idx == -1:
                    st.error("❌ 找不到包含「代號」的標題！")
                    status.update(label="任務失敗", state="error", expanded=True)
                else:
                    vip_codes = [str(row[c_code_idx-1]).split('.')[0].strip() for i, row in enumerate(all_data) if i > 0 and len(row) >= c_code_idx and str(row[c_code_idx-1]).strip()]
                    row_map = {code: i + 1 for i, code in enumerate(vip_codes)}
                    
                    st.write(f"2. 連線國際 API (Yahoo Finance) 繞過政府防火牆...")
                    st.write(f"👉 預計耗時約 1~2 分鐘，請耐心等候，機器人正在為您結算 {len(vip_codes)} 檔股票...")
                    
                    df_all_list = []
                    
                    # 建立進度條
                    progress_bar = st.progress(0)
                    
                    # 💡 核心武器：yfinance 抓取邏輯 (無懼任何防火牆)
                    for idx, code in enumerate(vip_codes):
                        # 更新進度條
                        progress_bar.progress((idx + 1) / len(vip_codes))
                        
                        try:
                            # 嘗試抓取上市或上櫃
                            stock = yf.Ticker(f"{code}.TW")
                            q_inc = stock.quarterly_income_stmt
                            if q_inc is None or q_inc.empty:
                                stock = yf.Ticker(f"{code}.TWO")
                                q_inc = stock.quarterly_income_stmt
                                
                            if q_inc is not None and not q_inc.empty:
                                # 尋找對應的年份與季度
                                target_col = None
                                for col in q_inc.columns:
                                    if col.year == target_year and col.quarter == target_q:
                                        target_col = col
                                        break
                                        
                                if target_col is not None:
                                    def safe_get(row_names):
                                        for name in row_names:
                                            if name in q_inc.index and pd.notna(q_inc.loc[name, target_col]):
                                                return float(q_inc.loc[name, target_col])
                                        return None

                                    rev = safe_get(['Total Revenue', 'Operating Revenue'])
                                    gp = safe_get(['Gross Profit'])
                                    op = safe_get(['Operating Income', 'Operating Profit'])
                                    eps = safe_get(['Diluted EPS', 'Basic EPS'])
                                    
                                    gm_val = round((gp / rev) * 100, 2) if rev and gp is not None and rev != 0 else ""
                                    om_val = round((op / rev) * 100, 2) if rev and op is not None and rev != 0 else ""
                                    eps_val = round(eps, 2) if eps is not None else ""
                                    
                                    if gm_val != "" or eps_val != "":
                                        df_all_list.append({
                                            '公司代號': code, '毛利率': gm_val, '營益率': om_val, 'EPS': eps_val
                                        })
                        except Exception:
                            pass # 找不到這檔的資料就跳過

                    if not df_all_list:
                        status.update(label=f"⚠️ 國際資料庫尚未發現 {target_year} Q{target_q} 的財報數據", state="error", expanded=True)
                    else:
                        st.write(f"3. 成功從國際資料庫擷取 {len(df_all_list)} 筆資料！開始寫入試算表...")
                        df_res = pd.DataFrame(df_all_list)
                        
                        cells_to_update = []
                        update_count = 0
                        
                        for index, row in df_res.iterrows():
                            code = str(row['公司代號']).strip()
                            if code in row_map:
                                row_idx = row_map[code] + 1 # 補回 header 的偏移
                                has_update = False
                                
                                if c_gm_idx != -1 and row['毛利率'] != "":
                                    cells_to_update.append(gspread.Cell(row=row_idx, col=c_gm_idx, value=float(row['毛利率'])))
                                    has_update = True
                                if c_om_idx != -1 and row['營益率'] != "":
                                    cells_to_update.append(gspread.Cell(row=row_idx, col=c_om_idx, value=float(row['營益率'])))
                                    has_update = True
                                if c_eps_idx != -1 and row['EPS'] != "":
                                    cells_to_update.append(gspread.Cell(row=row_idx, col=c_eps_idx, value=float(row['EPS'])))
                                    has_update = True
                                    
                                if has_update: update_count += 1

                        if cells_to_update:
                            sheet.update_cells(cells_to_update)
                            status.update(label=f"🎉 突破封鎖！完美為 {update_count} 檔 VIP 填寫最新財報數據！", state="complete", expanded=False)
                            st.balloons()
                        else:
                            status.update(label="⚠️ 引擎有抓到資料，但您的清單中無人匹配", state="error", expanded=True)
                            
            except Exception as e:
                status.update(label="任務中斷", state="error", expanded=True)
                st.error(f"❌ 錯誤說明：{e}")

# ==========================================
# 3. 讀取與解析引擎
# ==========================================
default_file_path = None
for f in ["MonthlyDataCSV.csv", "個股營收表.csv", "個股營收表.xlsx"]:
    if os.path.exists(f): default_file_path = f; break
uploaded_file = st.sidebar.file_uploader("或手動上傳備用檔 (CSV/Excel)", type=["csv", "xlsx"])

df_upload = None
try:
    if gsheet_url:
        sheet_id_match = re.search(r'd/([a-zA-Z0-9-_]+)', gsheet_url)
        if sheet_id_match:
            sheet_id = sheet_id_match.group(1)
            csv_export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            df_upload = pd.read_csv(csv_export_url)
    elif uploaded_file is not None:
        raw_bytes = uploaded_file.read()
        try: df_upload = pd.read_csv(io.StringIO(raw_bytes.decode('cp950')))
        except: 
            try: df_upload = pd.read_csv(io.StringIO(raw_bytes.decode('utf-8-sig')))
            except: df_upload = pd.read_excel(io.BytesIO(raw_bytes))
    elif default_file_path:
        if default_file_path.endswith('.csv'):
            try: df_upload = pd.read_csv(default_file_path, encoding='cp950')
            except: df_upload = pd.read_csv(default_file_path, encoding='utf-8-sig')
        else: df_upload = pd.read_excel(default_file_path)

    if df_upload is not None:
        cols = df_upload.columns.tolist()
        q_cols = [c for c in cols if re.search(r'(\d{2})Q', c)]
        ly = max([re.search(r'(\d{2})Q', c).group(1) for c in q_cols]) if q_cols else "25"
        y1 = str(int(ly) - 1) 

        def get_col(kw1, kw2="", exclude=""):
            for c in reversed(cols):
                clean_c = str(c).replace('\n', '').replace(' ', '').replace('\r', '')
                if kw1 in clean_c and kw2 in clean_c:
                    if exclude and exclude in clean_c: continue
                    return c
            return None
            
        c_code, c_name, c_price = get_col("代號"), get_col("名稱"), get_col("成交")
        c_rev_last_11, c_rev_last_12 = get_col("11單月營收", exclude="增"), get_col("12單月營收", exclude="增")
        c_rev_this_1, c_rev_this_2, c_rev_this_3 = get_col("01單月營收", exclude="增"), get_col("02單月營收", exclude="增"), get_col("03單月營收", exclude="增")
        c_ly_q1, c_ly_q2, c_ly_q3, c_ly_q4 = get_col(f"{ly}Q1", "營收", exclude="增"), get_col(f"{ly}Q2", "營收", exclude="增"), get_col(f"{ly}Q3", "營收", exclude="增"), get_col(f"{ly}Q4", "營收", exclude="增") 
        c_eps_q3, c_eps_q4 = get_col(f"{ly}Q3", "盈餘"), get_col(f"{ly}Q4", "盈餘")
        c_y1_q1, c_y1_q2, c_y1_q3, c_y1_q4 = get_col(f"{y1}Q1", "營收", exclude="增"), get_col(f"{y1}Q2", "營收", exclude="增"), get_col(f"{y1}Q3", "營收", exclude="增"), get_col(f"{y1}Q4", "營收", exclude="增")
        c_rev_10, c_non_op, c_payout = get_col("10單月營收", exclude="增"), get_col("業外損益"), get_col("分配率")
        c_liab_qoq = get_col("合約負債季增")
        if not c_liab_qoq: c_liab_qoq = get_col("季增", "負債")
        c_liab = next((c for c in reversed(cols) if "合約負債" in c and "季增" not in c and "%" not in c), None)

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
                "payout": get_val(c_payout), "price": get_val(c_price), "contract_liab": get_val(c_liab), "contract_liab_qoq": get_val(c_liab_qoq)
            }
        st.session_state["stock_db_v80"] = stock_db
except Exception as e:
    if gsheet_url or uploaded_file or default_file_path: st.error(f"檔案解析失敗：{e}")

# ==========================================
# 4. 執行與呈現
# ==========================================
if "stock_db_v80" in st.session_state:
    if st.button(f"🚀 執行 {simulated_month} 月分析", type="primary"):
        with st.spinner("雲端運算中..."):
            results, current_rule_note = [], ""
            for code, data in st.session_state["stock_db_v80"].items():
                
                price = data["price"]
                try: 
                    hist = yf.Ticker(f"{code}.TW").history(period="1d", interval="1m")
                    if not hist.empty: price = hist['Close'].dropna().iloc[-1]
                    else:
                        hist_otc = yf.Ticker(f"{code}.TWO").history(period="1d", interval="1m")
                        if not hist_otc.empty: price = hist_otc['Close'].dropna().iloc[-1]
                except: pass 
                
                res = auto_strategic_model(
                    name=f"{code} {data['name']}", current_month=simulated_month,
                    rev_last_11=data.get("rev_last_11",0), rev_last_12=data.get("rev_last_12",0), rev_this_1=data.get("rev_this_1",0), rev_this_2=data.get("rev_this_2",0), rev_this_3=data.get("rev_this_3",0),
                    base_q_eps=data["base_q_eps"], non_op_ratio=data["non_op"], base_q_avg_rev=data["base_q_avg_rev"],
                    ly_q1_rev=data["ly_q1_rev"], ly_q2_rev=data["ly_q2_rev"], ly_q3_rev=data["ly_q3_rev"], ly_q4_rev=data["ly_q4_rev"],
                    y1_q1_rev=data["y1_q1_rev"], y1_q2_rev=data["y1_q2_rev"], y1_q3_rev=data["y1_q3_rev"], y1_q4_rev=data["y1_q4_rev"],
                    recent_payout_ratio=data["payout"], current_price=price, 
                    contract_liab=data.get("contract_liab", 0), contract_liab_qoq=data.get("contract_liab_qoq", 0)
                )
                current_rule_note = res["套用公式"] 
                results.append(res)
            
            st.session_state["df_final_v80"] = pd.DataFrame(results)
            st.session_state["current_rule_note"] = current_rule_note

if "df_final_v80" in st.session_state:
    df = st.session_state["df_final_v80"].copy()
    watch_list = list(dict.fromkeys([c.strip() for c in re.split(r'[;,\s\t]+', watch_list_input) if c.strip()]))
    if watch_list:
        df['is_vip'] = df['股票名稱'].apply(lambda x: 1 if any(w in str(x) for w in watch_list) else 0)
        df['股票名稱'] = df.apply(lambda row: f"⭐ {row['股票名稱']}" if row['is_vip'] == 1 else row['股票名稱'], axis=1)
    else: df['is_vip'] = 0

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown(f"⚙️ **預估邏輯：** {st.session_state['current_rule_note']}<br>(Q2=Q1保守推算；下半年採H2/H1比例)", unsafe_allow_html=True)
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
        chart_data = pd.DataFrame({
            "季度": ["Q1", "Q2", "Q3", "Q4"], "1.去年實際": stock_row["_ly_qs"],
            "2.今年已公布": stock_row["_known_qs"], "3.今年純預估": stock_row["_pure_est_qs"]
        }).melt(id_vars="季度", var_name="營收類別", value_name="營收(億)")
        bars = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('營收類別:N', title=None, axis=alt.Axis(labels=False, ticks=False)),
            y=alt.Y('營收(億):Q', title=None), color=alt.Color('營收類別:N', legend=alt.Legend(title=None, orient="top")),
            column=alt.Column('季度:N', header=alt.Header(title=None, labelOrient='bottom'))
        ).properties(width=55, height=220)
        st.altair_chart(bars, use_container_width=False) 
    
    st.divider()
    st.markdown(f"### 🎯 【{selected_stock}】 數據特寫 (免受下方大表排序影響)")
    mini_df = df[df["股票名稱"] == selected_stock].drop(columns=["_ly_qs", "_known_qs", "_pure_est_qs", "套用公式", "is_vip"])
    mini_df = mini_df[["股票名稱", "最新股價", "當季預估均營收", "季成長率(YoY)%", "前瞻殖利率(%)", "預估今年Q1_EPS", "預估今年度_EPS", "本益比(PER)", "預估年成長率(%)", "運算配息率(%)", "最新季度流動合約負債(億)", "最新季度流動合約負債季增(%)"]]
    mini_df = mini_df.set_index(["股票名稱", "最新股價"])
    format_dict = {"最新股價": "{:.2f}", "當季預估均營收": "{:.2f}", "季成長率(YoY)%": "{:.2f}%", "前瞻殖利率(%)": "{:.2f}%", "預估今年Q1_EPS": "{:.2f}", "預估今年度_EPS": "{:.2f}", "本益比(PER)": "{:.2f}", "預估年成長率(%)": "{:.2f}%", "運算配息率(%)": "{:.2f}%", "最新季度流動合約負債(億)": "{:.2f}", "最新季度流動合約負債季增(%)": "{:.2f}%"}
    st.dataframe(mini_df.style.apply(lambda x: ['background-color: rgba(255, 235, 59, 0.2)']*len(x), axis=1).format(format_dict), use_container_width=True)
    
    st.markdown("### 🧮 2026 全市場戰略數據總表")
    display_df = df.drop(columns=["_ly_qs", "_known_qs", "_pure_est_qs", "套用公式"])
    display_df = display_df.sort_values(by=['is_vip', '季成長率(YoY)%', '前瞻殖利率(%)'], ascending=[False, False, False]).drop(columns=['is_vip'])
    display_df = display_df[["股票名稱", "最新股價", "當季預估均營收", "季成長率(YoY)%", "前瞻殖利率(%)", "預估今年Q1_EPS", "預估今年度_EPS", "本益比(PER)", "預估年成長率(%)", "運算配息率(%)", "最新季度流動合約負債(億)", "最新季度流動合約負債季增(%)"]]
    display_df = display_df.set_index(["股票名稱", "最新股價"])
    def highlight_yield(val): return f'color: #ff4b4b; font-weight: bold' if isinstance(val, (int, float)) and val >= 4.0 else ''
    st.dataframe(display_df.style.map(highlight_yield, subset=['前瞻殖利率(%)']).format(format_dict), height=500, use_container_width=True)
