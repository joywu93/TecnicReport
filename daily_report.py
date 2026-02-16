name: Daily Stock Report

on:
  schedule:
    # GitHub 使用 UTC 時間，台灣時間 = UTC + 8
    # ---------------------------------------
    # 台灣 10:00 (盤中) = UTC 02:00
    # 台灣 13:00 (盤中) = UTC 05:00
    # 台灣 15:30 (盤後) = UTC 07:30
    # ---------------------------------------
    
    # 設定盤中兩次掃描 (週一至週五)
    - cron: '0 2,5 * * 1-5'
    
    # 設定盤後一次掃描 (週一至週五)
    - cron: '30 7 * * 1-5'

  # 允許手動點擊按鈕執行 (方便測試用)
  workflow_dispatch:

jobs:
  run-script:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout code
      uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'

    - name: Install dependencies
      run: |
        pip install yfinance pandas

    - name: Run daily report
      env:
        # 這裡會自動去抓您在 Secrets 設定的帳密
        GMAIL_USER: ${{ secrets.GMAIL_USER }}
        GMAIL_PASSWORD: ${{ secrets.GMAIL_PASSWORD }}
      run: python daily_report.py
