# run_formal.py —— 跑正式集（6 人物 714 题）的适配器
#
# 用法（在 memory-bench 目录下）：
#   python run_formal.py --out formal_answers.jsonl
#
# 与 demo 的区别：
#   - 正式集有 6 个人物（P01/P12/P14/P16/P17/P20），各自独立历史。
#   - 必须「按人物隔离记忆库」：6 个人是 6 个不同的人，混在一起会撞「认错人」考点。
#   - 每个人物单遍回放自己的历史，在各 cutoff 检查点 consolidate + 答题。

import json
import sys
import os
from collections import defaultdict

MNEMOSYNE_CODE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "code",
)
sys.path.insert(0, MNEMOSYNE_CODE)

from llm import make_deepseek_llm
from index import Cognition
from reconstruct import reconstruct
from embed import make_embedder_from_config

BENCH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "chat-memory-benchmark-main")
FORMAL_DIR = os.path.join(BENCH, "datasets", "natural-timegrid-20261101-v2")


def process_one_turn(cog, llm, user_msg, now=None, no_reply=False, assistant_reply=None):
    """喂一轮：快通道记忆 + （可选）生成回复。

    no_reply=True 时只提炼记忆、不生成回复——跑基准时中间回复没人看，
    省掉这次模型调用，喂历史成本约降 1/3，判分零影响。

    assistant_reply：这一轮 AI 自己的回复（历史里现成的）。
    喂给 reconstruct，让它把「AI 自己说过、用户可能回头问的话」也记进库
    （考点「助手自己说过的话」——AI 承诺/建议/自述，被问到时能答出来）。
    """
    buffer = ["用户：" + user_msg]
    if assistant_reply:
        buffer.append("助手：" + assistant_reply)
    reconstruct(llm, buffer, cog.remember, now=now)
    if no_reply:
        return ""
    memory_block = cog.semantic_recall_block(user_msg, limit=5)
    prompt = (
        "你是一个温柔、有点幽默的陪伴者。\n\n"
        + (memory_block if memory_block else "（你还没有关于他的记忆）") + "\n\n"
        + "用户说：" + user_msg + "\n"
        + "请自然、简短地回复。"
    )
    return llm(prompt)


def answer_question(cog, llm, question, now=None):
    """用原生召回作答。now=问问题时的虚拟日期（跑基准时从题目的 now 字段传进来），
    让语义召回能听懂「前天/上周」这类相对时间词，换算成绝对日期去匹配记忆。"""
    memory_block = cog.semantic_recall_block(question, limit=8, now=now)
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
    ap.add_argument("--out", default="formal_answers.jsonl", help="输出文件")
    ap.add_argument("--data-root", default="mnemosyne_formal", help="隔离记忆库根目录")
    ap.add_argument("--persona", default=None,
                    help="只跑指定人物，如 P14；省略=全部")
    ap.add_argument("--no-reply", action="store_true",
                    help="喂历史时跳过生成回复（省约1/3模型调用，判分零影响）")
    args = ap.parse_args()

    llm = make_deepseek_llm()
    embedder = make_embedder_from_config()

    # 启动时读已有结果做跳过集（断点续跑：已答过的题不再重答）
    done = set()
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    done.add(json.loads(line)["id"])

    # 读正式集 714 题
    exam_file = os.path.join(FORMAL_DIR, "exam-inputs.jsonl")
    qs = []
    with open(exam_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                qs.append(json.loads(line))

    # 按人物分组
    by_persona = defaultdict(list)
    for q in qs:
        by_persona[q["persona"]].append(q)

    personas = sorted(by_persona.keys())
    if args.persona:
        personas = [p for p in personas if p == args.persona]
        if not personas:
            print(f"未找到人物 {args.persona}，可用：{sorted(by_persona.keys())}")
            return

    for persona in personas:
        qs_p = by_persona[persona]
        # 整段跳过已完成人物：这个人的题全答完了，就一个人字的历史都不再喂，
        # 直接 continue，避免续跑时白白重喂历史、白花 token。
        if all(q["id"] in done for q in qs_p):
            print(f"=== {persona} 已全部完成，整段跳过 ===", flush=True)
            continue
        # 每个人物独立记忆库（防认错人）
        data_dir = os.path.join(args.data_root, persona)
        cog = Cognition(data_dir=data_dir, llm=llm, embedder=embedder)

        # 按 cutoff_turn 分组
        by_cutoff = defaultdict(list)
        for q in qs_p:
            by_cutoff[q["cutoff_turn"]].append(q)

        # 读该人物的历史
        hist_file = os.path.join(FORMAL_DIR, qs_p[0]["history_file"])
        history = []
        with open(hist_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    history.append(json.loads(line))

        max_cutoff = max(q["cutoff_turn"] for q in qs_p)
        for idx, turn in enumerate(history):
            if idx >= max_cutoff:
                break
            # 把「逻辑时间」里的日期传给 reconstruct，让模型能把相对时间换算成绝对日期
            now = turn.get("逻辑时间", "").split("T")[0] if turn.get("逻辑时间") else None
            process_one_turn(cog, llm, turn["用户消息"], now=now, no_reply=args.no_reply,
                             assistant_reply=turn.get("助手回复"))
            fed = idx + 1
            if fed in by_cutoff:
                cog.consolidate()
                for q in by_cutoff[fed]:
                    if q["id"] in done:
                        print(f"{q['id']}: 已答过，跳过", flush=True)
                        continue
                    ans = answer_question(cog, llm, q["question"],
                                          now=q["now"].split("T")[0] if q.get("now") else None)
                    # 每答一题立即追加落盘（断点续跑：中途崩也不丢已答答案）
                    with open(args.out, "a", encoding="utf-8") as fo:
                        fo.write(json.dumps({"id": q["id"], "answer": ans},
                                            ensure_ascii=False) + "\n")
                    done.add(q["id"])
                    print(f"{q['id']}: {ans}", flush=True)

        print(f"=== {persona} 完成（{len(qs_p)} 题）===", flush=True)

    print(f"已完成 {len(done)} 条，结果在 {args.out}")


if __name__ == "__main__":
    main()
