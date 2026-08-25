"""端到端演示:验证全品类能力与三层核心问题。"""

import json
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8000"

REQUESTS = {
    "laptop": "笔记本预算 7000 左右,主要编程开发,经常带出门",
    "phone": "手机预算 4000 以内,主要拍照,大屏看着爽",
    "earbuds": "降噪耳机预算 800 以内,通勤地铁用,入耳式",
    "robot_vacuum": "扫地机器人预算 3000 以内,养宠物毛发多,需要基础拖地",
}


def stream(client, payload):
    events = []
    with client.stream("POST", f"{BASE}/api/chat/stream", json=payload) as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def rule(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    with httpx.Client(timeout=60) as client:
        health = client.get(f"{BASE}/api/health").json()
        categories = client.get(f"{BASE}/api/categories").json()

        rule("已注册品类(新增品类只需加一份配置,无需改代码)")
        for item in categories:
            dimensions = "/".join(d["label"] for d in item["dimensions"])
            print(f"  {item['label']:<8} 打分维度:{dimensions}")
            print(f"  {'':<8} 供货平台:{', '.join(item['platforms'])}")
        print(f"\n  数据模式:{health['data_source_mode']}")

        rule("场景一:品类自动路由 + 需求不全时主动追问")
        events = stream(client, {"message": "想买个降噪耳机"})
        task_id = next(e["task_id"] for e in events if e["type"] == "task_created")
        detected = next((e for e in events if e["type"] == "category"), None)
        if detected:
            print(f"  识别品类:{detected['label']}")
        for event in events:
            if event["type"] == "clarify":
                print(f"  追问:{event['question']}")
                print(f"  选项:{' / '.join(event['options'])}")

        rule("场景二:四个品类各跑一遍完整决策流程")
        for category, message in REQUESTS.items():
            events = stream(client, {"message": message, "category": category})
            report = next(e["report"] for e in events if e["type"] == "report")
            top = report["picks"][0]

            print(f"\n  【{report['category_label']}】{message}")
            print(f"    推荐:{top['title']}  ¥{top['final_price']:,.0f} @ {top['platform']}"
                  f"  匹配度 {top['score']}")
            print(f"    参数:{top['summary']}")
            spread = top.get("price_spread")
            if spread:
                print(f"    比价:{spread['min_platform']} ¥{spread['min_price']:,.0f}"
                      f" ↔ {spread['max_platform']} ¥{spread['max_price']:,.0f}"
                      f"  可省 ¥{spread['saved']:,.0f}")
            for pro in top["pros"][:3]:
                print(f"    + {pro}")
            for con in top["cons"][:2]:
                print(f"    - {con}")

        rule("场景三:同一句话在不同品类下解析出不同参数")
        for category in ("laptop", "phone"):
            detail = client.get(f"{BASE}/api/tasks/{task_id}").json()
            events = stream(client, {"message": REQUESTS[category], "category": category})
            understood = next((e for e in events if e["type"] == "understood"), None)
            label = next(c["label"] for c in categories if c["key"] == category)
            if understood:
                print(f"  {label}:{'、'.join(understood['signals'])}")

        rule("场景四:到手价明细(比价可解释性)")
        events = stream(client, {"message": REQUESTS["earbuds"], "category": "earbuds"})
        earbuds_task = next(e["task_id"] for e in events if e["type"] == "task_created")
        detail = client.get(f"{BASE}/api/tasks/{earbuds_task}").json()
        top = detail["candidates"][0]
        print(f"  {top['title']} 各平台报价:")
        for offer in top["offers"]:
            print(f"    {offer['platform']:<7} 到手 ¥{offer['final_price']:>8,.0f}"
                  f"  ({offer['delivery_days']} 天达)")
            for component in offer["breakdown"]["components"]:
                print(f"        {component['label']:<10} {component['amount']:>9,.0f}"
                      f"  ← {component['evidence']}")

        rule("场景五:权重滑块重排(维度随品类变化)")
        schema = detail["schema"]
        print(f"  {schema['label']}的维度:{[d['key'] for d in schema['dimensions']]}")
        before = [c["title"] for c in detail["candidates"][:3]]
        print(f"  当前排序:{before}")

        flat = {d["key"]: 0.02 for d in schema["dimensions"]}
        result = client.post(
            f"{BASE}/api/tasks/{earbuds_task}/weights",
            json={"weights": {**flat, "price": 0.9}},
        ).json()
        print(f"  价格权重拉满:{[c['title'] for c in result['candidates'][:3]]}")

        result = client.post(
            f"{BASE}/api/tasks/{earbuds_task}/weights",
            json={"weights": {**flat, "noise_cancel": 0.9}},
        ).json()
        print(f"  降噪权重拉满:{[c['title'] for c in result['candidates'][:3]]}")

        bad = client.post(
            f"{BASE}/api/tasks/{earbuds_task}/weights",
            json={"weights": {"portability": 0.9}},
        )
        print(f"  传入耳机不存在的「便携」维度 → HTTP {bad.status_code}(已拒绝)")

        rule("场景六:对话中途换品类,上下文正确重置")
        events = stream(client, {"message": "算了,我想看扫地机器人,预算 3000 以内养宠物需要基础拖地",
                                 "task_id": earbuds_task})
        switched = next((e for e in events if e["type"] == "category"), None)
        if switched:
            print(f"  从 {switched['switched_from']} 切换到 {switched['label']}")
        report = next(e["report"] for e in events if e["type"] == "report")
        print(f"  新结论:{report['summary']}")

        rule("场景七:跳转前价格二次校验(只做决策+跳转)")
        detail = client.get(f"{BASE}/api/tasks/{earbuds_task}").json()
        offer = detail["candidates"][0]["offers"][0]
        check = client.post(
            f"{BASE}/api/tasks/{earbuds_task}/redirect/{offer['offer_id']}"
        ).json()
        print(f"  展示价 ¥{check['shown_price']:,.0f} → 实时价 ¥{check['current_price']:,.0f}")
        print(f"  {check['message']}")
        print(f"  跳转:{check['redirect_url']}")

        rule("场景八:决策链路可回溯")
        for entry in detail["decision_log"][-10:]:
            print(f"  [{entry['action']:<10}] {entry['detail']}")
        print(f"  … 共 {len(detail['decision_log'])} 条记录")


if __name__ == "__main__":
    main()