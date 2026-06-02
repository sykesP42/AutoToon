"""
ui_pro.py — AutoToon Studio 专业版
工业级材质球预览 + 卡通着色效果
"""
import os
import numpy as np
import cv2
import dearpygui.dearpygui as dpg

VIEWER_SIZE = 400

# 全局状态
ref_image = None
engine = None

# 材质参数
material = {
    "base_color": [0.9, 0.9, 0.9],      # 基础色
    "shadow_color": [0.3, 0.3, 0.4],     # 阴影色
    "specular_power": 32,                 # 高光锐度
    "specular_intensity": 0.6,            # 高光强度
    "rim_power": 3.0,                     # 边缘光范围
    "rim_intensity": 0.5,                 # 边缘光强度
    "outline_width": 2.0,                 # 描边宽度
    "outline_color": [0.1, 0.1, 0.15],    # 描边颜色
    "shade_levels": 3,                    # 色阶数量
    "ambient": 0.15,                      # 环境光
}

# 预渲染的球体法线贴图（用于加速）
_normal_map = None


def create_sphere_normal_map(size=400):
    """创建球体法线贴图（只需一次）"""
    global _normal_map
    if _normal_map is not None and _normal_map.shape[0] == size:
        return _normal_map

    cx, cy = size // 2, size // 2
    radius = size // 2 - 20

    normal_map = np.zeros((size, size, 3), dtype=np.float32)

    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = np.sqrt(dx*dx + dy*dy)
            if dist <= radius:
                nx = dx / radius
                ny = dy / radius
                nz_sq = 1 - nx*nx - ny*ny
                if nz_sq > 0:
                    nz = np.sqrt(nz_sq)
                else:
                    nz = 0
                normal_map[y, x] = [nx, ny, nz]

    _normal_map = normal_map
    return normal_map


def render_toon_sphere(size=400):
    """
    渲染卡通风格材质球

    特性：
    - 离散色阶光照
    - 高光控制
    - 边缘光 (Rim)
    - 描边效果
    """
    normal_map = create_sphere_normal_map(size)
    cx, cy = size // 2, size // 2
    radius = size // 2 - 20

    # 输出图像
    img = np.zeros((size, size, 3), dtype=np.float32)

    # 光源方向（可调节）
    light_dir = np.array([0.5, -0.5, 0.8])
    light_dir = light_dir / np.linalg.norm(light_dir)

    # 补光方向
    fill_dir = np.array([-0.4, 0.2, 0.4])
    fill_dir = fill_dir / np.linalg.norm(fill_dir)

    # 视线方向（指向相机）
    view_dir = np.array([0, 0, 1])

    # 半程向量（用于高光）
    half_vec = (light_dir + view_dir)
    half_vec = half_vec / np.linalg.norm(half_vec)

    for y in range(size):
        for x in range(size):
            dist = np.sqrt((x-cx)**2 + (y-cy)**2)

            # 描边区域
            outline_dist = radius - dist
            outline_threshold = material["outline_width"]

            if outline_dist < outline_threshold and outline_dist > -outline_threshold:
                # 描边
                outline_alpha = 1 - (outline_dist + outline_threshold) / (2 * outline_threshold)
                outline_alpha = max(0, min(1, outline_alpha))
                oc = material["outline_color"]
                img[y, x] = oc
            elif dist <= radius:
                # 正常着色
                normal = normal_map[y, x]

                if normal[2] <= 0:
                    # 背面，用描边颜色
                    img[y, x] = material["outline_color"]
                    continue

                # 漫反射
                NdotL = max(0, np.dot(normal, light_dir))
                NdotF = max(0, np.dot(normal, fill_dir))

                # 主光 + 补光
                diffuse = NdotL * 0.7 + NdotF * 0.3

                # 色阶化（卡通效果）
                levels = material["shade_levels"]
                if levels == 2:
                    shade = 1.0 if diffuse > 0.5 else 0.0
                elif levels == 3:
                    if diffuse > 0.66:
                        shade = 1.0
                    elif diffuse > 0.33:
                        shade = 0.5
                    else:
                        shade = 0.0
                else:  # 4 levels
                    if diffuse > 0.75:
                        shade = 1.0
                    elif diffuse > 0.5:
                        shade = 0.66
                    elif diffuse > 0.25:
                        shade = 0.33
                    else:
                        shade = 0.0

                # 颜色混合
                base = np.array(material["base_color"])
                shadow = np.array(material["shadow_color"])

                # 环境光 + 色阶着色
                color = shadow + (base - shadow) * (shade + material["ambient"])
                color = np.clip(color, 0, 1)

                # 高光
                NdotH = max(0, np.dot(normal, half_vec))
                spec = pow(NdotH, material["specular_power"]) * material["specular_intensity"]

                # 离散高光（更卡通）
                if spec > 0.3:
                    spec = 1.0
                elif spec > 0.1:
                    spec = 0.5
                else:
                    spec = 0.0
                spec *= material["specular_intensity"]

                color = color + spec * 0.8

                # 边缘光 (Rim)
                NdotV = max(0, np.dot(normal, view_dir))
                rim = pow(1 - NdotV, material["rim_power"]) * material["rim_intensity"]
                rim_color = np.array([0.9, 0.95, 1.0])  # 微蓝白色
                color = color + rim * rim_color

                img[y, x] = np.clip(color, 0, 1)

    # 转换为 8 位 BGR
    img_bgr = (img * 255).astype(np.uint8)
    # BGR 顺序 (OpenCV)
    img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_RGB2BGR)

    return img_bgr


