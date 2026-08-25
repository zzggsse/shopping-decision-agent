"""洗发水与食品(零食)品类定义,以及共享的成分知识库。

这两个品类用于验证"成分表精准分析 + 用户档案"能力:
  - 洗发水:配料表(表面活性剂/调理剂/功效成分)+ 头发问题匹配
  - 食品:营养成分(糖/钠/脂肪)+ 糖尿病/高血压等条件匹配
"""

from __future__ import annotations

from .schema import (
    AttributeDef,
    CategorySchema,
    ConcernRule,
    DimensionDef,
    IngredientKnowledge,
    SlotDef,
)

# --------------------------------------------------------------------------
# 洗发水成分知识库
# --------------------------------------------------------------------------

SHAMPOO_KNOWLEDGE: dict[str, IngredientKnowledge] = {
    "sles": IngredientKnowledge(
        name="月桂醇聚醚硫酸酯钠", aliases=["SLES", "sles", "月桂醇聚醚硫酸酯钠"],
        benefits=["清洁力强,泡沫丰富"],
        risks=["脱脂力较强,敏感头皮可能发干"],
        helps_with=["油性头发", "日常清洁"],
    ),
    "sls": IngredientKnowledge(
        name="月桂醇硫酸酯钠", aliases=["SLS", "sls", "月桂醇硫酸酯钠", "K12"],
        benefits=["强力去油"],
        risks=["刺激性较高,长期用可能损伤头皮屏障"],
        avoid_for=["sensitive_scalp", "sulfate_allergy"],
        helps_with=["重度油性头发"],
    ),
    "amino": IngredientKnowledge(
        name="氨基酸表活",
        aliases=["氨基酸表面活性剂", "椰油酰谷氨酸钠", "甲基椰油酰基牛磺酸钠",
                 "椰油酰甘氨酸钾", "氨基酸"],
        benefits=["温和低刺激,接近头皮 pH"],
        risks=["清洁力相对温和,大油头可能觉得不够爽"],
        helps_with=["敏感头皮", "干性头发", "头皮瘙痒", "受损发质"],
    ),
    "ketoconazole": IngredientKnowledge(
        name="酮康唑", aliases=["ketoconazole"],
        benefits=["抗真菌,针对头屑和脂溢性皮炎"],
        risks=["属于药用成分,不宜长期连续使用,建议遵说明"],
        helps_with=["头屑", "脂溢性皮炎", "头皮瘙痒"],
    ),
    "zpt": IngredientKnowledge(
        name="吡硫鎓锌", aliases=["ZPT", "zpt", "吡硫鎓锌"],
        benefits=["抑制马拉色菌,减少头屑"],
        risks=["部分国家限用,敏感头皮先做测试"],
        helps_with=["头屑", "油性头发"],
    ),
    "salicylic": IngredientKnowledge(
        name="水杨酸", aliases=["salicylic acid", "BHA"],
        benefits=["疏通毛囊,减少头屑和油脂堆积"],
        risks=["浓度过高有刺激性,孕妇建议咨询医生"],
        avoid_for=["pregnant"],
        helps_with=["头屑", "油性头发", "毛囊堵塞"],
    ),
    "silicone": IngredientKnowledge(
        name="硅油", aliases=["聚二甲基硅氧烷", "硅氧烷", "dimethicone", "氨端聚二甲基硅氧烷"],
        benefits=["顺滑发丝,减少毛躁打结"],
        risks=["长期残留可能让发根扁塌,油头慎用"],
        helps_with=["干性头发", "受损发质", "毛躁"],
    ),
    "nosilicone": IngredientKnowledge(
        name="无硅油配方", aliases=["无硅油"],
        benefits=["发根蓬松,不易扁塌"],
        risks=["干性发质可能觉得干涩"],
        helps_with=["油性头发", "扁塌发质"],
    ),
    "menthol": IngredientKnowledge(
        name="薄荷醇", aliases=["menthol", "薄荷"],
        benefits=["清凉舒爽,减轻头皮瘙痒"],
        risks=["敏感头皮可能有刺痛感"],
        helps_with=["油性头发", "头皮瘙痒"],
    ),
    "biotin": IngredientKnowledge(
        name="生物素", aliases=["biotin", "维生素B7"],
        benefits=["强韧发丝,改善脆弱易断"],
        helps_with=["受损发质", "脱发护理"],
    ),
    "niacinamide": IngredientKnowledge(
        name="烟酰胺", aliases=["niacinamide", "维生素B3"],
        benefits=["养护头皮屏障,改善油脂平衡"],
        helps_with=["油性头发", "头皮瘙痒"],
    ),
    "ceramide": IngredientKnowledge(
        name="神经酰胺", aliases=["ceramide"],
        benefits=["修护头皮和发丝屏障"],
        helps_with=["干性头发", "受损发质", "敏感头皮"],
    ),
}

