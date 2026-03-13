# ==========================================
# 📂 檔案名稱： update_finance.py (V182 獲利成分拆解版)
# 💡 核心邏輯： 業外損益 = 繼續營業單位稅前淨利 - 營業利益
# ==========================================

import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

# 目前鎖定 114Q4 (即全年度累計)
TARGET_YEAR_ROC = "114"   
TARGET_Q = 4              
Q_STRING = "25Q4"         

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    if not key_data: raise ValueError("找不到 Google 金鑰")
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
    print(f"🚀 啟動偵測：{TARGET_YEAR_ROC}Q{TARGET_Q} 數據分析中...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 同時抓取上市與上櫃資料
    res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False, timeout=15).json()
    res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False, timeout=15).json()

    curr_dict = {}

    for item in (res_twse + res_tpex):
        code = str(item.get('公司代號', '')).strip()
        if not code or str(item.get('年度', '')).strip() != TARGET_YEAR_ROC or str(item.get('季別', '')).strip() != str(TARGET_Q): 
            continue
            
        # --- 核心抓取邏輯 ---
        # 1. EPS
        eps = parse_val(item.get('基本每股盈餘(元)')) or parse_val(item.get('基本每股盈餘'))
        
        # 2. 營業利益 (本業)
        op_profit = parse_val(item.get('營業利益（損失）')) or parse_val(item.get('營業利益'))
        
        # 3. 稅前淨利 (總獲利)
        # 注意：API 欄位名稱極度不穩，這裡做多重匹配
        pre_tax = 0.0
        pre_tax_keys = ['繼續營業單位稅前淨利（淨損）', '稅前淨利（淨損）', '繼續營業單位稅前純益（純損）', '稅前淨利']
        for k in pre_tax_keys:
            val = parse_val(item.get(k))
            if val != 0:
                pre_tax = val
                break
        
        # --- 業外佔比計算 (公式：(稅前 - 本業) / 稅前) ---
        non_op_ratio = 0.0
        if pre_tax != 0:
            # 這是最穩定的算法，直接避開官方那個亂填的「營業外收入及支出」欄位
            calc_non_op = pre_tax - op_profit
            non_op_ratio = round((calc_non_op / pre_tax) * 100, 2)
            
        curr_dict[code] = {
            "eps_cumulative": eps,
            "non_op_ratio": non_op_ratio
        }

    # 寫入 Google Sheets
    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        
        data = ws.get_all_values()
        if not data: continue
        h = data[0]
        
        # 定位欄位
        try:
            i_c = next(i for i, x in enumerate(h) if "代號" in x)
            i_e = next(i for i, x in enumerate(h) if f"{Q_STRING}單季每股盈餘" in x.replace(' ', ''))
            i_ae = next(i for i, x in enumerate(h) if "最新累季每股盈餘" in x.replace(' ', ''))
            i_nop = next(i for i, x in enumerate(h) if "最新單季業外損益" in x.replace(' ', ''))
            
            # 抓 Q1-Q3 算單季 EPS
            i_q1 = next((i for i, x in enumerate(h) if "25Q1單季每股盈餘" in x.replace(' ', '')), -1)
            i_q2 = next((i for i, x in enumerate(h) if "25Q2單季每股盈餘" in x.replace(' ', '')), -1)
            i_q3 = next((i for i, x in enumerate(h) if "25Q3單季每股盈餘" in x.replace(' ', '')), -1)
        except: continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            if code in curr_dict:
                c = curr_dict[code]
                
                # 計算單季 EPS
                single_eps = c["eps_cumulative"]
                if TARGET_Q == 4:
                    def v(idx):
                        if idx == -1: return 0
                        try: return float(row[idx].replace(',', ''))
                        except: return 0
                    single_eps -= (v(i_q1) + v(i_q2) + v(i_q3))

                cells.append(gspread.Cell(row=r_idx, col=i_e+1, value=round(single_eps, 2)))
                cells.append(gspread.Cell(row=r_idx, col=i_ae+1, value=round(c["eps_cumulative"], 2)))
                cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=c["non_op_ratio"]))
        
        if cells:
            ws.update_cells(cells)
            print(f"✅ {ws.title} 更新完成")

if __name__ == "__main__":
    fetch_and_update()
