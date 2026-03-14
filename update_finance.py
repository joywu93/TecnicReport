# ==========================================
# 📂 檔案名稱： update_finance.py (V186 防空值更新版)
# 💡 策略： 只有當 API 提供非 0 的利潤數據時，才更新業外佔比，避免被 0 覆蓋
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
    # 擷取正式損益表
    try:
        res_detail = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap11_L", headers=headers, verify=False, timeout=30).json()
        res_detail_o = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap11_O", headers=headers, verify=False, timeout=30).json()
        all_detail = res_detail + res_detail_o
    except: return

    stats = {}
    for item in all_detail:
        if str(item.get('年度')) == "114" and str(item.get('季別')) == "4":
            code = str(item.get('公司代號')).strip()
            op = force_float(item.get('營業利益（損失）'))
            pre_t = force_float(item.get('繼續營業單位稅前淨利（淨損）'))
            eps = force_float(item.get('基本每股盈餘（元）'))
            
            # 🌟 只有當數據不是 0 時才記錄
            stats[code] = {"eps": eps, "op": op, "pre_t": pre_t}

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        h = data[0]
        i_c = next(i for i, x in enumerate(h) if "代號" in x)
        i_nop = next(i for i, x in enumerate(h) if "業外" in x and "%" in x)
        
        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            if code in stats:
                d = stats[code]
                
                # 🌟 關鍵邏輯：如果 API 抓到的是 0，就不更新這一格，保留原本的數據
                if d["pre_t"] != 0:
                    non_op_ratio = round(((d["pre_t"] - d["op"]) / d["pre_t"]) * 100, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=non_op_ratio))
                
                # 同步更新 AO-AR 證據欄，方便我們觀察 API 什麼時候「活過來」
                cells.append(gspread.Cell(row=r_idx, col=41, value=d["eps"]))
                cells.append(gspread.Cell(row=r_idx, col=42, value=d["op"]))
                cells.append(gspread.Cell(row=r_idx, col=43, value=d["pre_t"]))
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 掃描更新完成。")

if __name__ == "__main__":
    fetch_and_update()