# --------------------------------------------------------------------------
# 食品营养知识库(关键成分)
# --------------------------------------------------------------------------

FOOD_KNOWLEDGE: dict[str, IngredientKnowledge] = {
    "sugar": IngredientKnowledge(
        name="添加糖", aliases=["白砂糖", "果葡糖浆", "蔗糖", "麦芽糖", "葡萄糖浆", "糖"],
        benefits=["提升口感"],
        risks=["过量摄入增加血糖波动、龋齿和代谢负担"],
        avoid_for=["diabetes"],
        helps_with=[],
    ),
    "sodium": IngredientKnowledge(
        name="钠", aliases=["食盐", "氯化钠", "钠", "盐"],
        benefits=["调味、保鲜"],
        risks=["高钠摄入与血压升高相关"],
        avoid_for=["hypertension"],
        helps_with=[],
    ),
    "sat_fat": IngredientKnowledge(
        name="饱和脂肪", aliases=["饱和脂肪", "棕榈油", "氢化植物油", "起酥油", "植脂末"],
        benefits=["提升风味与口感"],
        risks=["过量摄入不利于心血管健康"],
        avoid_for=["hypertension"],
        helps_with=[],
    ),
    "protein": IngredientKnowledge(
        name="蛋白质", aliases=["蛋白质", "乳清蛋白", "大豆蛋白"],
        benefits=["增加饱腹感,有助肌肉维持"],
        helps_with=["健身增肌", "控糖"],
    ),
    "fiber": IngredientKnowledge(
        name="膳食纤维", aliases=["膳食纤维", "菊粉", "抗性糊精", "聚葡萄糖"],
        benefits=["延缓糖分吸收,促进肠道健康"],
        helps_with=["糖尿病", "控糖", "健身增肌"],
    ),
    "nut": IngredientKnowledge(
        name="坚果", aliases=["花生", "杏仁", "腰果", "核桃", "榛子", "开心果", "坚果"],
        benefits=["提供优质脂肪与蛋白质"],
        risks=["坚果过敏者可能引发严重反应"],
        avoid_for=["nut_allergy"],
        helps_with=["健身增肌"],
    ),
    "sugar_alcohol": IngredientKnowledge(
        name="代糖/糖醇", aliases=["赤藓糖醇", "木糖醇", "麦芽糖醇", "甜菊糖苷", "三氯蔗糖"],
        benefits=["几乎不升血糖,适合控糖人群"],
        risks=["过量可能引起肠胃不适"],
        helps_with=["糖尿病", "控糖"],
    ),
    "trans_fat": IngredientKnowledge(
        name="反式脂肪", aliases=["反式脂肪", "氢化油", "人造奶油", "奶精", "植脂末"],
        risks=["明确增加心血管疾病风险"],
        avoid_for=["hypertension"],
        helps_with=[],
    ),
}


def _shampoo_slots() -> list[SlotDef]:
    return [
        SlotDef(
            key="hair_issue",
            label="头发/头皮问题",
            question="最想解决什么头发问题?",
            options=["头屑头痒", "出油扁塌", "干枯毛躁", "敏感头皮"],
            option_values={
                "头屑头痒": "dandruff",
                "出油扁塌": "oily",
                "干枯毛躁": "dry",
                "敏感头皮": "sensitive",
            },
            required=True,
            keywords={
                "dandruff": ["头屑", "头痒", "头皮屑", "脂溢"],
                "oily": ["出油", "油头", "扁塌", "油腻"],
                "dry": ["干枯", "毛躁", "受损", "分叉", "干燥"],
                "sensitive": ["敏感", "头皮痒", "刺痛", "屏障"],
            },
        ),
    ]


