# ==========================================
# 📂 檔案名稱： update_finance.py (表單標題偵測版)
# 💡 目的：印出表單第一列的所有標題，找出找不到欄位的真正原因
# ==========================================

import os
import json
import gspread
from google.oauth2.service_account import Credentials

MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    if not key_data: raise ValueError("找不到 Google 金鑰")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def fetch_and_update():
    print("啟動偵測機器人：連線至 Google 表單...")
    client = get_gspread_client()
    worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
    
    for ws in worksheets:
        if "個股總表" in ws.title:
            data = ws.get_all_values()
            if not data: continue
            
            headers = data[0]
            print(f"\n🔍 成功讀取分頁：{ws.title}")
            print("-" * 50)
            print("📝 以下是您的表單第一列的所有標題 (請仔細比對)：")
            
            for i, h in enumerate(headers):
                # 為了凸顯隱形字元，我們把它包在括號裡印出來
                print(f"[{i+1}] >>>{h}<<<")
            print("-" * 50)
            break # 只要印出第一個找到的總表就好

if __name__ == "__main__":
    fetch_and_update()
