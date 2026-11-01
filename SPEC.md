# 技术规格 · SPEC

> 配套 `DESIGN.md`。这里写「长什么样」，不写「为什么这样」。
> 状态：设计稿，**未实施**。

---

## 1. 数据模型

### 1.1 核心条目 `Item`

```js
{
  id: 'lq8f3a-2b7c',            // 时间戳36进制 + 随机
  layer: 'episode',             // episode | relationship | self
  text: '他胃疼那天我说了难听的，他回"你一点都不关心我"',
                                // 一句话能读懂，≤200 字
  source: 'user-said',          // user-said | her-inference | observed | third-party
  confidence: 0.95,             // 0~1
  evidence: ['原文片段1', '原文片段2'],   // 最多 3 条，可追溯
  subject: 'user:884293334',    // 关于谁（群聊时必须精确）
  tags: ['冲突', '健康', '敏感'],        // 召回用
  emotion: {                    // 立项时的情绪快照
    valence: -0.6,
    arousal: 0.7,
    label: '难过',
  },
  baseWeight: 1.5,              // 初始权重，由情绪强度决定
  hits: 0,                      // 被召回/被提及次数
  createdAt: 1792816155000,
  lastSeenAt: 1792816155000,
  supersededBy: null,           // 被哪条推翻（保留可追溯）
  pinned: false,                // 永不淘汰（对应第一代的"钉子"）
}
```

### 1.2 存储布局

```
data/
├── items.json            # 所有条目（单文件，便于备份）
├── sessions.json         # 会话 → 状态映射
└── audit/
    └── 2026-10-24.jsonl  # 每次变更的审计日志（谁在什么时候改了什么）
```

**单文件理由**：条目数是 10~15 条量级，不是几万条。单文件便于人工检查、备份、回滚。等真超过 500 条再考虑分片。

**必须无 BOM 写入**：
```js
fs.writeFileSync(p, JSON.stringify(obj, null, 2), 'utf8');
// 不要用 PowerShell 的 Set-Content -Encoding utf8（会带 BOM）
```

---

## 2. 模块划分

```
cognition-memory/
├── DESIGN.md              本项目的设计说明
├── SPEC.md                ← 本文档
├── README.md              快速开始
├── package.json
├── src/
│   ├── item.mjs           条目结构、校验、序列化
│   ├── decay.mjs          权重公式、衰减、晋升判定
│   ├── store.mjs          读写、备份、审计
│   ├── reconstruct.mjs    ★ 核心：事后重构（调用模型）
│   ├── recall.mjs         召回与注入格式化
│   ├── source.mjs         来源判定与置信度管理
│   └── index.mjs          对外统一入口
├── test/
│   ├── decay.test.mjs
│   ├── recall.test.mjs
│   └── fixtures/          真实样本（从线上事故里摘的）
└── examples/
    └── chat-loop.mjs      最小可跑的对话循环示例
```

**依赖原则**：零第三方依赖，只用 Node 内置。要调模型就通过注入的 adapter 函数，不绑定任何供应商。

---

## 3. 核心接口

### 3.1 对外门面 `index.mjs`

```js
export class Cognition {
  /**
   * @param {object} opts
   * @param {string} opts.dataDir            数据目录
   * @param {Function} opts.llm              async (prompt, opts) => string
   * @param {object} opts.config             见 §4
   */
  constructor(opts)

  /** 记一条原始对话（不立即提炼，只进缓冲区） */
  ingest({ speaker, text, at })

  /** 触发重构：把缓冲区里的对话提炼成认识。返回新增/修改的条目 */
  async reconstruct({ force = false } = {})

  /** 召回：给当前的对话上下文挑最相关的记忆，返回格式化好的文本块 */
  async recall({ subject, queryText, limit = 8 })

  /** 情绪事件：给相关条目加权 */
  touch({ subject, tags, emotion })

  /** 维护：衰减、淘汰、晋升 */
  maintain()

  /** 导出/导入（备份用） */
  export()
  import(data)
}
```

### 3.2 重构接口（最关键）

