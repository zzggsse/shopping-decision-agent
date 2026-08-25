"""品类定义集合。

新增品类只需在此追加一份 CategorySchema 并 register,
再提供对应的商品数据(fixture 或 live 适配器映射)。
"""

from __future__ import annotations

from .schema import AttributeDef, CategorySchema, DimensionDef, SlotDef, registry

# --------------------------------------------------------------------------
# 通用预算档位构造
# --------------------------------------------------------------------------


def budget_ladder(*bounds: int) -> tuple[list[str], dict[str, tuple[int | None, int | None]]]:
    """根据档位分界点生成预算选项与取值区间。"""
    options: list[str] = []
    values: dict[str, tuple[int | None, int | None]] = {}

    previous: int | None = None
    for bound in bounds:
        label = f"{bound} 以内" if previous is None else f"{previous}-{bound}"
        options.append(label)
        values[label] = (None, bound)
        previous = bound

    label = f"{previous} 以上"
    options.append(label)
    values[label] = (previous, None)
    return options, values


# --------------------------------------------------------------------------
# 笔记本电脑(当前主要测试品类)
# --------------------------------------------------------------------------

_laptop_budget_options, _laptop_budget_values = budget_ladder(4000, 7000, 10000)

LAPTOP = CategorySchema(
    key="laptop",
    label="笔记本电脑",
    triggers=["笔记本", "笔记本电脑", "轻薄本", "游戏本", "macbook", "电脑"],
    search_term="笔记本电脑",
    noise_words=["笔记本电脑", "轻薄本", "游戏本", "官方", "旗舰店", "正品"],
    budget_options=_laptop_budget_options,
    budget_values=_laptop_budget_values,
    slots=[
        SlotDef(
            key="primary_use",
            label="主要用途",
            question="主要拿来做什么?",
            options=["日常办公学习", "编程开发", "打游戏", "设计剪辑"],
            option_values={
                "日常办公学习": "office",
                "编程开发": "dev",
                "打游戏": "gaming",
                "设计剪辑": "design",
            },
            required=True,
            keywords={
                "gaming": ["游戏", "打游戏", "电竞", "3a", "帧率"],
                "design": ["设计", "剪辑", "视频", "修图", "渲染", "建模"],
                "dev": ["开发", "编程", "写代码", "编译", "docker", "算法"],
                "office": ["办公", "文档", "上课", "学习", "网课", "excel"],
                "media": ["追剧", "看电影", "影音", "娱乐"],
            },
        ),
        SlotDef(
            key="portability",
            label="便携需求",
            question="需要经常带出门吗?",
            options=["经常带,越轻越好", "偶尔带", "基本放家里"],
            option_values={"经常带,越轻越好": "high", "偶尔带": "medium", "基本放家里": "low"},
            required=True,
            keywords={
                "medium": ["偶尔带", "偶尔", "有时带", "不常带"],
                "high": ["轻", "便携", "通勤", "带出门", "背着", "薄"],
                "low": ["不用带", "放家里", "固定", "台式替代", "不带出门"],
            },
        ),
    ],
    attributes=[
        AttributeDef("cpu", "处理器", kind="text"),
        AttributeDef(
            "cpu_tier", "性能档位", kind="enum", direction="higher_better",
            scale={"entry": 0.25, "mainstream": 0.5, "high": 0.8, "flagship": 1.0},
            labels={"entry": "入门", "mainstream": "主流", "high": "高性能", "flagship": "旗舰"},
        ),
        AttributeDef("gpu", "显卡", kind="text"),
        AttributeDef(
            "gpu_need", "图形能力", kind="enum", direction="higher_better",
            scale={"none": 0.0, "light": 0.45, "serious": 1.0},
            labels={"none": "无独显", "light": "核显够用", "serious": "独立显卡"}, summary=False,
        ),
        AttributeDef("ram_gb", "内存", unit="G", direction="higher_better", identity=True),
        AttributeDef("storage_gb", "存储", unit="G", direction="higher_better", identity=True),
        AttributeDef("screen_size", "屏幕尺寸", unit='"', direction="none"),
        AttributeDef("pixels", "分辨率像素", direction="higher_better", summary=False),
        AttributeDef("refresh_hz", "刷新率", unit="Hz", direction="higher_better", summary=False),
        AttributeDef(
            "color_gamut", "色域", kind="enum", direction="higher_better",
            scale={"sRGB": 0.5, "P3": 0.9, "AdobeRGB": 1.0},
            labels={"sRGB": "sRGB", "P3": "P3 广色域", "AdobeRGB": "AdobeRGB"}, summary=False,
        ),
        AttributeDef("weight_kg", "重量", unit="kg", direction="lower_better"),
        AttributeDef("battery_hours", "续航", unit="h", direction="higher_better"),
    ],
    dimensions=[
        DimensionDef("price", "价格", 0.30),
        DimensionDef(
            "performance", "性能", 0.20,
            components={"cpu_tier": 0.5, "gpu_need": 0.2, "ram_gb": 0.2, "storage_gb": 0.1},
            pro_template="{cpu} + {ram_gb}G 内存,性能余量充足",
        ),
        DimensionDef(
            "portability", "便携", 0.15, components={"weight_kg": 1.0},
            pro_template="整机 {weight_kg}kg,通勤携带轻松",
            con_template="整机 {weight_kg}kg,长期背着通勤偏重",
        ),
        DimensionDef(
            "battery", "续航", 0.15, components={"battery_hours": 1.0},
            pro_template="续航约 {battery_hours} 小时,可覆盖一整天外出",
            con_template="续航约 {battery_hours} 小时,外出需带充电器",
        ),
        DimensionDef(
            "screen", "屏幕", 0.10,
            components={"pixels": 0.45, "color_gamut": 0.35, "refresh_hz": 0.20},
            pro_template="{screen_size} 英寸 {refresh_hz}Hz 屏幕素质突出",
        ),
        DimensionDef("reputation", "口碑", 0.10),
    ],
)

