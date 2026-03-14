# ==========================================
# 📂 檔案名稱： update_finance.py (AO 欄位數據展示版)
# 💡 核心邏輯： 從 AO 欄位開始，依次填入 EPS、營業利益、稅前淨利、季別
# ==========================================

import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

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
    print("📡 正在連線證交所 API (114年度數據)...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False, timeout=20).json()
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False, timeout=20).json()
        all_data = res_twse + res_tpex
    except Exception as e:
        print(f"❌ API 抓取失敗: {e}"); return

    curr_dict = {}
    # 只要是 114 年度的資料都抓，用來確認 Q4 是否已上線
    for item in all_data:
        code = str(item.get('公司代號', '')).strip()
        year = str(item.get('年度', '')).strip()
        if year == "114":
            eps, op_p, pre_t = 0.0, 0.0, 0.0
            for k, v in item.items():
                k_c = k.replace(' ', '')
                if '基本每股盈餘' in k_c: eps = force_float(v)
                if '營業利益' in k_c and '每股' not in k_c: op_p = force_float(v)
                if '稅前' in k_c and ('淨利' in k_c or '損益' in k_c) and '所得稅' not in k_c: pre_t = force_float(v)
            
            # 儲存該公司最新的一筆季報資料
            curr_dict[code] = {
                "eps": eps, 
                "op_p": op_p, 
                "pre_t": pre_t, 
                "q": str(item.get('季別', '')).strip()
            }

    # 執行偵錯：看看 API 裡有沒有 3023
    if '3023' in curr_dict:
        print(f"🎯 成功在 API 找到 3023 ! 內容: {curr_dict['3023']}")
    else:
        print("⚠️ 警告：API 114年度列表裡完全沒看到 3023。")

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        h = data[0]
        
        try:
            i_c = next(i for i, x in enumerate(h) if "代號" in x)
            cells = []
            for r_idx, row in enumerate(data[1:], start=2):
                c_code = row[i_c].split('.')[0].strip()
                if c_code in curr_dict:
                    d = curr_dict[c_code]
                    # 從 AO 欄位開始填入 (AO=41, AP=42, AQ=43, AR=44)
                    cells.append(gspread.Cell(row=r_idx, col=41, value=d["eps"]))    # AO: EPS
                    cells.append(gspread.Cell(row=r_idx, col=42, value=d["op_p"]))   # AP: 營業利益
                    cells.append(gspread.Cell(row=r_idx, col=43, value=d["pre_t"]))  # AQ: 稅前淨利
                    cells.append(gspread.Cell(row=r_idx, col=44, value=f"Q{d['q']}"))# AR: 來源季別
            
            if cells:
                ws.update_cells(cells, value_input_option='USER_ENTERED')
                print(f"✅ {ws.title} 原始數據已填入 AO-AR 欄。")
        except Exception as e:
            print(f"❌ {ws.title} 定位錯誤: {e}")

if __name__ == "__main__":
    fetch_and_update()
