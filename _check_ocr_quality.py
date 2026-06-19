# -*- coding: utf-8 -*-
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from ocr_utils import assess_ocr_quality

# Test with actual garbled chunk content
chunks = [
    u'专 扬 为 仪 知 万 顺 中 率 饲 识 贤 协 伦 忠 终 文 原 书 义 治 求 奥 备 恶 事 终 世 社 久 出 自 晋 齐 基 由 世 陵 梦 压 腾 训 鉴 学 钨 轰 籍 士 模 叭 字 是 物 后',
    u'本 三 不 师 于 而 子 四 五 大石 五 四 响 则 组 识 史学 过 修 太 卉 汉代 其 世 迫 百',
    u'入 so < O O 人防 O O 0 O O C O O 0 O O < < O 和 O O 到 O O O 0 中 OO',
    u'人 首 养 玉 香 首 三 日 日 三 日 酸 克 高 父 此 礼 有 用 论 作 考 有 我 日 三 五 自 夏 汤',
]

print("=== OCR Quality Assessment for actual chunks ===")
for i, text in enumerate(chunks):
    q = assess_ocr_quality(text)
    print(f'Chunk {i}: chinese_ratio={q["chinese_ratio"]:.2f} garbage_ratio={q["garbage_ratio"]:.2f} quality={q["quality"]} total={q["total_chars"]}')
    if q["warnings"]:
        for w in q["warnings"]:
            print(f'  WARNING: {w}')

print("\n=== Quality check for the full merged chunks ===")
from doc_ingest import vector_db
data = vector_db.get(include=['documents', 'metadatas'])
for i, (doc, meta) in enumerate(zip(data.get('documents',[]), data.get('metadatas',[]) or [])):
    q = assess_ocr_quality(doc)
    print(f'Chunk {i}: chinese_ratio={q["chinese_ratio"]:.2f} garbage_ratio={q["garbage_ratio"]:.2f} quality={q["quality"]}')
