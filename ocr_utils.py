from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageOps, ImageFilter, ImageStat

try:
    import pytesseract
    from pytesseract import TesseractNotFoundError
except Exception:  # pragma: no cover
    pytesseract = None
    TesseractNotFoundError = Exception

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

# ─── constants ────────────────────────────────────────────────
_CHINESE_CHAR_PATTERN = re.compile(
    r"[一-鿿㐀-䶿豈-﫿]"
)
_CHINESE_PUNCT = set("，。、；：？！""''《》…—·「」『』（）【】｛｝")
_GARBAGE_PATTERNS = [
    re.compile(r"^[\x00-\x7f\s]{1,3}$"),       # short pure-ASCII lines
    re.compile(r"[^\w\s一-鿿]{4,}"),     # 4+ consecutive non-word symbols
    re.compile(r"(?<![a-zA-Z])[a-zA-Z]{1,2}(?![a-zA-Z])"),  # isolated 1-2 letters
]
# Tesseract output that is clearly noise — single letters / digit clusters / stray punctuation
_NOISE_LINE_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9]{1,3}|[^\w\s一-鿿]{1,4})\s*$"
)

# ─── image file detection ─────────────────────────────────────
def is_image_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in {
        ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif",
    }


# ─── enhanced preprocessing ───────────────────────────────────
def _otsu_threshold(image: Image.Image) -> Image.Image:
    """纯 PIL + numpy 实现的大津法（Otsu）二值化。"""
    arr = np.array(image, dtype=np.uint8)
    hist, _ = np.histogram(arr.flatten(), bins=256, range=(0, 256))
    total = hist.sum()
    if total == 0:
        return image
    sum_all = (np.arange(256) * hist).sum()
    weight_bg = 0.0
    sum_bg = 0.0
    max_var = 0.0
    threshold = 128
    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        var_between = weight_bg * weight_fg * ((mean_bg - mean_fg) ** 2)
        if var_between > max_var:
            max_var = var_between
            threshold = t
    return image.point(lambda p: 255 if p > threshold else 0).convert("1")


def _adaptive_threshold(image: Image.Image, block_size: int = 31, c: int = 8) -> Image.Image:
    """自适应局部二值化（Sauvola 风格，纯 PIL + numpy）。

    block_size 必须是奇数，c 是减去均值的常数偏移。
    """
    arr = np.array(image, dtype=np.float64)
    h, w = arr.shape
    pad = block_size // 2
    padded = np.pad(arr, pad, mode="edge")
    result = np.zeros_like(arr, dtype=np.uint8)

    # 使用积分图加速均值计算
    integral = np.cumsum(np.cumsum(padded, axis=0), axis=1)

    for y in range(h):
        for x in range(w):
            y1, y2 = y, y + block_size
            x1, x2 = x, x + block_size
            s = integral[y2, x2] - integral[y1, x2] - integral[y2, x1] + integral[y1, x1]
            local_mean = s / (block_size * block_size)

            # 局部标准差
            patch = padded[y1:y2, x1:x2]
            local_std = np.std(patch)

            threshold = local_mean * (1 + 0.2 * (local_std / 128.0 - 1)) - c
            result[y, x] = 255 if arr[y, x] > threshold else 0

    return Image.fromarray(result).convert("1")


