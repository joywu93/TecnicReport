# ==========================================
# 📂 檔案名稱： update_finance.py (V182 終極除錯版)
# 💡 修改重點： 強化營業利益與稅前淨利的比對邏輯，確保相減不為 0
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
Q_STRING = "25Q4" 

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def parse_val(v):
    if v is None: return 0.0
    s = str(v).strip().replace(',', '')
    if not s or s in ['None', '', '-']: return 0.0
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    try: return float(s)
    except: return 0.0

def fetch_and_update():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False, timeout=15).json()
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False, timeout=15).json()
    except Exception as e:
        print(f"❌ API 失敗: {e}"); return

    curr_dict = {}
    for item in (res_twse + res_tpex):
        code = str(item.get('公司代號', '')).strip()
        if not code or str(item.get('年度', '')).strip() != TARGET_YEAR_ROC or str(item.get('季別', '')).strip() != str(TARGET_Q): 
            continue
        
        # 1. 抓 EPS
        eps = parse_val(item.get('基本每股盈餘(元)')) or parse_val(item.get('基本每股盈餘'))
        
        # 2. 抓 營業利益 (加強匹配)
        op_profit = 0.0
        for k, v in item.items():
            if '營業利益' in k and '每股' not in k:
                op_profit = parse_val(v)
                break
        
        # 3. 抓 稅前淨利 (加強匹配)
        pre_tax = 0.0
        for k, v in item.items():
            if ('稅前' in k and '淨利' in k) or ('稅前' in k and '損益' in k) or '繼續營業單位稅前' in k:
                if '所得稅' not in k and '每股' not in k:
                    pre_tax = parse_val(v)
                    if pre_tax != 0: break
        
        # 4. 計算業外佔比
        non_op_ratio = 0.0
        if pre_tax != 0:
            # 即使 op_profit 是 0 (例如金融業)，也會正確反應 pre_tax 的 100%
            calc_non_op = pre_tax - op_profit
            non_op_ratio = round((calc_non_op / pre_tax) * 100, 2)
        
        # 偵錯打印 (僅 3023)
        if code == '3023':
            print(f"DEBUG 3023: 稅前={pre_tax}, 營業利益={op_profit}, 業外佔比={non_op_ratio}")
            
        curr_dict[code] = {"eps": eps, "non_op": non_op_ratio}

    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        h = data[0]
        
        try:
            i_c = next(i for i, x in enumerate(h) if "代號" in x)
            i_e = next(i for i, x in enumerate(h) if f"{Q_STRING}單季每股盈餘" in x.replace(' ', ''))
            i_ae = next(i for i, x in enumerate(h) if "最新累季每股盈餘" in x.replace(' ', ''))
            # 抓取「佔稅前淨利(%)」關鍵字
            i_nop = next(i for i, x in enumerate(h) if "業外" in x and "%" in x)
            
            i_qs = [next((i for i, x in enumerate(h) if f"25Q{q}單季每股盈餘" in x.replace(' ', '')), -1) for q in [1,2,3]]
        except: continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            if code in curr_dict:
                info = curr_dict[code]
                q123 = sum(parse_val(row[idx]) for idx in i_qs if idx != -1)
                single_q_eps = info["eps"] - q123 if TARGET_Q == 4 else info["eps"]

                cells.append(gspread.Cell(row=r_idx, col=i_e+1, value=round(single_q_eps, 2)))
                cells.append(gspread.Cell(row=r_idx, col=i_ae+1, value=round(info["eps"], 2)))
                cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=info["non_op"]))
        
        if cells:
            ws.update_cells(cells)
            print(f"✅ {ws.title} 更新完成")

if __name__ == "__main__":
    fetch_and_update()
