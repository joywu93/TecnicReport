# ==========================================
# 📂 檔案名稱： update_finance.py (V182 型態純淨版)
# 💡 修改重點： 強制 float 轉換，排除字串干擾，確保 3023 業外佔比不為 0
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

def force_float(v):
    """ 強力將任何鬼東西轉成純 float，失敗就回傳 0.0 """
    if v is None: return 0.0
    s = str(v).strip().replace(',', '').replace('%', '')
    if not s or s in ['None', '', '-', 'NULL']: return 0.0
    # 處理括號負數 (123) -> -123
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    try:
        return float(s)
    except:
        return 0.0

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
        
        # 抓取 EPS (累計)
        eps = force_float(item.get('基本每股盈餘(元)')) or force_float(item.get('基本每股盈餘'))
        
        # 抓取 營業利益 & 稅前淨利
        op_profit = 0.0
        pre_tax = 0.0
        
        for k, v in item.items():
            ck = k.replace(' ', '')
            if '營業利益' in ck and '每股' not in ck:
                op_profit = force_float(v)
            if (('稅前' in ck and '淨利' in ck) or ('稅前' in ck and '損益' in ck) or '繼續營業單位稅前' in ck) and '所得稅' not in ck and '每股' not in ck:
                pre_tax = force_float(v)

        # 反推業外佔比
        non_op_ratio = 0.0
        if pre_tax != 0:
            calc_non_op = pre_tax - op_profit
            non_op_ratio = round((calc_non_op / pre_tax) * 100, 2)
            
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
            # 針對您的長欄位名稱進行深度匹配
            i_nop = next(i for i, x in enumerate(h) if "業外" in x and "佔" in x and "%" in x)
            
            i_qs = [next((i for i, x in enumerate(h) if f"25Q{q}單季每股盈餘" in x.replace(' ', '')), -1) for q in [1,2,3]]
        except Exception as e:
            print(f"⚠️ {ws.title} 欄位定位失敗: {e}"); continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            if code in curr_dict:
                info = curr_dict[code]
                
                # Q1-Q3 計算 (確保參與計算的都是 float)
                q123_sum = 0.0
                for idx in i_qs:
                    if idx != -1: q123_sum += force_float(row[idx])
                
                single_q_eps = float(info["eps"]) - q123_sum

                # 強制使用 Python 原生 float 型態寫入
                cells.append(gspread.Cell(row=r_idx, col=i_e+1, value=float(round(single_q_eps, 2))))
                cells.append(gspread.Cell(row=r_idx, col=i_ae+1, value=float(round(info["eps"], 2))))
                cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=float(info["non_op"])))
        
        if cells:
            # 使用 raw=False 讓 Google Sheets 自動嘗試解析格式，但傳入值確保是數字
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"✅ {ws.title} 更新完成 (含業外佔比)")

if __name__ == "__main__":
    fetch_and_update()
