"""
preview.py — 实时预览模块
用 OpenCV 对参考图做快速色调映射，模拟阴影色/高光/描边效果，
输出 numpy array 供 UI 纹理显示。
"""
import numpy as np
import cv2


def apply_style_preview(
    img_bgr: np.ndarray,
    shadow_r: float,
    shadow_g: float,
    shadow_b: float,
    specular: float,
    rim_light_width: float,
    width_scale: float,
) -> np.ndarray:
    """
    在参考图上模拟风格化效果。

    参数范围：
      shadow_r/g/b: [0, 1]  阴影色
      specular:     [0, 1]  高光强度
      rim_light_width: [0, 1]  边缘光宽度
      width_scale:  [0.5, 3.0]  描边宽度

    返回 BGR uint8 图像
    """
    img = img_bgr.astype(np.float32) / 255.0
    h, w = img.shape[:2]

    # 1. 阴影色叠加 — 用亮度蒙版
    #    亮区保留原色，暗区混合阴影色
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    shadow_mask = np.clip(1.0 - gray * 2.0, 0, 1.0)  # 暗区 mask
    shadow_color = np.array([shadow_b, shadow_g, shadow_r], dtype=np.float32)  # BGR

    # 将暗区颜色替换为阴影色，保留亮区原色
    for c in range(3):
        img[:, :, c] = img[:, :, c] * (1 - shadow_mask * 0.6) + shadow_color[c] * shadow_mask * 0.6

    # 2. 高光增强 — 在亮区增加 specular
    highlight_mask = np.clip(gray * 3.0 - 2.0, 0, 1.0)  # 仅最亮部分
    specular_boost = specular * 0.3
    img = img + highlight_mask[:, :, np.newaxis] * specular_boost

    # 3. 描边效果 — 边缘检测 + 描边叠加
    #    width_scale 越大描边越粗
    edge_kernel = max(1, int(width_scale * 1.5))
    gray_uint8 = (gray * 255).astype(np.uint8)
    edges = cv2.Canny(gray_uint8, 50, 150)

    # 膨胀边缘模拟描边粗细
    if edge_kernel > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (edge_kernel, edge_kernel))
        edges = cv2.dilate(edges, kernel, iterations=1)

    edge_mask = edges.astype(np.float32) / 255.0
    # 描边颜色为深色
    outline_color = 0.05
    for c in range(3):
        img[:, :, c] = img[:, :, c] * (1 - edge_mask * 0.8) + outline_color * edge_mask * 0.8

    # 4. 边缘光 (Rim Light) — 在边缘区域增加亮度
    if rim_light_width > 0.05:
        # 用距离变换模拟边缘光
        dist = cv2.distanceTransform(255 - edges, cv2.DIST_L2, 5)
        rim_range = rim_light_width * 30  # 映射到像素范围
        rim_mask = np.clip(1.0 - dist / max(rim_range, 1), 0, 1)
        rim_mask = rim_mask * edge_mask  # 只在边缘附近
        img = img + rim_mask[:, :, np.newaxis] * 0.15

    # 裁剪并转回 uint8
    img = np.clip(img, 0, 1.0)
    return (img * 255).astype(np.uint8)


def load_image_bgr(img_path: str, max_size: int = 512) -> np.ndarray:
    """加载图片并缩放到适合预览的尺寸"""
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"无法加载图片: {img_path}")

    h, w = img.shape[:2]
    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    return img


def bgr_to_rgba(img_bgr: np.ndarray) -> np.ndarray:
    """BGR uint8 → RGBA float32 [0,1]（Dear PyGui 纹理格式）"""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_rgba = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2RGBA)
    return img_rgba.astype(np.float32) / 255.0
