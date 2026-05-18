# -*- coding: utf-8 -*-
"""
第14题自动阅卷辅助脚本 v3
流程：Selenium截图 -> 图像预处理 -> OCR识别(手写体) -> 自动评分 -> 弹窗显示结果 -> 循环下一题

【OCR方案说明】
手写中文识别需要专用模型，本脚本支持两种方案：

方案A（推荐，识别率最高）：百度云"手写文字识别" API
  1. 注册百度智能云：https://console.bce.baidu.com/
  2. 进入"文字识别" -> 创建应用 -> 获取 API Key 和 Secret Key
  3. 免费额度：每天500次，手写识别每次约0.1元（超出后）
  4. 将下方 BAIDU_API_KEY / BAIDU_SECRET_KEY 填入即可

方案B（本地，无需API，但手写识别有限）：PaddleOCR
  pip install paddlepaddle paddleocr
  不填写百度Key时自动使用此方案

安装依赖：
    pip install selenium pillow opencv-python paddlepaddle paddleocr requests
"""

import sys
import os
import time
import re

# ══════════════════════════════════════════════════════════════════
#  可调配置区
# ══════════════════════════════════════════════════════════════════

USE_EXISTING_BROWSER  = False          # True=连接已有Chrome(需--remote-debugging-port=9222)
CHROME_DEBUG_PORT     = 9222
PAGE_URL              = "https://ejt.xkw.com/exam/index"
LOGIN_WAIT_SECONDS    = 60             # 首次登录等待秒数，按回车可提前跳过

OUTPUT_DIR            = r"C:\Users\22860\Desktop\cluade\screenshots"
RAW_SCREENSHOT        = os.path.join(OUTPUT_DIR, "raw_fullpage.png")
CROPPED_IMAGE         = os.path.join(OUTPUT_DIR, "q14_cropped.png")
PROCESSED_IMAGE       = os.path.join(OUTPUT_DIR, "q14_processed.png")

# CSS定位器列表（按优先级，第一个成功即用）
ANSWER_AREA_SELECTORS = [
    "div.answer-area",
    "div.student-answer",
    "div.stu-answer",
    "div[class*='answer']",
    "div[class*='paper']",
    "img[class*='paper']",
    "div.exam-content",
    "div.question-content",
]

# 坐标裁剪备用方案 (left, top, right, bottom)
# 先运行一次查看 raw_fullpage.png，用画图量出第14题答案区域后修改此处
CROP_BOX = (176, 191, 1766, 1293)

# 图像预处理参数
# 原图裁剪后已是 1590×1102，无需放大；放大反而使文件超出百度4MB限制
SCALE_FACTOR  = 1.0    # 1.0=不放大，仅在原图<800px时才放大
BAIDU_MAX_MB  = 3.5    # API调用前如超过此值(MB)自动JPEG压缩

# ── 百度OCR（手写文字识别，推荐，不填则使用PaddleOCR）───────────
# 申请地址：https://console.bce.baidu.com/ -> 文字识别 -> 创建应用
BAIDU_API_KEY    = ""   # ← 填入你的 API Key
BAIDU_SECRET_KEY = ""   # ← 填入你的 Secret Key

# OCR本地参数（PaddleOCR兜底用）
OCR_GPU = False

# 循环模式：每题评完弹窗，关闭弹窗后等待此秒数再截图下一题
NEXT_QUESTION_WAIT = 5   # 秒，给网页切换到下一题的时间

# ══════════════════════════════════════════════════════════════════
#  评分规则
# ══════════════════════════════════════════════════════════════════

