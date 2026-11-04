# Mnemosyne · 认知记忆层

> **对外交付名**：认知记忆层（长期记忆系统）
> **对内代号**：Mnemosyne（记忆女神）
>
> 借鉴人类记忆**若干特性**（不是全部）的 AI 长期记忆系统。用 **Python** 实现，已接入 **DeepSeek 真模型**。

---

## 状态

**核心机制已实现，可运行。** 10 个模块齐全，`pytest` 测试 89 条全部通过，已接入真实模型。

- 代码：`code/` 目录
- 测试：`code/test_*.py`（10 份），运行 `python -m pytest` 全绿
- 版本管理：Git（仓库根在当前目录，分支 `master`）

---

## 这是什么

给长期陪伴型 AI 用的记忆层。解决三个问题：

1. **记不准** —— 不逐句判断「值不值得记」，而是事后回看一段对话、只提炼「对这个人有没有新认识」
2. **不知道自己在猜** —— 每条记忆强制带来源，`[事实]`（他说的）/ `[猜测]`（我推的）物理隔离，注入时分开放
3. **越攒越多** —— 遗忘机制 + 晋升机制，只留下真正重要的，碎片自动淘汰

**一句话初心**：让陪伴型 AI **记得住、不遗忘、不乱编**，让「怕失去的人」不再失去。

---

## 核心机制（都已落地）

| 机制 | 说明 | 对应模块 |
|---|---|---|
| 遗忘 | 时间指数衰减 + 半衰期分层 + 用进废退（对数） + 复习失败倒退 | `decay.py` |
| 间隔重复 | SM-2 简化版，复习让半衰期变长 | `decay.py` |
| 来源监控 | 事实/猜测物理隔离，`subject` 字段区分「关于谁」 | `source.py` |
| 合并增强 | 相似记忆 → `occurrences+1` + 价值重估（只升不降） | `index.py` |
| 晋升 | state（动态表现）反复出现 ≥3 次 → trait（稳定内核，半衰期 60→3650 天） | `item.py` / `index.py` |
| 夜间整合 | consolidate，事件 → 印象（`digested` 记账防重复归纳） | `reconstruct.py` / `index.py` |
| 语义召回 | semantic_recall，用模型判断相关性（含时间远近、反义/过时识别） | `recall.py` |
| **冲突检测** | find_conflicts，新记忆推翻旧记忆时自动识别 | `conflict.py` |
| **软删除 + 墓碑** | 被推翻的记忆标 `deleted` 而不真删，可追溯、可恢复 | `item.py` / `recall.py` / `index.py` |
| **验证机制** | 两层触发：有不确定印象（规则）+ 用户敞开心扉（模型） | `verify.py` |

**10 个模块**：`decay` / `item` / `store` / `recall` / `source` / `reconstruct` / `conflict` / `verify` / `llm` / `index`

> 注：`llm.py` 是模型接入层（不参与记忆逻辑）；`conflict.py` / `verify.py` 是「记忆修正」的被动与主动两半。

---

## 项目边界（重要）

**Mnemosyne 只做「记忆」，不做「性格」和「情绪状态」：**

| 层面 | 属于谁 | Mnemosyne 做吗 |
|---|---|---|
| 记忆（存取/遗忘/召回/提炼/晋升） | Mnemosyne | ✅ 核心 |
| 性格/人设 | 人格系统（另做） | ❌ 预留接口 |
| 情绪状态（心情、好感度） | 情绪系统（另做） | ❌ 预留接口 |

情绪只用于「给记忆打情绪标签（峰终定律）并调制权重」，不管理情绪状态本身。

---

## 设计哲学（红线）

1. 像人 ≠ 像人的缺点（真实感来自「有分寸」，不是「会出错」）
2. 宁可漏记，不可乱记（假记忆是头号敌人）
3. 印象 ≠ 事实（归纳的来源是 observed/her_inference，不是 user_said）
4. 语义量用模型，机械量用规则
5. 尽可能「证实」，而非「猜」（要猜的允许，但必须标注「这是猜的」）
6. 话题主导权在用户

---

## 快速开始

### 1. 填 API key（必需）

在 `code/config.json` 里填入你自己的 DeepSeek API key：

```json
{
  "api_key": "在这里填你的 key",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat"
}
```

> ⚠️ `config.json` 已在 `.gitignore` 里，**不会被提交到版本库**，但请仍不要把你的真实 key 贴到公开场合。

### 2. 装依赖

```bash
pip install openai
```

### 3. 跑测试（确认环境正常）

```bash
cd code
python -m pytest
```

### 4. 跑演示

```bash
cd code
python demo_1.py                 # 无模型：一条记忆的一生
python demo_semantic_recall.py   # 真模型：语义召回（需先填 key）
python demo_llm_verify.py        # 真模型：验证机制
python chat-loop.py              # 真模型：端到端（需先填 key）
python chat_demo.py              # 真模型：交互式对话（双通道 + 验证，需先填 key）
```

