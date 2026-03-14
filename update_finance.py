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
    if v is None: return 0.0
    s = str(v).strip().replace(',', '').replace('%', '')
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    try: return float(s)
    except: return 0.0

def fetch_and_update():
    headers = {'User-Agent': 'Mozilla/5.0'}
    res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False).json()
    res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False).json()

    curr_dict = {}
    for item in (res_twse + res_tpex):
        code = item.get('公司代號', '').strip()
        # 這裡放寬條件，看看是不是季別抓錯
        if code in ['3023', '3030']:
            print(f"🔍 偵測到目標股 {code}: 年度={item.get('年度')}, 季別={item.get('季別')}")
        
        if str(item.get('年度')) == TARGET_YEAR_ROC and str(item.get('季別')) == str(TARGET_Q):
            eps = force_float(item.get('基本每股盈餘(元)')) or force_float(item.get('基本每股盈餘'))
            
            # 遍歷所有 Key 找數字，不猜名字了
            op_p = 0.0
            pre_t = 0.0
            for k, v in item.items():
                if '營業利益' in k and '每股' not in k: op_p = force_float(v)
                if '稅前' in k and '淨利' in k and '所得稅' not in k: pre_t = force_float(v)
            
            non_op = 0.0
            if pre_t != 0:
                non_op = round(((pre_t - op_p) / pre_t) * 100, 2)
            
            if code in ['3023', '3030']:
                print(f"✅ {code} 計算成功: 稅前={pre_t}, 營業利益={op_p}, 業外%={non_op}")
            
            curr_dict[code] = {"eps": eps, "non_op": non_op}

    # 寫入 Sheet 邏輯 (保持 USER_ENTERED 強制寫入數字)
    client = get_gspread_client()
    ws_list = client.open_by_url(MASTER_GSHEET_URL).worksheets()
    for ws in ws_list:
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        h = data[0]
        try:
            i_c = next(i for i, x in enumerate(h) if "代號" in x)
            i_e = next(i for i, x in enumerate(h) if f"{Q_STRING}單季每股盈餘" in x.replace(' ', ''))
            i_nop = next(i for i, x in enumerate(h) if "業外" in x and "%" in x)
            
            cells = []
            for r_idx, row in enumerate(data[1:], start=2):
                c_code = row[i_c].split('.')[0].strip()
                if c_code in curr_dict:
                    info = curr_dict[c_code]
                    cells.append(gspread.Cell(row=r_idx, col=i_e+1, value=info["eps"])) # 先填累計 EPS 測試
                    cells.append(gspread.Cell(row=r_idx, col=i_nop+1, value=info["non_op"]))
            
            if cells:
                ws.update_cells(cells, value_input_option='USER_ENTERED')
                print(f"📊 {ws.title} 寫入完成")
        except Exception as e:
            print(f"❌ {ws.title} 錯誤: {e}")

if __name__ == "__main__":
    fetch_and_update()
