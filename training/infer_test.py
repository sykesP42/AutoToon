"""
infer_test.py — 纯 Python 推理验证（不需要 UE）
功能：加载 mooatoon_model.onnx，对 images/ 里任意一张图推理，打印输出参数
用于在进入 UE 之前先确认 ONNX 模型输出是否正常
"""

import onnxruntime as ort
import numpy as np
from PIL import Image
import sys
import os

ONNX_PATH  = "mooatoon_model.onnx"
IMAGES_DIR = "../data/images"

# 与 train.py 的 LABEL_COLS 顺序完全一致
PARAM_NAMES = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light_width", "width_scale"]

IMG_SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

def preprocess(img_path):
    img = Image.open(img_path).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
    x = np.array(img, dtype=np.float32) / 255.0      # HWC, [0,1]
    x = (x - MEAN) / STD                              # 归一化
    x = x.transpose(2, 0, 1)[np.newaxis, :]           # -> NCHW
    return x

def infer(img_path):
    sess = ort.InferenceSession(ONNX_PATH, providers=["CPUExecutionProvider"])
    x = preprocess(img_path)
    outputs = sess.run(["params"], {"image": x})
    preds = outputs[0][0]  # shape (6,)

    shadow_r, shadow_g, shadow_b, specular, rim_light_width, width_scale_norm = preds

    # width_scale 训练时归一化到 [0,1]，原始范围 [0.5, 3.0]
    width_scale = width_scale_norm * 2.5 + 0.5

    print(f"\n图片: {os.path.basename(img_path)}")
    print("─" * 45)
    for name, val in zip(PARAM_NAMES, preds):
        print(f"  {name:25s} = {val:.4f}")

    print(f"\n  [UE 写入参数]")
    print(f"  Shadow Color    = ({shadow_r:.3f}, {shadow_g:.3f}, {shadow_b:.3f})")
    print(f"  Specular        = {specular:.3f}          [图层参数]")
    print(f"  Rim Light Width = {rim_light_width:.3f}          [图层参数]")
    print(f"  Width Scale     = {width_scale:.3f}          [描边材质全局参数，反归一化后]")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        img_path = os.path.join(IMAGES_DIR, sys.argv[1])
    else:
        files = [f for f in os.listdir(IMAGES_DIR) if f.lower().endswith(('.png','.jpg','.jpeg'))]
        img_path = os.path.join(IMAGES_DIR, sorted(files)[0])

    if not os.path.exists(img_path):
        print(f"文件不存在: {img_path}")
        sys.exit(1)

    infer(img_path)
