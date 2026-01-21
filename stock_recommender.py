import akshare as ak
import pandas as pd
import datetime
 
# 新函数：动态获取热门板块（概念或行业）
def get_hot_sectors(date, top_n=10, sector_type="概念"):  # sector_type: "概念" or "行业"
    indicator = "今日"  # 可换 "5日"等
    sector_param = f"{sector_type}资金流"
    try:
        df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type=sector_param)
        # 按主力净流入降序，取top_n名称
        hot_sectors = df.sort_values(by='主力净流入', ascending=False).head(top_n)['板块名称'].tolist()
        print(f"动态热门{sector_type} ({date}): {hot_sectors}")
        return hot_sectors
    except Exception as e:
        print(f"获取热门{sector_type}失败: {e}，使用默认。")
        return ['半导体', '海南', '机器人']  # fallback

# 新函数：根据策略名称获取布尔Mask
def get_strategy_mask(df, strategy_name):
    # 基础指标预计算 (如果df中没有这些列，可能需要先计算)
    # 确保df中有 'early_seal' 和 'circ_mv' (这两个在主流程里是临时加的，需要注意)
    
    # 策略定义
    if strategy_name == 'combo1':
        # 高换手+小市值+早封
        return (df['换手率'] > 20) & (df['circ_mv'] < 50) & df['early_seal']
    
    elif strategy_name == 'combo2':
        # 换手+热点（历史固定，这里只做演示，实际analyze_historical_prob里用的静态热点）
        # 注意：recommend_stocks里会有动态热点逻辑，这里仅保留历史测试时的定义
        return (df['换手率'] > 15) & df['所属行业'].str.contains('半导体|海南|机器人')
        
    return None
 
def analyze_historical_prob(date_start='20240101', date_end=None):
    if date_end is None:
        date_end = datetime.datetime.now().strftime('%Y%m%d')
     
    # 获取历史所有涨停池
    dates = pd.date_range(start=date_start, end=date_end).strftime('%Y%m%d')
    zt_df_list = []
    for d in dates:
        try:
            df = ak.stock_zt_pool_em(date=d)
            if not df.empty:
                df['date'] = pd.to_datetime(d)
                zt_df_list.append(df)
        except:
            pass
    if not zt_df_list:
        return {'strategy_name': None, 'win_rate': 0.0, 'sample_count': 0}
     
    historical_zt = pd.concat(zt_df_list, ignore_index=True)
     
    # 添加circ_mv (流通市值，单位亿)
    historical_zt['circ_mv'] = historical_zt['流通市值'] / 100000000
     
    # 排序并识别首板和次日zt
    historical_zt = historical_zt.sort_values(['代码', 'date'])
    historical_zt['prev_date'] = historical_zt.groupby('代码')['date'].shift(1)
    historical_zt['is_first_board'] = historical_zt['prev_date'].isna() | (historical_zt['date'] - historical_zt['prev_date'] > pd.Timedelta(days=1))
     
    historical_zt['next_date'] = historical_zt.groupby('代码')['date'].shift(-1)
    historical_zt['next_day_zt'] = (historical_zt['next_date'] - historical_zt['date']) == pd.Timedelta(days=1)
     
    # 定义指标组合，计算概率
    # 早封板: 首次封板时间 < '1030' (格式'HHMMSS'，取前4位)
    historical_zt['early_seal'] = historical_zt['首次封板时间'].astype(str).str[:4] < '1030'
    
    strategy_names = ['combo1', 'combo2']
    max_prob = 0
    best_combo_name = None
    best_sample_count = 0
    
    for name in strategy_names:
        cond = get_strategy_mask(historical_zt, name)
        if cond is None: continue
        
        subset = historical_zt[historical_zt['is_first_board'] & cond]
        if len(subset) > 0:
            prob = subset['next_day_zt'].mean()
            if prob > max_prob:
                max_prob = prob
                best_combo_name = name
                best_sample_count = len(subset)
    return {
        'strategy_name': best_combo_name,
        'win_rate': max_prob,
        'sample_count': best_sample_count
    }

