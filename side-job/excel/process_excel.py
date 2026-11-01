# process_excel.py —— Excel 批量处理「通用骨架」
#
# 用法：
#   python process_excel.py 输入.xlsx [-o 输出.xlsx] [-s 工作表名]
#
# 这是「接单模板」：拿到客户的 Excel，先套这个骨架跑一遍，
# 再根据具体要求改 transform_row 里的业务逻辑。
#
# 骨架负责的部分（每个单子都要做，不要重复写）：
#   读表 → 规范化表头 → 清洗每格 → 丢掉废行 → 写新表 → 生成汇总 + 排版

import argparse
import re
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ---------------- 第 1 层：清洗单个单元格 ----------------
# 这一层与业务无关，任何单子都能直接复用。


def clean_text(value):
    """去掉首尾空白，把各种空白字符压成一个空格；空值返回 ''。"""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_date(value):
    """
    把各种写法的日期转成标准 YYYY-MM-DD。
    支持：日期类型 / 2025-03-04 / 2025/3/4 / 2025.3.4 / 2025年3月4日 / 20250304
    认不出来返回原字符串，并在 calling 侧被标为异常。
    """
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 10000:
        # Excel 里日期也可能是数字序列号，这里只处理 YYYYMMDD 这种整数
        s = str(int(value))
        if len(s) == 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:]}"

    s = clean_text(value)
    if not s:
        return ""
    s = s.replace("年", "-").replace("月", "-").replace("日", "").replace(".", "-").replace("/", "-")

    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    # 补零再试一次：2025-3-4 → 2025-03-04
    parts = s.split("-")
    if len(parts) == 3:
        try:
            y, m, d = [int(p) for p in parts]
            return f"{y:04d}-{m:02d}-{d:02d}"
        except ValueError:
            pass
    return s


