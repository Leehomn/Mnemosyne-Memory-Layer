# 第一代实现参考（qq-bridge 的记忆系统）

> 本文档是**只读参考**，从 `qq-bridge/` 里提炼出来的。
> 目的是让新项目知道：有哪些坑已经踩过、哪些设计验证有效。
> **不改动 qq-bridge 任何文件。**

---

## 1. 四个模块的职责

| 模块 | 文件 | 职责 | 规模 |
|---|---|---|---|
| 记忆分层 | `memory.mjs` | 三层分级 + 艾宾浩斯衰减 | 15.8 KB |
| 关系层 | `bond.mjs` | 梗/称呼/雷点/默契 | 11.2 KB |
| 情绪 | `mood.mjs` | 心情 + 好感度 | 7.4 KB |
| 承诺 | `promises.mjs` | 答应过的事到点提醒 | 4.1 KB |

**共同设计原则**：纯函数 + 一个小 JSON 文件 + 不碰网络。这个原则值得新项目继承。

---

## 2. memory.mjs —— 什么值得继承，什么要改

### 继承：三层分级

```js
export const TIERS = {
  IMPORTANT: 'important',  // 永不删
  NORMAL: 'normal',        // 两三周淡忘
  TRIVIA: 'trivia',        // 几天就忘
};
```

分层的思路是对的。新项目改为 **episode / relationship / self**，语义更清晰。

### 继承：衰减公式

```js
export function decayedWeight(item, now = Date.now()) {
  const half = item.tier === TIERS.IMPORTANT
    ? Infinity
    : (item.tier === TIERS.TRIVIA ? DECAY.trivia : DECAY.normal);
  // weight = 0.5 ^ (age / half) × (1 + hits × 0.5)
}
```

**「越久没提权重越低 + 提过就加固」这个思路验证有效**，新项目保留。

### 继承：可配置衰减

```js
export function configureDecay({ normalHalfLifeDays, triviaHalfLifeDays, forgetBelow }) {
  // 非法值忽略并保留原值
}
```

不用改代码就能调参数——这个设计直接搬。

### ⚠️ 要改：`classify()` 逐句判定

**这是第一代最大的问题**。下面是它现在长什么样（约 100 行）：

```js
export function classify(text) {
  // ① 问单词/翻译/语法 → trivia
  if (/(是什么意思|啥意思|怎么读|...)/.test(t)) return { tier: TRIVIA, reason: 'query' };
  // ①b 「我是说/我是问」是解释不是身份
  if (/我是(说|问|想|觉得|...)/.test(t)) return { tier: TRIVIA, reason: 'self-explain' };
  // ② 「我叫X」才算名字
  if (/^我叫[\u4e00-\u9fa5]{1,4}$/.test(t)) return { tier: IMPORTANT, reason: 'name' };
  // ...
  // ⑦ 疑问句
  if (/[\?？]\s*$/.test(t)) return { tier: TRIVIA, reason: 'question' };
  // ⑧ 剩下的
  if (len >= 8) return { tier: NORMAL, reason: 'daily' };
}
```

**它每修一次就加一条正则**，从 8 条涨到 20 多条。下面是这条路的完整事故史：

| 日期 | 事故 | 加的正则 |
|---|---|---|
| 10-22 | 「我是说让你别乱动」被当成身份 | `我是(说\|问\|想\|...)` |
| 10-22 | 「就叫就叫」被当成名字 | 去掉可选前缀 |
| 10-23 | 「我家小鲸鲸这么可爱」被当成家庭信息 | `我家` 后必须跟 在/住/有/养 |
| 10-23 | 「我记得/是唤醒词吧」被当成承诺 | `记得` 后必须跟动作 |
| 10-24 | 中文问句不带问号全部漏网 | `(吗\|嘛\|呢\|么)$` + 疑问代词 + 第二人称 + 使唤句 |

**结论**：单句信息量不足，这条路没有终点。新项目改为**事后重构**。

### ⚠️ 要改：`brief()` 的注入顺序

