"""
expense_splitter — 智能费用分摊计算器

功能：支持 AA 制、按比例分摊、带特殊消费项的复杂分摊。
输入参数会被注入为 Python 变量，计算结果从 stdout 输出。

调用示例（LLM 生成）：
  expense_splitter(total_amount=428, participants=["张三","李四","王五","赵六"],
                   paid_by="张三", special_items={"赵六": 68})
"""

META = {
    "description": "智能费用分摊计算器，支持 AA 制、带额外消费项的多人分摊。"
                   "输入总金额、参与人、付款人，自动算出每人应付/应收。",
    "parameters": {
        "type": "object",
        "properties": {
            "total_amount": {
                "type": "number",
                "description": "消费总金额（元）"
            },
            "participants": {
                "type": "array",
                "items": {"type": "string"},
                "description": "参与者名单，如 ['张三', '李四', '王五']"
            },
            "paid_by": {
                "type": "string",
                "description": "实际付款人姓名（必须是 participants 之一）"
            },
            "special_items": {
                "type": "object",
                "description": "可选：特殊消费项，如 {'赵六': 68} 表示某人额外点了专属商品",
                "additionalProperties": {"type": "number"}
            },
            "ratios": {
                "type": "object",
                "description": "可选：非均分比例，如 {'张三': 2, '李四': 1} 表示张三付双份",
                "additionalProperties": {"type": "number"}
            }
        },
        "required": ["total_amount", "participants", "paid_by"]
    }
}

CODE = r'''
# ===== 费用分摊计算器 =====
# 注入变量：total_amount, participants, paid_by, special_items(可选), ratios(可选)

def split_expense(total, people, payer, special=None, ratio=None):
    """计算分摊结果"""
    n = len(people)
    if n == 0:
        print("参与者列表不能为空")
        return
    if payer not in people:
        print(f"付款人 '{payer}' 不在参与者列表中")
        return

    special = special or {}
    ratio = ratio or {p: 1 for p in people}

    for p in people:
        if p not in ratio:
            ratio[p] = 1

    special_total = sum(special.values())
    base_pool = total - special_total
    if base_pool < 0:
        print("特殊消费项金额超过总金额")
        return

    ratio_sum = sum(ratio.get(p, 1) for p in people)
    shares = {}
    for p in people:
        base_share = base_pool * ratio.get(p, 1) / ratio_sum
        total_share = round(base_share + special.get(p, 0), 2)
        shares[p] = total_share

    total_allocated = round(sum(shares.values()), 2)
    diff = round(total - total_allocated, 2)
    if abs(diff) > 0.01:
        shares[people[-1]] = round(shares[people[-1]] + diff, 2)

    width = 12
    sep = " | "
    print(f"{'参与者'.ljust(width)}{sep}{'应付(元)'.rjust(width)}{sep}{'结算'.rjust(width)}")
    print("-" * (width * 3 + len(sep) * 2))

    for p in people:
        pay = shares[p]
        if p == payer:
            received = round(total - pay, 2)
            balance = f"应收 {received} 元"
        else:
            balance = f"应付 {pay} 元"
        print(f"{p.ljust(width)}{sep}{str(pay).rjust(width)}{sep}{balance}")

    print()
    print(f"总金额：{total} 元 | 付款人：{payer}")
    if special:
        print(f"专属消费：{special}")
    if ratio and set(ratio.values()) != {1}:
        print(f"分摊比例：{ratio}")
    print(f"--- 已结清，{payer} 应收回 {round(total - shares[payer], 2)} 元 ---")

_special = None
_ratio = None
try:
    _special = special_items
except NameError:
    pass
try:
    _ratio = ratios
except NameError:
    pass

split_expense(total_amount, participants, paid_by, special=_special, ratio=_ratio)
'''
