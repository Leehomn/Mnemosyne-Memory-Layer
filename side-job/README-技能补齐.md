# 兼职接单 · 技能补齐指南

> 针对交接文档第三节的表格：把「要补的技能」变成「能交付的代码」。
> 所有脚本都在本地**跑通验证过**，不是纸上代码。

---

## 一、环境结论（重要，先看这个）

| 库 | 状态 | 说明 |
|---|---|---|
| openpyxl 3.1.5 | ✅ 已装 | Excel 读写，够用 |
| pandas 3.0.1 | ✅ 已装 | 大表、复杂统计时用 |
| requests | ❌ 装不上 | 本机网络连不通 PyPI（pypi.org 和清华源都超时） |

**这条约束决定了交付策略**：你的交付物一律走**零依赖路线**（只用 Python 自带库）。好处是客户拿到脚本双击就能跑，不用他配环境——很多客户电脑连 pip 都跑不动。所以 `crawl_stdlib.py` 是主交付版本，`crawl_requests.py` 只在你自己的网络好了之后、或客户明确能装包时才用。

想装 requests 的话：换手机热点 / 校园网再试 `pip install requests beautifulsoup4`。

---

## 二、文件清单

```
side-job/
├── README-技能补齐.md          ← 本文件
├── excel/
│   ├── make_practice_data.py   生成「脏数据」练手用
│   ├── process_excel.py        ★ Excel 处理通用骨架
│   └── practice_raw.xlsx       练手数据（已生成）
├── crawler/
│   ├── crawl_stdlib.py         ★ 爬虫零依赖版（主交付）
│   ├── crawl_requests.py       爬虫增强版（需装包）
│   ├── quick_test.py           离线验证脚本
│   └── test_page.html          本地测试页
└── delivery/
    └── 交付骨架.bat            给客户双击用的批处理
```

---

## 三、Excel 处理（`excel/process_excel.py`）

### 跑一遍看看

```bash
cd excel
python make_practice_data.py              # 生成脏数据
python process_excel.py practice_raw.xlsx -o output.xlsx
```

实测输出：

```
读入 62 行
有效 61 行，发现 1 个问题
已写出 output.xlsx
金额合计：153,228.92
最大部门：技术部（52,542.84）
```

生成三个表：**清洗后**（逐行干净数据）、**部门汇总**（按部门聚合金额）、**异常明细**（第几行有什么问题）。最后这个表是加分项——客户拿到「哪几行有问题」通常比拿到结果更高兴。

### 骨架的四层结构，接单时只改第二层

| 层 | 内容 | 要不要改 |
|---|---|---|
| 1. 清洗单格 | `clean_text` / `parse_date` / `parse_number` / `normalize_phone` | 不用，通用 |
| 2. 业务变换 | **`transform_row`** | ★ 每次接单主要改这里 |
| 3. 汇总 | `summarize` | 改个 key 就行（按部门→按月） |
| 4. 读入写出 | `read_sheet` / `write_sheet` / `autosize` | 不用 |

实测这四个清洗函数能吃的脏格式：

```
parse_date("2025年3月4日") → "2025-03-04"
parse_date("2025.3.4")     → "2025-03-04"
parse_date(20250304)       → "2025-03-04"
parse_number("￥1,234.56") → 1234.56
parse_number(" 88 元 ")    → 88.0
clean_text("  运营部 ")    → "运营部"      ← 部门名带空格导致分错组，最坑的一种
```

### 三个踩过的坑（都写在代码注释里了）

1. **`load_workbook(..., data_only=True)`** —— 不加这个，公式列读出来是 `=SUM(A1:A10)` 字符串而不是计算结果。客户的表全是公式。
2. **`parse_number` 失败返回 `None` 而不是 `0`** —— 「没填」和「填了 0」是两回事，混成 0 会把平均值拉歪。
3. **写 csv 用 `utf-8-sig`** —— 普通 utf-8 用 Excel 打开中文是乱码，客户会以为你做错了。

---

## 四、爬虫（`crawler/crawl_stdlib.py`）

### 先离线跑测试

```bash
cd crawler
python quick_test.py          # 不需要联网，用本地 test_page.html
```