```js
brief(limit = 8, now = Date.now()) {
  const list = this.recall(limit, now);
  return list.map(i => `- ${i.text}${i.tier === IMPORTANT ? '（记牢）' : ''}`).join('\n');
}
```

问题：**所有条目平等排列，只靠一个「（记牢）」后缀区分**。实测 46 条里 39 条是碎片，真正有用的几条被淹没。

新项目改为**事实区/猜测区物理隔离**。

---

## 3. bond.mjs —— 质量最高，值得整体借鉴

关系层是第一代里**信息密度最高**的部分。8 条里每条都能拼出一个人。

### 继承：分类标签

```js
export function classifyBond(text) {
  if (/(管我叫|叫过|喊我|外号|昵称|起劲)/.test(t)) return 'nickname';
  if (/(雷点|禁区|不爱听|别提|忌讳|会伤心)/.test(t)) return 'landmine';
  if (/(互怼|曲解|损他|损我|玩梗|接不误)/.test(t)) return 'meme';
  if (/(口头禅|爱用|爱发|习惯|经常|天天|总是)/.test(t)) return 'habit';
  if (/(一起|那次|上次|昨天|前天|上周|发到)/.test(t)) return 'event';
  return 'general';
}
```

**注意**：这里的 `classify` 判的是**条目属于什么类别**，不是「值不值得记」。
**判断价值 vs 判断类别，是两件不同的事**。第一代在 bond 里做对了，在 memory 里做错了。

### 继承：钉子（pinned）机制

```js
export function isBondPinned(item) {
  return item?.kind === 'nickname' || item?.kind === 'landmine';
}
```

称呼和雷点**永不淘汰、永远排在最前**。理由：

> 丢了会导致她叫错称呼、说话踩雷。

**这个约束非常关键**，新项目保留，并扩展到 L3（自我叙事也永不淘汰）。

### 继承：同类上限

```js
const MAX_PER_KIND = { nickname: 2, landmine: 3, meme: 3, habit: 3, event: 3 };
```

2026-10-24 加。起因：夜间提炼两次写出同一条的两种说法。

```
「小鲸鲸这个称呼他越叫越起劲，还爱连发猫图」
「他管我叫「小鲸鲸/小鲸鱼」，还叫过「大肥鱼」」
```

去重规则只挡「前缀互相包含」，挡不住**换个说法再说一遍**。结果 6 条注入预算里 2 条在说同一件事。

新项目需要：
- 字符重合度去重（Jaccard ≥ 0.5）
- **同类上限**（兜底）

### 继承：语义重复判断

```js
function looksSameTopic(a, b) {
  // 都提到同一个称呼 → 同一条
  const names = ['小鲸鲸', '小鲸鱼', '大肥鱼', ...];
  // 或字符重合度 ≥ 0.5
}
```

---

## 4. mood.mjs —— 思路对，但没和记忆打通

### 继承：心情与好感分开

```js
export const MOOD_STATES = {
  calm:     { label: '平静', valence: 0.1,  arousal: 0.2 },
  happy:    { label: '开心', valence: 0.7,  arousal: 0.5 },
  annoyed:  { label: '有点烦', valence: -0.5, arousal: 0.55 },
  tsundere: { label: '嘴硬', valence: 0.2,  arousal: 0.45 },
  // ...
};
```

分成 valence（正负）和 arousal（激动程度）两个维度——比单一情绪标签信息量大。

### 继承：好感有「递减」和「每日额度」

```js
smallTalkGain(affection) {
  // 越熟越难涨：0.03 × (1 - affection/10)
}

budgetFor(rawGain) {
  // 日常闲聊每天最多 +0.3
  // 有事件的不受限
}
```

**为什么需要**：第一代原本每轮固定 +0.03，235 轮就把 5 分刷到 9.34，100 轮就「很亲」了，后面全是无效信息。

### ⚠️ 要改：情绪和记忆完全没关联

现在：
- `mood.observe()` 只看用户消息推断情绪
- `memory.remember()` 完全不看情绪

**新项目要做的是：情绪强度参与记忆权重计算**（见 DESIGN.md 决策 3）。