SCORING_RULES = {
    "q1": {
        "max": 6,
        "keju": {
            "name": "科举制",
            "points": 2,
            "keywords": [["科举制", "科举制度", "科举选官", "科举考试",
                          "通过考试选官", "以考试取士", "考试选拔官员",
                          "科举", "考试取士", "开科取士"]],
        },
        "influence_points": [
            {
                "name": "扩大统治基础",
                "keywords": [
                    ["扩大", "拓宽", "拓展", "扩展", "广泛", "增加"],
                    ["统治基础", "社会基础", "统治集团", "统治阶层",
                     "官员来源", "选官范围", "统治阶级基础"],
                ],
            },
            {
                "name": "旧贵族衰落/消失",
                "keywords": [
                    ["旧贵族", "门阀", "世家大族", "贵族", "门第",
                     "士族", "门阀士族"],
                    ["消失", "衰落", "衰亡", "没落", "瓦解",
                     "削弱", "式微", "逐渐消失", "下降", "减弱"],
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
        "influence_ladder": {0: 0, 1: 2, 2: 4, 3: 4},
    },
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
                    ["纳谏", "接受谏言", "广开言路", "虚心纳谏",
                     "从谏如流", "纳谏如流", "接受意见", "听取意见",
                     "从善如流", "乐于听取", "善听建议", "接受大臣劝谏"],
                ],
            },
            {
                "name": "贞观之治",
                "points": 2,
                "keywords": [
                    ["贞观之治", "贞观盛世", "贞观",
                     "唐太宗时期的盛世", "唐太宗开创的治世"],
                ],
            },
        ],
    },
    "q3": {
        "max": 4,
        "measures": [
            {
                "name": "解除禁军高级将领的兵权",
                "exact_keywords": [
                    ["解除", "收回", "夺取", "剥夺", "杯酒释兵权", "释兵权"],
                    ["禁军", "将领", "兵权", "军权"],
                ],
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
                    ["以文制武"],
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
                    ["稍夺其权"],
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
                "fuzzy_keywords": [
                    ["制其钱谷", "钱谷", "控制财政", "削弱财权", "稍夺其权"],
                ],
            },
        ],
    },
}

# ══════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════

def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _normalize(text: str) -> str:
    text = re.sub(r"[\s　\r\n]+", "", text)
    text = text.replace("，", ",").replace("。", ".").replace("；", ";")
    return text


def _match_point(text: str, keyword_groups: list) -> bool:
    for group in keyword_groups:
        if not any(kw in text for kw in group):
            return False
    return True


# ══════════════════════════════════════════════════════════════════
#  截图
# ══════════════════════════════════════════════════════════════════

def capture_answer_region(driver) -> str:
    from selenium.webdriver.common.by import By
    from PIL import Image
    import io

    _ensure_dir(OUTPUT_DIR)

    for selector in ANSWER_AREA_SELECTORS:
        try:
            el = driver.find_element(By.CSS_SELECTOR, selector)
            if el.is_displayed():
                png = el.screenshot_as_png
                img = Image.open(io.BytesIO(png))
                img.save(CROPPED_IMAGE)
                print(f"[截图] CSS定位成功：{selector}")
                return CROPPED_IMAGE
        except Exception:
            continue

    print("[截图] CSS定位失败，使用整页截图+坐标裁剪")
    driver.save_screenshot(RAW_SCREENSHOT)
    img = Image.open(RAW_SCREENSHOT)
    cropped = img.crop(CROP_BOX)
    cropped.save(CROPPED_IMAGE)
    print(f"[截图] 裁剪图已保存：{CROPPED_IMAGE}  (CROP_BOX={CROP_BOX})")
    return CROPPED_IMAGE



# ══════════════════════════════════════════════════════════════════
#  Step 4: 图像预处理（手写体优化版 v3）
# ══════════════════════════════════════════════════════════════════