def update_preview():
    """更新预览"""
    img = render_toon_sphere(VIEWER_SIZE)
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0

    if dpg.does_item_exist("preview_tex"):
        dpg.set_value("preview_tex", rgba.ravel().tolist())


def on_param_change(sender, app_data, user_data):
    """参数变化回调"""
    param_name = user_data

    # 特殊处理阴影色分量
    if param_name == "shadow_color_r":
        material["shadow_color"][0] = app_data
    elif param_name == "shadow_color_g":
        material["shadow_color"][1] = app_data
    elif param_name == "shadow_color_b":
        material["shadow_color"][2] = app_data
    else:
        material[param_name] = app_data

    update_preview()


def on_ref_selected(sender, app_data):
    """选择参考图"""
    global ref_image
    path = app_data["file_path_name"]
    print(f"[Load] {path}")

    try:
        img = cv2.imread(path)
        if img is None:
            print("[Error] Cannot load image")
            return

        ref_image = img.copy()

        # 更新参考图显示
        h, w = img.shape[:2]
        max_size = VIEWER_SIZE
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = cv2.resize(img, (new_w, new_h))
        else:
            new_w, new_h = w, h

        rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0

        # 删除旧纹理
        if dpg.does_item_exist("ref_tex"):
            dpg.delete_item("ref_tex")

        # 创建新纹理
        with dpg.texture_registry():
            dpg.add_dynamic_texture(new_w, new_h, rgba.ravel().tolist(), tag="ref_tex")

        # 更新路径显示
        if dpg.does_item_exist("ref_path"):
            dpg.set_value("ref_path", os.path.basename(path))

        print(f"[OK] Image loaded: {new_w}x{new_h}")

    except Exception as e:
        import traceback
        print(f"[Error] {e}")
        traceback.print_exc()


