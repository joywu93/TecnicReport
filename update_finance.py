# ==========================================
# 📂 檔案名稱： update_finance.py (V182 欄位對位修正版)
# 💡 更新核心： 1. 精準比對長欄位名稱 2. 強制反推業外算法
# ==========================================

import os
import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 設定區 ---
MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

# 設定目標：114年 Q4 (即將收尾的數據)
TARGET_YEAR_ROC = "114"   
TARGET_Q = 4              
Q_STRING = "25Q4" # 您的 Sheet 應該是用 25Q4 代表 2025Q4 (民國114Q4)

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
    print(f"🚀 啟動更新：抓取 {TARGET_YEAR_ROC}Q{TARGET_Q} 數據...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 1. 抓取 API
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False, timeout=15).json()
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False, timeout=15).json()
    except Exception as e:
        print(f"❌ API 連線失敗: {e}"); return

    # 2. 數據封裝 (反推業外邏輯)
    curr_dict = {}
    for item in (res_twse + res_tpex):
        code = str(item.get('公司代號', '')).strip()
        if not code or str(item.get('年度', '')).strip() != TARGET_YEAR_ROC or str(item.get('季別', '')).strip() != str(TARGET_Q): 
            continue
        
        eps = parse_val(item.get('基本每股盈餘(元)')) or parse_val(item.get('基本每股盈餘'))
        op_profit = parse_val(item.get('營業利益（損失）')) or parse_val(item.get('營業利益'))
        
        pre_tax = 0.0
        for k in ['繼續營業單位稅前淨利（淨損）', '稅前淨利（淨損）', '稅前淨利']:
            v = parse_val(item.get(k))
            if v != 0:
                pre_tax = v
                break
        
        # 強制反推佔比
        non_op_ratio = 0.0
        if pre_tax != 0:
            calc_non_op = pre_tax - op_profit
            non_op_ratio = round((calc_non_op / pre_tax) * 100, 2)
            
        curr_dict[code] = {"eps": eps, "non_op": non_op_ratio}

    # 3. 精準寫入 Sheet
    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        if not data: continue
        h = data[0]
        
        # 欄位定位修正
        try:
            i_c = next(i for i, x in enumerate(h) if "代號" in x)
            i_e = next(i for i, x in enumerate(h) if f"{Q_STRING}單季每股盈餘" in x.replace(' ', ''))
            i_ae = next(i for i, x in enumerate(h) if "最新累季每股盈餘" in x.replace(' ', ''))
            
            # 🌟 這裡修正為您 Sheet 上的長名稱：最新單季業外損益佔稅前淨利(%)
            i_nop = next(i for i, x in enumerate(h) if "最新單季業外損益佔稅前淨利(%)" in x.replace(' ', ''))
            
            # 定位 Q1-Q3
            i_q1 = next((i for i, x in enumerate(h) if "25Q1單季每股盈餘" in x.replace(' ', '')), -1)
            i_q2 = next((i for i, x in enumerate(h) if "25Q2單季每股盈餘" in x.replace(' ', '')), -1)
            i_q3 = next((i for i, x in enumerate(h) if "25Q3單季每股盈餘" in x.replace(' ', '')), -1)
        except Exception as e:
            print(f"⚠️ {ws.title} 欄位定位失敗: {e}"); continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            if code in curr_dict:
                info = curr_dict[code]
                
                # Q4 單季 EPS 計算
                def get_v(idx):
                    if idx == -1 or idx >= len(row): return 0.0
                    try: return float(row[idx].replace(',', ''))
                    except: return 0.0
                
                single_q_eps = info["eps"] - (get_v(i_q1) + get_v(i_q2) + get_v(i_q3))

                cells.append(gspread.Cell(row=r_idx, col=i_e+1, value=round(single_q_eps, 2)))
                cells.append(gspread.Cell(row=r_idx, col=i_ae+1, value=round(info["eps"], 2)))
                cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=info["non_op"]))
        
        if cells:
            ws.update_cells(cells)
            print(f"✅ {ws.title} 更新成功")

if __name__ == "__main__":
    fetch_and_update()
