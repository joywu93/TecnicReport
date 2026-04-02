# ==========================================
# 📂 檔案名稱： update_finance.py (V194 不動比例純補Q4版)
# 💡 策略： 股價估值同步更新 + Q4四大絕對數值推算填入
# ⚠️ 修正： 徹底刪除「營益率」與「業外佔比」的更新邏輯，完美保留您表單上的原始比例！
# ==========================================

import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# V194 專屬的 Google Sheet 網址
MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit"

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_CREDENTIALS") or os.environ.get("GOOGLE_KEY_JSON")
    if not key_data: raise ValueError("找不到 Google 金鑰，請檢查 GitHub Secrets 設定！")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def force_float(v):
    if v is None or str(v).strip() in ["", "-", "--", "---", "N/A", "NaN"]: return 0.0
    s = str(v).strip().replace(',', '')
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    try: return float(s)
    except: return 0.0

def safe_parse_price(val):
    try:
        s = str(val).replace(',', '').strip()
        if not s or s == '-' or s == '--' or s == '---': return None
        return float(s)
    except: return None

def fetch_and_update():
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # ---------------------------------------------------------
    # 任務一：抓取 EPS 與 四大財報指標
    # ---------------------------------------------------------
    url_twse = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
    url_tpex = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"
    
    try:
        print("📡 任務一：下載最新【綜合損益表】...")
        res_twse = requests.get(url_twse, headers=headers, verify=False, timeout=30).json()
        res_tpex = requests.get(url_tpex, headers=headers, verify=False, timeout=30).json()
        all_detail = res_twse + res_tpex
    except Exception as e: 
        print(f"❌ API 抓取失敗: {e}")
        all_detail = []

    stats = {}
    for item in all_detail:
        code = str(item.get('公司代號', item.get('co_id', item.get('SecuritiesCompanyCode', '')))).strip()
        if not code: continue
        
        y = str(item.get('年度', item.get('Year', '')))
        q = str(item.get('季別', item.get('Quarter', '')))
        
        if y == "114" and q == "4":
            revenue, op_profit, non_op_income, annual_eps = 0.0, 0.0, 0.0, 0.0
            
            for k, v in item.items():
                if '營業收入' in k: revenue = force_float(v)
                elif '營業利益' in k: op_profit = force_float(v)
                elif '營業外收入' in k: non_op_income = force_float(v)
                elif '每股盈餘' in k: annual_eps = force_float(v)

            stats[code] = {
                "annual_eps": annual_eps, 
                "revenue": revenue,
                "op_profit": op_profit,
                "non_op_income": non_op_income
            }

    print(f"✅ 成功獲取 114年 Q4 資料，共 {len(stats)} 檔財報準備寫入！")

    # ---------------------------------------------------------
    # 任務二：抓取盤後股價與估值
    # ---------------------------------------------------------
    print("\n📡 任務二：下載最新【盤後收盤價與估值】...")
    price_dict = {}
    try:
        res_twse_price = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=headers, verify=False, timeout=30).json()
        if isinstance(res_twse_price, list):
            for i in res_twse_price:
                cp = safe_parse_price(i.get('ClosingPrice'))
                if cp is not None: price_dict[str(i.get('Code', '')).strip()] = {'price': cp}
    except: pass

    try:
        res_tpex_price = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=headers, verify=False, timeout=30).json()
        if isinstance(res_tpex_price, list):
            for i in res_tpex_price:
                cp = safe_parse_price(i.get('Close'))
                if cp is not None: price_dict.setdefault(str(i.get('SecuritiesCompanyCode', '')).strip(), {})['price'] = cp
    except: pass

    try:
        res_twse_val = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL", headers=headers, verify=False, timeout=30).json()
        if isinstance(res_twse_val, list):
            for i in res_twse_val:
                c = str(i.get('Code', '')).strip()
                if c:
                    price_dict.setdefault(c, {})['yield'] = force_float(i.get('Yield'))
                    price_dict.setdefault(c, {})['per'] = force_float(i.get('PEratio'))
                    price_dict.setdefault(c, {})['pbr'] = force_float(i.get('PBratio'))
    except: pass

    try:
        res_tpex_val = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_perpeild", headers=headers, verify=False, timeout=30).json()
        if isinstance(res_tpex_val, list):
            for i in res_tpex_val:
                c = str(i.get('SecuritiesCompanyCode', '')).strip()
                if c:
                    price_dict.setdefault(c, {})['yield'] = force_float(i.get('YieldRatio'))
                    price_dict.setdefault(c, {})['per'] = force_float(i.get('PERatio'))
                    price_dict.setdefault(c, {})['pbr'] = force_float(i.get('PBRatio'))
    except: pass

    print(f"✅ 成功抓取市場數據。")

    # ---------------------------------------------------------
    # 任務三：開始寫入 Google 表單 (避開比例欄位)
    # ---------------------------------------------------------
    print("\n📝 任務三：開始寫入 Google 表單...")
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_url(MASTER_GSHEET_URL)
    except Exception as e:
        print(f"❌ Google 表單連線失敗: {e}")
        return
    
    target_sheets = [ws for ws in spreadsheet.worksheets() if any(n in ws.title for n in ["當年度表", "個股總表", "總表", "金融股", "歷史表單"])]
    
    for ws in target_sheets:
        data = ws.get_all_values()
        if not data: continue
        
        h = data[0]
        i_c = next((i for i, x in enumerate(h) if str(x).strip() in ["代號", "股票代號", "證券代號"]), -1)
        i_price = next((i for i, x in enumerate(h) if str(x).strip() in ["成交", "股價", "最新股價", "收盤價"]), -1)
        i_pbr = next((i for i, x in enumerate(h) if "淨值比" in str(x) or "PBR" in str(x).upper()), -1)
        i_per = next((i for i, x in enumerate(h) if "本益比" in str(x) or "PER" in str(x).upper()), -1)
        i_yield = next((i for i, x in enumerate(h) if "殖利率" in str(x) and "年化" not in str(x)), -1)
        
        def get_idx(year_q, keyword):
            return next((i for i, x in enumerate(h) if year_q in str(x).upper() and keyword in str(x)), -1)

        i_q1_eps, i_q2_eps, i_q3_eps, i_q4_eps_target = get_idx("25Q1", "盈餘"), get_idx("25Q2", "盈餘"), get_idx("25Q3", "盈餘"), get_idx("25Q4", "盈餘")
        i_q1_rev, i_q2_rev, i_q3_rev, i_q4_rev_target = get_idx("25Q1", "營收"), get_idx("25Q2", "營收"), get_idx("25Q3", "營收"), get_idx("25Q4", "營收")
        i_q1_op, i_q2_op, i_q3_op, i_q4_op_target = get_idx("25Q1", "營益"), get_idx("25Q2", "營益"), get_idx("25Q3", "營益"), get_idx("25Q4", "營益")
        i_q1_nop, i_q2_nop, i_q3_nop, i_q4_nop_target = get_idx("25Q1", "業外"), get_idx("25Q2", "業外"), get_idx("25Q3", "業外"), get_idx("25Q4", "業外")
        
        i_accum_eps_target = next((i for i, x in enumerate(h) if "最新累季每股盈餘" in str(x)), -1)
        
        # ⚠️ 移除了搜尋 i_op_m_target 與 i_nop_target 的程式碼！

        if i_c == -1: continue

        cells = []
        for r_idx, row in enumerate(data[1:], start=2):
            if i_c >= len(row): continue
            code = str(row[i_c]).split('.')[0].strip()
            
            # 【寫入 市場資料】
            if code in price_dict:
                m = price_dict[code]
                if i_price != -1 and m.get('price', 0) > 0:
                    cells.append(gspread.Cell(row=r_idx, col=i_price+1, value=m['price']))
                if i_pbr != -1 and m.get('pbr', 0) > 0:
                    cells.append(gspread.Cell(row=r_idx, col=i_pbr+1, value=m['pbr']))
                if i_per != -1 and m.get('per', 0) > 0:
                    cells.append(gspread.Cell(row=r_idx, col=i_per+1, value=m['per']))
                if i_yield != -1 and m.get('yield', 0) > 0:
                    cells.append(gspread.Cell(row=r_idx, col=i_yield+1, value=m['yield']))
            
            # 【寫入 Q4 四大絕對數值與累計EPS】
            if code in stats:
                d = stats[code]
                
                if i_accum_eps_target != -1:
                    cells.append(gspread.Cell(row=r_idx, col=i_accum_eps_target+1, value=d["annual_eps"]))

                if i_q4_eps_target != -1:
                    q1 = force_float(row[i_q1_eps]) if i_q1_eps != -1 and i_q1_eps < len(row) else 0.0
                    q2 = force_float(row[i_q2_eps]) if i_q2_eps != -1 and i_q2_eps < len(row) else 0.0
                    q3 = force_float(row[i_q3_eps]) if i_q3_eps != -1 and i_q3_eps < len(row) else 0.0
                    q4_eps_calculated = round(d["annual_eps"] - q1 - q2 - q3, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_eps_target+1, value=q4_eps_calculated))
                
                if i_q4_rev_target != -1:
                    q1 = force_float(row[i_q1_rev]) if i_q1_rev != -1 and i_q1_rev < len(row) else 0.0
                    q2 = force_float(row[i_q2_rev]) if i_q2_rev != -1 and i_q2_rev < len(row) else 0.0
                    q3 = force_float(row[i_q3_rev]) if i_q3_rev != -1 and i_q3_rev < len(row) else 0.0
                    q4_rev = round((d["revenue"] / 100000) - q1 - q2 - q3, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_rev_target+1, value=q4_rev))

                if i_q4_op_target != -1:
                    q1 = force_float(row[i_q1_op]) if i_q1_op != -1 and i_q1_op < len(row) else 0.0
                    q2 = force_float(row[i_q2_op]) if i_q2_op != -1 and i_q2_op < len(row) else 0.0
                    q3 = force_float(row[i_q3_op]) if i_q3_op != -1 and i_q3_op < len(row) else 0.0
                    q4_op = round((d["op_profit"] / 100000) - q1 - q2 - q3, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_op_target+1, value=q4_op))

                if i_q4_nop_target != -1:
                    q1 = force_float(row[i_q1_nop]) if i_q1_nop != -1 and i_q1_nop < len(row) else 0.0
                    q2 = force_float(row[i_q2_nop]) if i_q2_nop != -1 and i_q2_nop < len(row) else 0.0
                    q3 = force_float(row[i_q3_nop]) if i_q3_nop != -1 and i_q3_nop < len(row) else 0.0
                    q4_nop = round((d["non_op_income"] / 100000) - q1 - q2 - q3, 2)
                    cells.append(gspread.Cell(row=r_idx, col=i_q4_nop_target+1, value=q4_nop))
                
                # ⚠️ 移除了計算與寫入單季營益率 & 業外損益佔稅前淨利的邏輯！
        
        if cells:
            ws.update_cells(cells, value_input_option='USER_ENTERED')
            print(f"📊 {ws.title} 更新完成。共寫入了 {len(cells)} 個儲存格。")

if __name__ == "__main__":
    fetch_and_update()
