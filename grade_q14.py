# -*- coding: utf-8 -*-
"""
第14题主观题辅助评分脚本
用法: python grade_q14.py
或在其他脚本中 from grade_q14 import grade_answer
"""

import re
import sys
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# 评分规则配置
# ──────────────────────────────────────────────────────────────────────────────

SCORING_RULES = {
    # ── 第(1)题 共6分 ────────────────────────────────────────────────────────
    # 科举制 2分 + 政治影响阶梯分（0/2/4）
    "q1": {
        "max": 6,
        "keju": {
            "name": "科举制",
            "points": 2,
            "keywords": [["科举制", "科举", "科举考试", "科举选官", "科举取士",
                          "科举制度", "通过考试选官", "以考试取士", "考试选拔官员"]],
        },
        # 政治影响三点，按命中数阶梯给分
        "influence_points": [
            {
                "name": "扩大统治基础",
                "keywords": [
                    ["扩大", "拓宽", "拓展", "扩展", "广泛"],
                    ["统治基础", "社会基础", "统治集团", "统治阶层",
                     "统治阶级", "执政基础", "官员来源", "选官范围"],
                ],
            },
            {
                "name": "旧贵族衰落/消失",
                "keywords": [
                    ["旧贵族", "门阀", "世家大族", "贵族", "门第", "士族"],
                    ["消失", "衰落", "衰亡", "没落", "瓦解", "削弱", "式微", "逐渐消失"],
                ],
            },
            {
                "name": "皇权加强/专制加强",
                "keywords": [
                    ["皇帝", "皇权", "君权", "专制", "中央集权", "君主专制"],
                    ["加强", "扩大", "强化", "巩固", "集中", "提升", "增强"],
                ],
            },
        ],
        # 阶梯分：命中影响点数 -> 得分
        "influence_ladder": {0: 0, 1: 2, 2: 4, 3: 4},
    },

    # ── 第(2)题 共4分 ────────────────────────────────────────────────────────
    "q2": {
        "max": 4,
        "points": [
            {
                "name": "重用人才",
                "points": 1,
                "keywords": [
                    ["重用", "任用", "选用", "重视", "广纳", "招揽", "选拔", "用人",
                     "知人善用", "广纳贤才", "任贤用能", "善用人才",
                     "知人善任", "爱惜人才"],
                ],
            },
            {
                "name": "善于纳谏",
                "points": 1,
                "keywords": [
                    ["纳谏", "接受谏言", "广开言路", "虚心纳谏", "从谏如流",
                     "善于纳谏", "纳谏如流", "接受意见", "听取意见", "从善如流"],
                ],
            },
            {
                "name": "贞观之治",
                "points": 2,
                "keywords": [["贞观之治", "贞观"]],
            },
        ],
    },

    # ── 第(3)题 共4分 ────────────────────────────────────────────────────────
    # 两层匹配：
    #   exact_keywords  - 准确/较准确近义表达，命中即算精确命中（每条1分，最多4分）
    #   fuzzy_keywords  - 概括性/模糊性表达，方向正确但不够具体
    "q3": {
        "max": 4,
        "measures": [
            {
                "name": "解除禁军高级将领的兵权",
                # 精确匹配：必须同时体现"解除/收回"和"禁军/将领/兵权"
                "exact_keywords": [
                    ["解除", "收回", "夺取", "剥夺", "杯酒释兵权", "释兵权"],
                    ["禁军", "将领", "兵权", "军权"],
                ],
                # 模糊匹配：只提到"兵权"或"收兵"，但不够具体
                "fuzzy_keywords": [
                    ["收其精兵", "收精兵", "收兵权", "夺兵权", "削兵权"],
                ],
            },
            {
                "name": "任用文臣管理军务（以文制武）",
                "exact_keywords": [
                    ["文臣", "文官", "以文制武", "文官管军"],
                    ["管理军务", "管军", "统兵", "领兵", "军务", "军事"],
                ],
                "fuzzy_keywords": [
                    ["以文制武"],  # 单独出现"以文制武"算模糊命中
                ],
            },
            {
                "name": "禁军将领握兵之重而无发兵之权",
                "exact_keywords": [
                    ["握兵之重", "发兵之权", "有兵无权", "兵权分离"],
                ],
                "fuzzy_keywords": [],
            },
            {
                "name": "经常调换军队将领，定期换防",
                "exact_keywords": [
                    ["调换", "轮换", "换防", "调动将领", "更换将领", "轮调"],
                    ["将领", "军队", "驻军"],
                ],
                "fuzzy_keywords": [
                    ["稍夺其权"],  # "稍夺其权"方向相关但过于笼统
                ],
            },
            {
                "name": "派文臣担任各地州县长官",
                "exact_keywords": [
                    ["文臣", "文官"],
                    ["州县", "知州", "知县", "长官", "地方官", "担任地方"],
                ],
                "fuzzy_keywords": [],
            },
            {
                "name": "设置通判，分知州权力",
                "exact_keywords": [
                    ["通判"],
                ],
                "fuzzy_keywords": [],
            },
            {
                "name": "取消节度使收税的权力",
                "exact_keywords": [
                    ["节度使", "藩镇"],
                    ["收税", "税收", "财权", "赋税", "取消", "收回", "剥夺"],
                ],
                # "制其钱谷"方向相关（控制财政），但不够准确对应"取消节度使收税权"
                "fuzzy_keywords": [
                    ["制其钱谷", "钱谷", "控制财政", "削弱财权", "稍夺其权"],
                ],
            },
        ],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# 核心匹配函数
# ──────────────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    text = re.sub(r"[\s　\r\n①②③④⑤⑥]+", "", text)
    text = text.replace("，", ",").replace("。", ".").replace("；", ";")
    return text


def _match_point(text: str, keyword_groups: list) -> bool:
    """AND 逻辑：每组至少命中一个关键词，所有组都命中才返回 True。"""
    for group in keyword_groups:
        if not any(kw in text for kw in group):
            return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# 第(1)(2)题评分
# ──────────────────────────────────────────────────────────────────────────────

def _grade_q1(text: str):
    norm = _normalize(text)
    r = SCORING_RULES["q1"]
    score, matched, missing = 0, [], []

    # 科举制 2分
    keju = r["keju"]
    if _match_point(norm, keju["keywords"]):
        score += keju["points"]
        matched.append(keju["name"])
    else:
        missing.append(keju["name"])

    # 政治影响阶梯分
    hit = 0
    for pt in r["influence_points"]:
        if _match_point(norm, pt["keywords"]):
            hit += 1
            matched.append(pt["name"])
        else:
            missing.append(pt["name"])
    score += r["influence_ladder"][min(hit, 3)]
    return min(score, r["max"]), matched, missing


def _grade_q2(text: str):
    norm = _normalize(text)
    r = SCORING_RULES["q2"]
    score, matched, missing = 0, [], []
    for pt in r["points"]:
        if _match_point(norm, pt["keywords"]):
            score += pt["points"]
            matched.append(pt["name"])
        else:
            missing.append(pt["name"])
    return min(score, r["max"]), matched, missing


# ──────────────────────────────────────────────────────────────────────────────
# 第(3)题评分（两层匹配）
# ──────────────────────────────────────────────────────────────────────────────

def _grade_q3(text: str):
    """
    两层匹配逻辑：
    - exact_matches：准确命中标准措施（每条1分，最多4分）
    - fuzzy_matches：方向正确但表述概括/模糊（不直接计入精确分）

    降档规则：
    - 精确命中 >= 1 条：按精确命中数给分（上限4分）
    - 精确命中 = 0，但有模糊命中：
        - 模糊命中 >= 2 条：给 2 分（概括型答案上限）
        - 模糊命中 = 1 条：给 1 分
    - 两者均无：0 分

    典型案例："收其精兵；稍夺其权；制其钱谷；发展文教"
    -> 精确命中 0 条，模糊命中 3 条 -> 给 2 分
    """
    norm = _normalize(text)
    r = SCORING_RULES["q3"]

    exact_matches = []   # 准确命中的措施名
    fuzzy_matches = []   # 模糊命中的措施名
    missing = []

    for measure in r["measures"]:
        name = measure["name"]
        exact_kw = measure.get("exact_keywords", [])
        fuzzy_kw = measure.get("fuzzy_keywords", [])

        if exact_kw and _match_point(norm, exact_kw):
            # 精确命中
            exact_matches.append(name)
        elif fuzzy_kw and any(_match_point(norm, [grp]) for grp in fuzzy_kw):
            # 模糊命中（只要命中任意一个模糊关键词组即算）
            fuzzy_matches.append(name)
        else:
            missing.append(name)

    # ── 计分 ──────────────────────────────────────────────────────
    exact_count = len(exact_matches)
    fuzzy_count = len(fuzzy_matches)

    if exact_count >= 2:
        score = 4
        reason = f"精确命中{exact_count}条，满分"
    elif exact_count == 1:
        score = 2
        reason = "精确命中1条，得2分"
    elif fuzzy_count >= 2:
        score = 2
        reason = f"无精确命中，模糊命中{fuzzy_count}条，概括型答案给2分"
    elif fuzzy_count == 1:
        score = 1
        reason = "无精确命中，模糊命中1条，给1分"
    else:
        score = 0
        reason = "无命中"

    return (
        min(score, r["max"]),
        exact_matches,
        fuzzy_matches,
        missing,
        reason,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 拆题
# ──────────────────────────────────────────────────────────────────────────────

def _split_by_question(text: str):
    patterns = [
        r"[（(]\s*1\s*[）)]",
        r"[（(]\s*2\s*[）)]",
        r"[（(]\s*3\s*[）)]",
    ]
    pos = []
    for p in patterns:
        m = re.search(p, text)
        pos.append(m.start() if m else -1)

    p1, p2, p3 = pos
    if p1 == -1 and p2 == -1 and p3 == -1:
        return text, text, text

    boundaries = sorted([(p, i) for i, p in enumerate(pos) if p != -1])

    def get_seg(qi):
        for idx, (start, _) in enumerate(boundaries):
            end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(text)
            chunk = text[start:end]
            if re.search(patterns[qi], chunk):
                return chunk
        return text

    return get_seg(0), get_seg(1), get_seg(2)


# ──────────────────────────────────────────────────────────────────────────────
# 主评分函数（对外接口）
# ──────────────────────────────────────────────────────────────────────────────

def grade_answer(student_text: str) -> dict:
    """
    对第14题学生答案进行辅助评分。

    返回字典：
        score_q1, score_q2, score_q3, total_score
        matched_points  - 命中点（q3 细分为 exact / fuzzy）
        missing_points  - 漏掉点
        q3_reason       - 第(3)题计分说明
        comment         - 简短评语
    """
    t1, t2, t3 = _split_by_question(student_text)

    s1, m1, miss1 = _grade_q1(t1)
    s2, m2, miss2 = _grade_q2(t2)
    s3, exact3, fuzzy3, miss3, reason3 = _grade_q3(t3)

    total = s1 + s2 + s3

    lines = []
    if s1 == 6:
        lines.append("第(1)题答得完整。")
    elif s1 >= 4:
        lines.append(f"第(1)题基本到位，漏了：{'、'.join(miss1)}。")
    else:
        lines.append(f"第(1)题得分较低，漏了：{'、'.join(miss1)}。")

    if s2 == 4:
        lines.append("第(2)题全对。")
    else:
        lines.append(f"第(2)题漏了：{'、'.join(miss2)}。")

    if s3 == 4:
        lines.append(f"第(3)题满分（{reason3}）。")
    else:
        lines.append(f"第(3)题{s3}分（{reason3}）。")

    return {
        "score_q1": s1,
        "score_q2": s2,
        "score_q3": s3,
        "total_score": total,
        "matched_points": {
            "q1": m1,
            "q2": m2,
            "q3_exact": exact3,   # 精确命中
            "q3_fuzzy": fuzzy3,   # 模糊命中
        },
        "missing_points": {"q1": miss1, "q2": miss2, "q3": miss3},
        "q3_reason": reason3,
        "comment": " ".join(lines),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 格式化输出
# ──────────────────────────────────────────────────────────────────────────────

def print_result(result: dict, label: str = "") -> None:
    sep = "─" * 52
    if label:
        print(f"\n{'═'*52}")
        print(f"  {label}")
        print(f"{'═'*52}")
    else:
        print(f"\n{sep}")

    print(f"  第(1)题：{result['score_q1']} / 6 分")
    print(f"  第(2)题：{result['score_q2']} / 4 分")
    print(f"  第(3)题：{result['score_q3']} / 4 分")
    print(f"  总  分：{result['total_score']} / 14 分")
    print(sep)

    for q, lbl in [("q1", "第(1)题"), ("q2", "第(2)题")]:
        if result["matched_points"][q]:
            print(f"  [+] {lbl} 命中：{' | '.join(result['matched_points'][q])}")
        if result["missing_points"][q]:
            print(f"  [-] {lbl} 漏掉：{' | '.join(result['missing_points'][q])}")

    # 第(3)题单独展示精确/模糊
    exact3 = result["matched_points"]["q3_exact"]
    fuzzy3 = result["matched_points"]["q3_fuzzy"]
    miss3  = result["missing_points"]["q3"]
    if exact3:
        print(f"  [+] 第(3)题 精确命中：{' | '.join(exact3)}")
    if fuzzy3:
        print(f"  [~] 第(3)题 模糊命中：{' | '.join(fuzzy3)}")
    if miss3:
        print(f"  [-] 第(3)题 漏掉：{' | '.join(miss3)}")
    print(f"  [?] 第(3)题 计分说明：{result['q3_reason']}")

    print(sep)
    print(f"  评语：{result['comment']}")
    print(sep)


# ──────────────────────────────────────────────────────────────────────────────
# 测试样例
# ──────────────────────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "label": "样例1：答案较完整（预期第3题4分）",
        "text": (
            "（1）隋唐时期实行科举制，通过考试选拔官员，扩大了统治集团的社会基础，"
            "使旧贵族逐渐消失，皇帝扩大了专制权力。"
            "（2）唐太宗的治国理念是重用人才，善于纳谏，从而出现了贞观之治的盛世局面。"
            "（3）宋太祖采取了以下措施：解除禁军高级将领的兵权；任用文臣管理军务，"
            "使禁军将领有握兵之重而无发兵之权；经常调换军队将领，定期换防；"
            "派文臣担任各地州县的长官；设置通判，以分知州的权力；取消节度使收税的权力。"
        ),
    },
    {
        "label": "样例2：部分作答，有同义表达（预期第3题4分）",
        "text": (
            "（1）科举考试制度，拓宽了统治阶层的社会基础，门阀贵族逐渐衰落，君权得到加强。"
            "（2）唐太宗广纳贤才，从谏如流，出现了贞观之治。"
            "（3）宋朝杯酒释兵权，以文制武，设置通判监督地方，取消藩镇的财权。"
        ),
    },
    {
        "label": "样例3：答案较差（预期第3题2分）",
        "text": (
            "（1）科举制，皇权加强。"
            "（2）贞观之治。"
            "（3）宋太祖解除了将领的兵权，派文官管理地方。"
        ),
    },
    {
        "label": "样例4：概括型答案——收其精兵等（预期第3题2分）",
        "text": (
            "（3）措施：①收其精兵；②稍夺其权；③制其钱谷；④发展文教。"
        ),
    },
]


if __name__ == "__main__":
    for case in TEST_CASES:
        result = grade_answer(case["text"])
        print_result(result, label=case["label"])

    # 交互模式
    print("\n" + "═" * 52)
    print("  进入交互模式（直接回车跳过）")
    print("  粘贴学生答案后，输入空行+回车结束输入")
    print("═" * 52)
    lines_input = []
    try:
        while True:
            line = input()
            if line == "" and lines_input:
                break
            lines_input.append(line)
    except (EOFError, KeyboardInterrupt):
        pass

    if lines_input:
        result = grade_answer("\n".join(lines_input))
        print_result(result, label="手动输入评分结果")
