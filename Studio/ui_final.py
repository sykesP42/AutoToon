"""
ui_final.py — AutoToon Studio 最终版
简单可靠的图片预览 + 涂鸦功能
"""
import os
import numpy as np
import cv2
import dearpygui.dearpygui as dpg

VIEWER_SIZE = 400

# 全局状态
ref_image = None
mask_image = None
engine = None
brush_mode = 0
brush_size = 20

_sphere_data = None

material = {
    "shadow_r": 0.35, "shadow_g": 0.35, "shadow_b": 0.4,
    "specular": 0.6, "rim": 0.5, "outline": 2.0, "levels": 3,
}


def precompute_sphere(size=400):
    global _sphere_data
    if _sphere_data is not None:
        return _sphere_data
    cx, cy = size // 2, size // 2
    radius = size // 2 - 20
    y_coords, x_coords = np.ogrid[:size, :size]
    dx, dy = x_coords - cx, y_coords - cy
    dist = np.sqrt(dx*dx + dy*dy)
    nx, ny = dx / radius, dy / radius
    nz = np.sqrt(np.maximum(0, 1 - nx*nx - ny*ny))
    _sphere_data = {'nx': nx.astype(np.float32), 'ny': ny, 'nz': nz,
                    'mask': dist <= radius, 'outline': (dist > radius-3) & (dist <= radius)}
    return _sphere_data


def render_sphere():
    data = precompute_sphere(VIEWER_SIZE)
    light = np.array([0.5, -0.5, 0.8]) / np.linalg.norm([0.5, -0.5, 0.8])
    nx, ny, nz, mask = data['nx'], data['ny'], data['nz'], data['mask']

    NdotL = np.maximum(0, nx*light[0] + ny*light[1] + nz*light[2])
    shade = np.clip(np.floor(NdotL * 3) / 2, 0, 1) + material["shadow_r"] * 0.3
    shade = np.clip(shade, 0, 1)

    shadow = [material["shadow_r"], material["shadow_g"], material["shadow_b"]]
    base = [0.9, 0.9, 0.92]

    img = np.zeros((VIEWER_SIZE, VIEWER_SIZE, 3), dtype=np.float32)
    for c in range(3):
        img[:,:,c] = shadow[c] + (base[c] - shadow[c]) * shade

    half = np.array([0.25, -0.25, 0.9]) / np.linalg.norm([0.25, -0.25, 0.9])
    NdotH = np.maximum(0, nx*half[0] + ny*half[1] + nz*half[2])
    spec = np.clip(np.power(NdotH, 32) * material["specular"], 0, 1)
    img[:,:,0] += spec * 0.7; img[:,:,1] += spec * 0.8; img[:,:,2] += spec * 0.9

    rim = np.power(1 - nz, 3) * material["rim"]
    img[:,:,0] += rim * 0.8; img[:,:,1] += rim * 0.85; img[:,:,2] += rim * 1.0

    img = np.clip(img, 0, 1)
    result = np.ones((VIEWER_SIZE, VIEWER_SIZE, 3), dtype=np.float32) * 0.12
    result[mask] = img[mask]
    result[data['outline']] = [0.1, 0.1, 0.12]

    return (result * 255).astype(np.uint8)[:,:,::-1].copy()  # RGB->BGR


def update_sphere():
    img = render_sphere()
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    dpg.set_value("sphere_tex", rgba.ravel().tolist())


def update_ref_image():
    """更新参考图显示"""
    if ref_image is None:
        return

    # 缩放到固定尺寸
    display = cv2.resize(ref_image.copy(), (VIEWER_SIZE, VIEWER_SIZE))

    # 叠加涂鸦
    if mask_image is not None:
        mask_resized = cv2.resize(mask_image, (VIEWER_SIZE, VIEWER_SIZE), interpolation=cv2.INTER_NEAREST)
        # 绿色 = 重点
        green = (mask_resized == 1)
        display[green] = (display[green] * 0.6 + np.array([100, 255, 0]) * 0.4).astype(np.uint8)
        # 红色 = 忽略
        red = (mask_resized == 2)
        display[red] = (display[red] * 0.6 + np.array([0, 50, 255]) * 0.4).astype(np.uint8)

    rgba = cv2.cvtColor(display, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    dpg.set_value("ref_tex", rgba.ravel().tolist())
    print(f"[Display] Updated")


def on_file_select(sender, app_data):
    global ref_image, mask_image
    path = app_data.get("file_path_name", "") if isinstance(app_data, dict) else ""
    if not path:
        return

    img = cv2.imread(path)
    if img is None:
        print(f"[Error] Cannot load: {path}")
        return

    ref_image = img
    mask_image = np.zeros(img.shape[:2], dtype=np.uint8)
    update_ref_image()
    dpg.set_value("ref_path", os.path.basename(path))
    print(f"[Load] {img.shape[1]}x{img.shape[0]}")


def on_mouse_drag(sender, app_data):
    if ref_image is None or brush_mode == 0:
        return

    # 获取鼠标在参考图区域的位置
    mx, my = dpg.get_mouse_pos()
    # 假设参考图在窗口左侧，起点约 (20, 80)
    x = int((mx - 20) / VIEWER_SIZE * ref_image.shape[1])
    y = int((my - 80) / VIEWER_SIZE * ref_image.shape[0])

    if 0 <= x < ref_image.shape[1] and 0 <= y < ref_image.shape[0]:
        size = int(brush_size * ref_image.shape[1] / VIEWER_SIZE)
        cv2.circle(mask_image, (x, y), size, brush_mode, -1)
        update_ref_image()


def on_brush(mode):
    global brush_mode
    brush_mode = mode
    modes = ["Off", "Focus (Green)", "Ignore (Red)"]
    print(f"[Brush] {modes[mode]}")


def on_clear():
    global mask_image
    if ref_image is not None:
        mask_image = np.zeros(ref_image.shape[:2], dtype=np.uint8)
        update_ref_image()


def on_infer():
    global engine
    if engine is None or ref_image is None:
        dpg.set_value("status", "No image or model")
        return

    try:
        from PIL import Image
        MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])

        img = ref_image.copy()
        # 忽略区域模糊
        if mask_image is not None and np.any(mask_image == 2):
            img[mask_image == 2] = cv2.GaussianBlur(img, (51, 51), 0)[mask_image == 2]

        x = np.array(Image.fromarray(img).convert("RGB").resize((224, 224)), dtype=np.float32) / 255.0
        x = ((x - MEAN) / STD).astype(np.float32).transpose(2, 0, 1)[np.newaxis, :]

        preds = engine.run(["params"], {engine.get_inputs()[0].name: x})[0][0]

        material["shadow_r"] = float(preds[0])
        material["shadow_g"] = float(preds[1])
        material["shadow_b"] = float(preds[2])
        material["specular"] = float(preds[3])
        material["rim"] = float(preds[4])
        material["outline"] = float(preds[5]) * 2.5 + 0.5

        for k, tag in [("shadow_r","s_r"), ("shadow_g","s_g"), ("shadow_b","s_b"),
                       ("specular","s_sp"), ("rim","s_rm"), ("outline","s_ot")]:
            dpg.set_value(tag, material[k])

        update_sphere()
        dpg.set_value("status", "Done!")
        print(f"[Infer] {preds[:6]}")
    except Exception as e:
        print(f"[Error] {e}")
        dpg.set_value("status", "Error")


