import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 設定區 ---
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
    # 🌟 關鍵更換：改用 t187ap11_L (正式綜合損益表 API)
    print(f"📡 正在從【正式損益表 API】抓取 {TARGET_YEAR}Q{TARGET_Q} 數據...")
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap11_L", headers=headers, verify=False, timeout=30).json()
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap11_O", headers=headers, verify=False, timeout=30).json()
        all_data = res_twse + res_tpex
    except Exception as e:
        print(f"❌ API 連線失敗: {e}"); return

    stats = {}
    for item in all_data:
        # 正式表的年度與季別過濾
        if str(item.get('年度')) == TARGET_YEAR and str(item.get('季別')) == TARGET_Q:
            code = str(item.get('公司代號', '')).strip()
            
            # 正式損益表的欄位名稱 (這是最穩定的來源)
            eps = force_float(item.get('基本每股盈餘（元）'))
            op_p = force_float(item.get('營業利益（損失）'))
            pre_t = force_float(item.get('繼續營業單位稅前淨利（淨損）'))
            
            if code in ['3023', '3030']:
                print(f"🎯 成功鎖定 {code}: EPS={eps}, 營業利益={op_p}, 稅前={pre_t}")
            
            stats[code] = {"eps": eps, "op_p": op_p, "pre_t": pre_t}

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        h = data[0]
        
        try:
            i_c = next(i for i, x in enumerate(h) if "代號" in x)
            i_q4_eps = next(i for i, x in enumerate(h) if "25Q4單季每股盈餘" in x.replace(' ', ''))
            i_non_op = next(i for i, x in enumerate(h) if "業外" in x and "佔" in x and "%" in x)
            i_q123 = [next((i for i, x in enumerate(h) if f"25Q{q}單季" in x.replace(' ', '')), -1) for q in [1,2,3]]

            cells = []
            for r_idx, row in enumerate(data[1:], start=2):
                code = row[i_c].split('.')[0].strip()
                if code in stats:
                    d = stats[code]
                    # 單季 EPS 計算 (累計 - 前三季)
                    q123_val = sum(force_float(row[idx]) for idx in i_q123 if idx != -1)
                    q4_single_eps = d["eps"] - q123_val
                    
                    # 業外佔比計算
                    non_op_ratio = 0.0
                    if d["pre_t"] != 0:
                        non_op_ratio = round(((d["pre_t"] - d["op_p"]) / d["pre_t"]) * 100, 2)
                    
                    # 1. 更新 Q4 單季 EPS
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_eps+1, value=round(q4_single_eps, 2)))
                    # 2. 更新 業外損益佔比
                    cells.append(gspread.Cell(row=r_idx, col=i_non_op+1, value=non_op_ratio))
                    # 3. 更新 AO-AQ 證據欄位 (供您檢視數據有沒有進來)
                    cells.append(gspread.Cell(row=r_idx, col=41, value=d["op_p"]))   # AO
                    cells.append(gspread.Cell(row=r_idx, col=42, value=d["pre_t"]))  # AP
            
            if cells:
                ws.update_cells(cells, value_input_option='USER_ENTERED')
                print(f"📊 {ws.title} 同步成功！")
        except: continue

if __name__ == "__main__":
    fetch_and_update()
