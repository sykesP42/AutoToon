"""
ui_brush.py — AutoToon Studio 带涂鸦刷子版本
支持在参考图上涂鸦标记重点/忽略区域
"""
import os
import numpy as np
import cv2
import dearpygui.dearpygui as dpg

VIEWER_SIZE = 400

# 全局状态
ref_image = None
ref_image_display = None  # 带涂鸦的显示图像
mask_image = None  # 涂鸦掩码 (0=无, 1=重点, 2=忽略)
engine = None
brush_mode = 0  # 0=无, 1=重点(绿色), 2=忽略(红色)
brush_size = 20
last_pos = None

_sphere_data = None

# 材质参数
material = {
    "shadow_r": 0.35,
    "shadow_g": 0.35,
    "shadow_b": 0.4,
    "specular": 0.6,
    "rim": 0.5,
    "outline": 2.0,
    "levels": 3,
}


def precompute_sphere(size=400):
    global _sphere_data
    if _sphere_data is not None:
        return _sphere_data

    cx, cy = size // 2, size // 2
    radius = size // 2 - 20
    y_coords, x_coords = np.ogrid[:size, :size]
    dx = x_coords - cx
    dy = y_coords - cy
    dist = np.sqrt(dx*dx + dy*dy)
    nx = dx / radius
    ny = dy / radius
    nz_sq = 1 - nx*nx - ny*ny
    nz = np.sqrt(np.maximum(0, nz_sq))
    mask = dist <= radius
    outline_mask = (dist > radius - 3) & (dist <= radius)

    _sphere_data = {'nx': nx.astype(np.float32), 'ny': ny.astype(np.float32),
                    'nz': nz.astype(np.float32), 'mask': mask, 'outline_mask': outline_mask}
    return _sphere_data


def render_sphere_fast():
    data = precompute_sphere(VIEWER_SIZE)
    size = VIEWER_SIZE

    light = np.array([0.5, -0.5, 0.8])
    light = light / np.linalg.norm(light)

    nx, ny, nz = data['nx'], data['ny'], data['nz']
    mask = data['mask']

    NdotL = np.maximum(0, nx * light[0] + ny * light[1] + nz * light[2])

    levels = material["levels"]
    if levels == 2:
        shade = (NdotL > 0.5).astype(np.float32)
    elif levels == 3:
        shade = np.clip(np.floor(NdotL * 3) / 2, 0, 1)
    else:
        shade = np.clip(np.floor(NdotL * 4) / 3, 0, 1)

    shade = np.clip(shade + material["shadow_r"] * 0.3, 0, 1)

    shadow = np.array([material["shadow_r"], material["shadow_g"], material["shadow_b"]])
    base = np.array([0.9, 0.9, 0.92])

    img = np.zeros((size, size, 3), dtype=np.float32)
    for c in range(3):
        img[:,:,c] = shadow[c] + (base[c] - shadow[c]) * shade

    half = np.array([0.25, -0.25, 0.9])
    half = half / np.linalg.norm(half)
    NdotH = np.maximum(0, nx * half[0] + ny * half[1] + nz * half[2])
    spec = np.power(NdotH, 32) * material["specular"]
    spec = np.clip(spec, 0, 1)

    img[:,:,0] += spec * 0.7
    img[:,:,1] += spec * 0.8
    img[:,:,2] += spec * 0.9

    rim = np.power(1 - nz, 3) * material["rim"]
    img[:,:,0] += rim * 0.8
    img[:,:,1] += rim * 0.85
    img[:,:,2] += rim * 1.0

    img = np.clip(img, 0, 1)

    bg = np.ones((size, size, 3), dtype=np.float32) * 0.12
    result = bg.copy()
    result[mask] = img[mask]
    result[data['outline_mask']] = np.array([0.1, 0.1, 0.12])

    result_bgr = (result * 255).astype(np.uint8)
    return cv2.cvtColor(result_bgr, cv2.COLOR_RGB2BGR)


def update_preview():
    img = render_sphere_fast()
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    if dpg.does_item_exist("preview_tex"):
        dpg.set_value("preview_tex", rgba.ravel().tolist())


