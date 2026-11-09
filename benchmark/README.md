# benchmark —— Mnemosyne 跑分适配器

> 用 [memory-system-benchmark](https://github.com/Ornn8/memory-system-benchmark)（公开基准）跑 Mnemosyne 的适配器 + 判官 + 成绩记录。
> 这套脚本**不属于 Mnemosyne 核心代码**，只是「拿第三方基准验证记忆系统效果」的工具。

---

## 一、目录说明

| 文件 | 作用 |
|---|---|
| `run_mnemosyne.py` | demo 卷（1 人物 108 题）适配器 |
| `run_formal.py` | 正式卷（6 人物 714 题）适配器，支持 `--persona` 断点续跑 |
| `run_sample.py` | 小样本验证（只跑漏记重灾区考点，几分钟出信号） |
| `judge_demo.py` | demo 卷判官（DeepSeek 当判官，复刻官方 grading 规则） |
| `judge_formal.py` | 正式卷判官 |
| `judge_formal_gap.py` | 补判缺口题（断点续判） |
| `judge_formal_P14_rerun.py` | P14 重跑单人物判官 |
| `测试日记.md` | 每次跑分的过程记录 + 根因追踪 |
| `评测报告.md` | demo 108 题的完整评测报告 |
| `测试数据记录.md` | 结构化成绩汇总（跑分总览/时间档/考点/根因/库状态） |
| `*.json` | 判分汇总结果（`summary`/`formal_summary*`） |

---

## 二、复现方法

1. 把基准数据 `chat-memory-benchmark-main/` 放到本目录下（从 [Ornn8/memory-system-benchmark](https://github.com/Ornn8/memory-system-benchmark) 拉取）
2. 配置 `../code/config.json`（参考 `../code/config.json.example`，填 DeepSeek api_key）
3. 跑适配器（喂历史 + 答题）：
   ```bash
   python -X utf8 run_formal.py --out formal_answers.jsonl --no-reply
   ```
4. 跑判官（判分 + 汇总）：
   ```bash
   python -X utf8 judge_formal.py
   ```

> 注意：判分产物（`formal_reviews.jsonl` 等大文件）和记忆库目录（`mnemosyne_formal/`）含运行期数据，不进 git、不上传 GitHub，只留在本地。

---

## 三、成绩一览

> 详见 `测试数据记录.md`。

| 次数 | 日期 | 范围 | 成绩 | 通过率 |
|---|---|---|---|---|
| 第 1 次 | 2026-11-06 | 全量 6 人 714 题 | 243/714 | 34.0% |
| 第 2 次 | 2026-11-07 | P14 82 题 | 46/82 | 56.1% |
| 第 3 次 | 2026-11-08 | P14 82 题 | 63/82 | 76.8% |

---

## 四、依赖

- 运行适配器/判官需 `openai`（见仓库根 `requirements.txt`）
- 判官与被测系统都走 `../code/` 里的 Mnemosyne 模块