# --------------------------------------------------------------------------
# 智能手机
# --------------------------------------------------------------------------

_phone_budget_options, _phone_budget_values = budget_ladder(2000, 4000, 6000)

PHONE = CategorySchema(
    key="phone",
    label="智能手机",
    triggers=["手机", "智能手机", "iphone", "安卓机"],
    search_term="智能手机",
    noise_words=["手机", "全网通", "5g", "官方", "旗舰店", "正品"],
    budget_options=_phone_budget_options,
    budget_values=_phone_budget_values,
    slots=[
        SlotDef(
            key="primary_use",
            label="主要用途",
            question="你最在意手机的哪方面?",
            options=["拍照", "打游戏", "长续航", "日常够用"],
            option_values={"拍照": "camera", "打游戏": "gaming", "长续航": "battery", "日常够用": "daily"},
            required=True,
            keywords={
                "camera": ["拍照", "拍视频", "影像", "相机", "长焦", "vlog"],
                "gaming": ["游戏", "打游戏", "王者", "原神", "帧率"],
                "battery": ["续航", "电池", "耐用", "充电快"],
                "daily": ["日常", "够用", "备用", "打电话"],
            },
        ),
        SlotDef(
            key="size_pref",
            label="尺寸偏好",
            question="偏好什么机身尺寸?",
            options=["小屏易握持", "无所谓", "大屏看着爽"],
            option_values={"小屏易握持": "small", "无所谓": "any", "大屏看着爽": "large"},
            required=True,
            keywords={"small": ["小屏", "小尺寸", "单手", "易握"], "large": ["大屏", "大尺寸", "看剧"]},
        ),
    ],
    attributes=[
        AttributeDef("chipset", "芯片", kind="text"),
        AttributeDef(
            "chip_tier", "性能档位", kind="enum", direction="higher_better",
            scale={"entry": 0.25, "mainstream": 0.5, "high": 0.8, "flagship": 1.0},
            labels={"entry": "入门", "mainstream": "主流", "high": "高性能", "flagship": "旗舰"},
        ),
        AttributeDef("ram_gb", "运存", unit="G", direction="higher_better", identity=True),
        AttributeDef("storage_gb", "存储", unit="G", direction="higher_better", identity=True),
        AttributeDef("screen_size", "屏幕", unit='"', direction="none"),
        AttributeDef("refresh_hz", "刷新率", unit="Hz", direction="higher_better", summary=False),
        AttributeDef("battery_mah", "电池容量", unit="mAh", direction="higher_better"),
        AttributeDef("charge_w", "充电功率", unit="W", direction="higher_better", summary=False),
        AttributeDef("main_camera_mp", "主摄", unit="MP", direction="higher_better"),
        AttributeDef(
            "camera_grade", "影像评级", kind="enum", direction="higher_better",
            scale={"basic": 0.3, "good": 0.6, "excellent": 0.85, "flagship": 1.0},
            labels={"basic": "基础", "good": "良好", "excellent": "优秀", "flagship": "旗舰级"}, summary=False,
        ),
        AttributeDef("weight_g", "重量", unit="g", direction="lower_better"),
    ],
    dimensions=[
        DimensionDef("price", "价格", 0.30),
        DimensionDef(
            "performance", "性能", 0.20,
            components={"chip_tier": 0.6, "ram_gb": 0.25, "storage_gb": 0.15},
            pro_template="{chipset},性能足以应对重载游戏",
        ),
        DimensionDef(
            "camera", "影像", 0.20,
            components={"camera_grade": 0.7, "main_camera_mp": 0.3},
            pro_template="主摄 {main_camera_mp}MP,影像表现出色",
            con_template="影像素质一般,对拍照要求高不建议",
        ),
        DimensionDef(
            "battery", "续航", 0.15,
            components={"battery_mah": 0.7, "charge_w": 0.3},
            pro_template="{battery_mah}mAh 电池 + {charge_w}W 快充",
            con_template="电池 {battery_mah}mAh,重度使用需随身充电",
        ),
        DimensionDef(
            "handfeel", "手感", 0.05, components={"weight_g": 1.0},
            pro_template="机身 {weight_g}g,单手握持轻盈",
            con_template="机身 {weight_g}g,长时间单手偏沉",
        ),
        DimensionDef("reputation", "口碑", 0.10),
    ],
)

