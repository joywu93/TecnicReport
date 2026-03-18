# ==========================================
# 📊 核心大腦一：一般/成長股預估引擎
# ==========================================
def auto_strategic_model(name, current_month, rev_last_11, rev_last_12, rev_this_1, rev_this_2, rev_this_3, base_q_eps, non_op_ratio, base_q_avg_rev, ly_q1_rev, ly_q2_rev, ly_q3_rev, ly_q4_rev, y1_q1_rev, y1_q2_rev, y1_q3_rev, y1_q4_rev, recent_payout_ratio, current_price, contract_liab, contract_liab_qoq, acc_eps, declared_div):
    try:
        current_price = float(current_price)
        if math.isnan(current_price) or math.isinf(current_price): current_price = 0.0
    except: current_price = 0.0

    if current_month <= 1: sim_rev_1, sim_rev_2, sim_rev_3 = 0, 0, 0
    elif current_month == 2: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, 0, 0
    elif current_month == 3: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, 0
    else: sim_rev_1, sim_rev_2, sim_rev_3 = rev_this_1, rev_this_2, rev_this_3

    actual_known_q1 = sum([v for v in [sim_rev_1, sim_rev_2, sim_rev_3] if v > 0])
    
    ratio_q1 = ly_q1_rev / y1_q4_rev if y1_q4_rev > 0 else 1.0
    
    sum_q2_history = y1_q2_rev + ly_q2_rev
    sum_q3_history = y1_q3_rev + ly_q3_rev
    sum_q4_history = y1_q4_rev + ly_q4_rev
    
    ratio_q3 = sum_q3_history / sum_q2_history if sum_q2_history > 0 else 1.0
    ratio_q4 = sum_q4_history / sum_q3_history if sum_q3_history > 0 else 1.0

    base_11_12_avg = (rev_last_11 + rev_last_12) / 2
    
    # 🌟 【重大修正區塊】：強制 est_q1_rev 必須使用最新的動態真實營收！
    if current_month <= 1: 
        dynamic_base_avg, formula_note = base_11_12_avg, "推演1月(全未知)"
        est_q1_rev = (base_11_12_avg * 3) * ratio_q1 # 只有在全未知時，才依賴去年Q4與歷史轉換率
    elif current_month == 2: 
        dynamic_base_avg, formula_note = sim_rev_1 * 0.9 if sim_rev_1 > 0 else base_11_12_avg, "推演2月(知1月)"
        est_q1_rev = dynamic_base_avg * 3  # ✅ 乘上最新動態均值
    elif current_month == 3: 
        dynamic_base_avg, formula_note = (sim_rev_1 * 2 + sim_rev_2) / 3 if sim_rev_2 > 0 else sim_rev_1, "推演3月(知1,2月)"
        est_q1_rev = dynamic_base_avg * 3  # ✅ 完美對應您手算的 20.77 億
    else: 
        dynamic_base_avg, formula_note = (sim_rev_1 + sim_rev_2 + sim_rev_3) / 3, "推演4月+"
        est_q1_rev = dynamic_base_avg * 3  # ✅ 乘上最新動態均值

    # 由於 est_q1_rev 變準了，後面的 Q2~Q4 以及年成長率都會跟著精準校正！
    est_q2_rev = est_q1_rev
    est_q3_rev = est_q2_rev * ratio_q3
    est_q4_rev = est_q3_rev * ratio_q4

    est_total_rev = est_q1_rev + est_q2_rev + est_q3_rev + est_q4_rev
    ly_total_rev = (ly_q1_rev + ly_q2_rev + ly_q3_rev + ly_q4_rev)
    est_annual_yoy = ((est_total_rev - ly_total_rev) / ly_total_rev) * 100 if ly_total_rev > 0 else 0
    q1_yoy = ((est_q1_rev - ly_q1_rev) / ly_q1_rev) * 100 if ly_q1_rev > 0 else 0

    base_q_total_rev = base_q_avg_rev * 3 if base_q_avg_rev > 0 else 1.0
    profit_margin_factor = base_q_eps * (1 - (non_op_ratio / 100)) / base_q_total_rev 

    est_q1_eps_display = est_q1_rev * profit_margin_factor
    est_full_year_eps = est_total_rev * profit_margin_factor
    est_per = current_price / est_full_year_eps if est_full_year_eps > 0 else 0
    
    # 🌟 新版配息率強效防守邏輯 + 備註機制
    payout_note = ""
    if acc_eps > 0 and declared_div > 0:
        raw_payout = (declared_div / acc_eps) * 100
        if raw_payout >= 100:
            calc_payout_ratio = 90.0
            payout_note = "⚠️ 最新公告(壓回90%)"
        elif raw_payout <= 0:
            calc_payout_ratio = 50.0
            payout_note = "🛡️ 最新公告(異常補50%)"
        else:
            calc_payout_ratio = raw_payout
            payout_note = "✅ 最新公告股利推算"
    else:
        raw_payout = recent_payout_ratio
        if raw_payout >= 100:
            calc_payout_ratio = 90.0
            payout_note = "⚠️ 歷史配息(壓回90%)"
        elif raw_payout <= 0:
            calc_payout_ratio = 50.0
            payout_note = "🛡️ 無資料(防守填50%)"
        else:
            calc_payout_ratio = raw_payout
            payout_note = "🕒 歷史配息率"
            
    est_annual_dividend = est_full_year_eps * (calc_payout_ratio / 100)
    forward_yield = (max(declared_div, est_annual_dividend) / current_price) * 100 if current_price > 0 else 0

    return {
        "股票名稱": name, "最新股價": round(current_price, 2), 
        "_logic_note": formula_note, "_payout_note": "", 
        "當季預估均營收": round(dynamic_base_avg, 2), "季成長率(YoY)%": round(q1_yoy, 2),
        "前瞻殖利率(%)": round(forward_yield, 2), "預估今年Q1_EPS": round(est_q1_eps_display, 2), 
        "預估今年度_EPS": round(est_full_year_eps, 2), "最新累季EPS": acc_eps, "本益比(PER)": round(est_per, 2),         
        "預估年成長率(%)": round(est_annual_yoy, 2), "運算配息率(%)": calc_payout_ratio, "配息基準": payout_note,
        "最新季度流動合約負債(億)": contract_liab, "最新季度流動合約負債季增(%)": contract_liab_qoq,
        "_ly_qs": [round(ly_q1_rev, 2), round(ly_q2_rev, 2), round(ly_q3_rev, 2), round(ly_q4_rev, 2)], 
        "_known_qs": [round(actual_known_q1, 2), 0, 0, 0],
        "_known_q1_months": [round(max(0, sim_rev_1), 2), round(max(0, sim_rev_2), 2), round(max(0, sim_rev_3), 2)],
        "_total_est_qs": [round(est_q1_rev, 2), round(est_q2_rev, 2), round(est_q3_rev, 2), round(est_q4_rev, 2)]
    }
