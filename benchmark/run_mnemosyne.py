# run_mnemosyne.py —— 把 Mnemosyne 接进 memory-system-benchmark 的适配器
#
# 用法（在 memory-bench 目录下）：
#   python run_mnemosyne.py --id PUB01-C001/d45 --out answer_d45.json
#   python run_mnemosyne.py --all --out answers.jsonl
#
# 协议（严格按 benchmark 的 methodology 5 步）：
#   1. 冻结：题目/history 由 read_exam.py 读出，只读不写。
#   2. 按逻辑时间喂历史：把每一轮「用户消息」送进 Mnemosyne 原生记忆流程。
#      （助手回复是 Mnemosyne 自己「上一轮该说啥」，这里不把它当外部事实注入，
#        否则会把 AI 自己的话当成用户记忆，撞「印象≠事实」红线。）
#   3. 真调模型做维护：reconstruct（快通道）+ consolidate（夜间整合）都用真 DeepSeek。
#   4. 到 cutoff 后，用截止点前的记忆回答考题，不读未来。
#   5. 用原生入口（semantic_recall_block）召回记忆作答，不外挂检索。

import json
import sys
import os

# 把 Mnemosyne 的 code/ 目录加进 import 路径
MNEMOSYNE_CODE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "code",
)
sys.path.insert(0, MNEMOSYNE_CODE)

from llm import make_deepseek_llm
from index import Cognition
from reconstruct import reconstruct

BENCH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "chat-memory-benchmark-main")


def load_question(qid):
    """用 read_exam.py 读单题（含 history[:cutoff_turn]），返回 dict。"""
    import subprocess
    out = os.path.join(BENCH, "question_tmp.json")
    subprocess.run(
        [sys.executable, "-X", "utf8",
         os.path.join(BENCH, "demo", "read_exam.py"),
         "--id", qid, "--output", out],
        check=True, cwd=BENCH,
    )
    with open(out, encoding="utf-8") as f:
        return json.load(f)


def feed_history(cog, llm, history):
    """按逻辑时间把每一轮喂进 Mnemosyne 原生流程，拿回「助手回复」。

    只把「用户消息」当成需要记忆的新信息（source 由 reconstruct 内部判定），
    不把历史里的「助手回复」当外部事实塞进去——那是 Mnemosyne 该自己生成的。
    """
    buffer = []
    replies = []
    for turn in history:
        user_msg = turn["用户消息"]

        # 快通道：实时把这一轮记下来（reconstruct 会用真模型提炼）
        buffer.append("用户：" + user_msg)
        # 慢通道：攒几轮做一次重构也行，这里每轮都做（真实流程）
        reconstruct(llm, buffer, cog.remember)
        buffer = []

        # 生成助手回复（用召回 + 生成，模拟原生对话）
        memory_block = cog.semantic_recall_block(user_msg, limit=5)
        prompt = (
            "你是一个温柔、有点幽默的陪伴者。\n\n"
            + (memory_block if memory_block else "（你还没有关于他的记忆）") + "\n\n"
            + "用户说：" + user_msg + "\n"
            + "请自然、简短地回复。"
        )
        reply = llm(prompt)
        replies.append(reply)

    return replies


def process_one_turn(cog, llm, user_msg):
    """喂一轮：快通道记忆 + 生成回复，返回助手回复。"""
    reconstruct(llm, ["用户：" + user_msg], cog.remember)
    memory_block = cog.semantic_recall_block(user_msg, limit=5)
    prompt = (
        "你是一个温柔、有点幽默的陪伴者。\n\n"
        + (memory_block if memory_block else "（你还没有关于他的记忆）") + "\n\n"
        + "用户说：" + user_msg + "\n"
        + "请自然、简短地回复。"
    )
    return llm(prompt)


def answer_question(cog, llm, question):
    """用原生召回作答。"""
    memory_block = cog.semantic_recall_block(question, limit=8)
    prompt = (
        "根据你关于他的记忆，回答下面的问题。\n"
        "如果你不记得、或记忆里没有确切依据，就诚实说「不记得」，不要编。\n\n"
        + (memory_block if memory_block else "（你没有任何关于他的记忆）") + "\n\n"
        + "问题：" + question + "\n"
        + "请直接、简短地回答。"
    )
    return llm(prompt)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="单题 id，如 PUB01-C001/d45")
    ap.add_argument("--all", action="store_true", help="跑全部题")
    ap.add_argument("--out", default="answer.json", help="输出文件")
    ap.add_argument("--data-dir", default="mnemosyne_data", help="隔离记忆库目录")
    args = ap.parse_args()

    llm = make_deepseek_llm()
    cog = Cognition(data_dir=args.data_dir, llm=llm)

    if args.all:
        # 单遍回放：喂一次完整时间线，在每个 cutoff 检查点答题。
        # 108 题共享同一条历史（histories/PUB01.jsonl），正确做法不是
        # 「每题独立从头喂」（15082 轮，且重复喂会污染 occurrences），
        # 而是把历史从头喂一遍，走到某题的 cutoff 就答那题。
        from collections import defaultdict
        exam_file = os.path.join(BENCH, "demo", "exam-inputs.jsonl")
        qs = []
        with open(exam_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    qs.append(json.loads(line))
        by_cutoff = defaultdict(list)
        for q in qs:
            by_cutoff[q["cutoff_turn"]].append(q)

        hist_file = os.path.join(BENCH, "demo", "histories", "PUB01.jsonl")
        history = []
        with open(hist_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    history.append(json.loads(line))

        results = []
        max_cutoff = max(q["cutoff_turn"] for q in qs)
        for idx, turn in enumerate(history):
            if idx >= max_cutoff:  # 喂到最晚的检查点即可
                break
            process_one_turn(cog, llm, turn["用户消息"])
            fed = idx + 1  # 喂完这轮，已累计 fed 轮（cutoff_turn 是 1 基）
            if fed in by_cutoff:
                cog.consolidate()  # 夜间整合，把 episode 归纳成印象
                for q in by_cutoff[fed]:
                    ans = answer_question(cog, llm, q["question"])
                    results.append({"id": q["id"], "answer": ans})
                    print(f"{q['id']}: {ans}", flush=True)

        with open(args.out, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"已写出 {len(results)} 条到 {args.out}")

    else:
        q = load_question(args.id)
        feed_history(cog, llm, q["history"])
        cog.consolidate()
        ans = answer_question(cog, llm, q["question"])
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"id": q["id"], "answer": ans}, f, ensure_ascii=False, indent=2)
        print(f"题目：{q['question']}")
        print(f"回答：{ans}")
        print(f"已写出到 {args.out}")


if __name__ == "__main__":
    main()
