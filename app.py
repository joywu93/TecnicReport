# (前略：STOCK_NAMES 與 init_sheet 保持不變)

def analyze_strategy(df):
    try:
        if df.empty or len(df) < 240: return "資料不足", 0, 0, 0, False
        df.columns = df.columns.get_level_values(0)
        close, highs, lows, volume = df['Close'].astype(float), df['High'].astype(float), df['Low'].astype(float), df['Volume'].astype(float)
        
        curr_p, prev_p = float(close.iloc[-1]), float(close.iloc[-2])
        curr_v, prev_v = float(volume.iloc[-1]), float(volume.iloc[-2])
        
        ma60 = float(close.rolling(60).mean().iloc[-1])
        ma240 = float(close.rolling(240).mean().iloc[-1])
        
        msg, is_mail = [], False
        bias = ((curr_p - ma60) / ma60) * 100

        # A. 趨勢線偵測 [💡 補上 is_mail 開關]
        recent_l_60 = lows.tail(60)
        l1_val = float(recent_l_60.min())
        l1_idx = recent_l_60.idxmin()
        post_l1 = recent_l_60.loc[l1_idx:]
        if len(post_l1) > 5:
            l2_val = float(post_l1.iloc[1:].min())
            l2_idx = post_l1.iloc[1:].idxmin()
            dist = len(df) - 1 - df.index.get_loc(l1_idx)
            l2_dist = len(df) - 1 - df.index.get_loc(l2_idx)
            if dist != l2_dist:
                slope = (l2_val - l1_val) / (dist - l2_dist)
                support = l2_val + (slope * l2_dist)
                gap = ((curr_p - support) / support) * 100
                if abs(gap) <= 2.5: # 縮小範圍，精準支撐才通知
                    msg.append(f"🛡️ 趨勢線支撐: {support:.2f} (距 {gap:.1f}%)")
                    is_mail = True # ✅ 焊上開關

        # B. 形態偵測 (M頭/W底) [保持不變]
        # ... (此處代碼同昨日版本)
        
        # C. 爆量與反彈 [保持不變]
        # ... (此處代碼同昨日版本)

        if not msg: msg.append("🌊 多方行進" if curr_p > ma60 else "☁ 空方盤整")
        return " | ".join(msg), curr_p, ma60, bias, is_mail
    except Exception as e: return f"分析失敗: {str(e)}", 0, 0, 0, False

# (後略：UI 介面保持不變)
