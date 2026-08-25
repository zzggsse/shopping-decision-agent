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
    {
        "brand": "蜂花", "model": "无硅油护发精华素洗发水", "base": 26,
        "volume_ml": 500, "scalp_gentleness": "balanced", "hair_type": "oily",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、椰油酰胺丙基甜菜碱(两性表活)、"
                       "无硅油配方、烟酰胺、柠檬酸、香精",
    },
    {
        "brand": "拉芳", "model": "去屑止痒洗发露", "base": 19,
        "volume_ml": 400, "scalp_gentleness": "harsh", "hair_type": "oily",
        "ingredients": "水、月桂醇硫酸酯钠(SLS)、吡硫鎓锌(ZPT)、薄荷醇、"
                       "氯化钠、香精、防腐剂",
    },
    {
        "brand": "滋源", "model": "无硅油氨基酸洗头水", "base": 42,
        "volume_ml": 480, "scalp_gentleness": "gentle", "hair_type": "sensitive",
        "ingredients": "水、椰油酰谷氨酸钠(氨基酸表活)、甲基椰油酰基牛磺酸钠(氨基酸表活)、"
                       "无硅油配方、神经酰胺、生姜提取物、柠檬酸",
    },
    {
        "brand": "海飞丝", "model": "水润去屑洗发露 小样装", "base": 15,
        "volume_ml": 200, "scalp_gentleness": "balanced", "hair_type": "all",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、吡硫鎓锌(ZPT)、"
                       "二甲基硅油(硅油)、香精、防腐剂",
    },
    {
        "brand": "阿道夫", "model": "精油护理洗发水", "base": 48,
        "volume_ml": 520, "scalp_gentleness": "balanced", "hair_type": "dry",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、聚二甲基硅氧烷(硅油)、"
                       "透明质酸、生物素、植物精油、香精",
    },
    {
        "brand": "康王", "model": "水杨酸控油去屑洗发水", "base": 38,
        "volume_ml": 300, "scalp_gentleness": "harsh", "hair_type": "oily",
        "ingredients": "水、月桂醇硫酸酯钠(SLS)、水杨酸、薄荷醇、"
                       "烟酰胺、氯化钠、香精",
    },
    {
        "brand": "谜尚", "model": "氨基酸敏感头皮洗发水", "base": 33,
        "volume_ml": 400, "scalp_gentleness": "gentle", "hair_type": "sensitive",
        "ingredients": "水、椰油酰谷氨酸钠(氨基酸表活)、神经酰胺、泛醇、"
                       "无硅油配方、积雪草提取物、柠檬酸",
    },
    {
        "brand": "潘婷", "model": "3分钟奇迹强韧洗发水", "base": 79,
        "volume_ml": 500, "scalp_gentleness": "balanced", "hair_type": "dry",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、二甲基硅油(硅油)、"
                       "生物素、泛醇、水解角蛋白、香精",
    },
    {
        "brand": "卡诗", "model": "白金赋活精华洗发水", "base": 320,
        "volume_ml": 250, "scalp_gentleness": "gentle", "hair_type": "sensitive",
        "ingredients": "水、椰油酰谷氨酸钠(氨基酸表活)、神经酰胺、生物素、"
                       "烟酰胺、透明质酸、无硅油配方",
    },
    {
        "brand": "馥绿德雅", "model": "复合精油净化洗发水", "base": 268,
        "volume_ml": 200, "scalp_gentleness": "gentle", "hair_type": "oily",
        "ingredients": "水、甲基椰油酰基牛磺酸钠(氨基酸表活)、水杨酸、薄荷醇、"
                       "烟酰胺、无硅油配方、植物精油",
    },
    {
        "brand": "自然之名", "model": "神经酰胺修护洗发水", "base": 88,
        "volume_ml": 460, "scalp_gentleness": "gentle", "hair_type": "dry",
        "ingredients": "水、椰油酰谷氨酸钠(氨基酸表活)、神经酰胺、二甲基硅油(硅油)、"
                       "透明质酸、生物素、柠檬酸",
    },
    {
        "brand": "施华蔻", "model": "去屑控油洗发露", "base": 62,
        "volume_ml": 750, "scalp_gentleness": "balanced", "hair_type": "oily",
        "ingredients": "水、月桂醇聚醚硫酸酯钠(SLES)、吡硫鎓锌(ZPT)、"
                       "水杨酸、烟酰胺、香精",
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
    {
        "brand": "三只松鼠", "model": "每日坚果混合装", "base": 69,
        "sugar_g": 6, "sodium_mg": 60, "protein_g": 14, "fiber_g": 6, "calories_kcal": 610,
        "sugar_level": "low",
        "nutrition": "腰果、核桃(坚果)、扁桃仁(坚果)、蔓越莓干、添加糖、膳食纤维",
    },
    {
        "brand": "王小卤", "model": "虎皮鸡爪", "base": 32,
        "sugar_g": 8, "sodium_mg": 890, "protein_g": 19, "fiber_g": 0, "calories_kcal": 220,
        "sugar_level": "medium",
        "nutrition": "鸡爪、酱油、白砂糖(添加糖)、食用盐(钠)、香辛料、防腐剂",
    },
    {
        "brand": "元气森林", "model": "气泡水 白桃味", "base": 5,
        "sugar_g": 0, "sodium_mg": 20, "protein_g": 0, "fiber_g": 0, "calories_kcal": 2,
        "sugar_level": "free",
        "nutrition": "水、二氧化碳、赤藓糖醇(代糖/糖醇)、三氯蔗糖(代糖/糖醇)、食用香精",
    },
    {
        "brand": "奥利奥", "model": "夹心饼干原味", "base": 14,
        "sugar_g": 38, "sodium_mg": 320, "protein_g": 5, "fiber_g": 2, "calories_kcal": 480,
        "sugar_level": "high",
        "nutrition": "小麦粉、白砂糖(添加糖)、植物油、可可粉、食用盐(钠)、"
                     "起酥油(反式脂肪)、碳酸氢钠",
    },
    {
        "brand": "乐事", "model": "薯片 黄瓜味", "base": 9,
        "sugar_g": 4, "sodium_mg": 610, "protein_g": 6, "fiber_g": 3, "calories_kcal": 530,
        "sugar_level": "low",
        "nutrition": "马铃薯、植物油(饱和脂肪)、食用盐(钠)、白砂糖(添加糖)、食用香精",
    },
    {
        "brand": "伊利", "model": "安慕希无糖酸奶", "base": 58,
        "sugar_g": 3, "sodium_mg": 70, "protein_g": 23, "fiber_g": 0, "calories_kcal": 160,
        "sugar_level": "free",
        "nutrition": "生牛乳、乳清蛋白粉(蛋白质)、赤藓糖醇(代糖/糖醇)、乳酸菌",
    },
    {
        "brand": "myprotein", "model": "乳清蛋白粉 香草味", "base": 149,
        "sugar_g": 2, "sodium_mg": 140, "protein_g": 82, "fiber_g": 1, "calories_kcal": 400,
        "sugar_level": "low",
        "nutrition": "浓缩乳清蛋白(蛋白质)、三氯蔗糖(代糖/糖醇)、食用香精、大豆卵磷脂",
    },
    {
        "brand": "好麦多", "model": "高纤麦片 低糖版", "base": 45,
        "sugar_g": 5, "sodium_mg": 90, "protein_g": 12, "fiber_g": 11, "calories_kcal": 380,
        "sugar_level": "low",
        "nutrition": "燕麦(膳食纤维)、藜麦(膳食纤维)、赤藓糖醇(代糖/糖醇)、"
                     "冻干草莓、扁桃仁(坚果)",
    },
    {
        "brand": "康师傅", "model": "红烧牛肉面", "base": 6,
        "sugar_g": 5, "sodium_mg": 1980, "protein_g": 9, "fiber_g": 2, "calories_kcal": 470,
        "sugar_level": "low",
        "nutrition": "小麦粉、棕榈油(饱和脂肪)、食用盐(钠)、味精、白砂糖(添加糖)、脱水牛肉粒",
    },
    {
        "brand": "无穷", "model": "盐焗鸡蛋", "base": 25,
        "sugar_g": 0, "sodium_mg": 720, "protein_g": 26, "fiber_g": 0, "calories_kcal": 150,
        "sugar_level": "free",
        "nutrition": "鸡蛋(蛋白质)、食用盐(钠)、香辛料、水",
    },
    {
        "brand": "百草味", "model": "冻干榴莲", "base": 89,
        "sugar_g": 24, "sodium_mg": 15, "protein_g": 4, "fiber_g": 8, "calories_kcal": 420,
        "sugar_level": "medium",
        "nutrition": "榴莲(膳食纤维)、无添加糖",
    },
    {
        "brand": "钟薛高", "model": "低糖雪糕礼盒", "base": 168,
        "sugar_g": 9, "sodium_mg": 85, "protein_g": 7, "fiber_g": 1, "calories_kcal": 210,
        "sugar_level": "low",
        "nutrition": "生牛乳、稀奶油(饱和脂肪)、赤藓糖醇(代糖/糖醇)、可可粉、蛋白质",
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