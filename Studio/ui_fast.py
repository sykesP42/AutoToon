"""
ui_fast.py — AutoToon Studio 高效版本
预计算球体数据 + 快速渲染
"""
import os
import numpy as np
import cv2
import dearpygui.dearpygui as dpg

VIEWER_SIZE = 400

# 全局状态
ref_image = None
engine = None

# 预计算的球体数据
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
    """预计算球体几何数据（只执行一次）"""
    global _sphere_data
    if _sphere_data is not None:
        return _sphere_data

    cx, cy = size // 2, size // 2
    radius = size // 2 - 20

    # 创建坐标网格
    y_coords, x_coords = np.ogrid[:size, :size]
    dx = x_coords - cx
    dy = y_coords - cy
    dist = np.sqrt(dx*dx + dy*dy)

    # 法线
    nx = dx / radius
    ny = dy / radius
    nz_sq = 1 - nx*nx - ny*ny
    nz = np.sqrt(np.maximum(0, nz_sq))

    # 掩码
    mask = dist <= radius
    outline_mask = (dist > radius - 3) & (dist <= radius)

    _sphere_data = {
        'nx': nx.astype(np.float32),
        'ny': ny.astype(np.float32),
        'nz': nz.astype(np.float32),
        'mask': mask,
        'outline_mask': outline_mask,
        'radius': radius,
        'cx': cx, 'cy': cy
    }
    return _sphere_data


def render_sphere_fast():
    """快速渲染球体（向量化计算）"""
    data = precompute_sphere(VIEWER_SIZE)
    size = VIEWER_SIZE

    # 光源
    light = np.array([0.5, -0.5, 0.8])
    light = light / np.linalg.norm(light)

    # 获取法线
    nx, ny, nz = data['nx'], data['ny'], data['nz']
    mask = data['mask']

    # 漫反射 (向量化)
    NdotL = np.maximum(0, nx * light[0] + ny * light[1] + nz * light[2])

    # 色阶化
    levels = material["levels"]
    if levels == 2:
        shade = (NdotL > 0.5).astype(np.float32)
    elif levels == 3:
        shade = np.clip(np.floor(NdotL * 3) / 2, 0, 1)
    else:
        shade = np.clip(np.floor(NdotL * 4) / 3, 0, 1)

    # 环境光
    shade = np.clip(shade + material["shadow_r"] * 0.3, 0, 1)

    # 创建颜色
    shadow = np.array([material["shadow_r"], material["shadow_g"], material["shadow_b"]])
    base = np.array([0.9, 0.9, 0.92])

    # 广播计算颜色
    img = np.zeros((size, size, 3), dtype=np.float32)
    for c in range(3):
        img[:,:,c] = shadow[c] + (base[c] - shadow[c]) * shade

    # 高光 (向量化)
    half = np.array([0.25, -0.25, 0.9])
    half = half / np.linalg.norm(half)
    NdotH = np.maximum(0, nx * half[0] + ny * half[1] + nz * half[2])
    spec = np.power(NdotH, 32) * material["specular"]
    spec = np.clip(spec, 0, 1)

    # 添加高光
    img[:,:,0] += spec * 0.7
    img[:,:,1] += spec * 0.8
    img[:,:,2] += spec * 0.9

    # 边缘光
    rim = np.power(1 - nz, 3) * material["rim"]
    img[:,:,0] += rim * 0.8
    img[:,:,1] += rim * 0.85
    img[:,:,2] += rim * 1.0

    # 应用掩码
    img = np.clip(img, 0, 1)

    # 背景
    bg = np.ones((size, size, 3), dtype=np.float32) * 0.12
    result = bg.copy()
    result[mask] = img[mask]

    # 描边
    outline_mask = data['outline_mask']
    outline_color = np.array([0.1, 0.1, 0.12])
    result[outline_mask] = outline_color

    # 转 BGR uint8
    result_bgr = (result * 255).astype(np.uint8)
    result_bgr = cv2.cvtColor(result_bgr, cv2.COLOR_RGB2BGR)

    return result_bgr


def update_preview():
    """更新预览"""
    img = render_sphere_fast()
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    if dpg.does_item_exist("preview_tex"):
        dpg.set_value("preview_tex", rgba.ravel().tolist())


def on_param_change(sender, app_data, user_data):
    """参数变化"""
    material[user_data] = app_data
    update_preview()


def on_upload_click():
    """上传按钮点击"""
    print("[UI] Opening file dialog...")
    if dpg.does_item_exist("file_dlg"):
        dpg.show_item("file_dlg")
    else:
        print("[UI] File dialog not found!")


