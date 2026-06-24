"""示例技能注册表 —— 所有预置示例技能在这里注册"""
from app.skills.examples import expense_splitter, investment_planner

EXAMPLE_SKILLS = [
    {
        "name": "expense_splitter",
        "description": expense_splitter.META["description"],
        "parameters": expense_splitter.META["parameters"],
        "code": expense_splitter.CODE,
        "language": "python",
        "tags": ["生活工具", "财务"],
    },
    {
        "name": "investment_planner",
        "description": investment_planner.META["description"],
        "parameters": investment_planner.META["parameters"],
        "code": investment_planner.CODE,
        "language": "python",
        "tags": ["理财", "定投", "财务规划"],
    },
]
