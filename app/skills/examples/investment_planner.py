"""
investment_planner — 定投计划计算器

功能：按月复利计算定投收益，支持两种模式：
  - 给定目标金额 → 算出需要定投多久
  - 给定定投时长 → 算出到期总金额
输入参数被注入为 Python 变量，计算结果从 stdout 输出。

调用示例（LLM 生成）：
  investment_planner(monthly_amount=5000, annual_return_rate=8, target_amount=500000)
  investment_planner(monthly_amount=3000, annual_return_rate=6, target_months=120, current_savings=50000)
"""

META = {
    "description": "定投计划计算器：按月复利计算基金/理财定投收益。"
                   "输入每月定投金额和年化收益率，输出预期收益表。"
                   "支持给定目标金额算时长，或给定时长算终值。",
    "parameters": {
        "type": "object",
        "properties": {
            "monthly_amount": {
                "type": "number",
                "description": "每月定投金额（元）"
            },
            "annual_return_rate": {
                "type": "number",
                "description": "预期年化收益率（%），如 8 表示 8%"
            },
            "target_amount": {
                "type": "number",
                "description": "目标金额（元），与 target_months 二选一"
            },
            "target_months": {
                "type": "integer",
                "description": "定投时长（月），与 target_amount 二选一"
            },
            "current_savings": {
                "type": "number",
                "description": "当前已投入本金（元，可选，默认 0）"
            }
        },
        "required": ["monthly_amount", "annual_return_rate"]
    }
}

CODE = r'''
# ===== 定投计划计算器 =====
# 注入变量：monthly_amount, annual_return_rate, target_amount(可选), target_months(可选), current_savings(可选)

def calc_investment(monthly, annual_rate, target_amount=None, target_months=None, current=0):
    """计算定投收益"""
    monthly_rate = (1 + annual_rate / 100) ** (1 / 12) - 1

    if target_months and target_months > 0:
        # 模式A：给定时长 → 算终值
        months = target_months
        total_principal = current + monthly * months
        # FV = PV*(1+r)^n + PMT*((1+r)^n-1)/r
        future_value = current * (1 + monthly_rate) ** months
        if abs(monthly_rate) > 1e-10:
            future_value += monthly * ((1 + monthly_rate) ** months - 1) / monthly_rate
        else:
            future_value += monthly * months
        future_value = round(future_value, 2)
        total_principal = round(total_principal, 2)
        earnings = round(future_value - total_principal, 2)
        earnings_pct = round(earnings / total_principal * 100, 2) if total_principal > 0 else 0

        print(f"{'月份'.rjust(4)} | {'投入(元)'.rjust(10)} | {'累计本金'.rjust(10)} | {'总资产(元)'.rjust(12)} | {'收益(元)'.rjust(10)}")
        print("-" * 58)
        val = current
        for m in range(1, months + 1):
            val = val * (1 + monthly_rate) + monthly
            if months <= 60 or m % 12 == 0 or m == months:
                principal = current + monthly * m
                profit = round(val - principal, 2)
                print(f"{str(m).rjust(4)} | {str(monthly).rjust(10)} | {str(round(principal, 2)).rjust(10)} | {str(round(val, 2)).rjust(12)} | {str(profit).rjust(10)}")
        print("-" * 58)
        print(f"目标时长：{months} 个月（{months // 12} 年 {months % 12} 个月）")
        print(f"投入本金：{total_principal} 元")
        print(f"最终资产：{future_value} 元")
        print(f"总收益：{earnings} 元（+{earnings_pct}%）")

    elif target_amount and target_amount > 0:
        # 模式B：给定目标 → 算需要多久
        if monthly <= 0:
            print("每月定投金额必须大于 0")
            return
        if current >= target_amount:
            print(f"当前已有 {current} 元，已达到目标 {target_amount} 元")
            return

        max_months = 1200  # 最多算 100 年
        val = current
        for m in range(1, max_months + 1):
            val = val * (1 + monthly_rate) + monthly
            if val >= target_amount:
                needed_months = m
                total_principal = round(current + monthly * needed_months, 2)
                earnings = round(val - total_principal, 2)
                earnings_pct = round(earnings / total_principal * 100, 2)

                years = needed_months // 12
                rem_months = needed_months % 12

                print(f"\n目标金额：{target_amount} 元")
                print(f"每月定投：{monthly} 元")
                if current > 0:
                    print(f"当前本金：{current} 元")
                print(f"年化收益：{annual_rate}%")
                print(f"{'='*40}")
                print(f"需要定投：{years} 年 {rem_months} 个月（共 {needed_months} 个月）")
                print(f"投入本金：{total_principal} 元")
                print(f"到期资产：{round(val, 2)} 元")
                print(f"总收益：{earnings} 元（+{earnings_pct}%）")

                # 输出关键节点
                print(f"\n关键节点：")
                for check_month in [12, 36, 60, 120, 180, 240]:
                    if check_month <= needed_months:
                        v = current
                        for mm in range(1, check_month + 1):
                            v = v * (1 + monthly_rate) + monthly
                        p = current + monthly * check_month
                        print(f"  {check_month // 12} 年：资产 {round(v, 2)} 元 | 投入 {round(p, 2)} 元 | 收益 {round(v - p, 2)} 元")
                return

        print(f"在 {max_months // 12} 年内无法达到目标，请增加月投金额或降低目标")
    else:
        print("请提供 target_amount（目标金额）或 target_months（定投时长）")


_tm = None
_ta = None
_cs = 0
try:
    _tm = target_months
except NameError:
    pass
try:
    _ta = target_amount
except NameError:
    pass
try:
    _cs = current_savings
except NameError:
    pass

calc_investment(monthly_amount, annual_return_rate, target_amount=_ta, target_months=_tm, current=_cs)
'''