### ⚠️ 要修：好感撞顶后失去信息量

```
线上实测：affection = 10.0（满值），事件加成无递减
「被夸 +0.25」不受每日额度限制，一天从 9.34 顶到 10
```

修法：`observe()` 里事件加成也要乘 `headroom = (10 - affection) / 10`。

---

## 5. promises.mjs —— 小而完整，直接参考

```js
export function extractPromise(text) {
  // 「我明天给你查」这类，按时限排队
  // 立刻 2h / 今天 8h / 明天 24h / 下次 72h
}
```

**核心洞察**：承诺 = 带时间窗的情节。这正好对应新项目的 L1 episode。

已知坑：
```js
// ❌ 原来「记得」单字就触发，于是群友说的「我记得/是唤醒词吧」
//    被当成她的承诺
// ✅ 现在必须跟具体动作
if (/(记得|别忘了)/.test(t) && /(给|带|帮|发|告诉|回|提醒)/.test(t))
```

---

## 6. 血泪坑清单（新项目必须避开）

### 6.1 写 JSON 必须无 BOM

```powershell
# ❌ Windows PowerShell 5.1 的 Set-Content -Encoding utf8 会带 BOM
Set-Content -Path x.json -Value $json -Encoding UTF8
# → JSON.parse 直接抛错，readState 静默返回 {}，表现成"有会话却没人"

# ✅
[IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding($false)))
```

### 6.2 文件名不能有冒号

```js
// ❌ 'user:884293334'.json → Windows 当成盘符，创建失败
// ✅
const safeKey = (key) => String(key).replace(/[^\w.-]/g, '_');
```

### 6.3 测试别用固定 setTimeout

```js
// ❌ 机器一忙就等不够，随机假失败
await new Promise(r => setTimeout(r, 3000));

// ✅ 轮询等条件
async function waitFor(fn, timeout = 20000, step = 200) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    if (await fn()) return true;
    await new Promise(r => setTimeout(r, step));
  }
  return false;
}
```

### 6.4 中文口语问句大多不带问号

```
「我什么时候变成广东胃了」  ← 没有问号，但这是问句
「你能做出这样的图片吗」    ← 靠「吗」
「你QQ名字要不要换啊」      ← 靠疑问代词
「吃午饭了没呀」            ← 靠「了没」
```

只认 `/[?？]$/` 会漏掉 80%。

### 6.5 「我」开头 ≠ 关于我的事实

```
「我什么时候变成广东胃了」  ← 是反问，不是陈述
「我以为你今天不来了」      ← 是假设
```

### 6.6 群聊不能默认主语是「他」

真实事故（2026-10-22）：

```
群友 芝士不列颠车窗：你能教我玩李白吗
她：能啊 但你先学会攒剑气 别一进场就送
↓ 夜间提炼后
记忆：「他玩王者荣耀，想学李白，容易一进场就送」
                                ↑ 这其实是她说的话，被安到对话对象头上
```

修法：群聊保留真实昵称，她的回复明确标注「你自己说的话，不是事实来源」。

### 6.7 改结构性东西前必须能回滚

第一代的做法：`<文件名>.bak-<原因>-<时间戳>`

实际用过很多次，每次都没后悔。新项目从一开始就要有。

### 6.8 时间必须用本地日期

```js
// ❌ now.toISOString().slice(0, 10)  → 东八区凌晨会算成前一天
// ✅
function localDayStr(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
```

第一代踩过：夜间整理因为 UTC 日期永远判定"今天已跑过"，一次都没执行成功。

---

## 7. 第一代的实测数据（做新项目时的基线）

```
记忆层 46 条
  关于对方的陈述   6 条（13%）   ← 有用
  他逗她的         1 条
  其他            39 条（85%）   ← 碎片

关系层 8 条（信息密度远高于记忆层）

上下文用量 85,050 / 600,000（14%）

token 成本：每轮约 500（缓存命中后），冷启动一次性约 6 万
```

**新项目的目标**：记忆条目 10~15 条，信息密度 ≥ 关系层水平。
