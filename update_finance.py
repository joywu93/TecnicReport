# ==========================================
# 📂 檔案名稱： update_finance.py (V182 財報全項目搜索版)
# 💡 更新內容： 針對 API 欄位不固定問題，改用「全項目加總」抓取業外數據
# ==========================================

import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"
TARGET_YEAR_ROC = "114"   
TARGET_Q = 4              
Q_STRING = "25Q4"         

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    if not key_data: raise ValueError("找不到 Google 金鑰")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def fetch_and_update():
    print(f"啟動財報機器人：鎖定抓取【{TARGET_YEAR_ROC}年 Q{TARGET_Q}】資料...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False, timeout=15).json()
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False, timeout=15).json()
    except Exception as e:
        print(f"抓取失敗: {e}"); return

    curr_dict = {}

    def parse_float(v):
        if v is None: return 0.0
        s = str(v).strip().replace(',', '')
        if not s or s in ['None', '', '-']: return 0.0
        if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
        try: return float(s)
        except: return 0.0

    for item in (res_twse + res_tpex):
        code = str(item.get('公司代號', '')).strip()
        if not code or str(item.get('年度', '')).strip() != TARGET_YEAR_ROC or str(item.get('季別', '')).strip() != str(TARGET_Q): 
            continue
            
        # 1. 抓取 EPS (基本每股盈餘)
        eps_raw = 0.0
        for k, v in item.items():
            if '基本每股盈餘' in k or '每股盈餘' in k:
                eps_raw = parse_float(v)
                if eps_raw != 0: break

        # 2. 抓取「稅前淨利」
        pre_tax = 0.0
        for k, v in item.items():
            ck = k.replace(' ', '')
            if ('稅前' in ck and '淨利' in ck) or ('稅前' in ck and '損益' in ck) or '繼續營業單位稅前' in ck:
                if '所得稅' not in ck and '每股' not in ck:
                    pre_tax = parse_float(v)
                    if pre_tax != 0: break

        # 3. 抓取「營業外損益」 (這是本案難點)
        non_op = 0.0
        # 先找直接欄位
        for k, v in item.items():
            ck = k.replace(' ', '')
            if '營業外收入及支出' in ck or '營業外損益' in ck or '營業外收支' in ck:
                non_op = parse_float(v)
                if non_op != 0: break
        
        # 如果還是 0，嘗試用「稅前淨利 - 營業利益」
        if non_op == 0:
            op_profit = 0.0
            for k, v in item.items():
                if '營業利益' in k.replace(' ', ''):
                    op_profit = parse_float(v)
                    if op_profit != 0: break
            if pre_tax != 0 and op_profit != 0:
                non_op = pre_tax - op_profit

        non_op_ratio = 0.0
        if pre_tax != 0:
            non_op_ratio = round((non_op / pre_tax) * 100, 2)
            
        curr_dict[code] = {
            "eps_cumulative": eps_raw,
            "non_op_ratio": non_op_ratio
        }

    # 寫入邏輯
    client = get_gspread_client()
    worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
    target_sheets = [ws for ws in worksheets if any(n in ws.title for n in ["個股總表", "金融股"])]
    
    def ultra_clean(text):
        return str(text).replace('\n', '').replace('\r', '').replace(' ', '').replace('（', '(').replace('）', ')')
    
    update_count = 0
    for ws in target_sheets:
        data = ws.get_all_values()
        if not data: continue
        h = data[0]
        i_c = next((i for i, x in enumerate(h) if "代號" in ultra_clean(x)), -1)
        i_e = next((i for i, x in enumerate(h) if f"{Q_STRING}單季每股盈餘" in ultra_clean(x)), -1)
        i_ae = next((i for i, x in enumerate(h) if "最新累季每股盈餘" in ultra_clean(x)), -1)
        i_nop = next((i for i, x in enumerate(h) if "最新單季業外損益" in ultra_clean(x)), -1)
        
        # 尋找 Q1-Q3 欄位以便計算 Q4 單季
        i_q1 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q1單季每股盈餘" in ultra_clean(x)), -1)
        i_q2 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q2單季每股盈餘" in ultra_clean(x)), -1)
        i_q3 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q3單季每股盈餘" in ultra_clean(x)), -1)

        if i_c != -1 and i_e != -1:
            cells_to_update = []
            for r, row in enumerate(data):
                if r == 0: continue
                code = str(row[i_c]).split('.')[0].strip()
                if code in curr_dict:
                    curr = curr_dict[code]
                    
                    # 計算單季 EPS
                    single_q_eps = curr["eps_cumulative"]
                    def get_v(idx):
                        if idx == -1: return 0.0
                        v = str(row[idx]).replace(',', '').strip()
                        try: return float(v) if v and v != '-' else 0.0
                        except: return 0.0
                    if TARGET_Q == 4:
                        single_q_eps -= (get_v(i_q1) + get_v(i_q2) + get_v(i_q3))
                    
                    # 準備批次更新
                    cells_to_update.append(gspread.Cell(row=r+1, col=i_e+1, value=round(single_q_eps, 2)))
                    if i_ae != -1:
                        cells_to_update.append(gspread.Cell(row=r+1, col=i_ae+1, value=round(curr["eps_cumulative"], 2)))
                    if i_nop != -1:
                        cells_to_update.append(gspread.Cell(row=r+1, col=i_nop+1, value=curr["non_op_ratio"]))

            if cells_to_update:
                ws.update_cells(cells_to_update)
                update_count += len(cells_to_update)
                print(f"   🚀 {ws.title} 更新完成")

    print(f"\n🎉 任務圓滿完成！共更新 {update_count} 個儲存格。")

if __name__ == "__main__":
    fetch_and_update()
