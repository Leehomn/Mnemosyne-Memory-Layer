# demo.py —— 综合演示：一条记忆的一生

from item import make_item, is_valid
from store import save_items, load_items
from decay import decayed_weight, should_forget

print("=" * 40)
print("Mnemosyne 记忆系统 · 综合演示")
print("=" * 40)

# 1. 创建一条记忆
m = make_item("我叫南风", "user_said", 0.95, hits=1)
print("\n① 创建记忆：", m["text"])
print("   校验是否合法：", is_valid(m))

# 2. 存到硬盘
save_items([m])
print("\n② 已保存到 data/items.json")

# 3. 读回来
loaded = load_items()
print("③ 读回", len(loaded), "条记忆 ✅")

# 4. 模拟过了 60 天，算权重
age = 60
half_life = 14
w = decayed_weight(1.8, half_life, m["hits"], m["confidence"], age)
print(f"\n④ 过了 {age} 天，权重 = {round(w, 3)}")

# 5. 判断该不该忘
if should_forget(w):
    print("⑤ 结论：这条记忆该被遗忘了 💤")
else:
    print("⑤ 结论：这条记忆还记着 💪")

print("\n" + "=" * 40)
print("演示结束")
print("=" * 40)