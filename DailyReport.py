# (💡 此處請全選複製上方 app.py 裡的 STOCK_NAMES 與 analyze_strategy 函式)

def run_batch():
    try:
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
        client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
                 scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
        sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        
        for row in sheet.get_all_records():
            email = row.get('Email')
            tickers = re.findall(r'\d{4}', str(row.get('Stock_List', '')))
            if not email: continue
            
            # 💡 關鍵修正：notify_list 起始不為空，保證一定會發信
            notify_list = [f"✅ 戰略巡航連線成功：{datetime.now().strftime('%m/%d %H:%M:%S')}"]
            for t in tickers:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                if not df.empty:
                    sig, p, s60, b, im = analyze_strategy(df)
                    if im: # 符合戰略條件才加入
                        notify_list.append(f"【{STOCK_NAMES.get(t, t)}】${p:.2f} | {sig}")

            msg = MIMEText("\n\n".join(notify_list))
            msg['Subject'] = f"📈 戰略巡航回報 - {datetime.now().strftime('%m/%d')}"
            msg['From'], msg['To'] = sender, email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender, pwd); server.send_message(msg)
                print(f"Mail sent to {email}")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_batch()
