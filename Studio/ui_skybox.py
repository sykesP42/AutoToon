"""
ui_skybox.py — AutoToon Studio Skybox 版本
材质球预览 + 多种 Skybox 背景 + 多形状支持
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
current_skybox = 0
current_shape = "sphere"  # 新增: 当前形状

# 预计算数据缓存
_sphere_data = None
_cube_data = None
_cylinder_data = None
_skybox_cache = {}

material = {
    "shadow_r": 0.35, "shadow_g": 0.35, "shadow_b": 0.4,
    "specular": 0.6, "rim": 0.5, "outline": 2.0, "levels": 3,
}

# 形状列表
SHAPE_NAMES = ["sphere", "cube", "cylinder"]
SHAPE_LABELS = {"sphere": "Sphere", "cube": "Cube", "cylinder": "Cylinder"}


# =============================================================================
# Skybox 预设 - 工业级渲染背景
# =============================================================================

SKYBOX_PRESETS = [
    {"name": "Studio Gray", "desc": "Neutral gray - Standard studio"},
    {"name": "Warm Sunset", "desc": "Warm sunset - Cinematic"},
    {"name": "Cool Dawn", "desc": "Cool dawn - Morning vibe"},
    {"name": "HDR White", "desc": "White HDR - Product display"},
    {"name": "Dark Studio", "desc": "Dark studio - Highlight material"},
    {"name": "Gradient Blue", "desc": "Blue gradient - Tech feel"},
    {"name": "Gradient Orange", "desc": "Orange gradient - Warm vibe"},
    {"name": "Checkerboard", "desc": "Checkerboard - Alpha test"},
]


def generate_skybox(preset_idx, size=400):
    """生成 Skybox 背景图像 - 更明显的差异"""
    if preset_idx in _skybox_cache and _skybox_cache[preset_idx].shape[0] == size:
        return _skybox_cache[preset_idx]

    img = np.zeros((size, size, 3), dtype=np.float32)

    if preset_idx == 0:  # Studio Gray
        # 中性灰，微弱顶部渐变
        for y in range(size):
            t = y / size
            img[y, :] = [0.18 - 0.03*t, 0.18 - 0.03*t, 0.20 - 0.02*t]

    elif preset_idx == 1:  # Warm Sunset
        # 橙色到深蓝渐变
        for y in range(size):
            t = y / size
            r = 0.6 * (1-t) + 0.1 * t
            g = 0.35 * (1-t) + 0.08 * t
            b = 0.15 * (1-t) + 0.4 * t
            img[y, :] = [b, g, r]

    elif preset_idx == 2:  # Cool Dawn
        # 深蓝到浅蓝
        for y in range(size):
            t = y / size
            img[y, :] = [0.15 + 0.35*t, 0.18 + 0.25*t, 0.35 + 0.15*t]

    elif preset_idx == 3:  # HDR White
        # 明亮白色，边缘暗化
        img[:] = [0.95, 0.95, 0.98]
        cx, cy = size/2, size/2
        for y in range(size):
            for x in range(size):
                dist = np.sqrt((x-cx)**2 + (y-cy)**2) / (size * 0.8)
                vignette = max(0.6, 1 - dist * 0.4)
                img[y, x] = img[y, x] * vignette

    elif preset_idx == 4:  # Dark Studio
        # 深色背景，底部微光
        img[:] = [0.04, 0.04, 0.05]
        for y in range(size):
            if y > size * 0.8:
                t = (y - size * 0.8) / (size * 0.2)
                img[y, :] = [0.08 + 0.1*t, 0.08 + 0.1*t, 0.10 + 0.08*t]

    elif preset_idx == 5:  # Gradient Blue
        # 蓝色科技感渐变
        for y in range(size):
            t = y / size
            img[y, :] = [0.2 + 0.5*t, 0.3 + 0.4*t, 0.6 + 0.3*t]

    elif preset_idx == 6:  # Gradient Orange
        # 温暖橙色渐变
        for y in range(size):
            t = y / size
            img[y, :] = [0.15 + 0.15*t, 0.25 + 0.35*t, 0.7 - 0.1*t]

    elif preset_idx == 7:  # Checkerboard
        # 棋盘格
        cell_size = size // 10
        for y in range(size):
            for x in range(size):
                cy, cx = y // cell_size, x // cell_size
                if (cy + cx) % 2 == 0:
                    img[y, x] = [0.7, 0.7, 0.75]
                else:
                    img[y, x] = [0.25, 0.25, 0.28]

    _skybox_cache[preset_idx] = img.copy()
    return img


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

    # 球体坐标映射到 skybox
    # 使用球面坐标映射
    theta = np.arctan2(ny, nx)  # 水平角度
    phi = np.arcsin(np.clip(nz, -1, 1))  # 垂直角度

    _sphere_data = {
        'nx': nx.astype(np.float32), 'ny': ny, 'nz': nz,
        'mask': dist <= radius, 'outline': (dist > radius-3) & (dist <= radius),
        'theta': theta, 'phi': phi, 'radius': radius,
        'dist': dist
    }
    return _sphere_data


def precompute_cube(size=400):
    """预计算立方体法线数据 - 透视投影"""
    global _cube_data
    if _cube_data is not None:
        return _cube_data

    cx, cy = size // 2, size // 2
    half_size = size // 3

    # 创建坐标网格
    y_coords, x_coords = np.ogrid[:size, :size]

    # 模拟透视投影的立方体 (显示前、顶、右三个面)
    nx = np.zeros((size, size), dtype=np.float32)
    ny = np.zeros((size, size), dtype=np.float32)
    nz = np.zeros((size, size), dtype=np.float32)
    mask = np.zeros((size, size), dtype=bool)

    # 前面 (z 方向) - 中心区域
    front_x0 = cx - half_size
    front_x1 = cx + half_size
    front_y0 = cy - half_size
    front_y1 = cy + half_size

    front_mask = (x_coords >= front_x0) & (x_coords < front_x1) & \
                 (y_coords >= front_y0) & (y_coords < front_y1)
    mask |= front_mask
    nz[front_mask] = 0.9
    nx[front_mask] = 0.1  # 微微向右倾斜
    ny[front_mask] = 0.1  # 微微向上倾斜

    # 顶面 (y 方向) - 上方区域
    top_x0 = cx - half_size - half_size//3
    top_x1 = cx + half_size + half_size//3
    top_y0 = front_y0 - half_size//2
    top_y1 = front_y0

    top_mask = (x_coords >= top_x0) & (x_coords < front_x0) & \
               (y_coords >= top_y0) & (y_coords < top_y1)
    mask |= top_mask
    ny[top_mask] = -0.9
    nz[top_mask] = 0.3

    # 右面 (x 方向) - 右侧区域
    right_x0 = front_x1
    right_x1 = front_x1 + half_size//2
    right_y0 = cy - half_size + half_size//3
    right_y1 = cy + half_size

    right_mask = (x_coords >= right_x0) & (x_coords < right_x1) & \
                 (y_coords >= right_y0) & (y_coords < right_y1)
    mask |= right_mask
    nx[right_mask] = 0.9
    nz[right_mask] = 0.3

    # 计算边缘描边
    dist = np.zeros((size, size), dtype=np.float32)
    for y in range(size):
        for x in range(size):
            if mask[y, x]:
                # 计算到边缘的距离
                edge_dists = []
                if y >= front_y0 and y < front_y1 and x >= front_x0 and x < front_x1:
                    edge_dists = [x - front_x0, front_x1 - x - 1, y - front_y0, front_y1 - y - 1]
                elif mask[y, x]:
                    # 其他面的边缘
                    edge_dists = [3]  # 默认描边宽度
                if edge_dists:
                    dist[y, x] = min(edge_dists)

    outline = (dist > 0) & (dist <= 3)

    _cube_data = {
        'nx': nx, 'ny': ny, 'nz': nz,
        'mask': mask, 'outline': outline, 'dist': dist
    }
    return _cube_data


def precompute_cylinder(size=400):
    """预计算圆柱体法线数据"""
    global _cylinder_data
    if _cylinder_data is not None:
        return _cylinder_data

    cx, cy = size // 2, size // 2
    radius = size // 3
    half_height = size // 3

    y_coords, x_coords = np.ogrid[:size, :size]
    dx = (x_coords - cx).astype(np.float32)
    dy = (y_coords - cy).astype(np.float32)
    dist_xy = np.sqrt(dx*dx + dy*dy)

    nx = np.zeros((size, size), dtype=np.float32)
    ny = np.zeros((size, size), dtype=np.float32)
    nz = np.zeros((size, size), dtype=np.float32)
    mask = np.zeros((size, size), dtype=bool)

    # 圆柱体区域
    in_radius = dist_xy <= radius
    y_in_range = (dy >= -half_height) & (dy <= half_height)
    mask = in_radius & y_in_range

    # 侧面法线 - 指向外
    side_area = mask & (dist_xy > radius * 0.1)
    nx[side_area] = dx[side_area] / radius
    ny[side_area] = 0
    nz[side_area] = np.sqrt(np.maximum(0, 1 - (nx[side_area])**2))

    # 归一化
    norm = np.sqrt(nx[side_area]**2 + ny[side_area]**2 + nz[side_area]**2)
    nx[side_area] = nx[side_area] / np.maximum(norm, 0.01)
    nz[side_area] = nz[side_area] / np.maximum(norm, 0.01)

    # 顶面法线 - 指向上
    top_area = mask & (dy > half_height - 5)
    ny[top_area] = -1.0
    nz[top_area] = 0

    # 底面法线 - 指向下
    bottom_area = mask & (dy < -half_height + 5)
    ny[bottom_area] = 1.0
    nz[bottom_area] = 0

    # 描边
    outline = (dist_xy > radius - 3) & (dist_xy <= radius) & y_in_range
    # 上下边缘描边
    top_outline = in_radius & (dy > half_height - 3) & (dy <= half_height)
    bottom_outline = in_radius & (dy >= -half_height) & (dy < -half_height + 3)
    outline |= top_outline | bottom_outline

    _cylinder_data = {
        'nx': nx, 'ny': ny, 'nz': nz,
        'mask': mask, 'outline': outline,
        'dist': dist_xy
    }
    return _cylinder_data


def get_shape_data(shape_name, size=400):
    """获取指定形状的预计算数据"""
    if shape_name == "sphere":
        return precompute_sphere(size)
    elif shape_name == "cube":
        return precompute_cube(size)
    elif shape_name == "cylinder":
        return precompute_cylinder(size)
    return precompute_sphere(size)


def render_shape_with_skybox():
    """渲染带 Skybox 背景的材质形状"""
    data = get_shape_data(current_shape, VIEWER_SIZE)
    skybox = generate_skybox(current_skybox, VIEWER_SIZE)

    # 结果图像 - 先用 skybox 填充
    result = skybox.copy()

    # 光源方向
    light = np.array([0.5, -0.5, 0.8])
    light = light / np.linalg.norm(light)

    nx = data['nx']
    ny = data['ny']
    nz = data['nz']
    mask = data['mask']
    dist = data['dist']

    # 漫反射
    NdotL = np.maximum(0, nx*light[0] + ny*light[1] + nz*light[2])

    # 色阶化
    levels = int(material["levels"])
    if levels == 2:
        shade = (NdotL > 0.5).astype(np.float32)
    elif levels == 3:
        shade = np.clip(np.floor(NdotL * 3) / 2, 0, 1)
    else:
        shade = np.clip(np.floor(NdotL * 4) / 3, 0, 1)

    shade = np.clip(shade + material["shadow_r"] * 0.3, 0, 1)

    # 颜色 - BGR
    shadow = [material["shadow_b"], material["shadow_g"], material["shadow_r"]]
    base = [0.92, 0.9, 0.9]

    sphere_color = np.zeros((VIEWER_SIZE, VIEWER_SIZE, 3), dtype=np.float32)
    for c in range(3):
        sphere_color[:,:,c] = shadow[c] + (base[c] - shadow[c]) * shade

    # 高光
    half = np.array([0.25, -0.25, 0.9])
    half = half / np.linalg.norm(half)
    NdotH = np.maximum(0, nx*half[0] + ny*half[1] + nz*half[2])
    spec = np.clip(np.power(NdotH, 32) * material["specular"], 0, 1)

    sphere_color[:,:,0] += spec * 0.9
    sphere_color[:,:,1] += spec * 0.8
    sphere_color[:,:,2] += spec * 0.7

    # 边缘光
    rim = np.power(1 - nz, 3) * material["rim"]
    sphere_color[:,:,0] += rim * 1.0
    sphere_color[:,:,1] += rim * 0.85
    sphere_color[:,:,2] += rim * 0.8

    # 环境反射 - 菲涅尔效应，边缘混合 skybox
    fresnel = np.power(1 - nz, 2)
    for c in range(3):
        sphere_color[:,:,c] = sphere_color[:,:,c] * (1 - fresnel * 0.2) + skybox[:,:,c] * fresnel * 0.2

    sphere_color = np.clip(sphere_color, 0, 1)

    # 合成
    result[mask] = sphere_color[mask]

    # 描边 - 根据 outline 参数动态计算宽度
    outline_width = int(material["outline"])
    if outline_width > 0 and 'outline' in data:
        outline_mask = data['outline']
        result[outline_mask] = [0.02, 0.02, 0.05]

    # 转为 BGR uint8
    return (result * 255).astype(np.uint8)


def update_shape():
    """更新形状渲染"""
    print(f"[Update] Rendering {current_shape} with skybox={current_skybox}")
    img = render_shape_with_skybox()
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    if dpg.does_item_exist("sphere_tex"):
        dpg.set_value("sphere_tex", rgba.ravel().tolist())
        print(f"[Update] Texture updated")
    else:
        print("[Update] ERROR: sphere_tex not found!")


def update_ref_image():
    if ref_image is None:
        return

    display = cv2.resize(ref_image.copy(), (VIEWER_SIZE, VIEWER_SIZE))

    if mask_image is not None:
        mask_resized = cv2.resize(mask_image, (VIEWER_SIZE, VIEWER_SIZE), interpolation=cv2.INTER_NEAREST)
        green = (mask_resized == 1)
        display[green] = (display[green] * 0.6 + np.array([100, 255, 0]) * 0.4).astype(np.uint8)
        red = (mask_resized == 2)
        display[red] = (display[red] * 0.6 + np.array([0, 50, 255]) * 0.4).astype(np.uint8)

    rgba = cv2.cvtColor(display, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    dpg.set_value("ref_tex", rgba.ravel().tolist())


def on_file_select(sender, app_data):
    global ref_image, mask_image
    path = app_data.get("file_path_name", "") if isinstance(app_data, dict) else ""
    if not path:
        return

    img = cv2.imread(path)
    if img is None:
        return

    ref_image = img
    mask_image = np.zeros(img.shape[:2], dtype=np.uint8)
    update_ref_image()
    dpg.set_value("ref_path", os.path.basename(path))
    print(f"[Load] {img.shape[1]}x{img.shape[0]}")


def on_mouse_drag(sender, app_data):
    if ref_image is None or brush_mode == 0:
        return

    mx, my = dpg.get_mouse_pos()
    x = int((mx - 20) / VIEWER_SIZE * ref_image.shape[1])
    y = int((my - 80) / VIEWER_SIZE * ref_image.shape[0])

    if 0 <= x < ref_image.shape[1] and 0 <= y < ref_image.shape[0]:
        size = int(brush_size * ref_image.shape[1] / VIEWER_SIZE)
        cv2.circle(mask_image, (x, y), size, brush_mode, -1)
        update_ref_image()


def on_brush(mode):
    global brush_mode
    brush_mode = mode
    modes = ["Off", "Focus", "Ignore"]
    print(f"[Brush] {modes[mode]}")


def on_clear():
    global mask_image
    if ref_image is not None:
        mask_image = np.zeros(ref_image.shape[:2], dtype=np.uint8)
        update_ref_image()


def on_skybox_change(sender, app_data):
    global current_skybox
    # app_data 是选中的名称，需要找到对应的索引
    for idx, preset in enumerate(SKYBOX_PRESETS):
        if preset["name"] == app_data:
            current_skybox = idx
            break
    update_shape()
    dpg.set_value("skybox_name", SKYBOX_PRESETS[current_skybox]["desc"])
    print(f"[Skybox] {SKYBOX_PRESETS[current_skybox]['name']}")


def on_shape_change(sender, app_data, user_data):
    """形状切换回调"""
    global current_shape
    new_shape = user_data
    if new_shape == current_shape:
        return

    current_shape = new_shape
    print(f"[Shape] Changed to {current_shape}")

    # 更新按钮颜色
    for i, shape in enumerate(SHAPE_NAMES):
        is_selected = shape == current_shape
        btn_color = (70, 130, 200) if is_selected else (50, 50, 55)
        hover_color = (100, 160, 230) if is_selected else (70, 70, 75)

        # 重新绑定主题
        theme_tag = f"shape_theme_{i}"
        if dpg.does_item_exist(theme_tag):
            dpg.delete_item(theme_tag)

        with dpg.theme(tag=theme_tag):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, btn_color, category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hover_color, category=dpg.mvThemeCat_Core)
        dpg.bind_item_theme(f"shape_btn_{i}", theme_tag)

    update_shape()


def on_infer():
    global engine
    if engine is None or ref_image is None:
        dpg.set_value("status", "No image/model")
        return

    try:
        from PIL import Image
        MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])

        img = ref_image.copy()
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
        material["outline"] = float(preds[5]) * 5  # 0~5 范围

        for k, tag in [("shadow_r","s_r"), ("shadow_g","s_g"), ("shadow_b","s_b"),
                       ("specular","s_sp"), ("rim","s_rm"), ("outline","s_ot")]:
            dpg.set_value(tag, material[k])

        update_shape()
        dpg.set_value("status", "Done!")
        print(f"[Infer] {preds[:6]}")
    except Exception as e:
        print(f"[Error] {e}")
        dpg.set_value("status", "Error")


def on_param(s, a, k):
    material[k] = a
    print(f"[Param] {k} = {a}")
    update_shape()


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


def make_param_callback(key):
    """创建参数回调函数"""
    def callback(s, a):
        material[key] = a
        print(f"[Param] {key} = {a:.3f}")
        update_shape()
    return callback


def build():
    dpg.create_context()
    dpg.create_viewport(title="AutoToon Studio - Skybox", width=920, height=620)

    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (25, 25, 28))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 45))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (55, 60, 70))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (70, 130, 200))
    dpg.bind_theme(t)

    with dpg.texture_registry():
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*VIEWER_SIZE**2, tag="ref_tex")
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*VIEWER_SIZE**2, tag="sphere_tex")

    with dpg.file_dialog(directory_selector=False, show=False, callback=on_file_select,
                        tag="fdlg", width=500, height=300):
        dpg.add_file_extension("Images{.png,.jpg,.jpeg,.bmp,.webp,.gif}", color=(80, 180, 220))

    with dpg.window(tag="main"):
        dpg.add_text("AutoToon Studio — Industrial Skybox Preview", color=(70, 140, 210))
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
                dpg.add_text("Material Preview", color=(140, 140, 150))

                # Skybox 选择
                with dpg.group(horizontal=True):
                    dpg.add_text("Skybox:")
                    dpg.add_combo(
                        items=[s["name"] for s in SKYBOX_PRESETS],
                        default_value=SKYBOX_PRESETS[0]["name"],
                        tag="skybox_combo",
                        width=150,
                        callback=on_skybox_change
                    )

                # 形状选择
                with dpg.group(horizontal=True):
                    dpg.add_text("Shape:")
                    for i, shape in enumerate(SHAPE_NAMES):
                        label = SHAPE_LABELS.get(shape, shape)
                        is_selected = shape == current_shape
                        btn_color = (70, 130, 200) if is_selected else (50, 50, 55)
                        dpg.add_button(
                            label=label,
                            tag=f"shape_btn_{i}",
                            width=60,
                            callback=on_shape_change,
                            user_data=shape
                        )
                        # 绑定主题
                        with dpg.theme(tag=f"shape_theme_{i}"):
                            with dpg.theme_component(dpg.mvButton):
                                dpg.add_theme_color(dpg.mvThemeCol_Button, btn_color, category=dpg.mvThemeCat_Core)
                                hover = (100, 160, 230) if is_selected else (70, 70, 75)
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hover, category=dpg.mvThemeCat_Core)
                        dpg.bind_item_theme(f"shape_btn_{i}", f"shape_theme_{i}")

                dpg.add_text(SKYBOX_PRESETS[0]["desc"], tag="skybox_name", color=(100, 100, 100))

                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                    dpg.draw_image("sphere_tex", (0, 0), (VIEWER_SIZE, VIEWER_SIZE))

                dpg.add_separator()
                dpg.add_text("Parameters", color=(110, 110, 120))

                # 使用 make_param_callback 创建正确的回调
                params_config = [
                    ("Shadow R", "s_r", "shadow_r", 0, 1, False),
                    ("Shadow G", "s_g", "shadow_g", 0, 1, False),
                    ("Shadow B", "s_b", "shadow_b", 0, 1, False),
                    ("Specular", "s_sp", "specular", 0, 1.5, False),
                    ("Rim Light", "s_rm", "rim", 0, 1.5, False),
                    ("Outline", "s_ot", "outline", 0, 5, False),
                    ("Shade Lv", "s_lv", "levels", 2, 4, True),
                ]

                for label, tag, key, mn, mx, is_int in params_config:
                    with dpg.group(horizontal=True):
                        dpg.add_text(f"{label}:")
                        if is_int:
                            dpg.add_slider_int(
                                tag=tag,
                                default_value=int(material[key]),
                                min_value=int(mn),
                                max_value=int(mx),
                                width=130,
                                callback=make_param_callback(key)
                            )
                        else:
                            dpg.add_slider_float(
                                tag=tag,
                                default_value=material[key],
                                min_value=mn,
                                max_value=mx,
                                width=130,
                                callback=make_param_callback(key)
                            )

        dpg.add_spacer(height=5)
        dpg.add_text("Tips: Focus=Green, Ignore=Red | Skybox simulates lighting environment", color=(70, 70, 70))

    with dpg.handler_registry():
        dpg.add_mouse_drag_handler(button=0, callback=on_mouse_drag)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)


def run():
    print("=" * 50)
    print("AutoToon Studio - Skybox & Multi-Shape")
    print("  8 Industrial Skybox Presets")
    print("  3 Shape Types: Sphere, Cube, Cylinder")
    print("=" * 50)
    load_model()
    build()
    update_shape()
    print("\n[Ready]\n")
    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()
    dpg.destroy_context()


if __name__ == "__main__":
    run()