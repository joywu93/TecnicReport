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

st.title("📊 2026 戰略指揮 (V82 財報全矩陣完全體)")

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
# 🌟 引擎一：月營收自動更新 
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
# 🌟 引擎二：財報矩陣一併同步 (V82 季增數強化版)
# ==========================================
st.sidebar.divider()
st.sidebar.header("💼 全歷史財報矩陣同步")
st.sidebar.info("一鍵掃描過去兩年單季營收、EPS，並自動計算最新毛利率、營益率與『季增數』差額！")

if st.sidebar.button("⚡ 一鍵自動填滿財報矩陣", type="primary"):
    if not gsheet_url: st.sidebar.error("❌ 請先貼上您的 Google 試算表連結！")
    elif "google_key" not in st.secrets: st.sidebar.error("❌ 找不到金鑰！")
    else:
        with st.status(f"🚀 啟動國際財經數據庫，展開財報矩陣深度掃描與季增數運算...", expanded=True) as status:
            try:
                st.write("1. 連結 Google 試算表，掃描所有標題欄位...")
                scopes = ['https://www.googleapis.com/auth/spreadsheets']
                raw_key = st.secrets["google_key"]
                key_dict = json.loads(raw_key) if isinstance(raw_key, str) else dict(raw_key)
                creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
                client = gspread.authorize(creds)
                
                sheet = client.open_by_url(gsheet_url).sheet1
                all_data = sheet.get_all_values()
                headers = all_data[0]
                
                # 建立標題的絕對索引字典，不管表單加了什麼新欄位 (如: 25Q3單季營收(億))，都能對得上！
                c_indices = {str(h).replace('\n', '').replace(' ', '').replace('\r', '').strip(): i + 1 for i, h in enumerate(headers)}
                
                c_code_idx = -1
                for k, v in c_indices.items():
                    if "代號" in k: 
                        c_code_idx = v
                        break
                        
                if c_code_idx == -1:
                    st.error("❌ 找不到包含「代號」的標題！")
                    status.update(label="任務失敗", state="error", expanded=True)
                else:
                    vip_codes = [str(row[c_code_idx-1]).split('.')[0].strip() for i, row in enumerate(all_data) if i > 0 and len(row) >= c_code_idx and str(row[c_code_idx-1]).strip()]
                    row_map = {code: i + 1 for i, code in enumerate(vip_codes)}
                    
                    st.write(f"2. 深度連線國際 API 抓取歷史矩陣並運算季增數...")
                    st.write(f"👉 此為深度掃描，預計耗時約 1~2 分鐘，請耐心等候...")
                    
                    cells_to_update = []
                    progress_bar = st.progress(0)
                    
                    def safe_get(names, df_table, col_name):
                        for n in names:
                            if n in df_table.index and pd.notna(df_table.loc[n, col_name]):
                                return float(df_table.loc[n, col_name])
                        return None

                    # 💡 核心迴圈：把過去 8 季資料抽出，並算出最新一季的季增數
                    for idx, code in enumerate(vip_codes):
                        progress_bar.progress((idx + 1) / len(vip_codes))
                        row_idx = row_map[code] + 1 
                        
                        try:
                            # 1. 抓取綜合損益表 (季報)
                            stock = yf.Ticker(f"{code}.TW")
                            q_inc = stock.quarterly_income_stmt
                            if q_inc is None or q_inc.empty:
                                stock = yf.Ticker(f"{code}.TWO")
                                q_inc = stock.quarterly_income_stmt
                                
                            if q_inc is not None and not q_inc.empty:
                                # A. 遍歷近 8 季，處理所有的「單季營收」與「單季EPS」
                                for col_date in q_inc.columns[:8]:
                                    y = col_date.year
                                    q = (col_date.month - 1) // 3 + 1
                                    prefix = f"{y-2000}Q{q}" # 轉換成 "24Q1", "25Q3" 等
                                    
                                    rev = safe_get(['Total Revenue', 'Operating Revenue'], q_inc, col_date)
                                    eps = safe_get(['Basic EPS', 'Diluted EPS'], q_inc, col_date)
                                    
                                    # 動態填入 (例如：25Q3單季營收(億))
                                    if rev and f"{prefix}單季營收(億)" in c_indices:
                                        cells_to_update.append(gspread.Cell(row=row_idx, col=c_indices[f"{prefix}單季營收(億)"], value=round(rev/100000000, 2)))
                                    if eps is not None and f"{prefix}單季每股盈餘(元)" in c_indices:
                                        cells_to_update.append(gspread.Cell(row=row_idx, col=c_indices[f"{prefix}單季每股盈餘(元