def preprocess_image(image_path: str) -> str:
    import cv2, numpy as np
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"无法读取图片：{image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 只在图片太小时才放大；原图已是1590x1102，不需要额外放大
    if max(h, w) < 800 or SCALE_FACTOR > 1.0:
        scale = max(SCALE_FACTOR, 1000 / max(h, w)) if max(h, w) < 800 else SCALE_FACTOR
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        h, w = gray.shape

    # CLAHE 对比度增强
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 去除答题纸横线（答题纸上的印刷横线会干扰OCR）
    horiz_len = max(w // 5, 50)
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horiz_len, 1))
    horiz_lines = cv2.morphologyEx(enhanced, cv2.MORPH_OPEN, horiz_kernel, iterations=1)
    no_lines = cv2.subtract(enhanced, horiz_lines)

    # 保存灰度版（供百度API用）
    cv2.imwrite(PROCESSED_IMAGE, no_lines)

    # 保存二值版（供PaddleOCR用），轻微加粗笔画
    _, binary = cv2.threshold(no_lines, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8)
    binary = cv2.dilate(binary, kernel, iterations=1)
    binary_path = PROCESSED_IMAGE.replace(".png", "_binary.png")
    cv2.imwrite(binary_path, binary)

    size_kb = os.path.getsize(PROCESSED_IMAGE) // 1024
    print(f"[预处理] 完成 ({w}x{h}, {size_kb}KB)：{PROCESSED_IMAGE}")
    return PROCESSED_IMAGE


