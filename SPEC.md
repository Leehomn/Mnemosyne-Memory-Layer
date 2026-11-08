# 技术规格 · SPEC

> 配套 `DESIGN.md`。这里写「长什么样」，不写「为什么这样」。
>
> **状态（2026-11-08）**：**已实施**，本文档已同步至实际 Python 代码。
> 10 个模块、106 条测试全绿。
>
> **历史说明**：本文件最初（2026-10-24）是给 **Node.js / `.mjs`** 写的规格。
> 2026-10-25 技术选型改为 **Python**（理由：开发者正在学 Python，学以致用；
> 原方案的 Node 只是第一代 `qq-bridge` 的环境选择，不是本项目的约束）。
> 下面所有代码示例均已改写为 Python 实际实现。

---

## 1. 数据模型

### 1.1 核心条目 `Item`

实际实现见 `code/item.py:make_item`。

```python
{
  "text": "他叫南风，是四川人",
  "source": "user_said",        # user_said | her_inference | observed | third_party
  "confidence": 0.9,            # 0~1，不传则按 source 自动取
  "layer": "episode",           # episode | impression | relationship
  "hits": 0,                    # 被想起的次数（decay 用它拉长半衰期）
  "base_weight": 1.0,           # 初始权重
  "half_life": 14,              # 半衰期（天）
  "created_at": 1792816155.0,   # Unix 时间戳（秒，浮点）—— 记住时间（驱动衰减）
  "event_time": "2026-05-25",   # 事件发生的逻辑日期（可选，None=不涉及具体某天）
  "subject": "about_user",      # about_user | about_self | about_us
  "kind": None,                 # trait | state（仅 impression 层用）
  "occurrences": 1,             # 反复出现的次数（去重合并时 +1）
  "deleted": False,             # 软删除标记（墓碑）
  "deleted_reason": None,       # 为什么失效，如「被新信息推翻」
  "superseded_by": None,        # 被哪条新记忆推翻
  "digested": False,            # 夜间整合是否已消化过
  "confidence_reason": None,    # 置信度变更原因（verify 用）
}
```

**半衰期分层**（`code/item.py:HALF_LIVES` / `IMPRESSION_HALF_LIVES`）：

| 层 | kind | 半衰期 | 含义 |
|---|---|---|---|
| `episode` | — | 14 天 | 发生了什么（情节） |
| `impression` | `state` | 60 天 | 他最近的状态 |
| `impression` | `trait` | 3650 天 | 他的稳定特质 |
| `relationship` | — | 3650 天 | 你们的关系 |

### 1.2 存储布局

```
code/
├── data/
│   └── items.json          # 所有条目（单文件，便于备份）
└── *.py                    # 10 个模块 + 测试 + demo
```

实际实现**没有** `sessions.json` 和 `audit/` 审计日志——这是原设计的过度设计，
单用户单文件场景用不上。备份采用 `items.json.bak-<YYYYmmdd-HHMMSS>`（`store.py:backup_file`）。

**单文件理由**：条目数是 10~15 条量级，不是几万条。单文件便于人工检查、备份、回滚。

**必须无 BOM 写入**：`store.py:save_items` 用 `encoding="utf-8"`（不是 `utf-8-sig`）。

---

## 2. 模块划分（实际 10 个模块）

```
code/
├── decay.py           权重公式、衰减、复习失败
├── item.py            条目结构、校验、半衰期
├── store.py           读写、备份、批量更新
├── source.py          来源→置信度映射
├── recall.py          召回（按权重 + 语义召回 + 格式化）
├── reconstruct.py     事后重构 + 夜间整合 + 解析层
├── conflict.py        冲突检测（反证修正·被动）
├── verify.py          验证机制（反证修正·主动）
├── llm.py             DeepSeek 接入层
└── index.py           统一入口 Cognition 类

测试（10 份，106 条）：
test_decay / test_item / test_store / test_source / test_recall
test_reconstruct / test_conflict / test_consolidate / test_verify / test_index

demo：
demo_1.py（无模型）、demo_semantic_recall.py、demo_llm_verify.py、chat_demo.py、chat-loop.py
```

**依赖原则**：唯一第三方依赖是 `openai`（调 DeepSeek 用）。其余全部标准库。
模型通过注入的 `llm(prompt) -> str` 函数接入，不绑定供应商——
`test` 里全部用 `fake_llm`，不花 token。