def on_infer():
    """AI 推理"""
    global engine

    if engine is None:
        print("[Infer] No model loaded!")
        if dpg.does_item_exist("status"):
            dpg.set_value("status", "No model!")
        return

    if ref_image is None:
        print("[Infer] Please upload a reference image first!")
        if dpg.does_item_exist("status"):
            dpg.set_value("status", "Upload image first!")
        return

    try:
        from PIL import Image
        IMG_SIZE = 224
        MEAN = np.array([0.485, 0.456, 0.406])
        STD = np.array([0.229, 0.224, 0.225])

        print("[Infer] Preprocessing image...")
        img = Image.fromarray(ref_image).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
        x = np.array(img, dtype=np.float32) / 255.0
        x = (x - MEAN) / STD
        x = x.transpose(2, 0, 1)[np.newaxis, :]

        print("[Infer] Running inference...")
        input_name = engine.get_inputs()[0].name
        outputs = engine.run(["params"], {input_name: x})
        preds = outputs[0][0]

        print(f"[Infer] Results: {preds[:6]}")

        # 更新材质参数
        material["shadow_color"] = [float(preds[0]), float(preds[1]), float(preds[2])]
        material["specular_intensity"] = float(preds[3])
        material["rim_intensity"] = float(preds[4])
        outline_raw = float(preds[5])
        material["outline_width"] = outline_raw * 2.5 + 0.5  # 反归一化到 [0.5, 3.0]

        print(f"[Infer] Applied: shadow=[{material['shadow_color']}], spec={material['specular_intensity']:.2f}, rim={material['rim_intensity']:.2f}, outline={material['outline_width']:.2f}")

        # 更新 UI 滑块
        if dpg.does_item_exist("slider_shadow_r"):
            dpg.set_value("slider_shadow_r", material["shadow_color"][0])
        if dpg.does_item_exist("slider_shadow_g"):
            dpg.set_value("slider_shadow_g", material["shadow_color"][1])
        if dpg.does_item_exist("slider_shadow_b"):
            dpg.set_value("slider_shadow_b", material["shadow_color"][2])
        if dpg.does_item_exist("slider_spec"):
            dpg.set_value("slider_spec", material["specular_intensity"])
        if dpg.does_item_exist("slider_rim"):
            dpg.set_value("slider_rim", material["rim_intensity"])
        if dpg.does_item_exist("slider_outline"):
            dpg.set_value("slider_outline", material["outline_width"])

        # 更新预览
        update_preview()

        if dpg.does_item_exist("status"):
            dpg.set_value("status", "Style extracted!")

        print("[Infer] Done!")

    except Exception as e:
        import traceback
        print(f"[Infer] Error: {e}")
        traceback.print_exc()
        if dpg.does_item_exist("status"):
            dpg.set_value("status", f"Error: {e}")


def load_model():
    """加载模型"""
    global engine
    try:
        import onnxruntime as ort
        paths = [
            os.path.join(os.path.dirname(__file__), "..", "training", "mooatoon_model.onnx"),
        ]
        for p in paths:
            if os.path.exists(p):
                engine = ort.InferenceSession(p, providers=["CPUExecutionProvider"])
                print(f"[Model] Loaded: {os.path.basename(p)}")
                return
        print("[Model] Not found")
    except Exception as e:
        print(f"[Model] Error: {e}")