def _food_slots() -> list[SlotDef]:
    return [
        SlotDef(
            key="diet_goal",
            label="饮食目标",
            question="选购零食主要考虑什么?",
            options=["控糖/低糖", "健身高蛋白", "低钠健康", "解馋就行"],
            option_values={
                "控糖/低糖": "low_sugar",
                "健身高蛋白": "fitness",
                "低钠健康": "low_sodium",
                "解馋就行": "casual",
            },
            required=True,
            keywords={
                "low_sugar": ["控糖", "低糖", "无糖", "血糖"],
                "fitness": ["健身", "增肌", "蛋白", "减脂"],
                "low_sodium": ["低钠", "少盐", "血压", "健康"],
                "casual": ["解馋", "随便", "好吃"],
            },
        ),
    ]



# 游戏重度档案对电子产品的通用规则(注入到 laptop / phone)
_GAMING_RULES = [
    ConcernRule(
        condition="gaming", severity="boost", target="dimension",
        key="performance", weight_delta=0.12,
        message="游戏重度玩家:性能权重提升",
    ),
]

SHAMPOO = CategorySchema(
    key="shampoo",
    label="洗发水",
    triggers=["洗发水", "洗发露", "洗头膏", "洗发", "洗头水"],
    search_term="洗发水",
    ingredient_attribute="ingredients",
    ingredient_separator="、,，;；/",
    noise_words=["洗发水", "洗发露", "正品", "官方", "旗舰店", "ml", "g", "装"],
    budget_options=["50 以内", "50-100", "100-200", "200 以上"],
    budget_values={
        "50 以内": (None, 50),
        "50-100": (50, 100),
        "100-200": (100, 200),
        "200 以上": (200, None),
    },
    slots=_shampoo_slots(),
    attributes=[
        AttributeDef("volume_ml", "容量", unit="ml", direction="none"),
        AttributeDef(
            "scalp_gentleness", "温和度", kind="enum", direction="higher_better",
            scale={"harsh": 0.2, "balanced": 0.6, "gentle": 0.95},
            labels={"harsh": "清洁力强", "balanced": "均衡", "gentle": "温和"},
        ),
        AttributeDef(
            "hair_type", "适配发质", kind="enum", direction="none",
            labels={"oily": "油性", "dry": "干性", "normal": "中性", "all": "全发质"},
        ),
    ],
    dimensions=[
        DimensionDef("price", "价格", 0.25),
        DimensionDef(
            "ingredient_fit", "成分匹配", 0.35,
            pro_template="成分与你的需求高度匹配",
            con_template="部分成分可能不适合你的头皮状况",
        ),
        DimensionDef(
            "gentleness", "温和度", 0.15, components={"scalp_gentleness": 1.0},
            pro_template="配方温和,日常使用对头皮友好",
            con_template="清洁力偏强,敏感头皮建议隔天使用",
        ),
        DimensionDef("reputation", "口碑", 0.25),
    ],
    ingredient_knowledge=SHAMPOO_KNOWLEDGE,
    concern_rules=[
        ConcernRule(
            condition="sensitive_scalp", severity="avoid", target="ingredient",
            key="月桂醇硫酸酯钠", message="含 SLS 强清洁成分,敏感头皮不建议",
        ),
        ConcernRule(
            condition="sulfate_allergy", severity="avoid", target="ingredient",
            key="月桂醇硫酸酯钠", message="含硫酸盐表活,硫酸盐过敏者不建议",
        ),
        ConcernRule(
            condition="pregnant", severity="avoid", target="ingredient",
            key="水杨酸", message="含水杨酸,孕期建议咨询医生后使用",
        ),
        ConcernRule(
            condition="sensitive_scalp", severity="prefer", target="ingredient",
            key="氨基酸表活", message="氨基酸表活,适合敏感头皮",
        ),
        ConcernRule(
            condition="sensitive_scalp", severity="boost", target="dimension",
            key="ingredient_fit", weight_delta=0.20,
            message="敏感头皮:成分匹配权重提升",
        ),
        ConcernRule(
            condition="sensitive_scalp", severity="boost", target="dimension",
            key="gentleness", weight_delta=0.20,
            message="敏感头皮:温和度权重提升",
        ),
    ],
)