# 风险控制：计算个股风险等级
def calculate_stock_risk(stock_row, hot_sectors):
    """
    计算个股风险等级
    返回: {'level': 'High'/'Medium'/'Low', 'reasons': [原因列表], 'emoji': '🔴'/'🟡'/'🟢'}
    """
    risk_score = 0
    reasons = []
    
    # 1. 流通市值风险
    circ_mv = stock_row['circ_mv']
    if circ_mv < 30:
        risk_score += 2
        reasons.append(f"小市值({circ_mv:.1f}亿)")
    elif circ_mv < 100:
        risk_score += 1
    
    # 2. 换手率风险
    turnover = stock_row['换手率']
    if turnover > 30:
        risk_score += 2
        reasons.append(f"超高换手({turnover:.1f}%)")
    elif turnover > 20:
        risk_score += 1
    
    # 3. 封板时间风险
    seal_time = str(stock_row['首次封板时间'])[:4]
    if seal_time > '1400':
        risk_score += 2
        reasons.append("尾盘封板")
    elif seal_time > '1100':
        risk_score += 1
    
    # 4. 是否热门板块 (降低风险)
    sector = stock_row['所属行业']
    if any(hot in sector for hot in hot_sectors):
        risk_score -= 1
        reasons.append(f"热门板块({sector})")
    
    # 综合评级
    if risk_score >= 3:
        return {'level': 'High', 'reasons': reasons, 'emoji': '🔴'}
    elif risk_score >= 1:
        return {'level': 'Medium', 'reasons': reasons, 'emoji': '🟡'}
    else:
        return {'level': 'Low', 'reasons': reasons, 'emoji': '🟢'}

# 风险控制:根据胜率推荐仓位
def get_position_recommendation(win_rate):
    """
    根据胜率推荐单只股票仓位
    返回: {'range': '仓位范围', 'warning': '警告信息或None'}
    """
    if win_rate >= 0.08:
        return {'range': '20-30%', 'warning': None}
    elif win_rate >= 0.05:
        return {'range': '10-20%', 'warning': None}
    elif win_rate >= 0.03:
        return {'range': '5-10%', 'warning': '⚠️ 胜率偏低，建议谨慎'}
    else:
        return {'range': '不建议', 'warning': '⚠️ 胜率过低，风险极大'}

 
# 辅助函数：回溯找到非空涨停数据日期（max_back_days=7）
def get_valid_zt_date(target_date, max_back_days=7):
    date_obj = datetime.datetime.strptime(target_date, '%Y%m%d')
    for i in range(max_back_days + 1):
        check_date = (date_obj - datetime.timedelta(days=i)).strftime('%Y%m%d')
        try:
            df = ak.stock_zt_pool_em(date=check_date)
            if not df.empty:
                print(f"使用回溯日期: {check_date} (原: {target_date})")
                return check_date, df
        except:
            pass
    print("无可用涨停数据。")
    return None, pd.DataFrame()
 
