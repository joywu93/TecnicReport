# 📂 檔案名稱： update_payout.py (專攻盈餘配息率突破版)
import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import urllib3
import json

# 關閉 SSL 憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 您的專屬 Google Sheet 網址
MASTER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1TI1RBZVFgqO8ir-PhMMakL7fBcuBP06fiklKPGENH5g/edit?usp=sharing"

def get_gspread_client():
    key_data = os.environ.get("GOOGLE_KEY_JSON")
    creds_dict = json.loads(key_data)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds)

def update_daily_payout():
    print("🚀 啟動【盈餘總分配率】突破更新引擎...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    magic_payout_dict = {}

    # ==========================
    # 1. 抓取上市資料 (TWSE)
    # ==========================
    try:
        print("📥 正在向證交所 API 獲取上市本益比與殖利率...")
        url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        res_twse = requests.get(url_twse, headers=headers, verify=False, timeout=15).json()
        for item in res_twse:
            code = str(item.get('Code', '')).strip()
            try:
                pe = float(str(item.get('PeRatio', '0')).replace(',', ''))
                dy = float(str(item.get('DividendYield', '0')).replace(',', ''))
                if pe > 0 and dy > 0:
                    magic_payout_dict[code] = round(pe * dy, 2)
            except: pass
    except Exception as e:
        print(f"❌ 上市資料獲取失敗: {e}")

    # ==========================
    # 2. 抓取上櫃資料 (TPEx)
    # ==========================
    try:
        print("📥 正在向櫃買中心 API 獲取上櫃本益比與殖利率...")
        url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_perwd_quotes"
        res_tpex = requests.get(url_tpex, headers=headers, verify=False, timeout=15).json()
        for item in res_tpex:
            code = str(item.get('SecuritiesCompanyCode', '')).strip()
            try:
                pe = float(str(item.get('PERatio', '0')).replace(',', ''))
                dy = float(str(item.get('Dividendyield', '0')).replace(',', ''))
                if pe > 0 and dy > 0:
                    magic_payout_dict[code] = round(pe * dy, 2)
            except: pass
    except Exception as e:
        print(f"❌ 上櫃資料獲取失敗: {e}")

    if not magic_payout_dict:
        print("⚠️ 無法取得官方資料，程式終止。")
        return

    print(f"✅ 成功反推計算出 {len(magic_payout_dict)} 檔股票的盈餘分配率！")
    print("==================================================")
    print("🔗 準備連線 Google Sheet 寫入資料...")

    client = get_gspread_client()
    worksheets = client.open_by_url(MASTER_GSHEET_URL).worksheets()
    
    # 只鎖定有需要更新的分頁
    target_sheets = [ws for ws in worksheets if "個股總表" in ws.title or "金融股" in ws.title]

    total_updated = 0
    for ws in target_sheets:
        data = ws.get_all_values()
        if not data or len(data) < 2: continue
        
        headers_row = data[0]
        c_idx = next((i for i, x in enumerate(headers_row) if "代號" in str(x)), -1)
        
        # 🛡️ 絕對防護：精準鎖定「盈餘總分配率」
        p_idx = next((i for i, x in enumerate(headers_row) if "盈餘總分配率" in str(x).strip()), -1)
        
        if c_idx != -1 and p_idx != -1:
            # 💡 檢查防呆：讓您確認是不是在第 28 欄 (也就是 AB 欄)
            print(f"🔍 分頁 [{ws.title}] 鎖定成功！「盈餘總分配率」位於第 {p_idx + 1} 欄 (AB欄為28)。")
            
            cells_to_update = []
            for r, row in enumerate(data):
                if r == 0: continue
                code = str(row[c_idx]).split('.')[0].strip()
                
                # 若魔法公式有算出這檔股票的配息率，打包準備寫入
                if code in magic_payout_dict:
                    val_str = str(magic_payout_dict[code])
                    # row=r+1 是因為 index 從 0 開始，col=p_idx+1 也是
                    cells_to_update.append(gspread.Cell(row=r+1, col=p_idx+1, value=val_str))
                    
            if cells_to_update:
                ws.update_cells(cells_to_update, value_input_option='USER_ENTERED')
                total_updated += len(cells_to_update)
                print(f"📝 分頁 [{ws.title}] 成功將 {len(cells_to_update)} 檔股票的分配率寫入完成！")
        else:
            print(f"⚠️ 分頁 [{ws.title}] 找不到「盈餘總分配率」欄位，已自動跳過。")

    print("==================================================")
    print(f"🎉 任務圓滿完成！總共更新了 {total_updated} 個儲存格！")

if __name__ == "__main__":
    update_daily_payout()