---

## 3. 核心接口

### 3.1 对外门面 `index.py`（`Cognition` 类）

```python
class Cognition:
    def __init__(self, data_dir="data", llm=None)

    # 记忆写入（冲突检测 → 去重合并增强 → 晋升）
    def remember(self, text, source, confidence=None, **kwargs)

    # 召回
    def recall_block(self, limit=8)                     # 按权重
    def semantic_recall_block(self, query, limit=8)     # 按语义相关性（需 llm）

    # 维护
    def maintain(self)                                  # 衰减 + 淘汰
    def consolidate(self)                               # 夜间整合：episode → impression

    # 修正
    def mark_deleted(self, old_item, reason, superseded_by=None)   # 软删除
    def update_confidence(self, item, new_confidence, reason=None) # 调置信度

    # 内部
    def _all_items(self)
```

### 3.2 重构接口（最关键）

见 `code/reconstruct.py`。

**提示词**（`reconstruct.py:reconstruct` 里实际拼的，不是原设计稿）：

```
下面是一段对话。你要从对话里，提炼出「对他这个人的新认识」。

【严格输出格式，必须遵守】
每行一条，只能以下面两种前缀开头，除此之外什么都不能有：
[事实] 后面写：他明确说过的事
[猜测] 后面写：你推断的、但没直说的事
没有新认识，就只输出一个词：无
绝对不要写「有」「好的」等其他任何话，不要解释。

【只记值得长期记的】
只提炼「他是谁」的稳定特质，或「近期相对持续」的表现。
不要记「最近很累」「今天心情不好」这类临时状态。

【猜测要谨慎】
[猜测] 只能基于「反复出现或稳定的线索」推断。
不要从「单次、临时的状态」（比如某天说累）去推断他长期的性格或习惯。

对话内容：
...
```

> **【实现时的演进】比原设计多了两段约束。** 原稿只说「不确定就别写」，
> 实际跑起来模型倾向把「今天很累」记成「他是个容易疲惫的人」——
> 从单次临时状态推出稳定特质，这是最典型的「过度推断」。
> 现在提示词明确禁止，但**这条约束仍然是最弱的一环**（见 §10 风险表）。

**解析规则**（`reconstruct.py:parse_reply`，2026-11-03 加固）：

- `[事实]` → `source="user_said"`, `confidence=0.9`
- `[猜测]` → `source="her_inference"`, `confidence=0.4`
- 没有前缀的行 → 丢弃（防止模型乱写）
- 输出「无」→ 什么都不做

**必须容忍模型的各种写法**（这是实战教训，旧代码只认顶格 `[事实]`，其余全部静默丢失）：

| 模型可能输出 | 是否解析 | 处理方式 |
|---|---|---|
| `[事实] 他叫南风` | ✅ | 标准格式 |
| `1. [事实] 他叫南风` | ✅ | 剥掉数字编号 |
| `- [事实] 他叫南风` | ✅ | 剥掉项目符号 |
| `**[事实]** 他叫南风` | ✅ | 剥掉 markdown 加粗 |
| `【事实】他叫南风` | ✅ | 全角方括号等价 |
| `[事实]：他叫南风` | ✅ | 冒号后取正文 |
| `他叫南风` | ❌ | 无前缀，丢弃 |
| 输出「无」 | ✅ | 不写入任何东西 |

实现里用 `_PREFIX_NOISE` + `_TAG` 两个正则循环剥最多 3 层装饰。

**为什么强制前缀**：这比事后用规则猜来源可靠得多。模型自己知道它是在引用还是在推演。

### 3.3 召回接口

见 `code/recall.py`。

```python
def recall_by_hits(items, limit=8)   # 按 hits 排序（简单版）
def recall(items, limit=8, now=None) # 按衰减后权重排序，过滤 deleted
def format_recall_block(items)       # 格式化成注入文本
def semantic_recall(llm, items, query)  # 用模型判断相关性
```

**格式化结果**（事实区和猜测区**物理隔离**，并给不同使用指令）：

```
关于他的事实（他说过的，可以当真）：
- 他叫南风，是四川人
- 他最近在找工作

你的猜测（不是他说的，别当事实讲）：
- 他可能不太喜欢被叫"大肥鱼"

用法：聊到相关再说，别主动复述。
```