# --------------------------------------------------------------------------
# 无线耳机
# --------------------------------------------------------------------------

_earbuds_budget_options, _earbuds_budget_values = budget_ladder(300, 800, 1500)

EARBUDS = CategorySchema(
    key="earbuds",
    label="无线耳机",
    triggers=["耳机", "无线耳机", "蓝牙耳机", "降噪耳机", "airpods", "tws"],
    search_term="无线蓝牙耳机",
    noise_words=["无线耳机", "蓝牙耳机", "真无线", "官方", "旗舰店", "正品"],
    budget_options=_earbuds_budget_options,
    budget_values=_earbuds_budget_values,
    slots=[
        SlotDef(
            key="primary_use",
            label="主要场景",
            question="主要在什么场景用?",
            options=["通勤地铁降噪", "运动健身", "打游戏低延迟", "居家听音乐"],
            option_values={
                "通勤地铁降噪": "commute", "运动健身": "sports",
                "打游戏低延迟": "gaming", "居家听音乐": "music",
            },
            required=True,
            keywords={
                "commute": ["通勤", "地铁", "飞机", "降噪", "吵"],
                "sports": ["运动", "健身", "跑步", "防水", "防汗"],
                "gaming": ["游戏", "延迟", "吃鸡", "手游"],
                "music": ["听歌", "音乐", "音质", "hifi", "居家"],
            },
        ),
        SlotDef(
            key="wear_style",
            label="佩戴形式",
            question="偏好哪种佩戴方式?",
            options=["入耳式", "半入耳", "都可以"],
            option_values={"入耳式": "in_ear", "半入耳": "semi_in_ear", "都可以": "any"},
            required=True,
            keywords={
                "in_ear": ["入耳", "隔音"],
                "semi_in_ear": ["半入耳", "不入耳", "耳朵疼", "不胀"],
            },
        ),
    ],
    attributes=[
        AttributeDef(
            "anc_grade", "降噪能力", kind="enum", direction="higher_better",
            scale={"none": 0.0, "basic": 0.35, "good": 0.65, "excellent": 0.85, "flagship": 1.0},
            labels={"none": "无降噪", "basic": "基础降噪", "good": "良好降噪",
                    "excellent": "优秀降噪", "flagship": "旗舰降噪"},
        ),
        AttributeDef("anc_db", "降噪深度", unit="dB", direction="higher_better", summary=False),
        AttributeDef(
            "sound_grade", "音质评级", kind="enum", direction="higher_better",
            scale={"basic": 0.3, "good": 0.6, "excellent": 0.85, "audiophile": 1.0},
            labels={"basic": "入门音质", "good": "良好音质",
                    "excellent": "优秀音质", "audiophile": "发烧级"},
        ),
        AttributeDef("battery_hours", "单次续航", unit="h", direction="higher_better"),
        AttributeDef("case_hours", "总续航", unit="h", direction="higher_better", summary=False),
        AttributeDef("latency_ms", "延迟", unit="ms", direction="lower_better"),
        AttributeDef("weight_g", "单耳重量", unit="g", direction="lower_better", summary=False),
        AttributeDef(
            "wear_style", "佩戴形式", kind="enum", direction="none", identity=True,
            labels={"in_ear": "入耳式", "semi_in_ear": "半入耳", "over_ear": "头戴式"},
        ),
        AttributeDef("waterproof", "防水等级", kind="text", summary=False),
    ],
    dimensions=[
        DimensionDef("price", "价格", 0.30),
        DimensionDef(
            "noise_cancel", "降噪", 0.25,
            components={"anc_grade": 0.7, "anc_db": 0.3},
            pro_template="降噪深度约 {anc_db}dB,通勤地铁足够安静",
            con_template="降噪能力有限,嘈杂环境下人声仍会漏进来",
        ),
        DimensionDef(
            "sound", "音质", 0.20, components={"sound_grade": 1.0},
            pro_template="音质评级出色,听感细节丰富",
            con_template="音质偏入门,对听感要求高会失望",
        ),
        DimensionDef(
            "battery", "续航", 0.10,
            components={"battery_hours": 0.6, "case_hours": 0.4},
            pro_template="单次 {battery_hours} 小时,充电盒可续 {case_hours} 小时",
        ),
        DimensionDef(
            "latency", "延迟", 0.05, components={"latency_ms": 1.0},
            pro_template="延迟约 {latency_ms}ms,打手游基本无感",
            con_template="延迟 {latency_ms}ms,打游戏会有声画不同步",
        ),
        DimensionDef("reputation", "口碑", 0.10),
    ],
)