```js
// src/reconstruct.mjs
export const RECONSTRUCT_PROMPT = `
（下面是你们最近的一段对话。不要复述，只回答一个问题：

  这段里，你对「他是什么样的人」或者「你们之间是什么关系」，
  **有没有产生新的认识**？

规则：
1. 没有新认识就输出「无」。宁可输出「无」，也不要把对话内容抄一遍。
2. 每条必须写清楚：这是**他说的**，还是**你猜的**。
   - 他说过 → 标 [事实]
   - 你推的 → 标 [猜测]
3. 一条一行，最多 5 条，每条不超过 40 字。
4. 不写"他喜欢这样""明知我"这种揣测；不确定就别写。
5. 同一个意思不要换几种说法重复。

输出格式（严格）：
[事实] 他是四川人，能吃辣
[猜测] 他可能不太喜欢被叫"大肥鱼"
或者：
无
`
```

**解析规则**：
- `[事实]` → `source: 'user-said'`, `confidence: 0.9`
- `[猜测]` → `source: 'her-inference'`, `confidence: 0.4`
- 没有前缀的行 → 丢弃（防止模型乱写）
- 输出「无」→ 什么都不做

**为什么强制前缀**：这比事后用规则猜来源可靠得多。模型自己知道它是在引用还是在推演。

### 3.3 召回接口

```js
// src/recall.mjs
export function buildRecallBlock(items, { subject }) {
  const facts = items.filter(i =>
    i.source === 'user-said' && i.confidence >= 0.8 && !i.supersededBy);
  const guesses = items.filter(i =>
    i.source === 'her-inference' && !i.supersededBy);

  const parts = [];
  if (facts.length) {
    parts.push(`（关于他的事实（他说过的，可以当真）：\n${
      facts.map(i => `- ${i.text}`).join('\n')}`);
  }
  if (guesses.length) {
    parts.push(`（你的猜测（**不是他说的**，别当事实讲，可以说"我猜"）：\n${
      guesses.map(i => `- ${i.text}`).join('\n')}`);
  }
  return parts.length ? `（${parts.join('\n\n')}\n\n用法：聊到相关再说，别主动复述。）` : '';
}
```

**关键**：事实区和猜测区**分开展示**，并给出不同的使用指令。第一代的问题就是所有条目混在一起，模型分不清真假。

---

## 4. 配置项

```js
export const DEFAULT_CONFIG = {
  // 重构
  reconstruct: {
    everyNTurns: 20,          // 每 20 轮触发一次
    maxItemsPerRun: 5,        // 单次最多产出 5 条
    model: 'same',            // 'same' = 用主模型；或传小模型 id
  },

  // 衰减
  decay: {
    episodeHalfLifeDays: 14,      // 情节记忆：两周减半
    relationshipHalfLifeDays: 90, // 关系模型：三个月减半
    selfHalfLifeDays: null,       // 自我叙事：永不衰减
    forgetBelow: 0.12,
    hitBoost: 0.5,                // 每次提及权重 +50%
  },

  // 晋升
  promote: {
    episodeToRelationship: {
      minOccurrences: 3,      // 同类出现 3 次
      minEmotionIntensity: 0.8, // 或单次强情绪
    },
  },

  // 召回
  recall: {
    limit: 8,
    minWeight: 0.12,
    alwaysIncludePinned: true,
  },

  // 上限
  limits: {
    maxItems: 200,
    maxEpisodes: 120,
    maxRelationship: 40,
  },
};
```

---

## 5. 生命周期

```
对话进来
   │
   ├─→ ingest() 进缓冲区（不判断，不做任何过滤）
   │
   ├─→ 每 20 轮 ──→ reconstruct()
   │                    │
   │                    ├─ 调模型回看这段
   │                    ├─ 解析 [事实]/[猜测]
   │                    ├─ 去重（字符重合 + 同类上限）
   │                    └─ 写入 items.json + 审计日志
   │
   ├─→ 每天的 maintain()
   │        ├─ 重算所有条目权重
   │        ├─ weight < forgetBelow → 淘汰（pinned 除外）
   │        └─ 满足条件 → 晋升到下一层
   │
   └─→ 每轮 recall()
            ├─ 按 subject 过滤（群聊必须精确到人）
            ├─ 按 weight 排序
            ├─ 事实区 / 猜测区分开
            └─ 返回注入文本
```

