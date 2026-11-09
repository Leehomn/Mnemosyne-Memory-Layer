"""小样本验证：只跑「漏记重灾区」的题（时间题/相对日期/称呼条件），几分钟出信号。

思路：从 714 题里挑 content_tags 命中这三类的题，对每个人物只喂到这些题所需的最大 cutoff，
然后答题，对比新提示词下这几类是否从「不记得」变成「记得」。

用法（memory-bench 目录）：
  python -X utf8 run_sample.py
"""
import json, sys, os
from collections import defaultdict

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "code",
))
from llm import make_deepseek_llm
from index import Cognition
from reconstruct import reconstruct

BENCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat-memory-benchmark-main")
FORMAL = os.path.join(BENCH, "datasets", "natural-timegrid-20261101-v2")

TARGET_TAGS = {"时间题", "相对日期", "称呼条件"}

llm = make_deepseek_llm()

# 读 answer-key 拿 content_tags
keys = {}
for l in open(os.path.join(FORMAL, "review-only", "answer-key.jsonl"), encoding="utf-8"):
    l = l.strip()
    if l:
        d = json.loads(l)
        keys[d["id"]] = d

# 读 exam-inputs
exams = {}
for l in open(os.path.join(FORMAL, "exam-inputs.jsonl"), encoding="utf-8"):
    l = l.strip()
    if l:
        d = json.loads(l)
        exams[d["id"]] = d

# 挑目标题（命中 TARGET_TAGS 任一）
picked = [qid for qid, k in keys.items()
          if any(t in TARGET_TAGS for t in k.get("content_tags", []))]
print(f"目标题数：{len(picked)}")
print(f"涉及人物：{sorted(set(exams[q]['persona'] for q in picked))}")

# 按人物分组，算每人需要的最大 cutoff
by_persona = defaultdict(list)
for qid in picked:
    e = exams[qid]
    by_persona[e["persona"]].append((e["cutoff_turn"], qid))

for persona, items in sorted(by_persona.items()):
    max_cutoff = max(c for c, _ in items)
    # 读历史
    hist_file = os.path.join(FORMAL, exams[items[0][1]]["history_file"])
    history = [json.loads(l) for l in open(hist_file, encoding="utf-8") if l.strip()]
    # 独立记忆库（临时，跑完删）
    data_dir = os.path.join("mnemosyne_sample", persona)
    cog = Cognition(data_dir=data_dir, llm=llm)
    # 按 cutoff 排序，边喂边答
    qs_at_cutoff = defaultdict(list)
    for c, qid in items:
        qs_at_cutoff[c].append(qid)
    for idx in range(max_cutoff):
        turn = history[idx]
        reconstruct(llm, ["用户：" + turn["用户消息"]], cog.remember)
        fed = idx + 1
        if fed in qs_at_cutoff:
            cog.consolidate()
            for qid in qs_at_cutoff[fed]:
                q = exams[qid]
                mem = cog.semantic_recall_block(q["question"], limit=8)
                prompt = (
                    "根据你关于他的记忆，回答下面的问题。\n"
                    "不记得就诚实说「不记得」，不要编。\n\n"
                    + (mem if mem else "（无记忆）") + "\n\n"
                    + "问题：" + q["question"] + "\n直接简短回答。"
                )
                ans = llm(prompt)
                tags = "、".join(t for t in keys[qid].get("content_tags", []) if t in TARGET_TAGS)
                print(f"[{tags}] {qid}: {ans[:50]}", flush=True)
    print(f"=== {persona} 完成（喂 {max_cutoff} 轮）===", flush=True)

print("小样本跑完。")