def _compress_for_api(image_path: str, max_mb: float = 3.5) -> str:
    """图片超过 max_mb 时转JPEG压缩，百度API限4MB。"""
    import cv2
    size_mb = os.path.getsize(image_path) / (1024 * 1024)
    if size_mb <= max_mb:
        return image_path
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    jpeg_path = image_path.replace(".png", "_compressed.jpg")
    for quality in [85, 70, 55, 40]:
        cv2.imwrite(jpeg_path, img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if os.path.getsize(jpeg_path) / (1024 * 1024) <= max_mb:
            print(f"[预处理] 压缩至JPEG(q={quality}): {os.path.getsize(jpeg_path)//1024}KB")
            return jpeg_path
    return jpeg_path


def _split_into_regions(image_path: str) -> list:
    """
    检测竖向空白区域，将答卷切分为3道小题分别OCR。
    分区识别比整图识别准确率更高。
    """
    import cv2, numpy as np
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    h, w = img.shape
    row_means = np.mean(img, axis=1)
    blank = np.where(row_means > 235)[0]

    gaps = []
    if len(blank) > 0:
        seg_s = blank[0]; prev = blank[0]
        for r in blank[1:]:
            if r - prev > 1:
                if prev - seg_s >= 8:
                    gaps.append((seg_s, prev))
                seg_s = r
            prev = r
        if prev - seg_s >= 8:
            gaps.append((seg_s, prev))
        gaps.sort(key=lambda x: x[1] - x[0], reverse=True)
        splits = sorted([g[0] for g in gaps[:2]])
    else:
        splits = [h // 3, 2 * h // 3]

    boundaries = [0] + splits + [h]
    regions = []
    for i in range(len(boundaries) - 1):
        y0, y1 = boundaries[i], boundaries[i + 1]
        if y1 - y0 < 40:
            continue
        crop = img[y0:y1, :]
        path = PROCESSED_IMAGE.replace(".png", f"_region{i+1}.png")
        cv2.imwrite(path, crop)
        regions.append(path)

    if len(regions) < 2:
        return [image_path]
    print(f"[预处理] 切分为{len(regions)}段，分界行：{splits}")
    return regions


# ══════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════
#  Step 5: OCR 识别（v3：分区识别 + 压缩 + 多接口降级）
# ══════════════════════════════════════════════════════════════════

_paddle_ocr = None


def _ocr_baidu(image_path: str) -> str:
    import base64, requests
    token_url = (
        "https://aip.baidubce.com/oauth/2.0/token"
        f"?grant_type=client_credentials"
        f"&client_id={BAIDU_API_KEY}&client_secret={BAIDU_SECRET_KEY}"
    )
    try:
        access_token = requests.post(token_url, timeout=10).json().get("access_token", "")
        if not access_token:
            return ""
    except Exception as e:
        print(f"[OCR] 百度Token失败：{e}"); return ""

    send_path = _compress_for_api(image_path, max_mb=BAIDU_MAX_MB)
    print(f"[OCR] 百度API，图片大小：{os.path.getsize(send_path)//1024}KB")
    with open(send_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    def _call(endpoint, label, extra=None):
        url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/{endpoint}?access_token={access_token}"
        data = {"image": img_b64}
        if extra:
            data.update(extra)
        try:
            result = requests.post(
                url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=data, timeout=20).json()
        except Exception as e:
            print(f"[OCR] {label}请求失败：{e}"); return None
        ec = result.get("error_code")
        if ec in (6, 17):
            print(f"[OCR] {label} error {ec}，跳过"); return None
        if ec:
            print(f"[OCR] {label} error {ec}: {result.get('error_msg')}"); return None
        words = [item["words"] for item in result.get("words_result", [])]
        if words:
            print(f"[OCR] {label} 识别到{len(words)}行")
        return chr(10).join(words)

    for ep, lb, ex in [
        ("handwriting",    "手写识别",   {"recognize_granularity": "big"}),
        ("accurate_basic", "高精度版",   None),
        ("general_basic",  "通用标准版", None),
    ]:
        t = _call(ep, lb, ex)
        if t is not None:
            return t
    return ""


def _ocr_paddle(image_path: str) -> str:
    global _paddle_ocr
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("[错误] pip install paddlepaddle paddleocr"); sys.exit(1)
    if _paddle_ocr is None:
        print("[OCR] 初始化 PaddleOCR...")
        _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="ch", use_gpu=OCR_GPU)
        print("[OCR] 初始化完成")
    binary_path = image_path.replace(".png", "_binary.png")
    ocr_path = binary_path if os.path.exists(binary_path) else image_path
    result = _paddle_ocr.ocr(ocr_path, cls=True)
    lines = []
    if result and result[0]:
        for item in sorted(result[0], key=lambda x: x[0][0][1]):
            conf, text = item[1][1], item[1][0]
            if conf > 0.15 and text.strip():
                lines.append(text)
    return chr(10).join(lines)


def _print_ocr_result(text: str, source: str) -> None:
    sep = "─" * 52
    print(f"\n{sep}")
    print(f"【OCR识别原文 - {source}】（请核对是否准确）")
    print(sep)
    print(text.strip() if text.strip() else "（未识别到文字，请检查截图和API配置）")
    print(sep + "\n")


def ocr_image(image_path: str) -> str:
    """
    先将图像切分为若干行区域，对每区域分别OCR，最后拼合。
    优先百度API（填写了Key时），否则用PaddleOCR。
    """
    regions = _split_into_regions(image_path)
    parts = []
    source = "百度手写OCR" if (BAIDU_API_KEY and BAIDU_SECRET_KEY) else "PaddleOCR"
    for i, rpath in enumerate(regions):
        print(f"[OCR] 识别区域 {i+1}/{len(regions)}...")
        text = ""
        if BAIDU_API_KEY and BAIDU_SECRET_KEY:
            text = _ocr_baidu(rpath)
        if not text.strip():
            if BAIDU_API_KEY and BAIDU_SECRET_KEY:
                print("[OCR] 百度API未返回内容，回退到 PaddleOCR...")
                source = "PaddleOCR"
            text = _ocr_paddle(rpath)
        parts.append(text)
    combined = chr(10).join(p for p in parts if p.strip())
    _print_ocr_result(combined, source)
    return combined



# ══════════════════════════════════════════════════════════════════
#  自动评分
# ══════════════════════════════════════════════════════════════════

def _split_by_question(text: str):
    patterns = [r"[（(]\s*1\s*[）)]", r"[（(]\s*2\s*[）)]", r"[（(]\s*3\s*[）)]"]
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


def grade_answer(student_text: str) -> dict:
    t1, t2, t3 = _split_by_question(student_text)
    n1, n2, n3 = _normalize(t1), _normalize(t2), _normalize(t3)

    # 第(1)题
    r1 = SCORING_RULES["q1"]
    s1, m1, miss1 = 0, [], []
    keju = r1["keju"]
    if _match_point(n1, keju["keywords"]):
        s1 += keju["points"]; m1.append(keju["name"])
    else:
        miss1.append(keju["name"])
    hit_inf = 0
    for pt in r1["influence_points"]:
        if _match_point(n1, pt["keywords"]):
            hit_inf += 1; m1.append(pt["name"])
        else:
            miss1.append(pt["name"])
    s1 += r1["influence_ladder"][min(hit_inf, 3)]
    s1 = min(s1, r1["max"])

    # 第(2)题
    r2 = SCORING_RULES["q2"]
    s2, m2, miss2 = 0, [], []
    for pt in r2["points"]:
        if _match_point(n2, pt["keywords"]):
            s2 += pt["points"]; m2.append(pt["name"])
        else:
            miss2.append(pt["name"])
    s2 = min(s2, r2["max"])

    # 第(3)题（两层匹配：精确/模糊）
    r3 = SCORING_RULES["q3"]
    exact3, fuzzy3, miss3 = [], [], []
    for measure in r3["measures"]:
        name = measure["name"]
        exact_kw = measure.get("exact_keywords", [])
        fuzzy_kw = measure.get("fuzzy_keywords", [])
        if exact_kw and _match_point(n3, exact_kw):
            exact3.append(name)
        elif fuzzy_kw and any(_match_point(n3, [grp]) for grp in fuzzy_kw):
            fuzzy3.append(name)
        else:
            miss3.append(name)

    ec, fc = len(exact3), len(fuzzy3)
    if ec >= 2:
        s3, q3_reason = 4, f"精确命中{ec}条，满分"
    elif ec == 1:
        s3, q3_reason = 2, "精确命中1条，得2分"
    elif fc >= 2:
        s3, q3_reason = 2, f"无精确命中，模糊命中{fc}条，概括型给2分"
    elif fc == 1:
        s3, q3_reason = 1, "无精确命中，模糊命中1条，给1分"
    else:
        s3, q3_reason = 0, "无命中"
    s3 = min(s3, r3["max"])

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
        lines.append(f"第(3)题满分（{q3_reason}）。")
    else:
        lines.append(f"第(3)题{s3}分（{q3_reason}）。")

    return {
        "score_q1": s1, "score_q2": s2, "score_q3": s3,
        "total_score": total,
        "matched_points": {"q1": m1, "q2": m2,
                           "q3_exact": exact3, "q3_fuzzy": fuzzy3},
        "missing_points": {"q1": miss1, "q2": miss2, "q3": miss3},
        "q3_reason": q3_reason,
        "comment": " ".join(lines),
    }


# ══════════════════════════════════════════════════════════════════
#  终端输出
# ══════════════════════════════════════════════════════════════════

def print_result(result: dict) -> None:
    sep = "─" * 52
    print("\n" + "═" * 52)
    print("  第14题 自动评分结果")
    print("═" * 52)
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
    print("═" * 52 + "\n")


# ══════════════════════════════════════════════════════════════════
#  弹窗显示结果（tkinter，关闭后继续下一题）
# ══════════════════════════════════════════════════════════════════

def show_result_popup(result: dict, ocr_text: str, driver=None) -> None:
    """
    弹出评分窗口。
    - 每道题显示 0~max 的分值按钮，推荐分高亮显示。
    - 点击任意分值按钮即可调整。
    - 点击「提交」按钮自动在网页填分并关闭窗口。
    """
    import tkinter as tk
    from tkinter import scrolledtext

    root = tk.Tk()
    root.title(f"第14题  总分：{result['total_score']}/14")
    root.geometry("560x580")
    root.resizable(True, True)
    root.attributes("-topmost", True)

    q1_var = tk.IntVar(value=result["score_q1"])
    q2_var = tk.IntVar(value=result["score_q2"])
    q3_var = tk.IntVar(value=result["score_q3"])

    # ── 蓝色标题 ──────────────────────────────────────────────────
    hdr = tk.Frame(root, bg="#1a73e8", pady=7)
    hdr.pack(fill="x")
    total_lbl = tk.Label(hdr,
        text=f"推荐总分  {result['total_score']} / 14",
        font=("Microsoft YaHei", 17, "bold"), fg="white", bg="#1a73e8")
    total_lbl.pack()
    tk.Label(hdr, text="点击分值按钮可调整，再点「提交」自动打分",
        font=("Microsoft YaHei", 9), fg="#cce0ff", bg="#1a73e8").pack()

    # ── 分题分值选择 ───────────────────────────────────────────────
    sel_frame = tk.Frame(root, pady=6, padx=12, bg="#f0f4ff")
    sel_frame.pack(fill="x")

    submit_btn_ref = [None]   # 用列表持有 submit_btn 引用，供内部函数更新文字

    def make_score_row(parent, label_text, var, max_score, row):
        tk.Label(parent, text=label_text,
                 font=("Microsoft YaHei", 10, "bold"),
                 bg="#f0f4ff", width=11, anchor="w").grid(
                     row=row, column=0, padx=4, pady=4)
        btn_refs = []

        def _select(v):
            var.set(v)
            for i, b in enumerate(btn_refs):
                b.config(
                    bg="#1a73e8" if i == v else "#dce8ff",
                    fg="white"   if i == v else "#333",
                )
            new_total = q1_var.get() + q2_var.get() + q3_var.get()
            total_lbl.config(text=f"推荐总分  {new_total} / 14")
            if submit_btn_ref[0]:
                submit_btn_ref[0].config(text=f"提交  {new_total} 分，下一题")

        for v in range(max_score + 1):
            b = tk.Button(parent, text=str(v), width=3,
                font=("Microsoft YaHei", 10),
                bg="#1a73e8" if v == var.get() else "#dce8ff",
                fg="white"   if v == var.get() else "#333",
                relief="flat", bd=1,
                command=lambda x=v: _select(x))
            b.grid(row=row, column=1 + v, padx=2, pady=4)
            btn_refs.append(b)

    make_score_row(sel_frame, "第(1)题  /6:", q1_var, 6, 0)
    make_score_row(sel_frame, "第(2)题  /4:", q2_var, 4, 1)
    make_score_row(sel_frame, "第(3)题  /4:", q3_var, 4, 2)

    # ── 命中/漏掉详情 ─────────────────────────────────────────────
    detail_frame = tk.Frame(root, padx=10, pady=4)
    detail_frame.pack(fill="both", expand=True)

    lines = []
    for q, lbl in [("q1", "第(1)题"), ("q2", "第(2)题")]:
        if result["matched_points"][q]:
            lines.append(f"[+] {lbl} 命中：{' | '.join(result['matched_points'][q])}")
        if result["missing_points"][q]:
            lines.append(f"[-] {lbl} 漏掉：{' | '.join(result['missing_points'][q])}")
    exact3 = result["matched_points"]["q3_exact"]
    fuzzy3 = result["matched_points"]["q3_fuzzy"]
    miss3  = result["missing_points"]["q3"]
    if exact3:
        lines.append(f"[+] 第(3)题 精确：{' | '.join(exact3)}")
    if fuzzy3:
        lines.append(f"[~] 第(3)题 模糊：{' | '.join(fuzzy3)}")
    if miss3:
        lines.append(f"[-] 第(3)题 漏掉：{' | '.join(miss3)}")
    lines.append(f"[?] 第(3)题：{result['q3_reason']}")
    lines.append("")
    lines.append("── OCR识别原文（供核对）──")
    lines.append(ocr_text[:500] + ("..." if len(ocr_text) > 500 else ""))

    txt = scrolledtext.ScrolledText(detail_frame, font=("Microsoft YaHei", 9),
                                    wrap="word", height=10)
    txt.pack(fill="both", expand=True)
    txt.insert("end", "\n".join(lines))
    txt.config(state="disabled")

    # ── 提交按钮 ──────────────────────────────────────────────────
    btn_frame = tk.Frame(root, pady=6)
    btn_frame.pack()

    def on_submit():
        q1 = q1_var.get()
        q2 = q2_var.get()
        q3 = q3_var.get()
        total = q1 + q2 + q3
        root.destroy()
        if driver:
            try:
                ok = auto_submit_score(driver, q1, q2, q3)
                if not ok:
                    print(f"[提示] 请手动打分：第(1)题{q1}  第(2)题{q2}  第(3)题{q3}  合计{total}")
            except Exception as e:
                print(f"[自动提交] 异常：{e}")
                print(f"[提示] 请手动打分：合计{total}分")
        else:
            print(f"[提示] 未连接浏览器，请手动打分：合计{total}分")

    init_total = result["total_score"]
    sbtn = tk.Button(btn_frame,
        text=f"提交  {init_total} 分，下一题",
        font=("Microsoft YaHei", 12, "bold"),
        bg="#27ae60", fg="white", padx=20, pady=8,
        command=on_submit)
    sbtn.pack(pady=4)
    submit_btn_ref[0] = sbtn

    root.mainloop()


# ══════════════════════════════════════════════════════════════════
#  自动填分（Selenium）
# ══════════════════════════════════════════════════════════════════

def auto_submit_score(driver, q1: int, q2: int, q3: int) -> bool:
    """
    在网页打分面板中自动填入各题分数并提交。
    返回 True = 已操作成功，False = 未找到打分界面（需手动）。
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    import time

    total = q1 + q2 + q3

    def _find_visible(selector):
        try:
            return [e for e in driver.find_elements(By.CSS_SELECTOR, selector)
                    if e.is_displayed() and e.is_enabled()]
        except Exception:
            return []

    def _set_input(el, value: int):
        """兼容普通 input 和 React/Vue 受控组件的赋值方式。"""
        try:
            driver.execute_script("""
                var el = arguments[0], val = arguments[1].toString();
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(el, val);
                el.dispatchEvent(new Event('input',  {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
            """, el, value)
        except Exception:
            el.click()
            el.send_keys(Keys.CONTROL + "a")
            el.send_keys(str(value))
        time.sleep(0.15)

    def _click_submit():
        for sel in [
            "button[class*='submit']", "button[class*='confirm']",
            "button[class*='save']",   "button[class*='提交']",
            ".submit-score",           ".btn-submit",
            ".confirm-btn",            "button.primary",
            "input[type='submit']",
        ]:
            btns = _find_visible(sel)
            if btns:
                btns[0].click()
                time.sleep(0.3)
                print(f"[自动提交] 已点击提交按钮 ({sel})")
                return True
        return False

    # ── 方案1：找数字/文本输入框 ──────────────────────────────────
    inputs = []
    for sel in [
        "input[type='number']",
        "input[class*='score']",
        "input[class*='grade']",
        "input[class*='mark']",
        ".score-input input",
        ".score-wrap input",
        ".grade-item input",
        ".mark-input",
    ]:
        found = _find_visible(sel)
        if found:
            inputs = found
            print(f"[自动提交] 找到 {len(inputs)} 个打分输入框 ({sel})")
            break

    if inputs:
        if len(inputs) == 1:
            _set_input(inputs[0], total)
            print(f"[自动提交] 总分输入 {total}")
        else:
            for el, val in zip(inputs[:3], [q1, q2, q3]):
                _set_input(el, val)
            print(f"[自动提交] 分题输入 Q1={q1} Q2={q2} Q3={q3}")
        if _click_submit():
            return True
        print("[自动提交] 分数已填入，未找到提交按钮，请手动点提交")
        return True

    # ── 方案2：预设分值按钮（如「满分」「6分」等）─────────────────
    try:
        # 先试总分按钮
        for text in [str(total), f"{total}分"]:
            el = driver.execute_script(f"""
                var all = document.querySelectorAll('button, [class*="score-item"], [class*="score-btn"]');
                return Array.from(all).find(function(b){{
                    return b.offsetParent !== null && b.innerText.trim() === '{text}';
                }}) || null;
            """)
            if el:
                el.click()
                time.sleep(0.2)
                print(f"[自动提交] 点击分值按钮「{text}」")
                _click_submit()
                return True
    except Exception as e:
        print(f"[自动提交] 按钮方案异常：{e}")

    print("[自动提交] 未找到打分界面，请手动操作")
    return False


# ══════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════

def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    if USE_EXISTING_BROWSER:
        print(f"[浏览器] 连接已有 Chrome（端口 {CHROME_DEBUG_PORT}）...")
        options.add_experimental_option("debuggerAddress",
                                        f"127.0.0.1:{CHROME_DEBUG_PORT}")
        driver = webdriver.Chrome(options=options)
    else:
        print(f"[浏览器] 启动新 Chrome，跳转到：{PAGE_URL}")
        driver = webdriver.Chrome(options=options)
        driver.get(PAGE_URL)
        print(f"[浏览器] 请在 Chrome 中登录并导航到第14题。")
        print(f"[浏览器] 等待 {LOGIN_WAIT_SECONDS} 秒，按回车可提前跳过...")
        for remaining in range(LOGIN_WAIT_SECONDS, 0, -1):
            print(f"\r[等待] 还剩 {remaining:3d} 秒...", end="", flush=True)
            try:
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key in ('\r', '\n'):
                        print("\n[等待] 回车跳过，继续执行。")
                        break
            except Exception:
                pass
            time.sleep(1)
        else:
            print(f"\n[等待] 时间到，继续执行。")

    print(f"[浏览器] 当前页面：{driver.current_url}")

    question_count = 0
    print("\n[循环] 开始批改循环，关闭弹窗后自动处理下一题，Ctrl+C 退出。\n")

    while True:
        question_count += 1
        print(f"{'='*52}")
        print(f"[第 {question_count} 题] 开始截图...")

        try:
            time.sleep(1)  # 等页面稳定
            image_path = capture_answer_region(driver)
            processed_path = preprocess_image(image_path)
            student_text = ocr_image(processed_path)

            if not student_text.strip():
                print("[警告] OCR未识别到文字，请检查截图")
                print(f"  截图路径：{image_path}")
                print(f"  请确认 CROP_BOX={CROP_BOX} 是否覆盖了答案区域")
                print(f"  等待 {NEXT_QUESTION_WAIT} 秒后重试...")
                time.sleep(NEXT_QUESTION_WAIT)
                continue

            result = grade_answer(student_text)
            print_result(result)

            # 弹窗显示结果，等你打完分关闭
            show_result_popup(result, student_text, driver=driver)

            # 关闭弹窗后等待网页切换到下一题
            print(f"[循环] 弹窗已关闭，等待 {NEXT_QUESTION_WAIT} 秒后截图下一题...")
            time.sleep(NEXT_QUESTION_WAIT)

        except KeyboardInterrupt:
            print("\n[退出] 用户中断，结束批改。")
            break
        except Exception as e:
            print(f"[错误] {e}")
            print(f"等待 {NEXT_QUESTION_WAIT} 秒后继续...")
            time.sleep(NEXT_QUESTION_WAIT)

    if not USE_EXISTING_BROWSER:
        driver.quit()


if __name__ == "__main__":
    main()