def build_ui():
    """构建 UI"""
    dpg.create_context()
    dpg.create_viewport(title="AutoToon Studio — Toon Shader Preview", width=950, height=650)

    # 主题
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (25, 25, 28))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 45))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (50, 50, 55))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (70, 70, 75))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (80, 140, 220))
    dpg.bind_theme(theme)

    # 纹理
    with dpg.texture_registry():
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*(VIEWER_SIZE**2), tag="preview_tex")
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.08]*4*(VIEWER_SIZE**2), tag="ref_tex")

    # 文件对话框
    with dpg.file_dialog(directory_selector=False, show=False, callback=on_ref_selected,
                         tag="file_dlg", width=500, height=300):
        dpg.add_file_extension(".png")
        dpg.add_file_extension(".jpg")
        dpg.add_file_extension(".jpeg")

    with dpg.window(tag="main"):
        # 标题
        dpg.add_text("AutoToon Studio — Toon Shader Preview", color=(80, 140, 220))
        dpg.add_separator()

        with dpg.group(horizontal=True):
            # === 左侧：参考图 ===
            with dpg.group():
                dpg.add_text("Reference Image", color=(150, 160, 180))
                dpg.add_button(label="  Upload Image  ", callback=lambda: dpg.show_item("file_dlg"))
                dpg.add_text("", tag="ref_path", color=(100, 100, 100))
                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                    dpg.draw_rectangle((0,0), (VIEWER_SIZE, VIEWER_SIZE), fill=(20, 20, 22))
                    dpg.draw_image("ref_tex", (0,0), (VIEWER_SIZE, VIEWER_SIZE))

                dpg.add_button(label="  Extract Style (AI)  ", callback=on_infer, height=30)
                dpg.add_text("", tag="status", color=(100, 180, 100))
                dpg.add_spacer(height=10)

            dpg.add_spacer(width=20)

            # === 右侧：预览 + 参数 ===
            with dpg.group():
                dpg.add_text("Material Preview", color=(150, 160, 180))

                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                    dpg.draw_rectangle((0,0), (VIEWER_SIZE, VIEWER_SIZE), fill=(20, 20, 22))
                    dpg.draw_image("preview_tex", (0,0), (VIEWER_SIZE, VIEWER_SIZE))

                dpg.add_separator()
                dpg.add_text("Material Parameters", color=(120, 130, 150))

                # 阴影色
                dpg.add_text("Shadow Color:", color=(100, 100, 100))
                with dpg.group(horizontal=True):
                    dpg.add_text("R")
                    dpg.add_slider_float(tag="slider_shadow_r", default_value=material["shadow_color"][0],
                                        min_value=0, max_value=1, width=120, callback=on_param_change, user_data="shadow_color_r")
                with dpg.group(horizontal=True):
                    dpg.add_text("G")
                    dpg.add_slider_float(tag="slider_shadow_g", default_value=material["shadow_color"][1],
                                        min_value=0, max_value=1, width=120, callback=on_param_change, user_data="shadow_color_g")
                with dpg.group(horizontal=True):
                    dpg.add_text("B")
                    dpg.add_slider_float(tag="slider_shadow_b", default_value=material["shadow_color"][2],
                                        min_value=0, max_value=1, width=120, callback=on_param_change, user_data="shadow_color_b")

                dpg.add_spacer(height=5)

                # 其他参数
                with dpg.group(horizontal=True):
                    dpg.add_text("Specular:    ")
                    dpg.add_slider_float(tag="slider_spec", default_value=material["specular_intensity"],
                                        min_value=0, max_value=1.5, width=150, callback=on_param_change, user_data="specular_intensity")

                with dpg.group(horizontal=True):
                    dpg.add_text("Rim Light:   ")
                    dpg.add_slider_float(tag="slider_rim", default_value=material["rim_intensity"],
                                        min_value=0, max_value=1.5, width=150, callback=on_param_change, user_data="rim_intensity")

                with dpg.group(horizontal=True):
                    dpg.add_text("Outline:     ")
                    dpg.add_slider_float(tag="slider_outline", default_value=material["outline_width"],
                                        min_value=0.5, max_value=5, width=150, callback=on_param_change, user_data="outline_width")

                with dpg.group(horizontal=True):
                    dpg.add_text("Shade Levels:")
                    dpg.add_slider_int(tag="slider_levels", default_value=material["shade_levels"],
                                       min_value=2, max_value=4, width=150, callback=on_param_change, user_data="shade_levels")

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)


def run():
    print("=" * 50)
    print("AutoToon Studio — Toon Shader Preview")
    print("=" * 50)

    print("\n[Init] Loading model...")
    load_model()

    print("[Init] Building UI...")
    build_ui()

    print("[Init] Rendering initial preview...")
    update_preview()

    print("\n[Ready] Running main loop...\n")

    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()

    dpg.destroy_context()
    print("\n[Exit]")


if __name__ == "__main__":
    run()