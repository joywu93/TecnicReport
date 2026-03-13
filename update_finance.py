# ==========================================
# 📂 檔案名稱： update_finance.py (V182 業外佔比終極網羅版)
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
        
        # 🌟 終極網羅：把所有可能代表業外跟稅前的字眼都抓進來
        non_op = ext_val(item, ['營業外收入及支出', '營業外損益', '營業外收支', '業外', '其他利益', '其他損益', '其他收益'])
        pre_tax = ext_val(item, ['稅前淨利', '稅前息前', '稅前純益', '稅前損益', '繼續營業單位稅前'], ex=['所得稅', '稅後', '遞延', '停業', '每股'])
        
        non_op_ratio = 0.0
        if pre_tax != 0:
            non_op_ratio = round((non_op / pre_tax) * 100, 2)
            
        # 🌟 零值警告器：印出計算結果為 0 的股票，方便我們找原因
        if code in ['3023', '2330'] and non_op_ratio == 0:
            print(f"⚠️ 警告！{code} 的業外佔比算出來是 0！(業外抓到: {non_op}, 稅前抓到: {pre_tax})")
            
        curr_dict[code] = {
            "eps_cumulative": eps_raw,
            "non_op_ratio": non_op_ratio
        }

    print(f"✅ 解析完成 ({len(curr_dict)}檔股票)。準備寫入表單...")

    client = get_gspread_client()
    worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
    target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]
    
    def ultra_clean(text):
        if not text: return ""
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
        
        i_q1 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q1單季每股盈餘" in ultra_clean(x)), -1)
        i_q2 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q2單季每股盈餘" in ultra_clean(x)), -1)
        i_q3 = next((i for i, x in enumerate(h) if f"{Q_STRING[:2]}Q3單季每股盈餘" in ultra_clean(x)), -1)

        print(f"\n🔍 檢查分頁: {ws.title}")
        if i_e != -1: print(f"   ✅ 找到【單季EPS】")
        if i_ae != -1: print(f"   ✅ 找到【累季EPS】")
        if i_nop != -1: print(f"   ✅ 找到【業外佔比】")

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
                    if i_nop != -1:
                        cells_to_update.append(gspread.Cell(row=r+1, col=i_nop+1, value=curr["non_op_ratio"]))

            if cells_to_update:
                ws.update_cells(cells_to_update)
                update_count += len(cells_to_update)
                print(f"   🚀 成功寫入表單！")

    print(f"\n🎉 任務完成！共更新 {update_count} 個儲存格。")

if __name__ == "__main__":
    fetch_and_update()