**关键**：事实区要求 `source in (user_said, observed)` 且 `confidence >= 0.8`
且 `subject != about_self`；猜测区只放 `her_inference`。
第一代的问题就是所有条目混在一起，模型分不清真假。

**语义召回的「反义识别」**：`semantic_recall` 让模型判断相关性，
所以「我爱吃辣」vs「我不吃辣了」能区分（靠字符重合做不到）。
实测：说「我在戒辣了」时，语义召回**不会**把「超爱吃辣」当相关——生效。

---

## 4. 配置项

实际实现**没有集中的 `DEFAULT_CONFIG` 对象**，参数分散在各函数的默认值里。
`config.json` 只存模型接入信息（不提交 git）：

```json
{
  "api_key": "sk-...",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat"
}
```

> **`model` 写别名不写死型号**：`deepseek-chat` 会自动指向当前主力模型
> （实测返回 `deepseek-flash`）。这样官方换型号/下线旧型号时不用改配置。

主要可调参数（分布在各模块）：

| 参数 | 默认值 | 位置 |
|---|---|---|
| `forget_below` | 0.12 | `decay.py:should_forget` |
| `review_boost` | 0.5 | `decay.py:effective_half_life`（对数：`×(1+review_boost×log(1+hits))`） |
| `boost_k` | 1.0 | `decay.py:decayed_weight` |
| `reset_ratio` | 0.5 | `decay.py:after_review_fail` |
| Jaccard 合并阈值 | 0.5 | `index.py:remember` |
| 晋升阈值 | `occurrences >= 3` | `index.py:remember` |
| `limit` | 8 | `recall*` 各函数 |

---

## 5. 生命周期

```
对话进来
   │
   ├─→ 快通道：单句高价值 → remember() 立即存
   │        ├─ 冲突检测（find_conflicts，模型判断）
   │        │     └─ 有冲突 → 旧的标 deleted + deleted_reason + superseded_by
   │        ├─ 去重合并（Jaccard >= 0.5 且 subject 相同）
   │        │     ├─ occurrences + 1
   │        │     ├─ hits + 1（用进废退生效）
   │        │     ├─ 价值重估（置信度/权重只升不降）
   │        │     └─ state 出现 >= 3 次 → 晋升 trait（半衰期 60 → 3650 天）
   │        └─ 写入 items.json
   │
   ├─→ 慢通道：话题固化 → reconstruct()
   │        ├─ 调模型回看这段
   │        ├─ parse_reply 解析 [事实]/[猜测]（容错各种写法）
   │        └─ 写入
   │
   ├─→ 每轮召回
   │        ├─ recall_block()（按权重）
   │        └─ semantic_recall_block(query)（模型判断相关性）
   │              └─ 过滤 deleted → 事实区/猜测区分开 → 返回注入文本
   │
   ├─→ 每天 maintain()
   │        ├─ 重算所有条目权重
   │        └─ weight < 0.12 → 淘汰（物理删除）
   │
   ├─→ 夜间 consolidate()
   │        ├─ 筛 layer == episode 且 not digested
   │        ├─ 模型归纳成 impression（kind=state）
   │        └─ 记账 digested=True（防重复归纳）
   │
   └─→ 验证机制（verify）
            ├─ find_uncertain_impressions()：规则筛候选（her_inference + conf 0.4~0.7 + 未删）
            ├─ should_ask_now(llm, user_text)：模型判断用户是否敞开心扉
            ├─ pick_verify_target(llm, items, user_text)：模型挑问哪条
            └─ judge_feedback(llm, reply_text)：模型判 confirm/deny/unrelated
                  ├─ confirm → 置信度 0.9
                  ├─ deny    → 置信度 0.1
                  └─ unrelated → 不动
```

---

## 6. 测试策略

### 6.1 现状

**106 条测试，10 份文件，全部离线（fake_llm），跑一次 0.11 秒。**
分布见 `Mnemosyne-设计定稿.md` §10.1。

### 6.2 禁止的测试写法（红线）

**① 假模型不能依赖提示词模板里的固定字样。**

```python
# ❌ 错：这测的是 "是" in "是"
def fake_llm(prompt):
    return "是" if "敞开心扉" in prompt else "否"
# "敞开心扉" 这四个字写死在 verify.py 的提示词模板里，
# 跟用户说了什么完全无关 → fake_llm 永远返回「是」
```

