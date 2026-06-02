"""
engine.py — ONNX 推理引擎
封装 infer_test.py 的逻辑为 InferenceEngine 类，
支持图片路径和 numpy array 输入，返回 6 参数列表。

新增：支持涂鸦遮罩输入，让模型关注重点区域。
"""
import os
import numpy as np
from PIL import Image

try:
    import onnxruntime as ort
except ImportError:
    ort = None


# 参数名（与 train.py LABEL_COLS 顺序一致）
PARAM_NAMES = ["ShadowR", "ShadowG", "ShadowB", "Specular", "RimLightWidth", "WidthScale"]

# ImageNet 归一化常量
IMG_SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess_image(img_path: str, mask: np.ndarray = None) -> np.ndarray:
    """
    读取图片 → 224x224 → ImageNet 归一化 → NCHW numpy array

    Args:
        img_path: 图片路径
        mask: 涂鸦遮罩 (H,W) uint8, 0=正常, 1=重点, 2=忽略
    """
    img = Image.open(img_path).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
    x = np.array(img, dtype=np.float32) / 255.0       # HWC, [0,1]

    # 应用遮罩
    if mask is not None:
        mask_resized = np.array(Image.fromarray(mask).resize((IMG_SIZE, IMG_SIZE), Image.NEAREST))
        # 重点区域增强权重 (绿色)
        focus_mask = (mask_resized == 1)
        if focus_mask.any():
            # 简单处理：提高对比度
            x[focus_mask] = x[focus_mask] * 1.1 + 0.05
        # 忽略区域减弱 (红色)
        ignore_mask = (mask_resized == 2)
        if ignore_mask.any():
            # 降低对比度，让模型忽略
            x[ignore_mask] = x[ignore_mask] * 0.7

    x = (x - MEAN) / STD                                # 归一化
    x = x.transpose(2, 0, 1)[np.newaxis, :]             # → NCHW (1,3,224,224)
    return x


def preprocess_array(img_array: np.ndarray, mask: np.ndarray = None) -> np.ndarray:
    """
    numpy array (H,W,3) uint8 → NCHW 归一化

    Args:
        img_array: BGR 图像数组
        mask: 涂鸦遮罩 (H,W) uint8, 0=正常, 1=重点, 2=忽略
    """
    # BGR → RGB
    rgb = img_array[:, :, [2, 1, 0]]
    img = Image.fromarray(rgb).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
    x = np.array(img, dtype=np.float32) / 255.0

    # 应用遮罩
    if mask is not None:
        mask_resized = np.array(Image.fromarray(mask).resize((IMG_SIZE, IMG_SIZE), Image.NEAREST))
        focus_mask = (mask_resized == 1)
        if focus_mask.any():
            x[focus_mask] = x[focus_mask] * 1.1 + 0.05
        ignore_mask = (mask_resized == 2)
        if ignore_mask.any():
            x[ignore_mask] = x[ignore_mask] * 0.7

    x = (x - MEAN) / STD
    x = x.transpose(2, 0, 1)[np.newaxis, :]
    return x


class InferenceEngine:
    """ONNX 模型推理引擎"""

    def __init__(self, onnx_path: str):
        if ort is None:
            raise ImportError("onnxruntime 未安装，请运行: pip install onnxruntime")

        if not os.path.exists(onnx_path):
            raise FileNotFoundError(f"ONNX 模型不存在: {onnx_path}")

        self.onnx_path = onnx_path
        self.session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def infer(self, img_path: str, mask: np.ndarray = None) -> dict:
        """
        对一张图片推理，返回参数字典。

        Args:
            img_path: 图片路径
            mask: 涂鸦遮罩 (H,W) uint8, 0=正常, 1=重点, 2=忽略

        Returns:
            {
                "params": [shadow_r, shadow_g, shadow_b, specular, rim_light_width, width_scale],
                "named":  {"ShadowR": ..., "ShadowG": ..., ...},
                "width_scale_ue": 1.029  # 反归一化后写入 UE 的值
            }
        """
        x = preprocess_image(img_path, mask)
        return self._run(x)

    def infer_array(self, img_array: np.ndarray, mask: np.ndarray = None) -> dict:
        """
        对 numpy array (H,W,3) uint8 推理。
        用于实时预览场景。

        Args:
            img_array: BGR 图像数组
            mask: 涂鸦遮罩 (H,W) uint8, 0=正常, 1=重点, 2=忽略
        """
        x = preprocess_array(img_array, mask)
        return self._run(x)

    def _run(self, input_tensor: np.ndarray) -> dict:
        outputs = self.session.run(["params"], {"image": input_tensor})
        preds = outputs[0][0]  # shape (6,)

        params = preds.tolist()
        named = dict(zip(PARAM_NAMES, params))

        # width_scale 反归一化：训练时 Sigmoid 输出 [0,1]，原始范围 [0.5, 3.0]
        width_scale_ue = float(preds[5]) * 2.5 + 0.5

        return {
            "params": params,
            "named": named,
            "width_scale_ue": width_scale_ue,
        }

    @staticmethod
    def params_to_ue(result: dict) -> list:
        """
        将推理结果转为 UE5 写入参数列表（6 个 float）。
        width_scale 已反归一化。
        """
        params = list(result["params"])
        params[5] = result["width_scale_ue"]
        return params
