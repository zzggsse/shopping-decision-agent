"""生成洗发水与食品的 fixture 数据(含真实成分表/营养成分)。"""

from __future__ import annotations

import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
OUT = pathlib.Path(__file__).parent
sys.path.insert(0, str(OUT.parents[3]))

from generate import PLATFORM_PROFILE, BRAND_GAPS  # type: ignore  # noqa: E402

# 每个条目:brand, model, base, 规格属性, 成分表
SHAMPOOS = [
    {
        "brand": "海飞丝", "model": "去屑洗发露 经典款", "base": 59,
        "volume_ml": 750, "scalp_gentleness": "harsh", "hair_type": "oily",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、月桂醇硫酸酯钠(SLS)、"
                       "吡硫鎓锌(ZPT)、氯化钠、椰油酰胺 MEA、香精、柠檬酸",
    },
    {
        "brand": "施巴", "model": "温和洗发液", "base": 128,
        "volume_ml": 400, "scalp_gentleness": "gentle", "hair_type": "all",
        "ingredients": "水、椰油酰谷氨酸钠(氨基酸表活)、椰油酰甘氨酸钾(氨基酸)、"
                       "烟酰胺、神经酰胺、泛醇、pH5.5 弱酸性配方",
    },
    {
        "brand": "吕", "model": "棕吕 防脱滋养洗发水", "base": 89,
        "volume_ml": 500, "scalp_gentleness": "balanced", "hair_type": "dry",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、椰油酰谷氨酸钠(氨基酸表活)、"
                       "聚二甲基硅氧烷(硅油)、生物素、人参提取物、烟酰胺、香精",
    },
    {
        "brand": "滋源", "model": "茶籽控油去屑洗发水(无硅油)", "base": 99,
        "volume_ml": 535, "scalp_gentleness": "balanced", "hair_type": "oily",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、甲基椰油酰基牛磺酸钠(氨基酸)、"
                       "无硅油配方、吡硫鎓锌(ZPT)、薄荷醇、茶树精油",
    },
    {
        "brand": "馥绿德雅", "model": "小绿珠 控油强韧洗发水", "base": 198,
        "volume_ml": 600, "scalp_gentleness": "gentle", "hair_type": "oily",
        "ingredients": "水、椰油酰谷氨酸钠(氨基酸表活)、月桂醇聚醚硫酸酯钠(SLES)、"
                       "烟酰胺、生物素、薄荷醇、精油颗粒、无硅油配方",
    },
    {
        "brand": "康王", "model": "酮康唑洗剂(药用去屑)", "base": 45,
        "volume_ml": 100, "scalp_gentleness": "balanced", "hair_type": "all",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、酮康唑、椰油酰胺丙基甜菜碱、"
                       "氯化钠、柠檬酸、香精(药用洗剂,按说明使用)",
    },
    {
        "brand": "欧莱雅", "model": "透明质酸水润洗发露", "base": 69,
        "volume_ml": 700, "scalp_gentleness": "balanced", "hair_type": "dry",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、聚二甲基硅氧烷(硅油)、"
                       "透明质酸、神经酰胺、椰油酰胺 MEA、香精、氯化钠",
    },
    {
        "brand": "珂润", "model": "润浸保湿洗发水", "base": 138,
        "volume_ml": 420, "scalp_gentleness": "gentle", "hair_type": "sensitive",
        "ingredients": "水、椰油酰谷氨酸钠(氨基酸表活)、甲基椰油酰基牛磺酸钠(氨基酸)、"
                       "神经酰胺、桉叶提取物、无香精、无硅油配方",
    },
]