实际踩过：这条测试让「哈哈哈」和空串都判 True，却显示绿灯。
**这种「假通过」比没有测试更危险，因为它给人安全感。**

```python
# ✅ 对：按用户输入（真实变量）分支
def fake_llm(prompt):
    return "是" if "好累" in prompt else "否"
```

**② 别用固定 sleep 做断言**——机器一忙就假失败，要轮询等条件。

### 6.3 幂等性

同一个缓冲区跑两次 `reconstruct()`，第二次必须产出 0 条新增。
同理 `consolidate()` 靠 `digested` 标记保证不重复归纳
（否则同一批事件每晚会把一条印象顶成永久 trait）。

### 6.4 真实样本

原计划从线上事故摘固定用例（`SHOULD_NOT_REMEMBER`）。**实际未落地**——
第一代的数据全部未迁移（见 §7），所以没有线上样本可用。
现在的测试用例是手写的边界样本，覆盖格式变体而非真实事故。

---

## 7. 迁移策略（从第一代迁数据）

**建议：不迁移。** 实际执行：**未迁移**。

理由：第一代 46 条里 39 条是碎片，带过来只会污染新系统。
而且格式不同（没有 source 字段），强行转换等于造假来源。

如果一定要保留某些内容，**手工挑**（约 6~8 条：关系层 + 「四川胃」那条）。
这是**一次性人工操作**，不做自动化脚本（自动化会引入判断错误）。

---

## 8. 集成方式

本项目**独立**，不依赖任何现有系统。将来可以接。

### 方式 A：并行（推荐先做）

```
现有系统（不动）          Mnemosyne（新）
     │                        │
     └──── 同一份对话 ────────┘
```

好处：**原系统行为完全不变**，新系统只观察不干预。跑两周看它提炼得准不准。

### 方式 B：替换

等验证通过后，把原记忆层换成 Mnemosyne。**这一步要谨慎**——
旧系统虽有缺陷，但已在稳定运行。替换前必须保证新系统在「只观察」阶段明显更好。

**但边界要先定清楚**：Mnemosyne 只做记忆，不做性格/情绪状态。
替换时不能把人格系统或情绪系统也一起换掉。

---

## 9. 实施顺序（已全部完成）

按依赖关系排，实际执行顺序：

| # | 模块 | 状态 |
|---|---|---|
| 1 | `decay.py` — 纯函数，无依赖，能独立测试 | ✅ |
| 2 | `item.py` — 数据结构与校验 | ✅ |
| 3 | `store.py` — 读写 + 备份 | ✅ |
| 4 | `source.py` — 来源→置信度 | ✅ |
| 5 | `recall.py` — 召回与格式化（依赖 1、2） | ✅ |
| 6 | `reconstruct.py` — 核心（依赖 llm） | ✅ |
| 7 | `conflict.py` — 冲突检测 | ✅ |
| 8 | `verify.py` — 验证机制 | ✅ |
| 9 | `index.py` — 门面 | ✅ |
| 10 | `chat_demo.py` / `chat-loop.py` — 端到端示例 | ✅ |

**先写测试再写实现的模块**：`decay.py`（公式容易写错）、`recall.py`（格式化边界多）。
（实际是先写实现再补测试，但补测试时抓出了 5 个静默 bug，见设计定稿 §7.5b。）

---

## 10. 已知风险

| 风险 | 缓解 | 现状 |
|---|---|---|
| 模型输出格式乱写 → 解析不到 | 解析容错 6 种写法 + 无前缀就丢弃 | ✅ 已加固并测试 |
| 提炼出来的全是废话 | 提示词强制「没有新认识就输出无」 | ⚠️ 无真实样本回归验证 |
| 成本失控 | 提示词逼模型简短 | ⚠️ 未做成本测量（现在提示词里**没有**字数上限，原设计写的「≤40 字 × ≤5 条」实际未实现） |
| 猜测被当真 | 事实/猜测分区注入，物理隔离 + 置信度按来源 | ✅ |
| 与现有系统语义冲突 | 完全独立项目，可选并行观察 | ✅ |
| **静默失败**（最危险） | 所有「模型输出→解析」接缝都加容错 + 测试 | ✅ 2026-11-03 集中修 |
| 验证机制自然触发率低 | 放宽触发条件 | ⚠️ 待真实对话打磨 |
