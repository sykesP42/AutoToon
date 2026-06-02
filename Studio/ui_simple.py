"""
ui_simple.py — AutoToon Studio 简化版本
支持：参数调节 + 球体预览 + 上传参考图 + AI推理
"""
import os
import time
import numpy as np
import cv2
from typing import Optional

import dearpygui.dearpygui as dpg

VIEWER_W, VIEWER_H = 380, 380

# 全局状态
preview_tex_tag = "preview_tex"
ref_tex_tag = "ref_tex"
ref_image: Optional[np.ndarray] = None
ref_image_path: str = ""

# ONNX 引擎
engine = None

# 参数默认值
params = {
    "shadow_r": 0.3,
    "shadow_g": 0.3,
    "shadow_b": 0.3,
    "specular": 0.5,
    "rim_light": 0.5,
    "outline_width": 1.0,
}


def load_onnx_model():
    """加载 ONNX 模型"""
    global engine
    try:
        import onnxruntime as ort
        # 搜索模型路径
        search_paths = [
            os.path.join(os.path.dirname(__file__), "..", "training", "mooatoon_model.onnx"),
            "mooatoon_model.onnx",
        ]
        for path in search_paths:
            if os.path.exists(path):
                engine = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
                print(f"[Model] Loaded: {path}")
                return True
        print("[Model] No model found, running without AI inference")
        return False
    except Exception as e:
        print(f"[Model] Error: {e}")
        return False


def run_inference():
    """对参考图进行推理"""
    global params
    if engine is None:
        print("[Infer] No model loaded")
        return False
    if ref_image is None:
        print("[Infer] No reference image")
        return False

    try:
        # 预处理图像
        from PIL import Image
        IMG_SIZE = 224
        MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

        img = Image.fromarray(ref_image).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
        x = np.array(img, dtype=np.float32) / 255.0
        x = (x - MEAN) / STD
        x = x.transpose(2, 0, 1)[np.newaxis, :]  # NCHW

        # 推理
        input_name = engine.get_inputs()[0].name
        outputs = engine.run(["params"], {input_name: x})
        preds = outputs[0][0]

        # 更新参数
        params["shadow_r"] = float(preds[0])
        params["shadow_g"] = float(preds[1])
        params["shadow_b"] = float(preds[2])
        params["specular"] = float(preds[3])
        params["rim_light"] = float(preds[4])
        params["outline_width"] = float(preds[5]) * 2.5 + 0.5  # 反归一化

        # 更新 UI 滑块
        param_names = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light", "outline_width"]
        for i, name in enumerate(param_names):
            val = params[name]
            if dpg.does_item_exist(f"slider_{i}"):
                dpg.set_value(f"slider_{i}", val)
            if dpg.does_item_exist(f"val_{i}"):
                dpg.set_value(f"val_{i}", f"{val:.2f}")

        print(f"[Infer] Success! Params: {[f'{p:.2f}' for p in preds[:6]]}")
        update_preview()
        return True
    except Exception as e:
        print(f"[Infer] Error: {e}")
        return False