# 营养字段同时写入结构化属性(便于打分)和文本成分(便于成分分析)
FOODS = [
    {
        "brand": "旺旺", "model": "仙贝 咸味米饼", "base": 19,
        "sugar_g": 2, "sodium_mg": 680, "protein_g": 6, "fiber_g": 1, "calories_kcal": 180,
        "sugar_level": "low",
        "nutrition": "大米、植物油、食盐(氯化钠/钠)、酱油粉、白砂糖(添加糖)、味精",
    },
    {
        "brand": "乐事", "model": "原味薯片", "base": 12,
        "sugar_g": 1, "sodium_mg": 520, "protein_g": 7, "fiber_g": 2, "calories_kcal": 540,
        "sugar_level": "low",
        "nutrition": "马铃薯、植物油、食盐(氯化钠/钠)、饱和脂肪、葡萄糖(添加糖)、乳化剂",
    },
    {
        "brand": "三只松鼠", "model": "每日坚果 750g", "base": 99,
        "sugar_g": 6, "sodium_mg": 80, "protein_g": 18, "fiber_g": 8, "calories_kcal": 600,
        "sugar_level": "medium",
        "nutrition": "坚果(腰果、杏仁、核桃、榛子)、蔓越莓干、葡萄干、白砂糖(添加糖)",
    },
    {
        "brand": "ffit8", "model": "乳清蛋白棒 巧克力味", "base": 69,
        "sugar_g": 3, "sodium_mg": 140, "protein_g": 20, "fiber_g": 8, "calories_kcal": 220,
        "sugar_level": "low",
        "nutrition": "乳清蛋白(蛋白质)、聚葡萄糖(膳食纤维)、赤藓糖醇(代糖/糖醇)、"
                     "可可粉、坚果(花生)、MCT 油",
    },
    {
        "brand": "趣园", "model": "无糖粗粮饼干", "base": 29,
        "sugar_g": 0, "sodium_mg": 220, "protein_g": 9, "fiber_g": 12, "calories_kcal": 420,
        "sugar_level": "free",
        "nutrition": "全麦粉、燕麦、聚葡萄糖(膳食纤维)、麦芽糖醇(代糖/糖醇)、"
                     "植物油、食盐(钠)",
    },
    {
        "brand": "士力架", "model": "花生夹心巧克力", "base": 39,
        "sugar_g": 30, "sodium_mg": 180, "protein_g": 8, "fiber_g": 2, "calories_kcal": 490,
        "sugar_level": "high",
        "nutrition": "牛奶巧克力、白砂糖(添加糖)、葡萄糖浆(添加糖)、花生(坚果)、"
                     "植脂末(反式脂肪/饱和脂肪)、可可脂",
    },
    {
        "brand": "良品铺子", "model": "低脂鸡胸肉肠", "base": 35,
        "sugar_g": 1, "sodium_mg": 560, "protein_g": 22, "fiber_g": 0, "calories_kcal": 150,
        "sugar_level": "low",
        "nutrition": "鸡胸肉、水、食盐(氯化钠/钠)、香辛料、赤藓糖醇(代糖/糖醇)、大豆蛋白(蛋白质)",
    },
    {
        "brand": "百草味", "model": "海盐坚果混合", "base": 79,
        "sugar_g": 2, "sodium_mg": 320, "protein_g": 16, "fiber_g": 7, "calories_kcal": 580,
        "sugar_level": "low",
        "nutrition": "坚果(杏仁、腰果、开心果)、海盐(钠)、植物油",
    },
]


def build_category(category: str, items: list[dict], ingredient_key: str) -> None:
    now = "2026-08-25T00:00:00+00:00"
    total = 0
    for platform, profile in PLATFORM_PROFILE.items():
        if category not in profile["categories"]:
            continue
        gaps = BRAND_GAPS.get(platform, set())
        rows = []
        directory = OUT / platform
        directory.mkdir(parents=True, exist_ok=True)

        for index, item in enumerate(items):
            if item["brand"] in gaps:
                continue
            list_price = round(item["base"] * profile["factor"], 0)
            components = [
                {"label": "标价", "amount": list_price,
                 "evidence": f"{profile['name']}商品页标价"},
            ]
            coupon = round(list_price * profile["coupon_rate"], 0)
            if coupon:
                components.append({
                    "label": "平台/店铺券", "amount": -coupon,
                    "evidence": f"{profile['name']}优惠券,领取后自动抵扣",
                })
            if profile["shipping"]:
                components.append({
                    "label": "运费", "amount": profile["shipping"],
                    "evidence": "非包邮地区标准运费",
                })
            final = sum(c["amount"] for c in components)
            slug = f"{item['brand']}-{item['model']}".lower().replace(" ", "-")

            # 配料/营养成分文本必须保留在属性里,供成分分析读取
            attributes = {
                key: value for key, value in item.items()
                if key not in ("brand", "model", "base")
            }
            rows.append({
                "offer": {
                    "offer_id": f"{platform}-{category}-{slug}",
                    "platform": platform,
                    "platform_sku_id": f"{platform.upper()}{category[:2].upper()}{200 + index}",
                    "title": f"{item['brand']} {item['model']}",
                    "list_price": list_price,
                    "components": components,
                    "final_price": final,
                    "shop_name": f"{profile['name']}自营旗舰店",
                    "shop_rating": profile["rating"],
                    "review_count": 600 + index * 540,
                    "review_score": round(4.2 + (index % 7) * 0.1, 1),
                    "in_stock": True,
                    "delivery_days": profile["days"],
                    "condition": "new",
                    "url": f"https://example-{platform}.com/item/{slug}",
                    "fetched_at": now,
                    "stale": False,
                },
                "spec": {
                    "category": category,
                    "brand": item["brand"],
                    "model": item["model"],
                    "attributes": attributes,
                },
                "vendor_group_hint": slug,
            })

        path = directory / f"{category}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        total += len(rows)
        print(f"  {platform}/{category}.json  {len(rows)} items")
    print(f"  -> {total} {category} items total")


if __name__ == "__main__":
    build_category("shampoo", SHAMPOOS, "ingredients")
    build_category("food", FOODS, "nutrition")