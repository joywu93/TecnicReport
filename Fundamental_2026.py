# ==========================================
# 📂 檔案名稱： update_finance.py (V182 舊版專注 EPS 更新機器人)
# 💡 更新內容： 加入「欄位尋找診斷報告」，精準揪出不更新的原因
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
# ⚠️ 關鍵設定區：請確認這裡的 Q_STRING 是否與您表單的標題「完全一致」！
TARGET_YEAR_ROC = "113"   # 政府資料年度 (113年年報)
TARGET_Q = 4              # 政府資料季別
Q_STRING = "25Q4"         # 👈 尋找您表單上的標題前綴 (如表單是 25Q4單季每股盈餘，就填 25Q4)
COL_NAME_CUM_EPS = "最新累季" # 尋找最新累季的標題關鍵字
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
    
    update_count = 0
    for ws in target_sheets:
        data = ws.get_all_values()
        if not data: continue
        h = data[0]
        
        i_c = next((i for i, x in enumerate(h) if "代號" in str(x)), -1)
        i_e = next((i for i, x in enumerate(h) if f"{Q_STRING}單季每股盈餘" in str(x).replace(' ','')), -1)
        i_ae = next((i for i, x in enumerate(h) if COL_NAME_CUM_EPS in str(x).replace(' ','')), -1)
        
        i_q1 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q1單季每股盈餘" in str(x).replace(' ','')), -1)
        i_q2 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q2單季每股盈餘" in str(x).replace(' ','')), -1)
        i_q3 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q3單季每股盈餘" in str(x).replace(' ','')), -1)

        # 🌟 診斷系統：回報尋找欄位的結果
        print(f"\n🔍 正在檢查分頁: {ws.title}")
        if i_e == -1:
            print(f"   ❌ 找不到目標：'{Q_STRING}單季每股盈餘' (請檢查表單標題是否有空白或打錯字)")
        else:
            print(f"   ✅ 找到目標單季EPS欄位！")
            
        if i_ae == -1:
            print(f"   ❌ 找不到目標：包含 '{COL_NAME_CUM_EPS}' 的欄位")
        else:
            print(f"   ✅ 找到最新累季EPS欄位！")

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

                    # 寫入單季 EPS
                    cells_to_update.append(gspread.Cell(row=r+1, col=i_e+1, value=round(single_q_eps, 2)))
                    
                    # 寫入最新累季 EPS
                    if i_ae != -1:
                        cells_to_update.append(gspread.Cell(row=r+1, col=i_ae+1, value=round(curr["eps_cumulative"], 2)))

            if cells_to_update:
                ws.update_cells(cells_to_update)
                update_count += len(cells_to_update)
                print(f"   🚀 寫入 {len(cells_to_update)} 個儲存格。")

    print(f"\n🎉 任務完成！共更新 {update_count} 個儲存格。")

if __name__ == "__main__":
    fetch_and_update()