FOOD = CategorySchema(
    key="food",
    label="零食",
    triggers=["零食", "食品", "吃的", "饼干", "薯片", "巧克力", "代餐", "蛋白棒"],
    search_term="零食",
    ingredient_attribute="nutrition",
    ingredient_separator="、,，;；/",
    noise_words=["零食", "正品", "官方", "旗舰店", "g", "克", "装"],
    budget_options=["30 以内", "30-80", "80-150", "150 以上"],
    budget_values={
        "30 以内": (None, 30),
        "30-80": (30, 80),
        "80-150": (80, 150),
        "150 以上": (150, None),
    },
    slots=_food_slots(),
    attributes=[
        AttributeDef("sugar_g", "糖/每份", unit="g", direction="lower_better"),
        AttributeDef("sodium_mg", "钠/每份", unit="mg", direction="lower_better"),
        AttributeDef("protein_g", "蛋白质/每份", unit="g", direction="higher_better"),
        AttributeDef("fiber_g", "膳食纤维/每份", unit="g", direction="higher_better"),
        AttributeDef("calories_kcal", "热量/每份", unit="kcal", direction="none"),
        AttributeDef(
            "sugar_level", "糖分等级", kind="enum", direction="lower_better",
            scale={"high": 0.1, "medium": 0.5, "low": 0.85, "free": 1.0},
            labels={"high": "高糖", "medium": "中糖", "low": "低糖", "free": "无糖"},
        ),
    ],
    dimensions=[
        DimensionDef("price", "价格", 0.20),
        DimensionDef(
            "ingredient_fit", "成分匹配", 0.35,
            pro_template="营养成分与你的健康需求匹配",
            con_template="含有需要你注意的成分",
        ),
        DimensionDef(
            "low_sugar", "低糖", 0.20,
            components={"sugar_level": 0.7, "sugar_g": 0.3},
            pro_template="糖分控制得不错",
            con_template="糖分偏高",
        ),
        DimensionDef(
            "high_protein", "高蛋白", 0.10, components={"protein_g": 1.0},
            pro_template="蛋白质含量可观",
        ),
        DimensionDef("reputation", "口碑", 0.15),
    ],
    ingredient_knowledge=FOOD_KNOWLEDGE,
    concern_rules=[
        ConcernRule(
            condition="diabetes", severity="avoid", target="ingredient",
            key="添加糖", message="含添加糖,糖尿病患者不建议",
        ),
        ConcernRule(
            condition="diabetes", severity="avoid", target="ingredient",
            key="反式脂肪", message="含反式脂肪,糖尿病合并心血管风险者不建议",
        ),
        ConcernRule(
            condition="diabetes", severity="prefer", target="ingredient",
            key="代糖/糖醇", message="使用代糖,对血糖友好",
        ),
        ConcernRule(
            condition="diabetes", severity="prefer", target="ingredient",
            key="膳食纤维", message="富含膳食纤维,有助延缓血糖上升",
        ),
        ConcernRule(
            condition="hypertension", severity="avoid", target="ingredient",
            key="钠", message="钠含量偏高,高血压人群需注意",
        ),
        ConcernRule(
            condition="hypertension", severity="avoid", target="ingredient",
            key="饱和脂肪", message="含较多饱和脂肪,心血管人群需注意",
        ),
        ConcernRule(
            condition="nut_allergy", severity="avoid", target="ingredient",
            key="坚果", message="含坚果成分,坚果过敏者请勿食用",
        ),
        ConcernRule(
            condition="fitness", severity="prefer", target="ingredient",
            key="蛋白质", message="高蛋白,适合健身需求",
        ),
        ConcernRule(
            condition="diabetes", severity="boost", target="dimension",
            key="ingredient_fit", weight_delta=0.18,
            message="糖尿病:成分匹配权重提升",
        ),
        ConcernRule(
            condition="gaming", severity="boost", target="dimension",
            key="price", weight_delta=0.10,
            message="游戏玩家通常备货量大,价格权重略提升",
        ),
    ],
)