实测结果：抽出 4 个链接、4 个邮箱、4 个手机号（含 `139-8765-4321` 带横杠写法），`<script>`/`<style>`/HTML 注释全部被剔除干净，断言全过。

### 用法

```bash
python crawl_stdlib.py https://example.com -o result.csv --limit 20
python crawl_stdlib.py ./客户给的网页.html  -o result.csv   # 本地文件也行
```

本地文件模式是特意加的：客户经常「网页另存为」甩给你一个 html，或者网络受限时让人另存。同一套解析逻辑支持两种输入。

### 修掉的一个真 bug

`LinkCollector._text` 原本初始化成 `[]`，导致第一个 `<a>` 之前的正文会越界；改成 `None` 并补了 `handle_endtag` 断开逻辑。否则 `</a>` 后面的正文会粘到上一个链接标题上——这种 bug 在真实页面上是「标题莫名变长一大截」，很难一眼看出来。**写 `quick_test.py` 就是为了防这类东西。**

### 接单红线（你文档里没写，但接爬虫单必守）

1. **不抓需要登录的内容**（绕验证码 = 破坏控制措施，风险高）。
2. **先查 robots.txt**，`crawl_requests.py` 里的 `allowed_by_robots()` 已封装好；跑之前调用一次。
3. **限速**：`polite_wait()` 默认 1 秒 1 次。别并发轰炸别人的站，出事平台会封你闲鱼号。
4. **不抓公民个人信息牟利**——邮箱电话用于营销可以，打包卖给第三方不行。这条是法律红线，不是道德建议。
5. **明确拒绝**：爬取付费内容（视频/小说/课程）、批量下载他人数据库。这类单子来了一律拒，跟学术不端同级。

---

## 五、交付流程（`delivery/交付骨架.bat`）

客户多数不懂技术。给他的东西应该是：**拖上去就出结果**。

bat 里的使用逻辑：
- 客户把 Excel **拖到 bat 图标上**（拖放会把文件路径变成 `%1`）
- 输出文件名自动加 `_已处理` 后缀
- `chcp 65001` 解决中文乱码
- 出错时提示「截图发给我」，降低沟通成本

⚠️ **交付前必改**：bat 里 `PY=` 那行的 Python 路径是你本机的，给客户前要换成他的路径，或者直接打包成 exe（`pip install pyinstaller` 然后 `pyinstaller --onefile process_excel.py`）。打包 exe  Netzwerk 需要装包，等网络好了再说。

---

## 六、练习路径（按这个顺序，别跳）

| # | 任务 | 怎么算过关 |
|---|---|---|
| 1 | 跑通 `process_excel.py` | ✅ 已完成，产出三个表 |
| 2 | 改 `summarize` 的 key 为「按月份汇总」 | 能按 `日期` 的前 7 位分组求和 |
| 3 | 自己再造一张更脏的表（合并单元格 / 多行表头） | 骨架能撑住不崩 |
| 4 | 跑通 `crawl_stdlib.py` 的本地测试 | ✅ 已完成，断言全过 |
| 5 | 用 `crawl_stdlib` 抓一个静态站，导出 CSV | 自己选目标，注意 robots.txt |
| 6 | 网络通了之后装 requests，跑 `crawl_requests` | 对比两个版本的差异 |

任务 2 是重点：**它模拟的就是真实接单**——客户说「能不能再给我按月份看看」，你只需要改一行。

---

## 七、还没做但值得做的

- **报价参考**：简单清洗+汇总 30~50 元；带定时任务/多表合并 80~150 元；EXE 打包 +50 元（这是客户感知最强的「专业感」溢价点）
- **需求确认话术**：先问「原始表格发我看一眼」再报价，别先说价格——看完才知道工作量
- **交付物打包清单**：脚本 + bat + 一个 `使用说明.txt` + 处理结果示例图

---

## 附：和主线的关系

按交接文档第五节：这些脚本只在你主线（Mnemosyne + 学业）之外的时间做。`side-job/` 目录独立于 Mnemosyne 的代码，互不干扰。兼职的目的是「练手 + 零花」，Python 能力提升本身也在反哺主线项目。