def generate_sphere_image(w=380, h=380):
    """使用 OpenCV 生成球体预览"""
    # 创建背景
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (35, 35, 40)

    cx, cy = w // 2, h // 2
    radius = min(w, h) // 2 - 30

    # 阴影颜色
    shadow_r = int(50 + params["shadow_r"] * 150)
    shadow_g = int(50 + params["shadow_g"] * 150)
    shadow_b = int(50 + params["shadow_b"] * 150)

    spec = params["specular"]
    rim = params["rim_light"]
    outline = params["outline_width"]

    for y in range(h):
        for x in range(w):
            dx = x - cx
            dy = y - cy
            dist = np.sqrt(dx*dx + dy*dy)
            if dist <= radius:
                nx = dx / radius
                ny = dy / radius
                nz_sq = 1 - nx*nx - ny*ny
                nz = np.sqrt(max(0, nz_sq))

                # 光照计算
                light1 = np.array([0.5, -0.5, 0.7])
                light1 = light1 / np.linalg.norm(light1)
                normal = np.array([nx, ny, nz])
                diff1 = max(0, np.dot(normal, light1))

                light2 = np.array([-0.6, 0.0, 0.5])
                light2 = light2 / np.linalg.norm(light2)
                diff2 = max(0, np.dot(normal, light2)) * 0.3

                diffuse = diff1 * 0.7 + diff2 + 0.2

                # 高光
                view_dir = np.array([0, 0, 1])
                half_vec = light1 + view_dir
                half_vec = half_vec / np.linalg.norm(half_vec)
                spec_angle = max(0, np.dot(normal, half_vec))
                specular = pow(spec_angle, 32) * spec * 1.5

                brightness = min(1.0, diffuse + specular)

                bright_r = int(220 + specular * 50)
                bright_g = int(220 + specular * 50)
                bright_b = int(230 + specular * 50)

                r = int(shadow_r + (bright_r - shadow_r) * brightness)
                g = int(shadow_g + (bright_g - shadow_g) * brightness)
                b = int(shadow_b + (bright_b - shadow_b) * brightness)

                # Rim light
                edge_factor = 1 - nz
                rim_light = pow(edge_factor, 2) * rim * 1.5
                r = min(255, int(r + 150 * rim_light))
                g = min(255, int(g + 160 * rim_light))
                b = min(255, int(b + 200 * rim_light))

                img[y, x] = (b, g, r)

    # 描边
    outline_color = (25, 25, 35)
    outline_thickness = max(1, int(outline * 2))
    cv2.circle(img, (cx, cy), radius + outline_thickness, outline_color, outline_thickness + 2)

    return img


def update_preview():
    """更新预览"""
    img = generate_sphere_image(VIEWER_W, VIEWER_H)
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    if dpg.does_item_exist(preview_tex_tag):
        dpg.set_value(preview_tex_tag, rgba.ravel().tolist())


