import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定區
MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"
TARGET_YEAR_ROC = "114"   # 114年
TARGET_Q = 4              # 第4季
Q_STRING = "25Q4"         # 對應表單 25Q4

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
    print(f"🚀 開始執行：填入 {TARGET_YEAR_ROC}Q{TARGET_Q} 盈餘資料...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 抓取 API 資料
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False, timeout=15).json()
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False, timeout=15).json()
    except Exception as e:
        print(f"❌ API 抓取失敗: {e}"); return

    # 建立數據字典
    curr_dict = {}
    for item in (res_twse + res_tpex):
        code = str(item.get('公司代號', '')).strip()
        if not code or str(item.get('年度', '')).strip() != TARGET_YEAR_ROC or str(item.get('季別', '')).strip() != str(TARGET_Q): 
            continue
        
        # 抓取累計 EPS
        eps = parse_val(item.get('基本每股盈餘(元)')) or parse_val(item.get('基本每股盈餘'))
        curr_dict[code] = eps

    # 更新 Google Sheets
    client = get_gspread_client()
    spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    
    for ws in spreadsheet.worksheets():
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        
        data = ws.get_all_values()
        if not data: continue
        h = data[0]
        
        try:
            # 欄位定位
            i_c = next(i for i, x in enumerate(h) if "代號" in x)
            i_e = next(i for i, x in enumerate(h) if f"{Q_STRING}單季每股盈餘" in x.replace(' ', ''))
            i_ae = next(i for i, x in enumerate(h) if "最新累季每股盈餘" in x.replace(' ', ''))
            
            # 抓取 Q1, Q2, Q3 欄位索引，用於計算 Q4 單季
            i_q1 = next((i for i, x in enumerate(h) if "25Q1單季每股盈餘" in x.replace(' ', '')), -1)
            i_q2 = next((i for i, x in enumerate(h) if "25Q2單季每股盈餘" in x.replace(' ', '')), -1)
            i_q3 = next((i for i, x in enumerate(h) if "25Q3單季每股盈餘" in x.replace(' ', '')), -1)
        except Exception as e:
            print(f"⚠️ 跳過 {ws.title}，原因：找不到關鍵欄位 ({e})"); continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            code = row[i_c].split('.')[0].strip()
            if code in curr_dict:
                cum_eps = curr_dict[code]
                
                # 計算單季： Q4單季 = 累計(Q4) - Q1單季 - Q2單季 - Q3單季
                def get_row_val(idx):
                    if idx == -1 or idx >= len(row): return 0.0
                    try: return float(row[idx].replace(',', '')) if row[idx] and row[idx] != '-' else 0.0
                    except: return 0.0
                
                single_eps = cum_eps - (get_row_val(i_q1) + get_row_val(i_q2) + get_row_val(i_q3))

                # 準備寫入 (Cells)
                cells.append(gspread.Cell(row=r_idx, col=i_e+1, value=round(single_eps, 2)))
                cells.append(gspread.Cell(row=r_idx, col=i_ae+1, value=round(cum_eps, 2)))
        
        if cells:
            ws.update_cells(cells)
            print(f"✅ {ws.title} 更新成功 (累計與單季 EPS)")

    print(f"🎉 任務結束。")

if __name__ == "__main__":
    fetch_and_update()