def parse_number(value):
    """
    把「￥1,234.56」「 1234 元 」「1,234」转成 float。
    转不出来返回 None（注意：不要返回 0，0 和「没填」是两回事）。
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = clean_text(value)
    if not s:
        return None
    s = s.replace("￥", "").replace("¥", "").replace(",", "").replace("元", "").replace("$", "")
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None


def normalize_phone(value):
    """手机号：抽掉所有非数字，只留 11 位；不符合就原样返回并标记。"""
    s = clean_text(value)
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits.startswith("1"):
        return digits, True
    if len(digits) > 11 and digits.startswith("1"):
        # 有些是从 excel 导出的 +86 前缀
        tail = digits[-11:]
        if tail.startswith("1"):
            return tail, True
    return digits, False


# ---------------- 第 2 层：业务变换 ----------------
# ★ 接单时主要改这一层。客户的实际要求写在这里。


def transform_row(row):
    """
    把一行原始数据，变成一行干净数据。

    参数：
        row : dict，键是「原始表头」，值是单元格内容

    返回：
        (clean_row, errors)
        clean_row : dict，键是「输出表头」
        errors    : list[str]，这一行的问题清单（没有就空列表）
    """
    errors = []

    name = clean_text(row.get("姓名"))
    dept = clean_text(row.get("部门"))

    amount = parse_number(row.get("金额"))
    if amount is None:
        errors.append(f"金额无法识别：{row.get('金额')!r}")

    date_raw = row.get("日期")
    date_std = parse_date(date_raw)
    # 校验：清洗后是否成功（认不出来的会保持原样）
    if date_std and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_std):
        errors.append(f"日期格式异常：{date_raw!r}")

    phone, phone_ok = normalize_phone(row.get("手机号"))
    if phone and not phone_ok:
        errors.append(f"手机号不合规：{row.get('手机号')!r}")

    clean_row = {
        "姓名": name,
        "部门": dept,
        "金额": amount,
        "日期": date_std,
        "手机号": phone,
        "备注": clean_text(row.get("备注")),
    }
    return clean_row, errors


def is_empty_row(row):
    """整行全空（客户表里经常有这种分隔行）→ 丢弃。"""
    return all(clean_text(v) == "" for v in row.values())


# ---------------- 第 3 层：汇总 ----------------
# 客户 80% 的需求到这一步就结束了：给个按部门/按月的汇总表。


def summarize(clean_rows, key="部门", value="金额"):
    """
    按 key 列分组，对 value 列求和、计数。

    返回：list[dict]，每项含 key / 笔数 / 合计 / 平均，按合计降序。
    """
    buckets = {}
    for r in clean_rows:
        k = r.get(key) or "(空)"
        v = r.get(value)
        buckets.setdefault(k, {"total": 0.0, "count": 0, "missing": 0})
        buckets[k]["count"] += 1
        if v is None:
            buckets[k]["missing"] += 1
        else:
            buckets[k]["total"] += v

    result = []
    for k, b in buckets.items():
        valid = b["count"] - b["missing"]
        result.append({
            key: k,
            "笔数": b["count"],
            "合计": round(b["total"], 2),
            "平均": round(b["total"] / valid, 2) if valid else 0,
            "金额缺失": b["missing"],
        })
    result.sort(key=lambda x: x["合计"], reverse=True)
    return result


# ---------------- 第 4 层：读入 / 写出 ----------------


def read_sheet(path, sheet_name=None):
    """
    读 Excel 的第一个（或指定）工作表。

    返回：list[dict]，键是表头（已 strip），值是原始单元格内容。
    """
    wb = load_workbook(path, data_only=True)  # data_only=True：读公式的结果，而不是公式本身
    ws = wb[sheet_name] if sheet_name else wb.worksheets[0]

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [clean_text(h) for h in rows[0]]
    data = []
    for values in rows[1:]:
        data.append(dict(zip(headers, values)))
    return data


HEADER_FILL = PatternFill("solid", fgColor="4F6228")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def style_header(ws, ncols):
    """表头白字深绿底 + 冻结首行，让客户打开就觉得像样。"""
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"


def autosize(ws, min_width=8, max_width=40):
    """按内容长度调列宽。中文按 2 个字符宽度算。"""
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        longest = 0
        for cell in col:
            v = "" if cell.value is None else str(cell.value)
            width = sum(2 if ord(ch) > 127 else 1 for ch in v)
            longest = max(longest, width)
        ws.column_dimensions[letter].width = max(min_width, min(max_width, longest + 2))


def write_sheet(ws, rows, headers=None):
    """把 list[dict] 写进工作表，顺带排版。"""
    if not rows:
        return
    headers = headers or list(rows[0].keys())
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    style_header(ws, len(headers))
    autosize(ws)


def process(input_path, output_path, sheet_name=None):
    """串起全流程：读 → 变换 → 汇总 → 写。"""
    raw_rows = read_sheet(input_path, sheet_name)
    print(f"读入 {len(raw_rows)} 行")

    clean_rows, all_errors = [], []
    for i, row in enumerate(raw_rows, start=2):  # start=2：Excel 行号（第 1 行是表头）
        if is_empty_row(row):
            continue
        clean_row, errors = transform_row(row)
        for e in errors:
            all_errors.append({"行号": i, "问题": e})
        clean_rows.append(clean_row)

    print(f"有效 {len(clean_rows)} 行，发现 {len(all_errors)} 个问题")

    wb = Workbook()
    ws_clean = wb.active
    ws_clean.title = "清洗后"
    write_sheet(ws_clean, clean_rows)

    summary_rows = summarize(clean_rows, key="部门", value="金额")
    ws_sum = wb.create_sheet("部门汇总")
    write_sheet(ws_sum, summary_rows)

    if all_errors:
        ws_err = wb.create_sheet("异常明细")
        write_sheet(ws_err, all_errors)

    wb.save(output_path)

    total = sum(r["金额"] for r in clean_rows if r["金额"] is not None)
    print(f"已写出 {output_path}")
    print(f"金额合计：{total:,.2f}")
    if summary_rows:
        top = summary_rows[0]
        print(f"最大部门：{top['部门']}（{top['合计']:,.2f}）")
    return clean_rows, summary_rows, all_errors


def main():
    ap = argparse.ArgumentParser(description="Excel 批量处理通用骨架")
    ap.add_argument("input", help="输入 xlsx 路径")
    ap.add_argument("-o", "--output", default="output.xlsx", help="输出 xlsx 路径")
    ap.add_argument("-s", "--sheet", default=None, help="工作表名，默认第一个")
    args = ap.parse_args()
    process(args.input, args.output, args.sheet)


if __name__ == "__main__":
    main()
