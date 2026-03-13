# ==========================================
# 📂 檔案名稱： update_finance.py (V182 舊版專注 EPS 更新機器人)
# 💡 更新內容： 修正民國年對應 (114年=25Q4)、強化表單標題的換行與空白過濾機制
# ==========================================

import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

# ==========================================
# ⚠️ 關鍵設定區：已為您完全對齊 2025 年的數據
TARGET_YEAR_ROC = "114"   # 2025 年 = 民國 114 年 (非常重要！)
TARGET_Q = 4              
Q_STRING = "25Q4"         
COL_NAME_CUM_EPS = "最新累季每股盈餘(元)" # 您提供的精準標題
# ==========================================

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    if not key_data: raise ValueError("找不到 Google 金鑰環境變數")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def fetch_and_update():
    print(f"啟動財報機器人：抓取官方【{TARGET_YEAR_ROC}年 Q{TARGET_Q}】資料，準備填入表單【{Q_STRING}】欄位...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False, timeout=15).json()
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False, timeout=15).json()
    except Exception as e:
        print(f"抓取官方資料失敗: {e}")
        return

    curr_dict = {}
    
    def ext_val(item, kws, ex=None):
        if ex is None: ex = []
        for k, v in item.items():
            ck = str(k).replace(' ', '').replace('（', '(').replace('）', '')
            if any(kw in ck for kw in kws) and not any(e in ck for e in ex):
                v_str = str(v).strip()
                if v_str and v_str not in ['None', '']:
                    v_str = '-' + v_str[1:-1].replace(',', '') if v_str.startswith('(') else v_str.replace(',', '')
                    try: return float(v_str)
                    except: pass
        return 0.0

    for item in (res_twse + res_tpex):
        code = str(item.get('公司代號', '')).strip()
        if not code or str(item.get('年度', '')).strip() != TARGET_YEAR_ROC or str(item.get('季別', '')).strip() != str(TARGET_Q): 
            continue
            
        eps_raw = ext_val(item, ['基本每股盈餘', '每股盈餘'])
        curr_dict[code] = {"eps_cumulative": eps_raw}

    print(f"✅ 成功解析 {len(curr_dict)} 檔股票 EPS。準備進入表單尋找欄位...")

    client = get_gspread_client()
    worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
    target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]
    
    # 🌟 防彈級的標題清洗功能 (去除所有空白、換行、全形括號)
    def clean_h(val):
        return str(val).replace('\n', '').replace('\r', '').replace(' ', '').replace('（', '(').replace('）', ')')
    
    clean_target_eps = clean_h(COL_NAME_CUM_EPS)
    
    update_count = 0
    for ws in target_sheets:
        data = ws.get_all_values()
        if not data: continue
        h = data[0]
        
        i_c = next((i for i, x in enumerate(h) if "代號" in clean_h(x)), -1)
        i_e = next((i for i, x in enumerate(h) if f"{Q_STRING}單季每股盈餘" in clean_h(x)), -1)
        i_ae = next((i for i, x in enumerate(h) if clean_target_eps in clean_h(x)), -1)
        
        i_q1 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q1單季每股盈餘" in clean_h(x)), -1)
        i_q2 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q2單季每股盈餘" in clean_h(x)), -1)
        i_q3 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q3單季每股盈餘" in clean_h(x)), -1)

        print(f"\n🔍 正在檢查分頁: {ws.title}")
        if i_e == -1: print(f"   ❌ 找不到目標：'{Q_STRING}單季每股盈餘' (表單上的標題可能是: {[clean_h(x) for x in h if Q_STRING in clean_h(x)]})")
        else: print(f"   ✅ 成功鎖定目標：單季EPS欄位 (索引 {i_e})")
            
        if i_ae == -1: print(f"   ❌ 找不到目標：包含 '{COL_NAME_CUM_EPS}' 的欄位")
        else: print(f"   ✅ 成功鎖定目標：最新累季EPS欄位 (索引 {i_ae})")

        if i_c != -1 and i_e != -1:
            cells_to_update = []
            for r, row in enumerate(data):
                if r == 0: continue
                code = str(row[i_c]).split('.')[0].strip()
                if code in curr_dict:
                    curr = curr_dict[code]
                    
                    single_q_eps = curr["eps_cumulative"]
                    def get_v(idx):
                        if idx == -1: return 0.0
                        v = str(row[idx]).replace(',', '').strip()
                        try: return float(v) if v and v != '-' else 0.0
                        except: return 0.0
                        
                    if TARGET_Q == 4: single_q_eps -= (get_v(i_q1) + get_v(i_q2) + get_v(i_q3))
                    elif TARGET_Q == 3: single_q_eps -= (get_v(i_q1) + get_v(i_q2))
                    elif TARGET_Q == 2: single_q_eps -= get_v(i_q1)

                    cells_to_update.append(gspread.Cell(row=r+1, col=i_e+1, value=round(single_q_eps, 2)))
                    if i_ae != -1:
                        cells_to_update.append(gspread.Cell(row=r+1, col=i_ae+1, value=round(curr["eps_cumulative"], 2)))

            if cells_to_update:
                ws.update_cells(cells_to_update)
                update_count += len(cells_to_update)
                print(f"   🚀 成功將 {len(cells_to_update)} 筆資料寫入表單！")

    print(f"\n🎉 任務完成！共更新 {update_count} 個儲存格。")

if __name__ == "__main__":
    fetch_and_update()