def on_file_selected(sender, app_data):
    """文件选择回调"""
    global ref_image

    print(f"[DEBUG] sender={sender}, app_data={app_data}")

    # 获取文件路径
    if isinstance(app_data, dict):
        path = app_data.get("file_path_name", "")
    elif isinstance(app_data, str):
        path = app_data
    else:
        print(f"[Error] Unknown app_data type: {type(app_data)}")
        return

    print(f"[Load] Path: {path}")

    if not path:
        print("[Error] Empty path")
        return

    if not os.path.exists(path):
        print(f"[Error] File not found: {path}")
        return

    try:
        img = cv2.imread(path)
        if img is None:
            print(f"[Error] cv2.imread failed for: {path}")
            return

        print(f"[Load] Image shape: {img.shape}")
        ref_image = img.copy()

        # 缩放
        h, w = img.shape[:2]
        scale = VIEWER_SIZE / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w*scale), int(h*scale)))
        h, w = img.shape[:2]

        print(f"[Load] Resized: {w}x{h}")

        # 更新纹理
        rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
        data = rgba.ravel().tolist()

        # 直接设置纹理值（纹理已存在）
        if dpg.does_item_exist("ref_tex"):
            dpg.set_value("ref_tex", data)
            print(f"[Load] Texture updated: {w}x{h}")
        else:
            print("[Error] ref_tex does not exist")

        # 更新路径显示
        if dpg.does_item_exist("ref_path"):
            dpg.set_value("ref_path", os.path.basename(path))

        print("[Load] SUCCESS!")

    except Exception as e:
        import traceback
        print(f"[Error] Exception: {e}")
        traceback.print_exc()


def on_infer():
    """AI 推理"""
    global engine

    if engine is None:
        print("[Infer] No model")
        dpg.set_value("status", "No model!")
        return

    if ref_image is None:
        print("[Infer] No image")
        dpg.set_value("status", "Upload image first!")
        return

    try:
        from PIL import Image
        print("[Infer] Processing...")

        MEAN = np.array([0.485, 0.456, 0.406])
        STD = np.array([0.229, 0.224, 0.225])

        img = Image.fromarray(ref_image).convert("RGB").resize((224, 224))
        x = np.array(img, dtype=np.float32) / 255.0
        x = ((x - MEAN) / STD).astype(np.float32)  # 确保是 float32
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
        print(f"[Infer] Error: {e}")
        dpg.set_value("status", "Error!")


def load_model():
    global engine
    try:
        import onnxruntime as ort
        path = os.path.join(os.path.dirname(__file__), "..", "training", "mooatoon_model.onnx")
        if os.path.exists(path):
            engine = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
            print(f"[Model] Loaded")
    except Exception as e:
        print(f"[Model] {e}")


def build_ui():
    dpg.create_context()
    dpg.create_viewport(title="AutoToon Studio", width=900, height=580)

    # 主题
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (25, 25, 28))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 45))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (50, 55, 65))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (70, 130, 200))
    dpg.bind_theme(t)

    # 纹理 - 使用固定标签的 texture_registry
    with dpg.texture_registry(tag="tex_reg"):
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*VIEWER_SIZE**2, tag="preview_tex")
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.08]*4*VIEWER_SIZE**2, tag="ref_tex")

    # 文件对话框
    with dpg.file_dialog(directory_selector=False, show=False, callback=on_file_selected,
                        tag="file_dlg", width=500, height=300):
        dpg.add_file_extension("Image Files (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif){.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp,.gif}", color=(80, 180, 220))
        dpg.add_file_extension(".png", color=(100, 200, 255))
        dpg.add_file_extension(".jpg", color=(100, 200, 255))
        dpg.add_file_extension(".jpeg", color=(100, 200, 255))
        dpg.add_file_extension(".bmp", color=(100, 200, 255))
        dpg.add_file_extension(".tiff", color=(100, 200, 255))
        dpg.add_file_extension(".tif", color=(100, 200, 255))
        dpg.add_file_extension(".webp", color=(100, 200, 255))
        dpg.add_file_extension(".gif", color=(100, 200, 255))

    with dpg.window(tag="main"):
        dpg.add_text("AutoToon Studio", color=(70, 140, 210))
        dpg.add_separator()

        with dpg.group(horizontal=True):
            # 左：参考图
            with dpg.group():
                dpg.add_text("Reference", color=(140, 140, 150))
                dpg.add_button(label="Upload Image", callback=on_upload_click)
                dpg.add_text("", tag="ref_path", color=(90, 90, 90))
                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE, tag="ref_drawlist"):
                    dpg.draw_rectangle((0,0), (VIEWER_SIZE, VIEWER_SIZE), fill=(18, 18, 20))
                    dpg.draw_image("ref_tex", (0,0), (VIEWER_SIZE, VIEWER_SIZE), tag="ref_img")

                dpg.add_button(label="Extract Style", callback=on_infer)
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

                # 参数滑块
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

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)


def run():
    print("=" * 40)
    print("AutoToon Studio - Fast Version")
    print("=" * 40)

    load_model()
    build_ui()
    update_preview()

    print("\n[Ready]\n")

    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == "__main__":
    run()