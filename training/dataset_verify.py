"""
dataset_verify.py — 数据集验证脚本
训练前跑一次，确认图片和标签均正常
"""
import os
import pandas as pd
from PIL import Image

IMAGES_DIR = "../data/images"
LABELS_CSV = "labels.csv"
IMG_SIZE = (224, 224)

def verify():
    # 1. 读取 CSV
    df = pd.read_csv(LABELS_CSV)
    print(f"[CSV] 共 {len(df)} 条记录，列: {list(df.columns)}")

    # 2. 检查文件存在性
    missing = []
    corrupt = []
    ok = []

    for idx, row in df.iterrows():
        fname = os.path.basename(row["ImagePath"].strip('"'))
        path = os.path.join(IMAGES_DIR, fname)
        if not os.path.exists(path):
            missing.append(fname)
            continue
        try:
            img = Image.open(path).convert("RGB").resize(IMG_SIZE)
            ok.append((fname, img.size))
        except Exception as e:
            corrupt.append((fname, str(e)))

    # 3. 打印结果
    print(f"\n[OK]     {len(ok)} 张图片正常加载")
    if missing:
        print(f"[MISS]   {len(missing)} 张文件缺失:")
        for f in missing:
            print(f"         - {f}")
    if corrupt:
        print(f"[ERROR]  {len(corrupt)} 张图片损坏:")
        for f, e in corrupt:
            print(f"         - {f}: {e}")

    # 4. 标签范围检查（6个参数）
    print("\n[标签范围检查]")
    checks = {
        "ShadowR":       (0.0, 1.0),
        "ShadowG":       (0.0, 1.0),
        "ShadowB":       (0.0, 1.0),
        "Specular":      (0.0, 1.0),
        "RimLightWidth": (0.0, 1.0),
        "WidthScale":    (0.5, 3.0),
    }
    for col, (lo, hi) in checks.items():
        if col not in df.columns:
            print(f"  [{col}] !! 列不存在！请检查 labels.csv 表头")
            continue
        out = df[(df[col] < lo) | (df[col] > hi)]
        if not out.empty:
            print(f"  [{col}] X {len(out)} 行超出范围 [{lo}, {hi}]")
        else:
            print(f"  [{col}] OK  min={df[col].min():.3f}  max={df[col].max():.3f}")

    # 5. 打印前3条样本
    print("\n[前3条样本]")
    print(df.head(3).to_string(index=False))

    if not missing and not corrupt:
        print("\n>>> 数据集验证通过，可以开始训练 <<<")
    else:
        print("\n>>> 数据集存在问题，请先修复 <<<")

if __name__ == "__main__":
    verify()
