# ==========================================
# 📂 檔案名稱： update_finance.py (AO 數據展示研究版)
# 💡 目的： 將 API 所有原始欄位填入 AO 之後，找出為什麼金額是 0
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
    headers = {'User-Agent': 'Mozilla/5.0'}
    # 同時抓取兩個 API 來源進行比對
    print("📡 正在擷取 API 原始數據...")
    res_brief = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False).json()
    res_detail = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap11_L", headers=headers, verify=False).json()

    # 彙整數據字典
    raw_data_map = {}
    
    # 掃描簡表 (Brief)
    for item in res_brief:
        if str(item.get('年度')) == "114" and str(item.get('季別')) == "4":
            code = str(item.get('公司代號')).strip()
            raw_data_map[code] = {
                "brief_eps": force_float(item.get('基本每股盈餘(元)')),
                "brief_op": force_float(item.get('營業利益')),
                "detail_op": 0.0,
                "detail_pretax": 0.0
            }

    # 掃描正式損益表 (Detail)
    for item in res_detail:
        code = str(item.get('公司代號')).strip()
        if code in raw_data_map and str(item.get('年度')) == "114" and str(item.get('季別')) == "4":
            raw_data_map[code]["detail_op"] = force_float(item.get('營業利益（損失）'))
            raw_data_map[code]["detail_pretax"] = force_float(item.get('繼續營業單位稅前淨利（淨損）'))

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        h = data[0]
        i_c = next(i for i, x in enumerate(h) if "代號" in x)
        
        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            if code in raw_data_map:
                d = raw_data_map[code]
                # 填入 AO(41) 之後的欄位
                cells.append(gspread.Cell(row=r_idx, col=41, value=d["brief_eps"]))     # AO: 簡表EPS
                cells.append(gspread.Cell(row=r_idx, col=42, value=d["brief_op"]))      # AP: 簡表營業利益
                cells.append(gspread.Cell(row=r_idx, col=43, value=d["detail_op"]))     # AQ: 正式表營業利益
                cells.append(gspread.Cell(row=r_idx, col=44, value=d["detail_pretax"])) # AR: 正式表稅前淨利
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"✅ {ws.title} 原始數據展示完成 (AO-AR欄)")

if __name__ == "__main__":
    fetch_and_update()
