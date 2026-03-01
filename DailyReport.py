# (前略：analyze_strategy 保持不變)

def run_batch():
    try:
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sender, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_PASSWORD")
        if not creds_json or not sender: return
        
        client = gspread.authorize(Credentials.from_service_account_info(json.loads(creds_json), 
                 scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))
        sheet = client.open_by_key("1EBW0MMPovmYJ8gi6KZJRchnZb9sPNwr-_jVG_qoXncU").sheet1
        
        for row in sheet.get_all_records():
            email = row.get('Email')
            tickers = re.findall(r'\d{4}', str(row.get('Stock_List', '')))
            if not email: continue
            
            # 💡 強制測試模式：這行訊息保證信件內容不為空
            notify_list = [f"📢 自動化連線測試成功！執行時間：{datetime.now().strftime('%H:%M:%S')}"]
            
            for t in tickers:
                df = yf.download(f"{t}.TW", period="2y", progress=False)
                if df.empty: df = yf.download(f"{t}.TWO", period="2y", progress=False)
                if not df.empty:
                    sig, p, v60, b, is_mail = analyze_strategy(df)
                    if is_mail: # 只有符合戰略條件才加入
                        notify_list.append(f"【{t}】${p:.2f} | {sig}")
            
            # 💡 只要 notify_list 有內容 (含測試文字) 就發信
            if notify_list:
                msg = MIMEText("\n\n".join(notify_list))
                msg['Subject'] = f"📈 戰略巡航回報 - {datetime.now().strftime('%m/%d')}"
                msg['From'], msg['To'] = sender, email
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(sender, pwd); server.send_message(msg)
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    run_batch()
