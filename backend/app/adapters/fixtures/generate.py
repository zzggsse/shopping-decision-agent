"""生成开发期 fixture 样本(全品类)。

目录结构:fixtures/<platform>/<category>.json
真实上线时由采集脚本按同结构覆盖;此处仅保证本地开发可离线跑通。

新增品类:在 CATALOG_DATA 里加一份机型列表即可。
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

OUT = pathlib.Path(__file__).parent

# 平台差异:价格系数、券策略、运费、店铺口碑、可供货品类
PLATFORM_PROFILE = {
    "jd": {
        "name": "京东", "factor": 1.000, "coupon_rate": 0.045, "shipping": 0,
        "rating": 4.9, "days": 1,
        "categories": ["laptop", "phone", "earbuds", "robot_vacuum", "shampoo", "food"],
    },
    "tmall": {
        "name": "天猫", "factor": 0.985, "coupon_rate": 0.060, "shipping": 0,
        "rating": 4.8, "days": 2,
        "categories": ["laptop", "phone", "earbuds", "robot_vacuum", "shampoo", "food"],
    },
    "pdd": {
        "name": "拼多多", "factor": 0.948, "coupon_rate": 0.020, "shipping": 0,
        "rating": 4.6, "days": 3,
        "categories": ["laptop", "phone", "earbuds", "robot_vacuum", "shampoo", "food"],
    },
    "amazon": {
        "name": "亚马逊", "factor": 1.035, "coupon_rate": 0.0, "shipping": 39,
        "rating": 4.7, "days": 6,
        "categories": ["laptop", "earbuds", "shampoo"],
    },
}


def spec(brand: str, model: str, base: int, **attributes) -> dict:
    return {"brand": brand, "model": model, "base": base, "attributes": attributes}


CATALOG_DATA: dict[str, list[dict]] = {
    "laptop": [
        spec("Apple", "MacBook Air M3 13", 9499,
             cpu="Apple M3", cpu_tier="high", gpu="M3 10-core", gpu_need="light",
             ram_gb=16, storage_gb=512, screen_size=13.6, pixels=2560 * 1664,
             refresh_hz=60, color_gamut="P3", weight_kg=1.24, battery_hours=15.0),
        spec("Lenovo", "ThinkPad X1 Carbon Gen12", 12999,
             cpu="Core Ultra 7 155H", cpu_tier="high", gpu="Arc iGPU", gpu_need="light",
             ram_gb=32, storage_gb=1024, screen_size=14.0, pixels=2880 * 1800,
             refresh_hz=120, color_gamut="P3", weight_kg=1.09, battery_hours=11.5),
        spec("ASUS", "Zenbook 14 OLED UX3405", 5799,
             cpu="Core Ultra 5 125H", cpu_tier="mainstream", gpu="Arc iGPU", gpu_need="light",
             ram_gb=16, storage_gb=512, screen_size=14.0, pixels=2880 * 1800,
             refresh_hz=120, color_gamut="P3", weight_kg=1.28, battery_hours=12.0),
        spec("Dell", "XPS 14 9440", 13499,
             cpu="Core Ultra 7 155H", cpu_tier="high", gpu="RTX 4050", gpu_need="serious",
             ram_gb=16, storage_gb=512, screen_size=14.5, pixels=3200 * 2000,
             refresh_hz=120, color_gamut="P3", weight_kg=1.69, battery_hours=9.0),
        spec("ROG", "Zephyrus G14 GA403", 12499,
             cpu="Ryzen 9 8945HS", cpu_tier="flagship", gpu="RTX 4060", gpu_need="serious",
             ram_gb=32, storage_gb=1024, screen_size=14.0, pixels=2880 * 1800,
             refresh_hz=120, color_gamut="P3", weight_kg=1.50, battery_hours=8.0),
        spec("HUAWEI", "MateBook 14", 6299,
             cpu="Core Ultra 5 125H", cpu_tier="mainstream", gpu="Arc iGPU", gpu_need="light",
             ram_gb=16, storage_gb=1024, screen_size=14.2, pixels=2880 * 1920,
             refresh_hz=120, color_gamut="sRGB", weight_kg=1.31, battery_hours=10.5),
        spec("Redmi", "RedmiBook Pro 14", 4499,
             cpu="Core Ultra 5 125H", cpu_tier="mainstream", gpu="Arc iGPU", gpu_need="light",
             ram_gb=16, storage_gb=512, screen_size=14.0, pixels=2880 * 1800,
             refresh_hz=120, color_gamut="sRGB", weight_kg=1.46, battery_hours=9.5),
        spec("HP", "Spectre x360 14", 10999,
             cpu="Core Ultra 7 155H", cpu_tier="high", gpu="Arc iGPU", gpu_need="light",
             ram_gb=16, storage_gb=1024, screen_size=14.0, pixels=2880 * 1800,
             refresh_hz=120, color_gamut="P3", weight_kg=1.44, battery_hours=12.5),
    ],
    "phone": [
        spec("Apple", "iPhone 15", 5999,
             chipset="A16 Bionic", chip_tier="flagship", ram_gb=6, storage_gb=128,
             screen_size=6.1, refresh_hz=60, battery_mah=3349, charge_w=20,
             main_camera_mp=48, camera_grade="excellent", weight_g=171),
        spec("Xiaomi", "Xiaomi 14", 4299,
             chipset="Snapdragon 8 Gen3", chip_tier="flagship", ram_gb=12, storage_gb=256,
             screen_size=6.36, refresh_hz=120, battery_mah=4610, charge_w=90,
             main_camera_mp=50, camera_grade="flagship", weight_g=193),
        spec("Redmi", "Redmi K70", 2499,
             chipset="Snapdragon 8 Gen2", chip_tier="high", ram_gb=12, storage_gb=256,
             screen_size=6.67, refresh_hz=120, battery_mah=5000, charge_w=120,
             main_camera_mp=64, camera_grade="good", weight_g=209),
        spec("HUAWEI", "Mate 60", 5499,
             chipset="Kirin 9000S", chip_tier="high", ram_gb=12, storage_gb=256,
             screen_size=6.69, refresh_hz=120, battery_mah=4750, charge_w=66,
             main_camera_mp=50, camera_grade="flagship", weight_g=209),
        spec("vivo", "vivo X100", 4299,
             chipset="Dimensity 9300", chip_tier="flagship", ram_gb=12, storage_gb=256,
             screen_size=6.78, refresh_hz=120, battery_mah=5000, charge_w=100,
             main_camera_mp=50, camera_grade="flagship", weight_g=206),
        spec("OPPO", "OPPO Reno11", 2499,
             chipset="Dimensity 8200", chip_tier="mainstream", ram_gb=12, storage_gb=256,
             screen_size=6.7, refresh_hz=120, battery_mah=4800, charge_w=67,
             main_camera_mp=50, camera_grade="good", weight_g=182),
        spec("Realme", "realme GT5", 2999,
             chipset="Snapdragon 8 Gen2", chip_tier="high", ram_gb=16, storage_gb=256,
             screen_size=6.74, refresh_hz=144, battery_mah=5240, charge_w=150,
             main_camera_mp=50, camera_grade="good", weight_g=199),
        spec("Honor", "Honor 100", 1999,
             chipset="Snapdragon 7 Gen3", chip_tier="mainstream", ram_gb=12, storage_gb=256,
             screen_size=6.7, refresh_hz=120, battery_mah=5000, charge_w=100,
             main_camera_mp=50, camera_grade="good", weight_g=187),
    ],
    "earbuds": [
        spec("Apple", "AirPods Pro 2", 1899,
             anc_grade="flagship", anc_db=48, sound_grade="excellent",
             battery_hours=6.0, case_hours=30, latency_ms=90, weight_g=5.3,
             wear_style="in_ear", waterproof="IPX4"),
        spec("Sony", "WF-1000XM5", 1699,
             anc_grade="flagship", anc_db=50, sound_grade="audiophile",
             battery_hours=8.0, case_hours=24, latency_ms=120, weight_g=5.9,
             wear_style="in_ear", waterproof="IPX4"),
        spec("Huawei", "FreeBuds Pro 3", 1099,
             anc_grade="excellent", anc_db=45, sound_grade="excellent",
             battery_hours=6.5, case_hours=31, latency_ms=90, weight_g=5.8,
             wear_style="in_ear", waterproof="IP54"),
        spec("Redmi", "Redmi Buds 5 Pro", 299,
             anc_grade="good", anc_db=52, sound_grade="good",
             battery_hours=8.0, case_hours=38, latency_ms=59, weight_g=5.0,
             wear_style="in_ear", waterproof="IP54"),
        spec("Edifier", "NeoBuds Pro 2", 649,
             anc_grade="good", anc_db=42, sound_grade="excellent",
             battery_hours=5.5, case_hours=22, latency_ms=66, weight_g=5.2,
             wear_style="in_ear", waterproof="IP54"),
        spec("Apple", "AirPods 4", 1099,
             anc_grade="basic", anc_db=25, sound_grade="good",
             battery_hours=5.0, case_hours=30, latency_ms=100, weight_g=4.3,
             wear_style="semi_in_ear", waterproof="IPX4"),
        spec("Xiaomi", "Xiaomi Buds 4", 499,
             anc_grade="good", anc_db=43, sound_grade="good",
             battery_hours=6.0, case_hours=30, latency_ms=88, weight_g=4.8,
             wear_style="semi_in_ear", waterproof="IP54"),
        spec("Honor", "Earbuds X5 Pro", 199,
             anc_grade="basic", anc_db=28, sound_grade="basic",
             battery_hours=7.0, case_hours=28, latency_ms=150, weight_g=4.5,
             wear_style="in_ear", waterproof="IP54"),
    ],
    "robot_vacuum": [
        spec("Roborock", "S8 MaxV Ultra", 5799,
             suction_pa=10000, mop_type="spin_lift", base_station="wash_dry",
             dust_bag_days=60, navigation="lidar_ai", obstacle_avoid="双光三维 + AI",
             climb_mm=40, noise_db=60, height_mm=96),
        spec("Dreame", "X30 Pro", 4699,
             suction_pa=8300, mop_type="spin_lift", base_station="wash_dry",
             dust_bag_days=75, navigation="lidar_ai", obstacle_avoid="3D 结构光",
             climb_mm=60, noise_db=62, height_mm=98),
        spec("Ecovacs", "T30 Pro", 3499,
             suction_pa=11000, mop_type="spin", base_station="wash",
             dust_bag_days=60, navigation="lidar_ai", obstacle_avoid="AI 视觉",
             climb_mm=22, noise_db=65, height_mm=103),
        spec("Narwal", "Freo X Ultra", 5299,
             suction_pa=8200, mop_type="spin_lift", base_station="wash_dry",
             dust_bag_days=60, navigation="lidar_ai", obstacle_avoid="双目视觉",
             climb_mm=30, noise_db=58, height_mm=104),
        spec("Xiaomi", "Robot Vacuum X20", 2299,
             suction_pa=6000, mop_type="spin", base_station="wash",
             dust_bag_days=45, navigation="lidar", obstacle_avoid="激光测距",
             climb_mm=20, noise_db=66, height_mm=97),
        spec("Roborock", "Q7 Max+", 1899,
             suction_pa=4200, mop_type="basic", base_station="dust_only",
             dust_bag_days=30, navigation="lidar", obstacle_avoid="激光测距",
             climb_mm=20, noise_db=67, height_mm=96),
        spec("Dreame", "L10s Pro", 2699,
             suction_pa=5300, mop_type="vibrate", base_station="dust_only",
             dust_bag_days=30, navigation="lidar_ai", obstacle_avoid="3D 结构光",
             climb_mm=20, noise_db=65, height_mm=97),
        spec("Ecovacs", "N10", 1399,
             suction_pa=4300, mop_type="basic", base_station="none",
             dust_bag_days=0, navigation="lidar", obstacle_avoid="激光测距",
             climb_mm=18, noise_db=68, height_mm=98),
    ],
}

#: 部分平台不覆盖全部品牌,模拟真实的供货缺失
BRAND_GAPS = {
    "pdd": {"Dell", "HP", "Sony", "Narwal"},
    "amazon": {"Redmi", "Honor", "Ecovacs", "Narwal", "Dreame"},
}


def build() -> None:
    now = datetime.now(timezone.utc).isoformat()
    total = 0

    for platform, profile in PLATFORM_PROFILE.items():
        directory = OUT / platform
        directory.mkdir(parents=True, exist_ok=True)
        gaps = BRAND_GAPS.get(platform, set())

        for category in profile["categories"]:
            rows = []
            for index, model in enumerate(CATALOG_DATA[category]):
                if model["brand"] in gaps:
                    continue

                list_price = round(model["base"] * profile["factor"], 0)
                components = [{
                    "label": "标价",
                    "amount": list_price,
                    "evidence": f"{profile['name']}商品页标价",
                }]

                coupon = round(list_price * profile["coupon_rate"], 0)
                if coupon:
                    components.append({
                        "label": "平台/店铺券",
                        "amount": -coupon,
                        "evidence": f"{profile['name']}优惠券,领取后自动抵扣",
                    })
                if profile["shipping"]:
                    components.append({
                        "label": "运费",
                        "amount": profile["shipping"],
                        "evidence": "非包邮地区标准运费",
                    })

                final = sum(item["amount"] for item in components)
                slug = f"{model['brand']}-{model['model']}".lower().replace(" ", "-")

                rows.append({
                    "offer": {
                        "offer_id": f"{platform}-{category}-{slug}",
                        "platform": platform,
                        "platform_sku_id": f"{platform.upper()}{category[:2].upper()}{100 + index}",
                        "title": f"{model['brand']} {model['model']}",
                        "list_price": list_price,
                        "components": components,
                        "final_price": final,
                        "shop_name": f"{profile['name']}自营旗舰店",
                        "shop_rating": profile["rating"],
                        "review_count": 800 + index * 690,
                        "review_score": round(4.3 + (index % 6) * 0.1, 1),
                        "in_stock": not (platform == "amazon" and index == 4),
                        "delivery_days": profile["days"],
                        "condition": "new",
                        "url": f"https://example-{platform}.com/item/{slug}",
                        "fetched_at": now,
                        "stale": False,
                    },
                    "spec": {
                        "category": category,
                        "brand": model["brand"],
                        "model": model["model"],
                        "attributes": model["attributes"],
                    },
                    "vendor_group_hint": slug,
                })

            path = directory / f"{category}.json"
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            total += len(rows)
            print(f"  {platform}/{category}.json  {len(rows)} offers")

    print(f"\n共生成 {total} 条报价,覆盖 {len(CATALOG_DATA)} 个品类 / {len(PLATFORM_PROFILE)} 个平台")


if __name__ == "__main__":
    build()