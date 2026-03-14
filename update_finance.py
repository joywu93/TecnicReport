# ==========================================
# 📂 檔案名稱： update_finance.py (V184 損益表全抓取版)
# 💡 核心突破： 捨棄不穩定的簡表，改用正式損益表 API 抓取「營業利益」與「稅前淨利」
# ==========================================

import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"
TARGET_YEAR = "114"
TARGET_Q = "4"

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def force_float(v):
    if v is None: return 0.0
    s = str(v).strip().replace(',', '')
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    try: return float(s)
    except: return 0.0

def fetch_and_update():
    headers = {'User-Agent': 'Mozilla/5.0'}
    print(f"📡 正在從正式損益表 API 提取 {TARGET_YEAR}Q{TARGET_Q} 數據...")
    
    # 🌟 改抓 t187ap11_L (綜合損益表) - 這是目前最完整的路徑
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap11_L", headers=headers, verify=False, timeout=20).json()
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap11_O", headers=headers, verify=False, timeout=20).json()
        all_data = res_twse + res_tpex
    except Exception as e:
        print(f"❌ API 連線失敗: {e}"); return

    stats = {}
    for item in all_data:
        if str(item.get('年度')) == TARGET_YEAR and str(item.get('季別')) == TARGET_Q:
            code = str(item.get('公司代號', '')).strip()
            
            # 從正式表抓取核心數值 (欄位名稱在正式表通常極度穩定)
            eps = force_float(item.get('基本每股盈餘（元）')) or force_float(item.get('基本每股盈餘(元)'))
            op_profit = force_float(item.get('營業利益（損失）'))
            pre_tax = force_float(item.get('繼續營業單位稅前淨利（淨損）'))
            
            if eps != 0 or op_profit != 0:
                stats[code] = {"eps": eps, "op": op_profit, "pre_tax": pre_tax}

    if '3023' in stats:
        print(f"✅ 成功抓取 3023: EPS={stats['3023']['eps']}, 營業利益={stats['3023']['op']}, 稅前={stats['3023']['pre_tax']}")

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        h = data[0]
        
        try:
            i_c = next(i for i, x in enumerate(h) if "代號" in x)
            i_q4_eps = next(i for i, x in enumerate(h) if "25Q4單季每股盈餘" in x.replace(' ', ''))
            i_non_op = next(i for i, x in enumerate(h) if "業外" in x and "%" in x)
            
            # Q1-Q3 欄位索引
            i_q123 = [next((i for i, x in enumerate(h) if f"25Q{q}單季" in x), -1) for q in [1,2,3]]

            cells = []
            for r_idx, row in enumerate(data[1:], start=2):
                code = row[i_c].split('.')[0].strip()
                if code in stats:
                    d = stats[code]
                    
                    # 計算 Q4 單季 EPS (累計 - Q1 - Q2 - Q3)
                    q123_val = sum(force_float(row[idx]) for idx in i_q123 if idx != -1)
                    q4_single_eps = d["eps"] - q123_val
                    
                    # 業外佔比反推
                    non_op_ratio = 0.0
                    if d["pre_tax"] != 0:
                        non_op_ratio = round(((d["pre_tax"] - d["op"]) / d["pre_tax"]) * 100, 2)
                    
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_eps+1, value=round(q4_single_eps, 2)))
                    cells.append(gspread.Cell(row=r_idx, col=i_non_op+1, value=non_op_ratio))
                    # AO, AP 原始數據供核對
                    cells.append(gspread.Cell(row=r_idx, col=41, value=d["op"]))
                    cells.append(gspread.Cell(row=r_idx, col=42, value=d["pre_tax"]))
            
            if cells:
                ws.update_cells(cells, value_input_option='USER_ENTERED')
                print(f"📊 {ws.title} 同步完成。")
        except: continue

if __name__ == "__main__":
    fetch_and_update()
