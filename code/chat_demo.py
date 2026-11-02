# chat_demo.py —— 端到端对话循环（双通道 + 验证机制）

from llm import make_deepseek_llm
from index import Cognition
from reconstruct import reconstruct
from verify import pick_verify_target, judge_feedback

llm = make_deepseek_llm()
cog = Cognition(data_dir="chat_data", llm=llm)

PERSONA = "你是一个温柔、有点幽默的陪伴者，说话简短自然。"

buffer = []
pending_verify = None   # 上一轮待验证的印象

print("开始对话（输入 quit 退出）\n")

while True:
    user_input = input("你：")
    if user_input.lower() == "quit":
        if buffer:
            reconstruct(llm, buffer, cog.remember)
        break

    # —— 验证机制：如果上一轮问过，先判断用户回答 ——
    if pending_verify is not None:
        feedback = judge_feedback(user_input, llm)
        if feedback == "confirm":
            cog.update_confidence(pending_verify, 0.9, reason="验证确认")
            print("（后台：验证确认，置信度提升）")
        elif feedback == "deny":
            cog.update_confidence(pending_verify, 0.1, reason="验证否认")
            print("（后台：验证否认，置信度降低）")
        pending_verify = None

    # 1. 语义召回相关记忆
    memory_block = cog.semantic_recall_block(user_input, limit=5)

    # 2. 综合判断：该不该验证、验证哪一条
    verify_target = None
    if pending_verify is None:
        all_items = cog._all_items()
        verify_target, should_ask = pick_verify_target(llm, all_items, user_input)
        if not should_ask:
            verify_target = None

    # 3. 拼提示词（若有验证目标，让模型顺带求证）
    verify_instruction = ""
    if verify_target is not None:
        verify_instruction = (
            "另外，你对他有一个还不确定的印象：「" + verify_target["text"] + "」。"
            "请自然、低声地顺带求证一句（比如「你是不是...？」），不要显得突兀。"
        )
        pending_verify = verify_target

    prompt = (
        PERSONA + "\n\n"
        + (memory_block if memory_block else "（你还没有关于他的记忆）") + "\n\n"
        + verify_instruction + "\n"
        + "用户说：" + user_input + "\n"
        + "请自然、简短地回复。"
    )
    reply = llm(prompt)

    # 4. 把这一轮加入缓冲区
    buffer.append("用户：" + user_input)
    buffer.append("AI：" + reply)

    print("AI：" + reply + "\n")