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
    # 抓取簡表 (用來抓 EPS)
    brief_data = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False).json()
    # 抓取損益表 (用來抓 營業利益 與 稅前淨利)
    detail_data = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap11_L", headers=headers, verify=False).json()
    
    # 建立數據字典
    stats = {}
    
    # 1. 先從簡表拿 EPS
    for item in brief_data:
        if str(item.get('年度')) == TARGET_YEAR and str(item.get('季別')) == TARGET_Q:
            code = str(item.get('公司代號')).strip()
            stats[code] = {"eps": force_float(item.get('基本每股盈餘(元)')), "op": 0.0, "pre_tax": 0.0}

    # 2. 從細表拿準確的金額
    for item in detail_data:
        code = str(item.get('公司代號')).strip()
        if code in stats and str(item.get('年度')) == TARGET_YEAR and str(item.get('季別')) == TARGET_Q:
            # 損益表的欄位更精準
            stats[code]["op"] = force_float(item.get('營業利益（損失）'))
            stats[code]["pre_tax"] = force_float(item.get('繼續營業單位稅前淨利（淨損）'))

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
            
            # 定位 Q1-Q3 欄位以便扣除
            i_q123 = [next((i for i, x in enumerate(h) if f"25Q{q}單季" in x), -1) for q in [1,2,3]]

            cells = []
            for r_idx, row in enumerate(data[1:], start=2):
                code = row[i_c].split('.')[0].strip()
                if code in stats:
                    d = stats[code]
                    
                    # 計算 Q4 單季 EPS
                    q123_val = sum(force_float(row[idx]) for idx in i_q123 if idx != -1)
                    q4_single_eps = d["eps"] - q123_val
                    
                    # 計算業外佔比 (稅前 - 營業利益) / 稅前
                    non_op_ratio = 0.0
                    if d["pre_tax"] != 0:
                        non_op_ratio = round(((d["pre_tax"] - d["op"]) / d["pre_tax"]) * 100, 2)
                    
                    # 寫入正確欄位
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_eps+1, value=round(q4_single_eps, 2)))
                    cells.append(gspread.Cell(row=r_idx, col=i_non_op+1, value=non_op_ratio))
                    
                    # 同時更新後面的證據欄位方便核對
                    cells.append(gspread.Cell(row=r_idx, col=41, value=d["op"]))      # AO
                    cells.append(gspread.Cell(row=r_idx, col=42, value=d["pre_tax"]))  # AP
            
            if cells:
                ws.update_cells(cells, value_input_option='USER_ENTERED')
                print(f"✅ {ws.title} 資料更新成功")
        except: continue

if __name__ == "__main__":
    fetch_and_update()