# 主函数（推荐时使用动态热点 + 风险控制）
def recommend_stocks():
    now = datetime.datetime.now()
    today = now.strftime('%Y%m%d')
    if now.hour >= 15:
        # 分析今日首板，推荐明天买
        analysis_date = today
        buy_day = '明天'
    else:
        # 分析昨天首板，推荐今天买
        yesterday = (now - datetime.timedelta(days=1)).strftime('%Y%m%d')
        analysis_date = yesterday
        buy_day = '今天'
     
    # 获取分析日涨停池（回溯如果空）
    analysis_date, zt_df = get_valid_zt_date(analysis_date)
    if zt_df.empty:
        print("无涨停数据，无法推荐。")
        return
     
    # 获取前日涨停池（回溯如果空）
    prev_date = (datetime.datetime.strptime(analysis_date, '%Y%m%d') - datetime.timedelta(days=1)).strftime('%Y%m%d')
    prev_date, prev_zt = get_valid_zt_date(prev_date)
    # 处理空prev_zt
    try:
        prev_codes = prev_zt['代码']
    except KeyError:
        prev_codes = pd.Series()
     
    # 过滤首板
    first_board = zt_df[~zt_df['代码'].isin(prev_codes)].copy()
     
    if first_board.empty:
        print("无首板股票，无法推荐。")
        return
     
    # 添加circ_mv
    first_board['circ_mv'] = first_board['流通市值'] / 100000000
     
    # 添加early_seal
    first_board['early_seal'] = first_board['首次封板时间'].astype(str).str[:4] < '1030'
     
    # ===== 多时间段策略分析 =====
    print("\n" + "="*60)
    print("策略有效性分析 (多时间段回测)")
    print("="*60)
    
    # 全历史
    all_time_result = analyze_historical_prob(date_start='20240101')
    # 近3个月
    three_months_ago = (now - datetime.timedelta(days=90)).strftime('%Y%m%d')
    three_month_result = analyze_historical_prob(date_start=three_months_ago)
    # 近1个月
    one_month_ago = (now - datetime.timedelta(days=30)).strftime('%Y%m%d')
    one_month_result = analyze_historical_prob(date_start=one_month_ago)
    
    best_strategy = all_time_result['strategy_name']
    all_time_rate = all_time_result['win_rate']
    three_month_rate = three_month_result['win_rate']
    one_month_rate = one_month_result['win_rate']
    
    strategy_names_cn = {
        'combo1': '高换手+小市值+早封',
        'combo2': '换手+热门行业'
    }
    
    print(f"最优策略: {strategy_names_cn.get(best_strategy, best_strategy)}")
    print(f"全历史胜率: {all_time_rate*100:.2f}% (样本数: {all_time_result['sample_count']})")
    print(f"近3月胜率: {three_month_rate*100:.2f}% (样本数: {three_month_result['sample_count']})", end="")
    
    # 策略衰减检测
    if all_time_rate > 0:
        decay_3m = (all_time_rate - three_month_rate) / all_time_rate
        if decay_3m > 0.3:
            print(" ⚠️ 策略衰减明显")
        elif decay_3m > 0.1:
            print(" ⚠️ 略有下降")
        else:
            print()
    else:
        print()
    
    print(f"近1月胜率: {one_month_rate*100:.2f}% (样本数: {one_month_result['sample_count']})", end="")
    
    if all_time_rate > 0:
        decay_1m = (all_time_rate - one_month_rate) / all_time_rate
        if decay_1m > 0.5:
            print(" 🔴 策略严重失效")
        elif decay_1m > 0.3:
            print(" ⚠️ 策略衰减明显")
        elif decay_1m > 0.1:
            print(" ⚠️ 略有下降")
        else:
            print()
    else:
        print()
    
    # 综合风险提示
    print()
    recent_rate = one_month_rate if one_month_result['sample_count'] >= 10 else three_month_rate
    position_rec = get_position_recommendation(recent_rate)
    
    if position_rec['warning']:
        print(f"⚠️ 风险提示: {position_rec['warning']}")
    
    if recent_rate < all_time_rate * 0.5 and all_time_rate > 0:
        print("⚠️ 近期胜率显著低于历史平均，建议降低仓位或观望")
     
    # 为推荐动态更新热点
    hot_sectors = get_hot_sectors(analysis_date, top_n=10, sector_type="概念")
    dynamic_contains = '|'.join(hot_sectors)
    dynamic_combo_mask = (first_board['换手率'] > 15) & first_board['所属行业'].str.contains(dynamic_contains)
     
    # 获取历史最佳策略在当前数据的表现
    if best_strategy:
        history_mask = get_strategy_mask(first_board, best_strategy)
    else:
        # fallback if None returned
        history_mask = get_strategy_mask(first_board, 'combo1')

    # 合并策略：可以是 OR 关系，或者优先选 historical + dynamic
    # 这里保持原逻辑意图：最终mask是 动态热点 OR 历史最佳
    final_combine_mask = dynamic_combo_mask | history_mask
     
    # 应用最佳组合，推荐5只（按换手率降序）
    recommended = first_board[final_combine_mask].sort_values(by='换手率', ascending=False).head(5).copy()
     
    # 如果少于5，补充top换手率首板股
    if len(recommended) < 5:
        additional = first_board[~first_board['代码'].isin(recommended['代码'])].sort_values(by='换手率', ascending=False).head(5 - len(recommended)).copy()
        recommended = pd.concat([recommended, additional])
     
    # ===== 推荐股票展示（含风险评级）=====
    print("\n" + "="*60)
    print(f"推荐股票 - 基于{analysis_date}首板，建议{buy_day}买入")
    print(f"建议单只仓位: {position_rec['range']}")
    print("="*60)
    
    for idx, (_, stock) in enumerate(recommended.iterrows(), 1):
        risk_info = calculate_stock_risk(stock, hot_sectors)
        
        print(f"\n{idx}. {stock['代码']} - {stock['名称']}")
        print(f"   风险等级: {risk_info['emoji']} {risk_info['level']}")
        print(f"   流通市值: {stock['circ_mv']:.1f}亿 | 换手率: {stock['换手率']:.1f}% | 封板: {str(stock['首次封板时间'])[:2]}:{str(stock['首次封板时间'])[2:4]}")
        print(f"   所属行业: {stock['所属行业']}")
        
        if risk_info['reasons']:
            print(f"   风险因素: {', '.join(risk_info['reasons'])}")
    
    
    print("\n" + "="*60)
    print("⚠️ 免责声明: 本推荐仅供参考,股市有风险，投资需谨慎！")
    print("="*60)
    
    # ===== 生成TXT报告 =====
    report_filename = f"stock_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_filename, 'w', encoding='utf-8') as f:
        f.write("="*60 + "\n")
        f.write(f"股票推荐报告 - {datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
        f.write("="*60 + "\n\n")
        
        # 策略分析部分
        f.write("【策略有效性分析】\n")
        f.write("-"*60 + "\n")
        f.write(f"最优策略: {strategy_names_cn.get(best_strategy, best_strategy)}\n")
        f.write(f"全历史胜率: {all_time_rate*100:.2f}% (样本数: {all_time_result['sample_count']})\n")
        f.write(f"近3月胜率: {three_month_rate*100:.2f}% (样本数: {three_month_result['sample_count']})\n")
        f.write(f"近1月胜率: {one_month_rate*100:.2f}% (样本数: {one_month_result['sample_count']})\n\n")
        
        # 策略衰减分析
        f.write("【策略时效性评估】\n")
        f.write("-"*60 + "\n")
        if all_time_rate > 0:
            decay_1m = (all_time_rate - one_month_rate) / all_time_rate
            if decay_1m > 0.5:
                f.write("⚠️ 警告: 策略严重失效，近1月胜率大幅下降\n")
                f.write("   建议: 暂停使用该策略，等待市场环境改善\n")
            elif decay_1m > 0.3:
                f.write("⚠️ 注意: 策略出现明显衰减\n")
                f.write("   建议: 降低仓位至5-10%，谨慎操作\n")
            elif decay_1m > 0.1:
                f.write("✓ 策略略有下降，属于正常波动范围\n")
                f.write("   建议: 保持正常仓位，密切关注\n")
            else:
                f.write("✓ 策略表现稳定，近期胜率与历史一致\n")
                f.write("   建议: 可按推荐仓位操作\n")
        f.write("\n")
        
        # 仓位建议
        f.write("【仓位管理建议】\n")
        f.write("-"*60 + "\n")
        f.write(f"建议单只股票仓位: {position_rec['range']}\n")
        if position_rec['warning']:
            f.write(f"风险提示: {position_rec['warning']}\n")
        f.write(f"\n说明: 基于近期胜率 {recent_rate*100:.2f}% 计算\n")
        f.write("      总仓位建议不超过5只股票，分散风险\n\n")
        
        # 推荐股票详情
        f.write("【推荐股票明细】\n")
        f.write("-"*60 + "\n")
        f.write(f"分析日期: {analysis_date}\n")
        f.write(f"建议操作: {buy_day}买入\n")
        f.write(f"数据来源: 东方财富网涨停池 (实时数据)\n\n")
        
        for idx, (_, stock) in enumerate(recommended.iterrows(), 1):
            risk_info = calculate_stock_risk(stock, hot_sectors)
            
            f.write(f"{idx}. {stock['代码']} - {stock['名称']}\n")
            f.write(f"   风险等级: {risk_info['emoji']} {risk_info['level']}\n")
            f.write(f"   流通市值: {stock['circ_mv']:.1f}亿元\n")
            f.write(f"   换手率: {stock['换手率']:.1f}%\n")
            f.write(f"   首次封板时间: {str(stock['首次封板时间'])[:2]}:{str(stock['首次封板时间'])[2:4]}\n")
            f.write(f"   所属行业: {stock['所属行业']}\n")
            
            # 推荐理由
            f.write(f"   \n   【推荐理由】\n")
            if stock['early_seal']:
                f.write(f"   ✓ 早盘封板 (10:30前)，资金认可度高\n")
            if stock['换手率'] > 20:
                f.write(f"   ✓ 高换手率 ({stock['换手率']:.1f}%)，市场活跃度高\n")
            if stock['circ_mv'] < 50:
                f.write(f"   ✓ 小市值 ({stock['circ_mv']:.1f}亿)，易于拉升\n")
            if any(hot in stock['所属行业'] for hot in hot_sectors):
                f.write(f"   ✓ 属于当前热门板块，资金关注度高\n")
            
            # 风险提示
            if risk_info['reasons']:
                f.write(f"   \n   【风险提示】\n")
                for reason in risk_info['reasons']:
                    f.write(f"   ⚠️ {reason}\n")
            
            f.write("\n")
        
        # 操作建议
        f.write("【操作建议】\n")
        f.write("-"*60 + "\n")
        f.write("1. 严格控制仓位，单只股票不超过建议仓位上限\n")
        f.write("2. 设置止损位，建议跌破当日最低价-3%止损\n")
        f.write("3. 次日如未能继续涨停，尾盘前择机卖出\n")
        f.write("4. 高风险股票需格外谨慎，优先选择中低风险标的\n")
        f.write("5. 关注大盘走势，大盘走弱时降低操作频率\n\n")
        
        # 免责声明
        f.write("【免责声明】\n")
        f.write("-"*60 + "\n")
        f.write("本报告基于历史数据统计分析生成，仅供参考学习。\n")
        f.write("股市有风险，投资需谨慎。请根据自身风险承受能力决策。\n")
        f.write("本报告不构成任何投资建议，据此操作风险自负。\n")
        f.write("="*60 + "\n")
    
    print(f"\n✓ 报告已生成: {report_filename}")
 
if __name__ == '__main__':
    new_var = recommend_stocks()