def update_ref_display():
    """更新参考图显示（带涂鸦叠加）"""
    global ref_image_display

    if ref_image is None:
        print("[Update] No ref_image")
        return

    # 复制原图
    display = ref_image.copy()

    # 叠加涂鸦掩码
    if mask_image is not None:
        focus_mask = (mask_image == 1)
        if np.any(focus_mask):
            display[focus_mask] = cv2.addWeighted(display[focus_mask], 0.6,
                                                   np.array([0, 255, 100], dtype=np.uint8), 0.4, 0)
        ignore_mask = (mask_image == 2)
        if np.any(ignore_mask):
            display[ignore_mask] = cv2.addWeighted(display[ignore_mask], 0.6,
                                                    np.array([100, 50, 255], dtype=np.uint8), 0.4, 0)

    ref_image_display = display.copy()

    # 缩放到固定尺寸
    display = cv2.resize(display, (VIEWER_SIZE, VIEWER_SIZE))

    # 转换 RGBA
    rgba = cv2.cvtColor(display, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    data = rgba.ravel().tolist()

    # 直接更新已存在的纹理
    if dpg.does_item_exist("ref_tex"):
        dpg.set_value("ref_tex", data)
        print("[Update] Texture value updated")
    else:
        print("[Update] ref_tex not found!")


def on_mouse_drag(sender, app_data):
    """鼠标拖动涂鸦"""
    global last_pos

    if ref_image is None or brush_mode == 0:
        return

    # 获取鼠标位置
    pos = dpg.get_mouse_pos(local=False)

    # 计算在图像上的位置
    # 这里简化处理，实际需要根据drawlist位置计算
    x = int(pos[0] - 50)  # 偏移量需要根据UI调整
    y = int(pos[1] - 80)

    if 0 <= x < VIEWER_SIZE and 0 <= y < VIEWER_SIZE:
        # 计算原图上的对应位置
        if mask_image is not None:
            h, w = mask_image.shape
            orig_x = int(x * w / VIEWER_SIZE)
            orig_y = int(y * h / VIEWER_SIZE)

            # 画圆
            cv2.circle(mask_image, (orig_x, orig_y), int(brush_size * w / VIEWER_SIZE), brush_mode, -1)

        update_ref_display()


def on_mouse_release(sender, app_data):
    """鼠标释放"""
    global last_pos
    last_pos = None


def set_brush_mode(mode):
    """设置刷子模式"""
    global brush_mode
    brush_mode = mode
    print(f"[Brush] Mode: {['Off', 'Focus (Green)', 'Ignore (Red)'][mode]}")


def clear_mask():
    """清除涂鸦"""
    global mask_image
    if ref_image is not None:
        mask_image = np.zeros(ref_image.shape[:2], dtype=np.uint8)
        update_ref_display()
        print("[Brush] Cleared")


def on_param_change(sender, app_data, user_data):
    material[user_data] = app_data
    update_preview()


def on_upload_click():
    if dpg.does_item_exist("file_dlg"):
        dpg.show_item("file_dlg")


def on_file_selected(sender, app_data):
    global ref_image, mask_image

    if isinstance(app_data, dict):
        path = app_data.get("file_path_name", "")
    elif isinstance(app_data, str):
        path = app_data
    else:
        return

    if not path or not os.path.exists(path):
        return

    img = cv2.imread(path)
    if img is None:
        return

    ref_image = img.copy()
    mask_image = np.zeros(img.shape[:2], dtype=np.uint8)  # 初始化涂鸦掩码

    update_ref_display()

    if dpg.does_item_exist("ref_path"):
        dpg.set_value("ref_path", os.path.basename(path))

    print(f"[Load] {img.shape[1]}x{img.shape[0]}")


def on_infer():
    """AI 推理 - 考虑涂鸦区域"""
    global engine

    if engine is None:
        dpg.set_value("status", "No model!")
        return

    if ref_image is None:
        dpg.set_value("status", "Upload image first!")
        return

    try:
        from PIL import Image
        print("[Infer] Processing...")

        MEAN = np.array([0.485, 0.456, 0.406])
        STD = np.array([0.229, 0.224, 0.225])

        # 准备图像
        img = ref_image.copy()

        # 如果有涂鸦掩码，可以在这里处理
        # 例如：对重点区域进行加权，或忽略某些区域
        if mask_image is not None and np.any(mask_image > 0):
            focus_ratio = np.sum(mask_image == 1) / mask_image.size
            ignore_ratio = np.sum(mask_image == 2) / mask_image.size
            print(f"[Infer] Mask: focus={focus_ratio:.1%}, ignore={ignore_ratio:.1%}")

            # 可选：对忽略区域进行模糊处理
            ignore_mask = (mask_image == 2)
            if np.any(ignore_mask):
                img_blur = cv2.GaussianBlur(img, (51, 51), 0)
                img[ignore_mask] = img_blur[ignore_mask]

        img_pil = Image.fromarray(img).convert("RGB").resize((224, 224))
        x = np.array(img_pil, dtype=np.float32) / 255.0
        x = ((x - MEAN) / STD).astype(np.float32)
        x = x.transpose(2, 0, 1)[np.newaxis, :]

        input_name = engine.get_inputs()[0].name
        preds = engine.run(["params"], {input_name: x})[0][0]

        # 更新参数
        material["shadow_r"] = float(preds[0])
        material["shadow_g"] = float(preds[1])
        material["shadow_b"] = float(preds[2])
        material["specular"] = float(preds[3])
        material["rim"] = float(preds[4])
        material["outline"] = float(preds[5]) * 2.5 + 0.5

        # 更新UI
        dpg.set_value("s_r", material["shadow_r"])
        dpg.set_value("s_g", material["shadow_g"])
        dpg.set_value("s_b", material["shadow_b"])
        dpg.set_value("s_spec", material["specular"])
        dpg.set_value("s_rim", material["rim"])
        dpg.set_value("s_out", material["outline"])

        update_preview()
        dpg.set_value("status", "Done!")
        print(f"[Infer] {preds[:6]}")

    except Exception as e:
        import traceback
        print(f"[Infer] Error: {e}")
        traceback.print_exc()
        dpg.set_value("status", "Error!")


def load_model():
    global engine
    try:
        import onnxruntime as ort
        path = os.path.join(os.path.dirname(__file__), "..", "training", "mooatoon_model.onnx")
        if os.path.exists(path):
            engine = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
            print("[Model] Loaded")
    except Exception as e:
        print(f"[Model] {e}")


def build_ui():
    dpg.create_context()
    dpg.create_viewport(title="AutoToon Studio - Brush Mode", width=1000, height=620)

    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (25, 25, 28))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 45))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (50, 55, 65))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (70, 130, 200))
    dpg.bind_theme(t)

    with dpg.texture_registry(tag="tex_reg"):
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*VIEWER_SIZE**2, tag="preview_tex")
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.08]*4*VIEWER_SIZE**2, tag="ref_tex")

    with dpg.file_dialog(directory_selector=False, show=False, callback=on_file_selected,
                        tag="file_dlg", width=500, height=300):
        dpg.add_file_extension("Image Files (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif){.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp,.gif}", color=(80, 180, 220))

    with dpg.window(tag="main"):
        dpg.add_text("AutoToon Studio — Brush Mode", color=(70, 140, 210))
        dpg.add_separator()

        with dpg.group(horizontal=True):
            # 左：参考图+涂鸦
            with dpg.group():
                dpg.add_text("Reference (Draw to mark)", color=(140, 140, 150))

                with dpg.group(horizontal=True):
                    dpg.add_button(label="Upload", callback=on_upload_click, width=70)

                    # 刷子模式按钮
                    dpg.add_button(label="Off", tag="btn_off", callback=lambda: set_brush_mode(0), width=50)
                    dpg.add_button(label="Focus", tag="btn_focus", callback=lambda: set_brush_mode(1), width=55)
                    dpg.add_button(label="Ignore", tag="btn_ignore", callback=lambda: set_brush_mode(2), width=60)
                    dpg.add_button(label="Clear", callback=clear_mask, width=50)

                dpg.add_text("", tag="ref_path", color=(90, 90, 90))

                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE, tag="ref_drawlist"):
                    dpg.draw_rectangle((0,0), (VIEWER_SIZE, VIEWER_SIZE), fill=(18, 18, 20))
                    dpg.draw_image("ref_tex", (0,0), (VIEWER_SIZE, VIEWER_SIZE), tag="ref_img")

                # 刷子大小
                with dpg.group(horizontal=True):
                    dpg.add_text("Brush Size:")
                    dpg.add_slider_int(tag="brush_size", default_value=20, min_value=5, max_value=50, width=150,
                                      callback=lambda s,a: globals().update(brush_size=a))

                dpg.add_button(label="Extract Style (AI)", callback=on_infer)
                dpg.add_text("", tag="status", color=(80, 180, 80))

            dpg.add_spacer(width=15)

            # 右：预览+参数
            with dpg.group():
                dpg.add_text("Preview", color=(140, 140, 150))
                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                    dpg.draw_rectangle((0,0), (VIEWER_SIZE, VIEWER_SIZE), fill=(18, 18, 20))
                    dpg.draw_image("preview_tex", (0,0), (VIEWER_SIZE, VIEWER_SIZE))

                dpg.add_separator()
                dpg.add_text("Parameters", color=(110, 110, 120))

                sl = [("Shadow R", "s_r", "shadow_r", 0, 1),
                      ("Shadow G", "s_g", "shadow_g", 0, 1),
                      ("Shadow B", "s_b", "shadow_b", 0, 1),
                      ("Specular", "s_spec", "specular", 0, 1.5),
                      ("Rim Light", "s_rim", "rim", 0, 1.5),
                      ("Outline", "s_out", "outline", 0.5, 5)]

                for label, tag, key, mn, mx in sl:
                    with dpg.group(horizontal=True):
                        dpg.add_text(f"{label}:", color=(100, 100, 100))
                        dpg.add_slider_float(tag=tag, default_value=material[key],
                                            min_value=mn, max_value=mx, width=140,
                                            callback=on_param_change, user_data=key)

        # 提示
        dpg.add_spacer(height=10)
        dpg.add_text("Tips: Focus=Green (analyze more), Ignore=Red (skip)", color=(80, 80, 80))

    # 鼠标事件
    with dpg.handler_registry():
        dpg.add_mouse_drag_handler(button=0, callback=on_mouse_drag)
        dpg.add_mouse_release_handler(button=0, callback=on_mouse_release)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)


def run():
    print("=" * 50)
    print("AutoToon Studio - Brush Mode")
    print("  - Green brush: Focus area")
    print("  - Red brush: Ignore area")
    print("=" * 50)

    load_model()
    build_ui()
    update_preview()

    print("\n[Ready]\n")

    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == "__main__":
    run()