---

## 6. 测试策略

### 6.1 必须有真实样本

从线上事故摘出来当固定用例，这些是花成本换来的：

```js
// test/fixtures/real-cases.mjs
export const SHOULD_NOT_REMEMBER = [
  // 用户的问句，不是关于他的事实
  '我什么时候变成广东胃了',
  '你能做出这样的图片吗',
  '你QQ名字要不要换啊',
  '吃午饭了没呀 小鲸鲸',
  // 使唤
  '把你的语言系统调一下',
  // 她自己的话被当素材
  '（她自己说的）别一进场就送',
];

export const SHOULD_REMEMBER = [
  { text: '我是四川胃好吧 他们家我天天吃 还点的特辣', expect: 'fact' },
  { text: '刚刚还去跑了个校园跑', expect: 'fact' },
  { text: '我叫南风', expect: 'fact' },
];
```

### 6.2 禁止的测试写法

```js
// ❌ 错：固定等待，机器一忙就假失败
await new Promise(r => setTimeout(r, 3000));
assert(reply);

// ✅ 对：轮询等条件
await waitFor(() => log.includes('[reply]'), 20000);
```

### 6.3 幂等性

同一个缓冲区跑两次 `reconstruct()`，第二个必须产出 0 条新增。

---

## 7. 迁移策略（从第一代迁数据）

**建议：不迁移。**

理由：第一代 46 条里 39 条是碎片，带过来只会污染新系统。而且格式不同（没有 source 字段），强行转换等于造假来源。

如果一定要保留某些内容，**手工挑**：

```
可以手工迁移的（约 6~8 条）：
- 关系层 8 条（本身质量就高）
- 记忆层里 important 那 1 条（四川胃）

其余全部丢弃，从零开始积累。
```

这是**一次性人工操作**，不做自动化脚本（自动化会引入判断错误）。

---

## 8. 两种集成方式

这个项目**独立于 QQ 桥接**，但将来可以接：

### 方式 A：并行（推荐先做）

```
QQ 桥接（不动）          cognition-memory（新）
     │                        │
     └──── 同一份对话 ────────┘
              （桥接把对话同时喂给两边）
```

好处：**她的行为完全不变**，新系统只观察不干预。跑两周看它提炼得准不准。

### 方式 B：替换

等验证通过后，把桥接的 `memory`/`bond` 换成新系统。

**但这一步要谨慎**——第一代虽有缺陷，但已经在稳定运行。替换前必须保证新系统在「只观察」阶段的表现明显更好。

---

## 9. 实施顺序（等你要做的时候）

按依赖关系排：

1. **`decay.mjs`** — 纯函数，无依赖，能独立测试。先做这个。
2. **`item.mjs`** — 数据结构与校验。
3. **`store.mjs`** — 读写 + 备份 + 审计。
4. **`recall.mjs`** — 召回与格式化（依赖 1、2）。
5. **`source.mjs`** — 来源判定规则。
6. **`reconstruct.mjs`** — 核心，需要 llm adapter（依赖 2、3、5）。
7. **`index.mjs`** — 门面。
8. **`examples/chat-loop.mjs`** — 端到端示例。

**先写测试再写实现**的模块：`decay.mjs`（公式容易写错）、`recall.mjs`（格式化边界多）。

---

## 10. 已知风险

| 风险 | 缓解 |
|---|---|
| 重构时模型不听话，格式乱写 | 解析严格，不符合格式直接丢弃；有审计日志可查 |
| 提炼出来的全是废话 | 用 `SHOULD_NOT_REMEMBER` 那批真实样本做回归 |
| 成本失控 | `everyNTurns` 可调；重构用 `[事实]/[猜测]` 逼模型简短 |
| 猜测被当真 | 事实/猜测分区注入，物理隔离 |
| 与现有系统语义冲突 | 阶段一完全并行，不干预 |