---

## 核心用法

```python
from index import Cognition
from llm import make_deepseek_llm

# 不接模型（纯规则记忆）
cog = Cognition(data_dir="data")
cog.remember("我叫南风", source="user_said")
block = cog.recall_block(limit=8)   # 按权重召回
cog.maintain()                      # 维护：淘汰过期记忆

# 接真模型（开放语义能力）
cog = Cognition(data_dir="data", llm=make_deepseek_llm())
block = cog.semantic_recall_block("我下周去面试")  # 语义召回
cog.consolidate()                   # 夜间整合：事件 → 印象
```

**记忆修正的两半：**

```python
from conflict import find_conflicts       # 被动：新信息推翻旧信息
from verify import find_uncertain_impressions, should_ask_now, judge_feedback, pick_verify_target

# 被动修正：remember 时自动调用 find_conflicts，冲突的旧记忆标墓碑
cog.remember("我不吃辣了", source="user_said")   # 旧记忆「他爱吃辣」自动标失效

# 主动修正：验证机制（在对话流里自然求证）
items = cog._all_items()
target, should_ask = pick_verify_target(llm, items, user_input)
# 用户回答后用 judge_feedback 判断 confirm / deny / unrelated
cog.update_confidence(target, 0.9, reason="验证确认")
```

---

## 文档

| 文件 | 内容 |
|---|---|
| [Mnemosyne-设计定稿.md](Mnemosyne-设计定稿.md) | 完整设计（思想层 + 技术层），**最重要** |
| [定位与参考.md](定位与参考.md) | 流派定位、学术地图、竞品分析 |
| [复习总纲.md](复习总纲.md) | 全景复习 |
| [方向锚点.md](方向锚点.md) | 心态锚点（焦虑时看） |
| [SPEC.md](SPEC.md) | 早期技术规格（数据模型/接口，历史参考） |
| [DESIGN.md](DESIGN.md) | 早期设计思路（历史参考） |
| [NOTES-FROM-V1.md](NOTES-FROM-V1.md) | 第一代的实测教训与血泪坑（只读参考） |

**建议阅读顺序**：先 `Mnemosyne-设计定稿.md`（理解为什么 + 怎么做），其余按需查。

---

## 目标指标

| 指标 | 目标 |
|---|---|
| 记忆条数 | 10~15 条，**不是越攒越多** |
| 假记忆率 | 说出用户没提过的事 → 0 |
| 信息密度 | 每条都能单独回答「他是个怎样的人」 |
| 可解释性 | 任意一条能追溯到原文和来源 |

---

## 环境说明

- **Python**：`python` = 3.13.15（`D:\python313`），pytest 装在这里
- **跑测试**：在 `code/` 目录下 `python -m pytest`（89 passed）
- **依赖**：只有 `openai`（调 DeepSeek 用）；不接模型时纯标准库
- **Git**：仓库在项目根目录，提交历史见 `git log`（部分 shell 里 `git.exe` 不在 PATH，需在 PyCharm 终端或配好 PATH 后使用）
- **Python 环境待统一**：本机有 3.13（D 盘）和 3.14（AppData）两个 Python，建议找时间统一，避免依赖混乱

---

## 已知局限（诚实清单）

| 局限 | 说明 | 缓解 |
|---|---|---|
| 去重用 Jaccard 按字拆分 | 看不出「爱吃辣 / 讨厌辣」的反义 | 语义召回用模型判断，已部分缓解 |
| 验证机制少在真实对话里自然触发 | 需要有 `her_inference` 候选 + 用户敞开心扉 | 已放宽触发条件，但仍需更多真实对话打磨 |
| 猜测会「过度推断」 | 从单次临时状态推出稳定特质 | 提示词待加强约束（见设计定稿 7.7c） |
| 没有模糊联想 | 只有精确召回，靠模型判断相关性 | 「进阶的灵气」，暂不做 |

---

## 工程收尾（未完成）

- [ ] `LICENSE`（开源协议）

---

## 开源

**做出来就开源。** 用宽松协议开源给普通人免费用（初心），专利防大公司白嫖（可选）。两者不冲突。

---

## 不做的事

- 不做向量数据库（字符重合 + 同类上限够用，模糊联想是「进阶灵气」，暂不做）
- 不做性格/人设、不做情绪状态（那是另外的系统）
- 不模拟人脑的遗忘缺陷（故意记错、联想扩散）
- 不碰任何现有生产系统（完全独立项目）

**核心理念**：像人 ≠ 像人的缺点。真实感来自「有分寸」，不是「会出错」。

---

> 本项目用 Git 管理版本，仓库根在项目目录（`master` 分支）。