def update_ref_preview():
    """更新参考图预览"""
    global ref_image
    if ref_image is None:
        return

    try:
        # 调整大小
        h, w = ref_image.shape[:2]
        max_size = VIEWER_W
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            ref_resized = cv2.resize(ref_image, (new_w, new_h))
        else:
            ref_resized = ref_image.copy()
            new_h, new_w = h, w

        # 转换为 RGBA
        rgba = cv2.cvtColor(ref_resized, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0

        # 删除旧纹理并创建新纹理
        if dpg.does_item_exist(ref_tex_tag):
            dpg.delete_item(ref_tex_tag)

        with dpg.texture_registry():
            dpg.add_dynamic_texture(new_w, new_h, rgba.ravel().tolist(), tag=ref_tex_tag)

        print(f"[Ref] Preview updated: {new_w}x{new_h}")
    except Exception as e:
        print(f"[Ref] Error updating preview: {e}")


def on_slider_change(sender, app_data, user_data):
    """滑块回调"""
    param_names = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light", "outline_width"]
    params[param_names[user_data]] = app_data
    dpg.set_value(f"val_{user_data}", f"{app_data:.2f}")
    update_preview()


def on_ref_selected(sender, app_data):
    """选择参考图"""
    global ref_image, ref_image_path
    path = app_data["file_path_name"]
    print(f"[Ref] Selected: {path}")

    try:
        ref_image = cv2.imread(path)
        if ref_image is None:
            print("[Ref] Failed to load image")
            return

        ref_image_path = path
        update_ref_preview()

        if dpg.does_item_exist("ref_path_text"):
            dpg.set_value("ref_path_text", os.path.basename(path))

        print("[Ref] Image loaded successfully")
    except Exception as e:
        print(f"[Ref] Error: {e}")


def on_infer_clicked():
    """点击推理按钮"""
    print("[Infer] Running inference...")
    if run_inference():
        if dpg.does_item_exist("status_text"):
            dpg.set_value("status_text", "Inference done!")
    else:
        if dpg.does_item_exist("status_text"):
            dpg.set_value("status_text", "Inference failed")


def build_ui():
    """构建 UI"""
    dpg.create_context()
    dpg.create_viewport(title="AutoToon Studio", width=900, height=600)

    # 暗黑主题
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (30, 30, 30))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (45, 45, 45))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (60, 60, 60))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 80, 80))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (100, 150, 255))
    dpg.bind_theme(theme)

    # 纹理
    with dpg.texture_registry():
        dpg.add_dynamic_texture(VIEWER_W, VIEWER_H, [0.2]*4*(VIEWER_W*VIEWER_H), tag=preview_tex_tag)
        dpg.add_dynamic_texture(VIEWER_W, VIEWER_H, [0.15]*4*(VIEWER_W*VIEWER_H), tag=ref_tex_tag)

    # 文件对话框
    with dpg.file_dialog(directory_selector=False, show=False,
                         callback=on_ref_selected, tag="ref_dialog", width=500, height=300):
        dpg.add_file_extension(".png", color=(100, 200, 255))
        dpg.add_file_extension(".jpg", color=(100, 200, 255))
        dpg.add_file_extension(".jpeg", color=(100, 200, 255))

    with dpg.window(tag="main"):
        dpg.add_text("AutoToon Studio", color=(100, 150, 255))
        dpg.add_separator()

        with dpg.group(horizontal=True):
            # 左侧：参考图
            with dpg.group():
                dpg.add_text("Reference Image", color=(180, 200, 255))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Upload Image", callback=lambda: dpg.show_item("ref_dialog"), width=120)
                dpg.add_text("", tag="ref_path_text", color=(120, 120, 120))
                with dpg.drawlist(width=VIEWER_W, height=VIEWER_H, tag="ref_drawlist"):
                    dpg.draw_rectangle((0, 0), (VIEWER_W, VIEWER_H), fill=(25, 25, 25))
                    dpg.draw_image(ref_tex_tag, (0, 0), (VIEWER_W, VIEWER_H), tag="ref_img_draw")
                dpg.add_text("Upload a reference image", tag="ref_hint", color=(80, 80, 80))

            # 中间分隔
            dpg.add_spacer(width=20)

            # 右侧：预览和参数
            with dpg.group():
                dpg.add_text("Sphere Preview", color=(180, 200, 255))
                with dpg.drawlist(width=VIEWER_W, height=VIEWER_H):
                    dpg.draw_rectangle((0, 0), (VIEWER_W, VIEWER_H), fill=(25, 25, 25))
                    dpg.draw_image(preview_tex_tag, (0, 0), (VIEWER_W, VIEWER_H))

                dpg.add_separator()

                # 参数滑块
                dpg.add_text("Parameters:", color=(150, 150, 150))
                param_labels = ["Shadow R", "Shadow G", "Shadow B", "Specular", "Rim Light", "Outline"]
                defaults = [0.3, 0.3, 0.3, 0.5, 0.5, 1.0]
                mins = [0.0, 0.0, 0.0, 0.0, 0.0, 0.5]
                maxs = [1.0, 1.0, 1.0, 1.0, 1.0, 3.0]

                for i, label in enumerate(param_labels):
                    with dpg.group(horizontal=True):
                        dpg.add_text(f"{label}:")
                        dpg.add_slider_float(
                            tag=f"slider_{i}",
                            default_value=defaults[i],
                            min_value=mins[i], max_value=maxs[i],
                            width=150,
                            callback=on_slider_change,
                            user_data=i
                        )
                        dpg.add_text(f"{defaults[i]:.2f}", tag=f"val_{i}")

                dpg.add_separator()

                # AI 推理按钮
                dpg.add_button(label="Extract Style from Image", callback=on_infer_clicked, width=200, height=30)
                dpg.add_text("", tag="status_text", color=(100, 150, 255))


def run():
    """运行程序"""
    print("[Init] Loading ONNX model...")
    load_onnx_model()

    build_ui()
    update_preview()

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)

    print("[Loop] Running...")
    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()

    dpg.destroy_context()
    print("[Done]")


if __name__ == "__main__":
    run()