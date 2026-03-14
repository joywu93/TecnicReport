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
    print("📡 正在全面掃描 API 欄位結構...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    res_twse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", headers=headers, verify=False).json()
    res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O", headers=headers, verify=False).json()
    all_data = res_twse + res_tpex

    curr_dict = {}
    for item in all_data:
        code = str(item.get('公司代號', '')).strip()
        
        # 🌟 核心突破：如果抓到 3023，把「所有」欄位名稱印出來看
        if code == '3023':
            print(f"👀 [3023 欄位大公開] 年度: {item.get('年度')}, 季別: {item.get('季別')}")
            # 這裡會印出這條資料所有的 Key，我們就能看到「營業利益」到底叫什麼名字
            print(f"原始欄位清單: {list(item.keys())}")
            
            # 嘗試抓取所有可能的數值
            eps = 0.0
            op_p = 0.0
            pre_t = 0.0
            for k, v in item.items():
                val = str(v).replace(',', '')
                try:
                    f_val = float(val)
                    if '基本每股盈餘' in k: eps = f_val
                    if '營業利益' in k and '每股' not in k: op_p = f_val
                    if '稅前' in k and '所得稅' not in k: pre_t = f_val
                except: continue
            
            curr_dict[code] = {"eps": eps, "op_p": op_p, "pre_t": pre_t, "q": item.get('季別')}
            print(f"🔍 抓取結果 -> EPS: {eps}, 營業利益: {op_p}, 稅前淨利: {pre_t}")

    # 更新到 AO 之後的欄位
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
                d = curr_dict[c_code]
                # 填入 AO-AR 欄位作為證據
                cells.append(gspread.Cell(row=r_idx, col=41, value=d["eps"]))
                cells.append(gspread.Cell(row=r_idx, col=42, value=d["op_p"]))
                cells.append(gspread.Cell(row=r_idx, col=43, value=d["pre_t"]))
                cells.append(gspread.Cell(row=r_idx, col=44, value=f"Q{d['q']}"))
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"✅ {ws.title} 證據欄位更新完成")

if __name__ == "__main__":
    fetch_and_update()
