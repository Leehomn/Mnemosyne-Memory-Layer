# 生成一批「脏数据」，专门给 process_excel.py 练手。
# 故意做得很乱，因为客户给的表永远比这还乱。

import random
from datetime import datetime, timedelta
from openpyxl import Workbook

random.seed(42)

DEPARTMENTS = ["技术部", "市场部", "  运营部", "财务部 ", "技术部", "人事部"]
NAMES = ["张三", "李四", "王五", "赵六", "孙七", "周八", "吴九", "郑十"]

# 各种奇形怪状的日期写法
DATE_STYLES = ["%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%Y年%m月%d日"]

HEADERS = ["  姓名 ", "部门", "金额", "日期", "手机号", "备注"]


def random_date():
    base = datetime(2025, 1, 1)
    d = base + timedelta(days=random.randint(0, 300))
    return d, random.choice(DATE_STYLES)


def random_phone():
    n = "1" + str(random.randint(30, 99)) + "".join(str(random.randint(0, 9)) for _ in range(8))
    style = random.randint(0, 3)
    if style == 0:
        return n                                   # 干净的
    if style == 1:
        return f"{n[:3]} {n[3:7]} {n[7:]}"         # 带空格
    if style == 2:
        return f"{n[:3]}-{n[3:7]}-{n[7:]}"         # 带横杠
    return f" {n} "                                # 带首尾空格


def main():
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(HEADERS)

    for _ in range(60):
        d, style = random_date()
        amount_style = random.randint(0, 3)
        amount = round(random.uniform(50, 5000), 2)
        if amount_style == 0:
            amount_cell = amount                   # 数字
        elif amount_style == 1:
            amount_cell = f"{amount}"              # 字符串数字
        elif amount_style == 2:
            amount_cell = f"￥{amount:,.2f}"       # 带货币符号和千分位
        else:
            amount_cell = f" {amount} 元 "         # 带单位

        ws.append([
            random.choice(NAMES),
            random.choice(DEPARTMENTS),
            amount_cell,
            d.strftime(style),
            random_phone(),
            random.choice(["", "", "  加急", "已核对 ", "待确认"]),
        ])

    # 插两个空行，模拟客户表格里的「分隔行」
    ws.append([None] * 6)
    ws.append(["合计", None, "不规范的合计行", None, None, None])
    ws.append([None] * 6)

    # 再来一个 sheet，练习多表
    ws2 = wb.create_sheet("Sheet2")
    ws2.append(["部门", "预算"])
    for dept in ["技术部", "市场部", "运营部", "财务部", "人事部"]:
        ws2.append([dept, round(random.uniform(10000, 100000), 2)])

    wb.save("practice_raw.xlsx")
    print("已生成 practice_raw.xlsx")


if __name__ == "__main__":
    main()
