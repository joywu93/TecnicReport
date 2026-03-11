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

COL_NAME_CUM_EPS = "最新累季"          # 對應：最新累季每股盈餘(元)
COL_NAME_CUM_GM  = "最新單季毛利率"     # 對應：最新單季毛利率(%) (註：填入的會是累計數字)
COL_NAME_CUM_OM  = "最新單季營益率"     # 對應：最新單季營益率(%) (註：填入的會是累計數字)

# ==========================================
# 🤖 智慧日期判讀系統：自動決定要抓哪一季
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

# ==========================================
def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    if not key_data:
        raise ValueError("找不到 Google 金鑰環境變數")
    
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(
        creds_dict, 
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.authorize(creds)

def fetch_and_update():
    print(f"啟動財報更新機器人：根據目前月份 ({current_month}月)，自動鎖定抓取【{TARGET_YEAR_ROC}年 Q{TARGET_Q}】資料 (標題前綴: {Q_STRING})...")
    
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
                    try: 
                        val = float(v_str)
                        if val != 0: return val  # 🌟 關鍵修復：跳過為 0 的雜訊欄位
                    except: pass
        return 0.0

    for item in (res_twse + res_tpex):
        code = str(item.get('公司代號', '')).strip()
        if not code or str(item.get('年度', '')).strip() != TARGET_YEAR_ROC or str(item.get('季別', '')).strip() != str(TARGET_Q): 
            continue
            
        eps_raw = ext_val(item, ['基本每股盈餘', '每股盈餘'])
        rev = ext_val(item, ['營業收入', '淨收益', '營業收益'])
        # 🌟 關鍵修復：精準鎖定營業毛利，排除已實現與未實現的干擾
        gp = ext_val(item, ['營業毛利', '營業毛損'], ex=['未實現', '已實現'])
        op = ext_val(item, ['營業利益', '營業損失', '營業損益'])
        
        gm_percent = round((gp / rev) * 100, 2) if rev > 0 else 0.0
        om_percent = round((op / rev) * 100, 2) if rev > 0 else 0.0

        if code in curr_dict and rev <= curr_dict[code]["rev"]: continue
        curr_dict[code] = {"rev": rev, "gm": gm_percent, "om": om_percent, "eps_cumulative": eps_raw}

    print(f"成功從政府 Open API 解析 {len(curr_dict)} 檔股票資料。準備尋找表單...")

    client = get_gspread_client()
    worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
    
    target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]
    print(f"找到目標分頁：{[ws.title for ws in target_sheets]}")
    
    update_count = 0
    for ws in target_sheets:
        data = ws.get_all_values()
        if not data: continue
        h = data[0]
        
        i_c = next((i for i, x in enumerate(h) if "代號" in str(x)), -1)
        i_e = next((i for i, x in enumerate(h) if f"{Q_STRING}單季每股盈餘" in str(x).replace(' ','')), -1)
        
        i_ae = next((i for i, x in enumerate(h) if COL_NAME_CUM_EPS in str(x).replace(' ','')), -1)
        i_gm = next((i for i, x in enumerate(h) if COL_NAME_CUM_GM in str(x).replace(' ','') and "增" not in str(x)), -1)
        i_om = next((i for i, x in enumerate(h) if COL_NAME_CUM_OM in str(x).replace(' ','') and "增" not in str(x)), -1)
        
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

                    cells_to_update.append(gspread.Cell(row=r+1, col=i_e+1, value=round(single_q_eps, 2)))
                    
                    if i_ae != -1:
                        cells_to_update.append(gspread.Cell(row=r+1, col=i_ae+1, value=round(curr["eps_cumulative"], 2)))

                    if i_gm != -1 and curr["gm"] != 0:
                        cells_to_update.append(gspread.Cell(row=r+1, col=i_gm+1, value=curr["gm"]))
                    if i_om != -1 and curr["om"] != 0:
                        cells_to_update.append(gspread.Cell(row=r+1, col=i_om+1, value=curr["om"]))
            
            if cells_to_update:
                ws.update_cells(cells_to_update)
                update_count += len(cells_to_update)

    print(f"🎉 任務完成！共更新 {update_count} 個儲存格。")

if __name__ == "__main__":
    fetch_and_update()
