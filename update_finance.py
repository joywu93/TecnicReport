import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# ⚙️ 晚輩接手必看：自訂設定區
# ==========================================
MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

# 設定要尋找的累計 EPS 欄位關鍵字
COL_NAME_CUM_EPS = "最新累季"          

# ==========================================
# 🤖 智慧日期判讀系統
# ==========================================
now = datetime.now()
current_year = now.year
current_month = now.month

if current_month in [5, 6, 7]:
    target_y = current_year
    target_q = 1
elif current_month in [8, 9, 10]:
    target_y = current_year
    target_q = 2
elif current_month in [11, 12]:
    target_y = current_year
    target_q = 3
else:
    target_y = current_year - 1
    target_q = 4

TARGET_YEAR_ROC = str(target_y - 1911)
TARGET_Q = target_q
Q_STRING = f"{str(target_y)[-2:]}Q{target_q}"

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    if not key_data:
        raise ValueError("找不到 Google 金鑰環境變數")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def fetch_and_update():
    print(f"啟動財報更新機器人：鎖定抓取【{TARGET_YEAR_ROC}年 Q{TARGET_Q}】EPS 資料 (標題: {Q_STRING})...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False, timeout=15).json()
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False, timeout=15).json()
    except Exception as e:
        print(f"抓取失敗: {e}")
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

    print(f"成功解析 {len(curr_dict)} 檔股票 EPS。準備寫入表單...")

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

    print(f"🎉 EPS 專屬任務完成！共更新 {update_count} 個儲存格。")

if __name__ == "__main__":
    fetch_and_update()
