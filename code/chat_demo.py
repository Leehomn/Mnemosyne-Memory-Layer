# chat_demo.py —— 端到端对话循环（双通道：即时记忆 + 话题固化）

from llm import make_deepseek_llm
from index import Cognition
from reconstruct import reconstruct

llm = make_deepseek_llm()
cog = Cognition(data_dir="chat_data", llm=llm)

PERSONA = "你是一个温柔、有点幽默的陪伴者，说话简短自然。"

buffer = []   # 当前话题的对话缓冲区（慢通道用）

print("开始对话（输入 quit 退出）\n")

while True:
    user_input = input("你：")
    if user_input.lower() == "quit":
        if buffer:
            reconstruct(llm, buffer, cog.remember)
        break

    # 1. 语义召回相关记忆
    memory_block = cog.semantic_recall_block(user_input, limit=5)

    # 2. 拼提示词：让模型回复 + 顺带输出两个标记
    prompt = (
        PERSONA + "\n\n"
        + (memory_block if memory_block else "（你还没有关于他的记忆）") + "\n\n"
        + "用户说：" + user_input + "\n"
        + "请自然、简短地回复。\n\n"
        + "然后，在最后单独输出两行（只输出这两行，不要解释）：\n"
        + "第一行：判断这句话是不是「用户明确陈述了关于自己的事实」（自我介绍、明确偏好、重要事实）。注意：提问、感叹、闲聊、寒暄都不算事实，输出 [即时:否]。是事实就输出 [即时:是]。\n"
        + "第二行：输出一个 0~1 的数，表示这句话和上一句的话题偏离程度（0=延续上一个话题，1=完全换了个新话题）。\n"
        + "[即时:否]\n"
        + "[话题偏离:0.3]"
    )
    reply = llm(prompt)

    # 3. 解析回复里的两个标记
    instant = None       # 是否即时记忆
    deviation = None     # 话题偏离度
    reply_body = reply

    for line in reply.split("\n"):
        line = line.strip()
        if line.startswith("[即时:"):
            instant = ("是" in line)
            reply_body = reply_body.replace(line, "").strip()
        elif line.startswith("[话题偏离:"):
            try:
                deviation = float(line.replace("[话题偏离:", "").replace("]", "").strip())
            except ValueError:
                deviation = None
            reply_body = reply_body.replace(line, "").strip()

    # 4. 快通道：高价值事实 → 提炼后当下记住
    if instant:
        added = reconstruct(llm, ["用户：" + user_input], cog.remember)
        if added > 0:
            print("（后台：已提炼并记住这条信息）")

    # 5. 慢通道：话题偏离度 ≥ 0.5 → 固化旧话题
    if deviation is not None and deviation >= 0.5 and buffer:
        added = reconstruct(llm, buffer, cog.remember)
        print(f"（后台：话题切换，从上一段对话提炼了 {added} 条记忆）")
        buffer = []

    # 6. 把这一轮加入缓冲区（慢通道用）
    buffer.append("用户：" + user_input)
    buffer.append("AI：" + reply_body)

    # 7. 打印 AI 回复
    print("AI：" + reply_body + "\n")
