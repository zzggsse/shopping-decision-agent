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
        # 刻意保留缺口:跨境物流不划算,亚马逊不供扫地机器人
        "categories": ["laptop", "phone", "earbuds", "shampoo", "food"],
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
        spec("Lenovo", "IdeaPad Slim 3 15", 3299,
             cpu="Ryzen 5 7530U", cpu_tier="entry", gpu="Radeon iGPU", gpu_need="none",
             ram_gb=16, storage_gb=512, screen_size=15.6, pixels=1920 * 1080,
             refresh_hz=60, color_gamut="sRGB", weight_kg=1.62, battery_hours=8.0),
        spec("Acer", "Aspire Lite 14", 2899,
             cpu="Core i5-12450H", cpu_tier="entry", gpu="UHD iGPU", gpu_need="none",
             ram_gb=16, storage_gb=512, screen_size=14.0, pixels=1920 * 1200,
             refresh_hz=60, color_gamut="sRGB", weight_kg=1.40, battery_hours=7.5),
        spec("HP", "ProBook 445 G11", 3899,
             cpu="Ryzen 7 7735U", cpu_tier="mainstream", gpu="Radeon iGPU", gpu_need="none",
             ram_gb=16, storage_gb=512, screen_size=14.0, pixels=1920 * 1200,
             refresh_hz=60, color_gamut="sRGB", weight_kg=1.39, battery_hours=9.5),
        spec("Honor", "MagicBook X14 Plus", 3599,
             cpu="Core i5-13420H", cpu_tier="mainstream", gpu="UHD iGPU", gpu_need="none",
             ram_gb=16, storage_gb=1024, screen_size=14.0, pixels=1920 * 1200,
             refresh_hz=60, color_gamut="sRGB", weight_kg=1.38, battery_hours=9.0),
        spec("ThundeRobot", "911 X Wild Hunter", 5999,
             cpu="Core i7-13650HX", cpu_tier="high", gpu="RTX 4060", gpu_need="serious",
             ram_gb=16, storage_gb=1024, screen_size=15.6, pixels=2560 * 1440,
             refresh_hz=165, color_gamut="sRGB", weight_kg=2.25, battery_hours=5.0),
        spec("Mechrevo", "Jiaolong 16 Pro", 6799,
             cpu="Ryzen 7 8845H", cpu_tier="high", gpu="RTX 4060", gpu_need="serious",
             ram_gb=32, storage_gb=1024, screen_size=16.0, pixels=2560 * 1600,
             refresh_hz=240, color_gamut="P3", weight_kg=2.20, battery_hours=6.0),
        spec("Lenovo", "Legion R9000P", 8299,
             cpu="Ryzen 9 8945HX", cpu_tier="flagship", gpu="RTX 4060", gpu_need="serious",
             ram_gb=16, storage_gb=1024, screen_size=16.0, pixels=2560 * 1600,
             refresh_hz=240, color_gamut="P3", weight_kg=2.35, battery_hours=6.5),
        spec("ASUS", "TUF Gaming A15", 5499,
             cpu="Ryzen 7 7435H", cpu_tier="mainstream", gpu="RTX 4050", gpu_need="serious",
             ram_gb=16, storage_gb=512, screen_size=15.6, pixels=1920 * 1080,
             refresh_hz=144, color_gamut="sRGB", weight_kg=2.20, battery_hours=5.5),
        spec("Xiaomi", "RedmiBook 16 2024", 3999,
             cpu="Core i5-13500H", cpu_tier="mainstream", gpu="UHD iGPU", gpu_need="none",
             ram_gb=16, storage_gb=512, screen_size=16.0, pixels=2560 * 1600,
             refresh_hz=120, color_gamut="sRGB", weight_kg=1.70, battery_hours=9.0),
        spec("Apple", "MacBook Pro 14 M3 Pro", 15999,
             cpu="Apple M3 Pro", cpu_tier="flagship", gpu="M3 Pro 14-core", gpu_need="serious",
             ram_gb=18, storage_gb=512, screen_size=14.2, pixels=3024 * 1964,
             refresh_hz=120, color_gamut="P3", weight_kg=1.55, battery_hours=17.0),
        spec("Dell", "Inspiron 14 5440", 4299,
             cpu="Core i5-1334U", cpu_tier="entry", gpu="Iris Xe", gpu_need="none",
             ram_gb=16, storage_gb=512, screen_size=14.0, pixels=1920 * 1200,
             refresh_hz=60, color_gamut="sRGB", weight_kg=1.55, battery_hours=8.5),
        spec("HUAWEI", "MateBook X Pro 2024", 13999,
             cpu="Core Ultra 9 185H", cpu_tier="flagship", gpu="Arc iGPU", gpu_need="light",
             ram_gb=32, storage_gb=1024, screen_size=14.2, pixels=3120 * 2080,
             refresh_hz=120, color_gamut="P3", weight_kg=0.98, battery_hours=12.0),
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
        spec("Redmi", "Redmi 13C", 699,
             chipset="Helio G85", chip_tier="entry", ram_gb=6, storage_gb=128,
             screen_size=6.74, refresh_hz=90, battery_mah=5000, charge_w=18,
             main_camera_mp=50, camera_grade="basic", weight_g=192),
        spec("Realme", "realme V50", 1099,
             chipset="Snapdragon 4 Gen2", chip_tier="entry", ram_gb=8, storage_gb=128,
             screen_size=6.72, refresh_hz=120, battery_mah=5000, charge_w=45,
             main_camera_mp=50, camera_grade="basic", weight_g=188),
        spec("Honor", "Honor X50", 1499,
             chipset="Snapdragon 6 Gen1", chip_tier="mainstream", ram_gb=8, storage_gb=256,
             screen_size=6.78, refresh_hz=120, battery_mah=5800, charge_w=35,
             main_camera_mp=108, camera_grade="good", weight_g=191),
        spec("OPPO", "OPPO K12", 1799,
             chipset="Snapdragon 7 Gen3", chip_tier="mainstream", ram_gb=12, storage_gb=256,
             screen_size=6.7, refresh_hz=120, battery_mah=5500, charge_w=100,
             main_camera_mp=50, camera_grade="good", weight_g=193),
        spec("iQOO", "iQOO Neo9", 2699,
             chipset="Snapdragon 8 Gen2", chip_tier="high", ram_gb=12, storage_gb=256,
             screen_size=6.78, refresh_hz=144, battery_mah=5160, charge_w=120,
             main_camera_mp=50, camera_grade="good", weight_g=190),
        spec("Xiaomi", "Redmi K70 Pro", 3299,
             chipset="Snapdragon 8 Gen3", chip_tier="flagship", ram_gb=16, storage_gb=512,
             screen_size=6.67, refresh_hz=120, battery_mah=5000, charge_w=120,
             main_camera_mp=50, camera_grade="excellent", weight_g=209),
        spec("Apple", "iPhone 15 Pro Max", 9999,
             chipset="A17 Pro", chip_tier="flagship", ram_gb=8, storage_gb=256,
             screen_size=6.7, refresh_hz=120, battery_mah=4441, charge_w=27,
             main_camera_mp=48, camera_grade="flagship", weight_g=221),
        spec("HUAWEI", "Pura 70 Pro", 6999,
             chipset="Kirin 9010", chip_tier="flagship", ram_gb=12, storage_gb=512,
             screen_size=6.8, refresh_hz=120, battery_mah=5050, charge_w=100,
             main_camera_mp=50, camera_grade="flagship", weight_g=220),
        spec("vivo", "vivo X100 Ultra", 6499,
             chipset="Snapdragon 8 Gen3", chip_tier="flagship", ram_gb=16, storage_gb=512,
             screen_size=6.78, refresh_hz=120, battery_mah=5500, charge_w=80,
             main_camera_mp=50, camera_grade="flagship", weight_g=226),
        spec("Samsung", "Galaxy S24", 5499,
             chipset="Snapdragon 8 Gen3", chip_tier="flagship", ram_gb=12, storage_gb=256,
             screen_size=6.2, refresh_hz=120, battery_mah=4000, charge_w=25,
             main_camera_mp=50, camera_grade="excellent", weight_g=167),
        spec("Meizu", "Meizu 21", 3399,
             chipset="Snapdragon 8 Gen3", chip_tier="flagship", ram_gb=12, storage_gb=256,
             screen_size=6.55, refresh_hz=120, battery_mah=4800, charge_w=80,
             main_camera_mp=50, camera_grade="good", weight_g=189),
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
        spec("QCY", "T13 ANC2", 99,
             anc_grade="basic", anc_db=30, sound_grade="basic",
             battery_hours=7.0, case_hours=30, latency_ms=120, weight_g=4.2,
             wear_style="in_ear", waterproof="IPX5"),
        spec("Redmi", "Redmi Buds 6 Lite", 129,
             anc_grade="basic", anc_db=35, sound_grade="basic",
             battery_hours=7.5, case_hours=38, latency_ms=110, weight_g=4.1,
             wear_style="in_ear", waterproof="IP54"),
        spec("Baseus", "Bowie MA10", 169,
             anc_grade="good", anc_db=48, sound_grade="good",
             battery_hours=6.5, case_hours=35, latency_ms=45, weight_g=4.6,
             wear_style="in_ear", waterproof="IPX4"),
        spec("Oladance", "OWS Pro", 1099,
             anc_grade="none", anc_db=0, sound_grade="excellent",
             battery_hours=16.0, case_hours=58, latency_ms=140, weight_g=10.5,
             wear_style="over_ear", waterproof="IPX4"),
        spec("Shokz", "OpenFit", 1198,
             anc_grade="none", anc_db=0, sound_grade="good",
             battery_hours=7.0, case_hours=28, latency_ms=130, weight_g=8.3,
             wear_style="over_ear", waterproof="IP54"),
        spec("Huawei", "FreeClip", 1299,
             anc_grade="none", anc_db=0, sound_grade="good",
             battery_hours=8.0, case_hours=36, latency_ms=95, weight_g=5.6,
             wear_style="over_ear", waterproof="IP54"),
        spec("Bose", "QuietComfort Ultra Earbuds", 2299,
             anc_grade="flagship", anc_db=52, sound_grade="audiophile",
             battery_hours=6.0, case_hours=24, latency_ms=110, weight_g=6.2,
             wear_style="in_ear", waterproof="IPX4"),
        spec("Sennheiser", "Momentum True Wireless 4", 1999,
             anc_grade="excellent", anc_db=44, sound_grade="audiophile",
             battery_hours=7.5, case_hours=30, latency_ms=100, weight_g=6.0,
             wear_style="in_ear", waterproof="IP54"),
        spec("vivo", "TWS 4 Hi-Fi", 599,
             anc_grade="excellent", anc_db=49, sound_grade="excellent",
             battery_hours=7.0, case_hours=30, latency_ms=48, weight_g=4.9,
             wear_style="in_ear", waterproof="IP54"),
        spec("OPPO", "Enco X3", 799,
             anc_grade="excellent", anc_db=47, sound_grade="excellent",
             battery_hours=6.0, case_hours=28, latency_ms=47, weight_g=5.1,
             wear_style="in_ear", waterproof="IP54"),
        spec("Xiaomi", "Xiaomi Buds 5 Pro", 1299,
             anc_grade="flagship", anc_db=55, sound_grade="excellent",
             battery_hours=7.5, case_hours=40, latency_ms=50, weight_g=5.4,
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
        spec("Xiaomi", "Robot Vacuum E10", 799,
             suction_pa=4000, mop_type="basic", base_station="none",
             dust_bag_days=0, navigation="gyro", obstacle_avoid="碰撞感应",
             climb_mm=15, noise_db=70, height_mm=81),
        spec("Ecovacs", "T20e", 1199,
             suction_pa=6000, mop_type="vibrate", base_station="none",
             dust_bag_days=0, navigation="lidar", obstacle_avoid="激光雷达",
             climb_mm=20, noise_db=68, height_mm=94),
        spec("Xiaomi", "Robot Vacuum S20+", 1699,
             suction_pa=5000, mop_type="spin", base_station="dust_only",
             dust_bag_days=45, navigation="lidar", obstacle_avoid="激光雷达",
             climb_mm=20, noise_db=66, height_mm=95),
        spec("Roborock", "Q10 S5+", 2499,
             suction_pa=7000, mop_type="vibrate", base_station="wash",
             dust_bag_days=60, navigation="lidar", obstacle_avoid="激光雷达",
             climb_mm=20, noise_db=64, height_mm=96),
        spec("Dreame", "L20 Ultra", 3999,
             suction_pa=7000, mop_type="spin_lift", base_station="wash_dry",
             dust_bag_days=75, navigation="lidar_ai", obstacle_avoid="3D 结构光 + AI",
             climb_mm=60, noise_db=62, height_mm=97),
        spec("Roborock", "S8 Pro Ultra", 4499,
             suction_pa=6000, mop_type="spin_lift", base_station="wash_dry",
             dust_bag_days=60, navigation="lidar_ai", obstacle_avoid="双线激光",
             climb_mm=30, noise_db=61, height_mm=96),
        spec("Narwal", "Freo Z Ultra", 6299,
             suction_pa=12000, mop_type="spin_lift", base_station="wash_dry",
             dust_bag_days=90, navigation="lidar_ai", obstacle_avoid="双芯 AI 视觉",
             climb_mm=40, noise_db=57, height_mm=104),
        spec("Roborock", "Saros 10R", 7299,
             suction_pa=20000, mop_type="spin_lift", base_station="wash_dry",
             dust_bag_days=90, navigation="lidar_ai", obstacle_avoid="固态激光 + AI",
             climb_mm=80, noise_db=56, height_mm=79),
        spec("Ecovacs", "X5 Pro Omni", 5499,
             suction_pa=12800, mop_type="spin_lift", base_station="wash_dry",
             dust_bag_days=75, navigation="lidar_ai", obstacle_avoid="AI 视觉",
             climb_mm=40, noise_db=59, height_mm=81),
        spec("Haier", "Sweeping Robot HB1", 999,
             suction_pa=4500, mop_type="basic", base_station="none",
             dust_bag_days=0, navigation="gyro", obstacle_avoid="碰撞感应",
             climb_mm=15, noise_db=71, height_mm=85),
    ],
}

#: 部分平台不覆盖全部品牌,模拟真实的供货缺失
BRAND_GAPS = {
    "pdd": {"Dell", "HP", "Sony", "Narwal", "Bose", "Sennheiser", "卡诗", "馥绿德雅"},
    "amazon": {
        "Redmi", "Honor", "Ecovacs", "Narwal", "Dreame", "iQOO", "Meizu",
        "ThundeRobot", "Mechrevo", "Haier", "QCY", "Baseus", "vivo",
        "蜂花", "拉芳", "王小卤", "无穷", "康师傅",
    },
    "tmall": {"Oladance"},
}


def build() -> None:
    now = datetime.now(timezone.utc).isoformat()
    total = 0

    for platform, profile in PLATFORM_PROFILE.items():
        directory = OUT / platform
        directory.mkdir(parents=True, exist_ok=True)
        gaps = BRAND_GAPS.get(platform, set())

        # 健康类品类(洗发水/食品)由 generate_health.py 负责,此处跳过
        for category in profile["categories"]:
            if category not in CATALOG_DATA:
                continue
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