def preprocess_image(
    image: Image.Image,
    method: str = "auto",
    target_min_dim: int = 1500,
) -> Image.Image:
    """增强的图像预处理管线。

    Parameters
    ----------
    image : PIL Image
    method : str
        "auto"      — 自动分析图像特征，选择最佳策略
        "binarize"  — 自适应二值化（适合墨迹清晰的文档）
        "descreen"  — 去网纹 / 去噪（适合扫描件 / 老照片 / 有底纹的图片）
        "upscale"   — 放大 + 锐化（适合分辨率不足的小字图片）
    target_min_dim : int
        放大时目标最小边长（仅 upscale / auto 模式生效）
    """
    # 基础步骤：转灰度
    if image.mode != "L":
        image = image.convert("L")

    original_dims = image.size

    if method == "auto":
        # 自动检测策略
        stat = ImageStat.Stat(image)
        std_dev = stat.stddev[0] if stat.stddev else 0
        min_dim = min(image.size)

        if min_dim < 800:
            # 小图 → 先放大再分析
            logger.info("preprocess auto: small image detected, upscale first | size=%s", image.size)
            method = "upscale"
        elif std_dev < 35:
            # 低对比度 → 二值化增强
            logger.info("preprocess auto: low contrast detected std=%.1f | binarize", std_dev)
            method = "binarize"
        elif std_dev > 80:
            # 高方差 → 可能有底纹噪点
            logger.info("preprocess auto: high variance detected std=%.1f | descreen", std_dev)
            method = "descreen"
        else:
            method = "binarize"

    if method == "upscale" or (method == "auto" and min(image.size) < target_min_dim):
        scale = max(1, target_min_dim // min(image.size))
        if scale > 1:
            new_size = (image.size[0] * scale, image.size[1] * scale)
            image = image.resize(new_size, Image.LANCZOS)
            logger.info("preprocess upscale: %s → %s (scale=%sx)", original_dims, image.size, scale)

    if method in ("binarize", "auto"):
        # 中值滤波去噪 → 自适应二值化
        image = image.filter(ImageFilter.MedianFilter(3))
        try:
            image = _adaptive_threshold(image, block_size=31, c=8)
        except Exception:
            logger.warning("adaptive threshold failed, falling back to otsu")
            image = _otsu_threshold(image)
        logger.info("preprocess binarize done | size=%s", image.size)

    elif method == "descreen":
        # 去网纹：大核中值滤波 → 保留对比度 → 二值化
        image = image.filter(ImageFilter.MedianFilter(5))
        image = ImageOps.autocontrast(image, cutoff=2)
        image = image.filter(ImageFilter.SHARPEN)
        try:
            image = _adaptive_threshold(image, block_size=41, c=10)
        except Exception:
            image = _otsu_threshold(image)
        logger.info("preprocess descreen done | size=%s", image.size)

    else:
        # 回退到原有逻辑：autocontrast + sharpen
        image = ImageOps.autocontrast(image)
        image = image.filter(ImageFilter.SHARPEN)

    return image


# ─── text orientation detection ───────────────────────────────
def detect_text_orientation(image: Image.Image) -> str:
    """根据图像宽高比判断横排/竖排中文。

    竖排中文（古籍、对联等）通常高 > 宽 1.5 倍以上。
    横排文档通常宽 > 高。
    """
    w, h = image.size
    ratio = h / max(w, 1)
    if ratio >= 1.5:
        logger.info("orientation detected: vertical | ratio=h/w=%.2f | size=%s", ratio, image.size)
        return "vertical"
    logger.info("orientation detected: horizontal | ratio=h/w=%.2f | size=%s", ratio, image.size)
    return "horizontal"


# ─── OCR post-processing ──────────────────────────────────────
def clean_ocr_text(text: str) -> str:
    """清洗 OCR 输出，移除垃圾字符，保留中文有效内容。

    - 移除纯 ASCII 垃圾行（短行、孤立字母数字）
    - 移除连续的随机符号块
    - 保留中文上下文中的英文和数字
    - 归一化空白
    """
    lines = text.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue

        # 统计行内中文字符数
        chinese_chars = len(_CHINESE_CHAR_PATTERN.findall(stripped))
        total_chars = len(stripped)

        # 纯噪声行：无中文且是短 ASCII 或纯符号
        if chinese_chars == 0:
            if _NOISE_LINE_PATTERN.match(stripped):
                continue  # 丢弃噪声行
            if total_chars <= 5 and all(c in "0123456789abcdefABCDEF \t" for c in stripped.split()):
                continue  # 丢弃看起来像 hex/hash 的行
            # 较长无中文行保留（可能是英文注释/引用）
            if total_chars >= 20:
                cleaned_lines.append(stripped)
            continue

        # 行内有中文：保留，但清理孤立的首尾垃圾
        # 移除行首的孤立 ASCII 碎片（如 "4p 82." 出现在中文行首）
        cleaned = stripped
        # 移除首部明显的 OCR 碎片：1-4 个 ASCII 字符后跟空格 + 中文
        cleaned = re.sub(r"^[A-Za-z0-9\x00-\x2f\x3a-\x40\x5b-\x60\x7b-\x7f\s]{1,8}(?=[一-鿿])", "", cleaned)
        # 移除尾部孤立的 ASCII 碎片
        cleaned = re.sub(r"(?<=[一-鿿])[\s\x00-\x2f\x3a-\x40\x5b-\x60\x7b-\x7f]{1,6}$", "", cleaned)
        # 移除行中夹在两段中文之间的 1-4 个无意义 ASCII（如 "A" "1a"）
        cleaned = re.sub(
            r"(?<=[一-鿿])\s+[A-Za-z0-9]{1,4}\s+(?=[一-鿿])",
            "",
            cleaned,
        )

        if cleaned.strip():
            cleaned_lines.append(cleaned.strip())

    # 合并结果，去除多余空白
    result = "\n".join(cleaned_lines)
    # 合并连续空行
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ─── quality assessment ───────────────────────────────────────
def assess_ocr_quality(text: str) -> dict:
    """评估 OCR 输出质量。

    Returns
    -------
    dict with keys:
        chinese_ratio  — 中文字符占比 (0.0 - 1.0)
        garbage_ratio  — 疑似垃圾字符占比
        total_chars    — 总字符数
        quality        — "good" | "acceptable" | "poor" | "unusable"
        warnings       — list[str]
    """
    total = len(text)
    if total == 0:
        return {
            "chinese_ratio": 0.0,
            "garbage_ratio": 1.0,
            "total_chars": 0,
            "quality": "unusable",
            "warnings": ["OCR 输出为空"],
        }

    chinese_chars = len(_CHINESE_CHAR_PATTERN.findall(text))
    chinese_ratio = chinese_chars / total

    # 垃圾字符估算：控制字符 + 孤立的 1-2 字母 + 可疑符号序列
    control_chars = sum(1 for c in text if ord(c) < 32)
    isolated_short_ascii = len(
        re.findall(r"(?<!\w)[A-Za-z0-9]{1,2}(?!\w)", text)
    )
    suspicious_symbols = len(
        re.findall(r"[^\w\s一-鿿　-〿＀-￯]{3,}", text)
    )
    garbage_chars = control_chars + isolated_short_ascii + suspicious_symbols
    garbage_ratio = min(1.0, garbage_chars / max(total, 1))

    warnings: list[str] = []
    if chinese_ratio < 0.30:
        quality = "unusable"
        warnings.append(f"中文字符占比极低 ({chinese_ratio:.1%})，OCR 结果不可用")
    elif chinese_ratio < 0.50:
        quality = "poor"
        warnings.append(f"中文字符占比偏低 ({chinese_ratio:.1%})，可能存在大量识别噪声")
    elif chinese_ratio < 0.70:
        quality = "acceptable"
    else:
        quality = "good"

    if garbage_ratio > 0.15:
        warnings.append(f"疑似垃圾字符占比过高 ({garbage_ratio:.1%})")
        if quality == "good":
            quality = "acceptable"

    logger.info(
        "ocr quality assessment | chinese_ratio=%.2f garbage_ratio=%.2f total=%s quality=%s",
        chinese_ratio,
        garbage_ratio,
        total,
        quality,
    )
    for w in warnings:
        logger.warning("ocr quality warning: %s", w)

    return {
        "chinese_ratio": round(chinese_ratio, 4),
        "garbage_ratio": round(garbage_ratio, 4),
        "total_chars": total,
        "quality": quality,
        "warnings": warnings,
    }


# ─── main OCR entry point ─────────────────────────────────────
def extract_text_from_image(
    file_path: str,
    lang: str = "auto",
    orientation: str = "auto",
    preprocess_method: str = "auto",
) -> str:
    """从图片中提取文字（增强版）。

    Parameters
    ----------
    file_path : str
        图片文件路径
    lang : str
        "auto"  — 根据方向自动选择 chi_sim 或 chi_sim_vert
        "chi_sim+eng" — 横排中文+英文
        "chi_sim_vert" — 竖排中文
        其他 — 直接传给 Tesseract
    orientation : str
        "auto" / "horizontal" / "vertical"
    preprocess_method : str
        预处理方法，参见 preprocess_image()
    """
    if pytesseract is None:
        raise RuntimeError("pytesseract 未安装，无法进行 OCR")

    image = Image.open(file_path)
    logger.info(
        "ocr start | file=%s | original_size=%s | mode=%s",
        os.path.basename(file_path),
        image.size,
        image.mode,
    )

    # 1. 检测文本方向
    if orientation == "auto":
        orientation = detect_text_orientation(image)

    # 2. 选择语言包
    if lang == "auto":
        if orientation == "vertical":
            tesseract_lang = "chi_sim_vert"
            logger.info("ocr using vertical chinese language pack: %s", tesseract_lang)
        else:
            tesseract_lang = "chi_sim+eng"
            logger.info("ocr using horizontal chinese+english language pack: %s", tesseract_lang)
    else:
        tesseract_lang = lang

    # 3. 增强预处理
    processed = preprocess_image(image, method=preprocess_method)

    # 4. OCR 识别
    try:
        psm_config = ""
        if orientation == "vertical":
            # PSM 5/7/11 对竖排中文效果较好
            psm_config = "--psm 5"
        raw_text = pytesseract.image_to_string(
            processed,
            lang=tesseract_lang,
            config=psm_config,
        )
    except TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract OCR 未安装或未配置到系统 PATH") from exc

    logger.info(
        "ocr raw output | len=%s | chinese_chars=%s",
        len(raw_text),
        len(_CHINESE_CHAR_PATTERN.findall(raw_text)),
    )

    # 5. 后处理清洗
    cleaned = clean_ocr_text(raw_text)

    # 如果清洗后结果为空，尝试用原始 lang 再识别一次
    if not cleaned.strip() and orientation == "vertical":
        logger.warning("vertical OCR returned empty after cleaning, retrying with chi_sim+eng")
        try:
            raw_text = pytesseract.image_to_string(processed, lang="chi_sim+eng")
            cleaned = clean_ocr_text(raw_text)
        except Exception:
            pass

    logger.info(
        "ocr cleaned output | len=%s | chinese_chars=%s",
        len(cleaned),
        len(_CHINESE_CHAR_PATTERN.findall(cleaned)),
    )

    return cleaned


def build_ocr_text(file_path: str) -> str:
    return extract_text_from_image(file_path)