def on_param(s, a, k):
    material[k] = a
    update_sphere()


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


def build():
    dpg.create_context()
    dpg.create_viewport(title="AutoToon Studio", width=920, height=560)

    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (25, 25, 28))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 45))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (55, 60, 70))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (70, 130, 200))
    dpg.bind_theme(t)

    # 纹理 - 固定尺寸
    with dpg.texture_registry():
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*VIEWER_SIZE**2, tag="ref_tex")
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*VIEWER_SIZE**2, tag="sphere_tex")

    # 文件对话框
    with dpg.file_dialog(directory_selector=False, show=False, callback=on_file_select,
                        tag="fdlg", width=500, height=300):
        dpg.add_file_extension("Images{.png,.jpg,.jpeg,.bmp,.webp,.gif}", color=(80, 180, 220))

    with dpg.window(tag="main"):
        dpg.add_text("AutoToon Studio", color=(70, 140, 210))
        dpg.add_separator()

        with dpg.group(horizontal=True):
            # 左: 参考图
            with dpg.group():
                dpg.add_text("Reference", color=(140, 140, 150))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Upload", callback=lambda: dpg.show_item("fdlg"), width=60)
                    dpg.add_button(label="Focus", callback=lambda: on_brush(1), width=50)
                    dpg.add_button(label="Ignore", callback=lambda: on_brush(2), width=55)
                    dpg.add_button(label="Clear", callback=on_clear, width=50)
                dpg.add_text("", tag="ref_path", color=(90, 90, 90))
                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                    dpg.draw_image("ref_tex", (0, 0), (VIEWER_SIZE, VIEWER_SIZE))
                with dpg.group(horizontal=True):
                    dpg.add_text("Brush:")
                    dpg.add_slider_int(tag="bsize", default_value=20, min_value=5, max_value=50, width=120,
                                      callback=lambda s,a: globals().__setitem__('brush_size', a))
                dpg.add_button(label="Extract Style", callback=on_infer, width=120)
                dpg.add_text("", tag="status", color=(80, 180, 80))

            dpg.add_spacer(width=15)

            # 右: 预览
            with dpg.group():
                dpg.add_text("Preview", color=(140, 140, 150))
                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                    dpg.draw_image("sphere_tex", (0, 0), (VIEWER_SIZE, VIEWER_SIZE))
                dpg.add_separator()
                dpg.add_text("Parameters", color=(110, 110, 120))
                for label, tag, key, mn, mx in [
                    ("Shadow R", "s_r", "shadow_r", 0, 1),
                    ("Shadow G", "s_g", "shadow_g", 0, 1),
                    ("Shadow B", "s_b", "shadow_b", 0, 1),
                    ("Specular", "s_sp", "specular", 0, 1.5),
                    ("Rim", "s_rm", "rim", 0, 1.5),
                    ("Outline", "s_ot", "outline", 0.5, 5)]:
                    with dpg.group(horizontal=True):
                        dpg.add_text(f"{label}:")
                        dpg.add_slider_float(tag=tag, default_value=material[key], min_value=mn, max_value=mx,
                                            width=130, callback=lambda s,a,k=key: on_param(s,a,k))

        dpg.add_text("Focus=Green (analyze), Ignore=Red (blur)", color=(70, 70, 70))

    # 鼠标拖动
    with dpg.handler_registry():
        dpg.add_mouse_drag_handler(button=0, callback=on_mouse_drag)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)


def run():
    print("=" * 40)
    print("AutoToon Studio")
    print("=" * 40)
    load_model()
    build()
    update_sphere()
    print("\n[Ready]\n")
    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()
    dpg.destroy_context()


if __name__ == "__main__":
    run()