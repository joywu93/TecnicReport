import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def fetch_and_update():
    headers = {'User-Agent': 'Mozilla/5.0'}
    res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False).json()
    res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False).json()
    all_data = res_twse + res_tpex

    curr_dict = {}
    for item in all_data:
        code = str(item.get('公司代號', '')).strip()
        # 🌟 關鍵偵測：把 3023 的所有原始欄位印出來
        if code == '3023' and str(item.get('年度')) == "114":
            print(f"🕵️ 發現 3023 原始 JSON 結構：")
            print(json.dumps(item, indent=2, ensure_ascii=False))
            
            # 暫時只抓 EPS 確保能寫入
            eps = 0.0
            for k, v in item.items():
                if '基本每股盈餘' in k: 
                    try: eps = float(str(v).replace(',', ''))
                    except: pass
            curr_dict[code] = {"eps": eps}

    # 寫入 AO 欄位
    client = get_gspread_client()
    ws_list = client.open_by_url(MASTER_GSHEET_URL).worksheets()
    for ws in ws_list:
        if not any(n in ws.title for n in ["個股總表", "金融股"]): continue
        data = ws.get_all_values()
        i_c = next(i for i, x in enumerate(data[0]) if "代號" in x)
        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            c_code = row[i_c].split('.')[0].strip()
            if c_code in curr_dict:
                cells.append(gspread.Cell(row=r_idx, col=41, value=curr_dict[c_code]["eps"]))
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"✅ {ws.title} EPS 原始值填入 AO 成功")

if __name__ == "__main__":
    fetch_and_update()
