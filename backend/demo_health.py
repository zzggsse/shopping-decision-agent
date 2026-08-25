"""成分分析与用户档案的端到端演示。"""

import json
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8000"


def stream(client, payload):
    events = []
    with client.stream("POST", f"{BASE}/api/chat/stream", json=payload) as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def rule(t):
    print(); print("=" * 70); print(t); print("=" * 70)


def main() -> None:
    with httpx.Client(timeout=60) as client:
        client.put(f"{BASE}/api/profile", json={"conditions": []})

        profile = client.get(f"{BASE}/api/profile").json()
        print("可选档案条件:", "、".join(
            f"{k}({v['label']})" for k, v in profile["conditions_meta"].items()
        ))
        print("平台/品类:", client.get(f"{BASE}/api/health").json()["categories"])

        rule("场景一:洗发水配料表精准分析(聚焦有配料表的)")
        events = stream(client, {"message": "洗发水预算 150 以内,头屑头痒", "category": "shampoo"})
        cands = next(e["candidates"] for e in events if e["type"] == "candidates_update")
        for c in cands[:3]:
            a = c["ingredient_analysis"]
            print(f"\n  {c['title']}  ¥{c['best_price']:.0f}  匹配度 {c['score']['total']}")
            print(f"    适配头发问题:{'、'.join(a['matched_concerns'])}")
            for b in a["benefits"][:2]:
                print(f"    + {b}")
        print("\n  配料原文:", cands[0]["ingredient_analysis"]["raw"])

        rule("场景二:标记糖尿病 → 食品自动避开高糖,优先低糖")
        client.put(f"{BASE}/api/profile", json={"conditions": ["diabetes"]})
        events = stream(client, {"message": "零食预算 80 以内,控糖", "category": "food"})
        rep = next(e["report"] for e in events if e["type"] == "report")
        print("  推荐:", rep["picks"][0]["title"], f"¥{rep['picks'][0]['final_price']:.0f}")
        for pick in rep["picks"]:
            pros = [p for p in pick["pros"] if any(k in p for k in ("糖", "糖尿", "纤维", "无糖"))]
            cons = [c for c in pick["cons"] if "糖" in c or "添加糖" in c]
            if pros or cons:
                print(f"    {pick['title']:<22}  {'✓ '.join(pros)}  {'✗ '.join(cons)}")
        # 士力架等高糖应被硬过滤
        titles = [p["title"] for p in rep["picks"]]
        print("  士力架是否在推荐中(应否):", any("士力架" in t for t in titles))

        rule("场景三:坚果过敏 → 硬过滤含坚果食品")
        client.put(f"{BASE}/api/profile", json={"conditions": ["nut_allergy"]})
        events = stream(client, {"message": "零食预算 100 以内,解馋就行", "category": "food"})
        rep = next(e["report"] for e in events if e["type"] == "report")
        titles = "、".join(p["title"] for p in rep["picks"])
        print("  坚果被排除,推荐:", titles)

        rule("场景四:游戏重度 → 电脑更看重性能")
        client.put(f"{BASE}/api/profile", json={"conditions": ["gaming"]})
        events = stream(client, {"message": "笔记本预算 13000,打游戏偶尔带", "category": "laptop"})
        rep = next(e["report"] for e in events if e["type"] == "report")
        for p in rep["picks"][:3]:
            print(f"  {p['title']}  ¥{p['final_price']:.0f}  匹配度 {p['score']}")
        # 对比:同预算不带游戏档案
        client.put(f"{BASE}/api/profile", json={"conditions": []})
        events = stream(client, {"message": "笔记本预算 13000,打游戏偶尔带", "category": "laptop"})
        rep2 = next(e["report"] for e in events if e["type"] == "report")
        print("  无档案时第1名:", rep2["picks"][0]["title"])

        rule("场景五:配料明细逐成分解释")
        events = stream(client, {"message": "洗发水预算 150 以内,头屑头痒", "category": "shampoo"})
        task_id = next(e["task_id"] for e in events if e["type"] == "task_created")
        cands = client.get(f"{BASE}/api/tasks/{task_id}").json()["candidates"]
        a = cands[0]["ingredient_analysis"]
        print(f"  {cands[0]['title']} 识别 {len(a['recognized'])} 种成分:")
        for item in a["recognized"]:
            print(f"    {item['name']}{'  - ' + '、'.join(item['helps_with']) if item['helps_with'] else ''}")

        client.put(f"{BASE}/api/profile", json={"conditions": []})
        print("\n(已重置档案)")


if __name__ == "__main__":
    main()