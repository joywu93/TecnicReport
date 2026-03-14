# ==========================================
# 📂 檔案名稱： update_finance.py (原始數據展示版)
# 💡 核心邏輯： 不做複雜計算，直接把 API 原始數值填入 AN 之後的欄位
# ==========================================

import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"
TARGET_YEAR_ROC = "114"   
TARGET_Q = 4              

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
    res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False).json()
    res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False).json()

    curr_dict = {}
    for item in (res_twse + res_tpex):
        code = str(item.get('公司代號', '')).strip()
        if str(item.get('年度')) == TARGET_YEAR_ROC and str(item.get('季別')) == str(TARGET_Q):
            
            # 遍歷抓取三大原始數據
            eps, op_p, pre_t = 0.0, 0.0, 0.0
            for k, v in item.items():
                k_c = k.replace(' ', '')
                if '基本每股盈餘' in k_c and '元' in k_c: eps = force_float(v)
                if '營業利益' in k_c and '每股' not in k_c: op_p = force_float(v)
                if '稅前' in k_c and ('淨利' in k_c or '損益' in k_c) and '所得稅' not in k_c: pre_t = force_float(v)
            
            curr_dict[code] = {"eps": eps, "op_p": op_p, "pre_t": pre_t}

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        h = data[0]
        
        try:
            i_c = next(i for i, x in enumerate(h) if "代號" in x)
            # 我們強制定義 AN=40, AO=41, AP=42 (索引從 0 開始)
            # 您可以觀察 Sheet 最後面是否出現這三欄數據
            
            cells = []
            for r_idx, row in enumerate(data[1:], start=2):
                c_code = row[i_c].split('.')[0].strip()
                if c_code in curr_dict:
                    d = curr_dict[c_code]
                    # 填入 AN 欄 (索引 39): 原始 EPS
                    cells.append(gspread.Cell(row=r_idx, col=40, value=d["eps"]))
                    # 填入 AO 欄 (索引 40): 原始營業利益
                    cells.append(gspread.Cell(row=r_idx, col=41, value=d["op_p"]))
                    # 填入 AP 欄 (索引 41): 原始稅前淨利
                    cells.append(gspread.Cell(row=r_idx, col=42, value=d["pre_t"]))
            
            if cells:
                ws.update_cells(cells, value_input_option='USER_ENTERED')
                print(f"✅ {ws.title} 原始數據展示完畢 (AN-AP欄)")
        except Exception as e:
            print(f"❌ {ws.title} 錯誤: {e}")

if __name__ == "__main__":
    fetch_and_update()