# --------------------------------------------------------------------------
# 扫地机器人(验证家电类:属性形态差异更大)
# --------------------------------------------------------------------------

_robot_budget_options, _robot_budget_values = budget_ladder(1500, 3000, 5000)

ROBOT_VACUUM = CategorySchema(
    key="robot_vacuum",
    label="扫地机器人",
    triggers=["扫地机器人", "扫地机", "拖地机器人", "洗地机器人"],
    search_term="扫地机器人",
    noise_words=["扫地机器人", "扫拖一体", "官方", "旗舰店", "正品"],
    budget_options=_robot_budget_options,
    budget_values=_robot_budget_values,
    slots=[
        SlotDef(
            key="primary_use",
            label="核心需求",
            question="你家最需要解决什么问题?",
            options=["养宠物毛发多", "地毯多", "户型大要省心", "预算优先够用"],
            option_values={
                "养宠物毛发多": "pet", "地毯多": "carpet",
                "户型大要省心": "large_home", "预算优先够用": "budget",
            },
            required=True,
            keywords={
                "pet": ["宠物", "猫", "狗", "毛发", "掉毛"],
                "carpet": ["地毯", "毛毯"],
                "large_home": ["大户型", "复式", "别墅", "多层", "省心", "自动"],
                "budget": ["便宜", "够用", "入门"],
            },
        ),
        SlotDef(
            key="mop_need",
            label="拖地需求",
            question="需要拖地功能吗?",
            options=["需要,且要自动洗拖布", "需要基础拖地", "只要扫地"],
            option_values={
                "需要,且要自动洗拖布": "self_clean",
                "需要基础拖地": "basic",
                "只要扫地": "none",
            },
            required=True,
            keywords={
                "self_clean": ["自动洗", "免手洗", "自清洁", "基站"],
                "basic": ["拖地", "湿拖"],
                "none": ["只扫", "不用拖", "不拖地"],
            },
        ),
    ],
    attributes=[
        AttributeDef("suction_pa", "吸力", unit="Pa", direction="higher_better"),
        AttributeDef(
            "mop_type", "拖地方式", kind="enum", direction="higher_better",
            scale={"none": 0.0, "basic": 0.4, "vibrate": 0.7, "spin": 0.85, "spin_lift": 1.0},
            labels={"none": "不支持拖地", "basic": "基础湿拖", "vibrate": "高频振动拖",
                    "spin": "双旋转拖布", "spin_lift": "旋转拖布+自动抬升"},
        ),
        AttributeDef(
            "base_station", "基站能力", kind="enum", direction="higher_better",
            scale={"none": 0.0, "dust_only": 0.5, "wash": 0.8, "wash_dry": 1.0},
            labels={"none": "无基站", "dust_only": "仅自动集尘",
                    "wash": "自动洗拖布", "wash_dry": "自动洗烘拖布"},
        ),
        AttributeDef("dust_bag_days", "免倒垃圾", unit="天", direction="higher_better", summary=False),
        AttributeDef(
            "navigation", "导航方案", kind="enum", direction="higher_better",
            scale={"gyro": 0.2, "lidar": 0.7, "lidar_ai": 1.0},
            labels={"gyro": "陀螺仪导航", "lidar": "激光导航", "lidar_ai": "激光+AI 视觉"},
        ),
        AttributeDef("obstacle_avoid", "避障方案", kind="text", summary=False),
        AttributeDef("climb_mm", "越障高度", unit="mm", direction="higher_better", summary=False),
        AttributeDef("noise_db", "噪音", unit="dB", direction="lower_better"),
        AttributeDef("height_mm", "机身高度", unit="mm", direction="lower_better", summary=False),
    ],
    dimensions=[
        DimensionDef("price", "价格", 0.30),
        DimensionDef(
            "cleaning", "清扫能力", 0.25,
            components={"suction_pa": 0.6, "climb_mm": 0.2, "mop_type": 0.2},
            pro_template="{suction_pa}Pa 吸力,宠物毛发和地毯浮尘都能带走",
            con_template="吸力 {suction_pa}Pa 偏弱,地毯和毛发场景会吃力",
        ),
        DimensionDef(
            "automation", "省心程度", 0.20,
            components={"base_station": 0.6, "dust_bag_days": 0.4},
            pro_template="基站可自动洗拖布,日常几乎不用管",
            con_template="需要手动清洗拖布和倒垃圾,省心程度有限",
        ),
        DimensionDef(
            "navigation", "导航避障", 0.15, components={"navigation": 1.0},
            pro_template="激光导航配 AI 避障,不容易被线缆和拖鞋绊住",
            con_template="导航方案偏基础,容易漏扫或卡住",
        ),
        DimensionDef(
            "quietness", "静音", 0.05, components={"noise_db": 1.0},
            pro_template="运行噪音约 {noise_db}dB,家里有人休息也不吵",
            con_template="运行噪音 {noise_db}dB 偏大,建议避开休息时段",
        ),
        DimensionDef("reputation", "口碑", 0.05),
    ],
)


from .categories_health import FOOD, SHAMPOO, _GAMING_RULES

# 给电子产品挂上"游戏重度"提升性能的规则
for _schema in (LAPTOP, PHONE):
    if _schema.key in ("laptop", "phone"):
        for _rule in _GAMING_RULES:
            if not any(r.condition == "gaming" for r in _schema.concern_rules):
                _schema.concern_rules.append(_rule)

for schema in (LAPTOP, PHONE, EARBUDS, ROBOT_VACUUM, SHAMPOO, FOOD):
    registry.register(schema)

DEFAULT_CATEGORY = "laptop"