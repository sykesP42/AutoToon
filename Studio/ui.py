"""
ui.py — AutoToon Studio 主界面
参考图提取风格 → 参数应用到 3D 模型 → 多槽位预览对比
"""
import os
import time
import numpy as np
import cv2

import dearpygui.dearpygui as dpg

from engine import InferenceEngine
from preview import apply_style_preview, load_image_bgr
from ue_client import UE5Client
from style_manager import StyleManager
from i18n import t, toggle_lang
from image_viewer import ImageViewer
from gl_renderer import GLRenderer, Camera, LightParams

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


# ─── 全局状态 ────────────────────────────────────────────────────────────────────
class AppState:
    def __init__(self):
        self.engine: InferenceEngine | None = None
        self.ue_client: UE5Client | None = None
        self.style_mgr = StyleManager()

        self.ref_image_bgr: np.ndarray | None = None
        self.ref_image_path: str = ""

        # 材质球（ModernGL GPU 渲染）
        self.gl: GLRenderer | None = None
        self.shape_name = "sphere"
        self.light = LightParams()

        # ONNX 风格参数（叠加在材质球上）
        self.shadow_r, self.shadow_g, self.shadow_b = 0.65, 0.65, 0.65
        self.specular, self.rim_light_width, self.width_scale = 0.5, 0.5, 1.0

        # 预设槽位
        self.preset_slots: list[dict] = []
        self.active_slot = -1

        self.ue_connected = False
        self.last_health_check = 0.0

        # 渲染缓存
        self._last_render_key: tuple = ()
        self._last_render_img: np.ndarray | None = None

        # 防抖
        self._preview_dirty = True
        self._last_change_time = 0.0


state = AppState()
ref_viewer: ImageViewer | None = None
preview_viewer: ImageViewer | None = None
popout_viewer: ImageViewer | None = None       # 弹出窗口的预览器
_popout_viewport_id = 0                         # 弹出窗口的 viewport ID

PARAM_DEFS = [
    ("label_shadow_r",    0,   1,    0.01),
    ("label_shadow_g",    0,   1,    0.01),
    ("label_shadow_b",    0,   1,    0.01),
    ("label_specular",    0,   1,    0.01),
    ("label_rim_light",   0,   1,    0.01),
    ("label_width_scale", 0.5, 3.0,  0.05),
]
DEFAULT_VALS = [0.3, 0.3, 0.3, 0.5, 0.5, 1.0]

NUM_SLOTS = 5


# ─── 初始化 ──────────────────────────────────────────────────────────────────────
def init_engine(onnx_path: str) -> str:
    try:
        state.engine = InferenceEngine(onnx_path)
        return t("log_model_ok", os.path.basename(onnx_path))
    except Exception as e:
        return t("log_model_fail", e)


def init_ue_client() -> str:
    try:
        state.ue_client = UE5Client()
        return t("log_ue_ready")
    except Exception as e:
        return t("log_ue_fail", e)


SHAPE_NAMES = ["sphere", "cube", "cylinder", "torus"]
SHAPE_LABELS = {"sphere": "球体", "cube": "立方体", "cylinder": "圆柱体", "torus": "圆环体"}
SHAPE_LABELS_EN = {"sphere": "Sphere", "cube": "Cube", "cylinder": "Cylinder", "torus": "Torus"}


def _create_base_thumbnails():
    """生成材质球缩略图（ModernGL 渲染 → DPG 纹理）"""
    THUMB = 48
    light_preview = LightParams()
    with dpg.texture_registry():
        for i, name in enumerate(SHAPE_NAMES):
            img = state.gl.render(name, Camera(), light_preview, width=THUMB, height=THUMB)
            rgba = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
                                cv2.COLOR_RGB2RGBA).astype(np.float32) / 255.0
            dpg.add_dynamic_texture(THUMB, THUMB, rgba.ravel().tolist(), tag=f"base_thumb_{i}")


def on_base_select(sender, app_data, user_data):
    """切换材质球形状"""
    state.shape_name = SHAPE_NAMES[user_data]
    state._last_render_key = ()  # 使缓存失效
    _update_preview()


def on_light_changed(sender, app_data, user_data):
    """灯光参数滑块回调"""
    attr = user_data
    setattr(state.light, attr, app_data)
    state._preview_dirty = True
    state._last_change_time = time.time()


# ─── 回调 ────────────────────────────────────────────────────────────────────────
def on_ref_selected(sender, app_data):
    """选择参考图"""
    file_path = app_data["file_path_name"]
    if not file_path:
        return
    try:
        state.ref_image_bgr = load_image_bgr(file_path)
        state.ref_image_path = file_path
        ref_viewer.set_image(state.ref_image_bgr)
        dpg.set_value("ref_path", os.path.basename(file_path))
        if state.engine:
            _run_inference()
        _log(t("log_img_loaded", os.path.basename(file_path)))
    except Exception as e:
        _log(t("log_img_fail", e), error=True)



def on_slider_changed(sender, app_data, user_data):
    attrs = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light_width", "width_scale"]
    setattr(state, attrs[user_data], app_data)
    dpg.set_value(f"val_{user_data}", f"{app_data:.3f}")
    # 标记需要更新，由定时器防抖后渲染（不立即调用 _update_preview）
    state._preview_dirty = True
    state._last_change_time = time.time()


def on_infer_clicked():
    if state.ref_image_bgr is None:
        _log(t("log_no_image"), error=True)
        return
    _run_inference()


def on_send_ue_clicked():
    if state.ue_client is None:
        _log(t("log_ue_not_init"), error=True)
        return
    params = _get_params()
    result = state.ue_client.send_params(params)
    if result["ok"]:
        _log(t("log_sent_ok", *[f"{p:.3f}" for p in params]))
    else:
        _log(t("log_sent_fail", result["error"]), error=True)


def on_health_check_clicked():
    if state.ue_client is None:
        state.ue_client = UE5Client()
    result = state.ue_client.health_check()
    state.ue_connected = result["ok"]
    state.last_health_check = time.time()
    if result["ok"]:
        _log(t("log_ue_ok"))
        dpg.set_value("ue_status", t("ue_status_ok"))
        dpg.configure_item("ue_status", color=(100, 255, 100))
    else:
        _log(t("log_ue_fail2", result["error"]), error=True)
        dpg.set_value("ue_status", t("ue_status_fail"))
        dpg.configure_item("ue_status", color=(255, 100, 100))


def on_save_preset_clicked():
    name = dpg.get_value("preset_name_input")
    if not name.strip():
        _log(t("log_no_preset_name"), error=True)
        return
    try:
        path = state.style_mgr.save(name, _get_params())
        _log(t("log_preset_saved", path))
        _refresh_preset_list()
    except Exception as e:
        _log(t("log_preset_save_fail", e), error=True)


def on_load_preset_clicked(sender, app_data, user_data):
    try:
        preset = state.style_mgr.load(user_data)
        _apply_params(preset["params"])
        _log(t("log_preset_loaded", preset["name"]))
    except Exception as e:
        _log(t("log_preset_load_fail", e), error=True)


def on_lang_toggle():
    toggle_lang()
    _refresh_ui_text()


# ─── 弹出预览窗口 ────────────────────────────────────────────────────────────────
_popout_last_size = (0, 0)  # 上一次检测到的弹出窗口尺寸


def on_popout_toggle():
    """弹出/收回预览窗口"""
    global popout_viewer, _popout_viewport_id, _popout_last_size

    if popout_viewer is not None:
        # 收回：关闭弹出 viewport，恢复主窗口预览
        if _popout_viewport_id and dpg.does_item_exist(_popout_viewport_id):
            dpg.delete_item(_popout_viewport_id)
        popout_viewer = None
        _popout_viewport_id = 0
        _popout_last_size = (0, 0)
        if dpg.does_item_exist("preview_placeholder"):
            dpg.configure_item("preview_placeholder", show=False)
        if dpg.does_item_exist("preview_viewer_group"):
            dpg.configure_item("preview_viewer_group", show=True)
        dpg.configure_item("btn_popout", label="Pop Out")
        state._preview_dirty = True
        state._last_change_time = 0
        _log("Preview docked")
    else:
        # 弹出：隐藏主窗口预览，创建独立窗口
        if dpg.does_item_exist("preview_viewer_group"):
            dpg.configure_item("preview_viewer_group", show=False)
        if dpg.does_item_exist("preview_placeholder"):
            dpg.configure_item("preview_placeholder", show=True)

        POP_W, POP_H = 600, 600
        _popout_viewport_id = dpg.add_window(
            label="AutoToon — Preview",
            width=POP_W + 20, height=POP_H + 40,
            on_close=lambda: on_popout_toggle(),
        )
        popout_viewer = ImageViewer(
            "popout_viewer", width=POP_W, height=POP_H,
            parent=_popout_viewport_id, camera_mode=True,
        )
        _popout_last_size = (POP_W, POP_H)
        # 共享相机状态
        if preview_viewer:
            popout_viewer.camera.yaw = preview_viewer.camera.yaw
            popout_viewer.camera.pitch = preview_viewer.camera.pitch
            popout_viewer.camera.zoom = preview_viewer.camera.zoom
        popout_viewer._on_camera_change = _update_preview
        dpg.add_text(
            "MidDrag=Orbit | Scroll=Zoom | LeftDrag=Pan | DblClick=Reset",
            color=(80, 80, 80), parent=_popout_viewport_id,
        )

        dpg.configure_item("btn_popout", label="Dock")
        state._preview_dirty = True
        state._last_change_time = 0
        _log("Preview popped out (600x600)")


# ─── 预设槽位 ────────────────────────────────────────────────────────────────────
def on_save_slot(sender, app_data, user_data):
    """保存当前参数到槽位"""
    idx = user_data
    while len(state.preset_slots) <= idx:
        state.preset_slots.append({})
    params = _get_params()
    preview = _render_preview(params)
    state.preset_slots[idx] = {
        "params": list(params),
        "preview": preview,
        "name": f"Slot {idx + 1}",
    }
    state.active_slot = idx
    _refresh_slots()


def on_apply_slot(sender, app_data, user_data):
    """点击槽位 → 应用该参数"""
    idx = user_data
    if idx >= len(state.preset_slots) or not state.preset_slots[idx]:
        return
    _apply_params(state.preset_slots[idx]["params"])
    state.active_slot = idx
    _refresh_slots()


def _refresh_slots():
    """刷新槽位缩略图"""
    for i in range(NUM_SLOTS):
        tag = f"slot_{i}_tex"
        if i < len(state.preset_slots) and state.preset_slots[i].get("preview") is not None:
            img = state.preset_slots[i]["preview"]
            rgba = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), cv2.COLOR_RGB2RGBA)
            flat = rgba.astype(np.float32).ravel() / 255.0
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, flat.tolist())
            dpg.configure_item(f"slot_{i}_btn", label=f"  {i+1}")
        else:
            dpg.configure_item(f"slot_{i}_btn", label=f"  {i+1}")

    # 高亮当前槽位
    for i in range(NUM_SLOTS):
        is_active = (i == state.active_slot)
        color = (100, 150, 255) if is_active else (60, 60, 60)
        dpg.configure_item(f"slot_{i}_btn", enabled=True)


# ─── 内部函数 ────────────────────────────────────────────────────────────────────
def _get_params() -> list:
    return [state.shadow_r, state.shadow_g, state.shadow_b,
            state.specular, state.rim_light_width, state.width_scale]


def _get_active_viewer() -> ImageViewer | None:
    """返回当前活跃的预览器（弹出窗口优先）"""
    if popout_viewer is not None:
        return popout_viewer
    return preview_viewer


def _render_preview(params: list = None) -> np.ndarray | None:
    """ModernGL GPU 渲染（带缓存）"""
    if params is None:
        params = _get_params()
    viewer = _get_active_viewer()
    cam = viewer.camera if viewer else Camera()
    cam_key = (cam.yaw, cam.pitch, cam.zoom, cam.pan_x, cam.pan_y)
    light = state.light
    light_key = (light.ambient, light.diffuse, light.specular_power,
                 light.specular_intensity, light.rim_intensity, light.rim_power,
                 light.ground_shadow)
    # 弹出窗口渲染尺寸 = 窗口实际大小，主窗口 = 0（使用 GLRenderer 默认）
    rw = viewer.width if popout_viewer and viewer else 0
    rh = viewer.height if popout_viewer and viewer else 0
    cache_key = (state.shape_name, light_key, cam_key,
                 tuple(round(p, 4) for p in params), rw, rh)

    if cache_key == state._last_render_key and state._last_render_img is not None:
        return state._last_render_img

    img = state.gl.render(
        state.shape_name, cam, state.light,
        color=(params[0], params[1], params[2]),
        spec_boost=params[3], rim_boost=params[4],
        width=rw, height=rh,
    )
    state._last_render_key = cache_key
    state._last_render_img = img
    return img


def _run_inference():
    if state.engine is None or state.ref_image_bgr is None:
        return
    _log(t("log_infering"))
    try:
        tmp = os.path.join(os.path.dirname(__file__), "_tmp.png")
        cv2.imwrite(tmp, state.ref_image_bgr)
        result = state.engine.infer(tmp)
        _apply_params(result["params"])
        _log(t("log_infer_ok",
               *[f"{p:.3f}" for p in result["params"][:5]],
               f"{result['width_scale_ue']:.3f}"))
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception as e:
        _log(t("log_infer_fail", e), error=True)


def _apply_params(params: list):
    state.shadow_r, state.shadow_g, state.shadow_b = params[0], params[1], params[2]
    state.specular, state.rim_light_width, state.width_scale = params[3], params[4], params[5]
    for i, val in enumerate(params):
        dpg.set_value(f"slider_{i}", val)
        dpg.set_value(f"val_{i}", f"{val:.3f}")
    _update_preview()


def _update_preview():
    """渲染预览并同步到所有活跃的查看器"""
    preview = _render_preview()
    if preview is None:
        return
    if preview_viewer is not None and dpg.does_item_exist("preview_viewer_group") \
       and dpg.is_item_visible("preview_viewer_group"):
        preview_viewer.set_image(preview)
    if popout_viewer is not None and dpg.does_item_exist(f"{popout_viewer.name}_group"):
        popout_viewer.set_image(preview)


def _debounce_tick(sender, app_data):
    """定时器回调：只有在参数停止变化 80ms 后才触发渲染"""
    if not state._preview_dirty:
        return
    if (time.time() - state._last_change_time) < 0.08:
        return
    state._preview_dirty = False
    _update_preview()


_log_items: list[int] = []

def _log(msg: str, error: bool = False):
    timestamp = time.strftime("%H:%M:%S")
    prefix = "[ERR]" if error else "[LOG]"
    color = (255, 100, 100) if error else (200, 200, 200)
    tag = dpg.add_text(f"[{timestamp}] {prefix} {msg}", parent="log_content", color=color, wrap=340)
    _log_items.append(tag)
    # 限制日志条目数，避免内存膨胀
    if len(_log_items) > 500:
        old = _log_items.pop(0)
        if dpg.does_item_exist(old):
            dpg.delete_item(old)
    if dpg.does_item_exist("log_window"):
        dpg.set_y_scroll("log_window", -1.0)


def _update_log_wrap():
    """根据日志区宽度更新所有文本换行"""
    if not dpg.does_item_exist("log_window"):
        return
    w = dpg.get_item_width("log_window")
    if w and w > 40:
        wrap = w - 20
        for tag in _log_items:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, wrap=wrap)


def _refresh_preset_list():
    if dpg.does_item_exist("preset_list_group"):
        dpg.delete_item("preset_list_group", children_only=True)
    for preset in state.style_mgr.list_presets():
        dpg.add_button(label=preset["name"], callback=on_load_preset_clicked,
                       user_data=preset["file_path"], width=-1, parent="preset_list_group")


def _refresh_ui_text():
    dpg.set_viewport_title(t("window_title"))
    dpg.set_value("header_ref", t("ref_image"))
    dpg.configure_item("btn_upload_ref", label=t("btn_upload"))
    dpg.set_value("header_param", t("param_adjust"))
    for i, (key, _, _, _) in enumerate(PARAM_DEFS):
        dpg.set_value(f"slider_label_{i}", f"{t(key)}:")
    dpg.set_value("header_preview", t("live_preview"))
    dpg.set_value("header_actions", t("actions"))
    dpg.configure_item("btn_infer", label=t("btn_infer"))
    dpg.configure_item("btn_check_ue", label=t("btn_check_ue"))
    dpg.configure_item("btn_send_ue", label=t("btn_send_ue"))
    dpg.set_value("header_presets", t("style_presets"))
    dpg.configure_item("preset_name_input", hint=t("hint_preset_name"))
    dpg.configure_item("btn_save_preset", label=t("btn_save"))
    dpg.set_value("header_log", t("log_title"))
    dpg.configure_item("btn_lang", label=t("btn_lang"))


# ─── 构建 UI ─────────────────────────────────────────────────────────────────────
VIEWER_W, VIEWER_H = 380, 380
SLOT_TEX_SIZE = 64


def build_ui():
    global ref_viewer, preview_viewer

    dpg.create_context()
    dpg.create_viewport(title=t("window_title"), width=1320, height=820)

    # 字体
    for fp in [os.path.join(os.path.dirname(__file__), "fonts", "NotoSansSC-Regular.ttf"),
               r"C:\Windows\Fonts\NotoSansSC-VF.ttf", r"C:\Windows\Fonts\msyh.ttc"]:
        if os.path.exists(fp):
            try:
                with dpg.font_registry():
                    with dpg.font(fp, 18) as f:
                        pass
                    dpg.bind_font(f)
                break
            except Exception:
                continue

    # 暗黑主题
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            for key, val in [
                (dpg.mvThemeCol_WindowBg, (30,30,30)), (dpg.mvThemeCol_TitleBg, (20,20,20)),
                (dpg.mvThemeCol_TitleBgActive, (40,40,40)), (dpg.mvThemeCol_FrameBg, (45,45,45)),
                (dpg.mvThemeCol_Button, (60,60,60)), (dpg.mvThemeCol_ButtonHovered, (80,80,80)),
                (dpg.mvThemeCol_SliderGrab, (100,150,255)), (dpg.mvThemeCol_Header, (50,50,50)),
                (dpg.mvThemeCol_ChildBg, (35,35,35)),
            ]:
                dpg.add_theme_color(key, val, category=dpg.mvThemeCat_Core)
    dpg.bind_theme(global_theme)

    # 槽位缩略图纹理
    with dpg.texture_registry():
        for i in range(NUM_SLOTS):
            dpg.add_dynamic_texture(SLOT_TEX_SIZE, SLOT_TEX_SIZE,
                                    [0.2]*4*(SLOT_TEX_SIZE*SLOT_TEX_SIZE),
                                    tag=f"slot_{i}_tex")

    # 材质球缩略图
    _create_base_thumbnails()

    # 文件对话框
    with dpg.file_dialog(directory_selector=False, show=False,
                         callback=on_ref_selected, tag="ref_dialog", width=600, height=400):
        dpg.add_file_extension(t("file_filter"), color=(100, 200, 255))

    # ─── 主窗口 ──────────────────────────────────────────────────────────────────
    with dpg.window(tag="primary_window"):
        with dpg.group(horizontal=True):

            # ====== 左栏：参考图 ======
            with dpg.child_window(width=410, height=-1):
                dpg.add_text(t("ref_image"), color=(180, 200, 255), tag="header_ref")
                dpg.add_separator()
                with dpg.group(horizontal=True):
                    dpg.add_button(label=t("btn_upload"), tag="btn_upload_ref",
                                   callback=lambda: dpg.show_item("ref_dialog"), width=120)
                    dpg.add_button(label="Reset", callback=lambda: ref_viewer.reset_view() if ref_viewer else None, width=50)
                    dpg.add_text("", tag="ref_path", color=(120,120,120))
                ref_viewer = ImageViewer("ref_viewer", width=VIEWER_W, height=VIEWER_H)
                dpg.add_text("Scroll=Zoom | Drag=Pan | DblClick=Fit", color=(80,80,80))

            # ====== 中栏：参数 + 预览 + 槽位 ======
            with dpg.child_window(width=460, height=-1):
                # 参数调节
                dpg.add_text(t("param_adjust"), color=(180,200,255), tag="header_param")
                dpg.add_separator()
                for i, (key, mn, mx, _) in enumerate(PARAM_DEFS):
                    with dpg.group(horizontal=True):
                        dpg.add_text(f"{t(key)}:", tag=f"slider_label_{i}")
                        dpg.add_slider_float(tag=f"slider_{i}", default_value=DEFAULT_VALS[i],
                                             min_value=mn, max_value=mx, width=180,
                                             callback=on_slider_changed, user_data=i)
                        dpg.add_text(f"{DEFAULT_VALS[i]:.3f}", tag=f"val_{i}")

                dpg.add_separator()
                # 预览区标题 + 重置 + 弹出
                with dpg.group(horizontal=True):
                    dpg.add_text(t("live_preview"), color=(180,200,255), tag="header_preview")
                    dpg.add_button(label="Reset", callback=lambda: preview_viewer.reset_view() if preview_viewer else None, width=50)
                    dpg.add_button(label="Pop Out", tag="btn_popout", callback=on_popout_toggle, width=70)

                # 材质球形状选择
                with dpg.group(horizontal=True):
                    for i, name in enumerate(SHAPE_NAMES):
                        with dpg.group():
                            dpg.add_image(f"base_thumb_{i}", width=48, height=48)
                            dpg.add_button(label=name[:4], tag=f"base_btn_{i}",
                                           callback=on_base_select, user_data=i,
                                           width=48, height=20)

                # 灯光参数调节
                with dpg.tree_node(label="Lighting", default_open=False):
                    light_defs = [
                        ("ambient",          0,    1,   0.01, state.light.ambient),
                        ("diffuse",          0,    1,   0.01, state.light.diffuse),
                        ("specular_power",   1,    80,  1,    state.light.specular_power),
                        ("specular_intensity", 0,  1,   0.01, state.light.specular_intensity),
                        ("rim_intensity",    0,    1,   0.01, state.light.rim_intensity),
                        ("rim_power",        1,    8,   0.1,  state.light.rim_power),
                        ("ground_shadow",    0,    1,   0.01, state.light.ground_shadow),
                    ]
                    for attr, mn, mx, step, val in light_defs:
                        with dpg.group(horizontal=True):
                            dpg.add_text(f"{attr}:")
                            dpg.add_slider_float(default_value=val, min_value=mn, max_value=mx,
                                                 width=160, callback=on_light_changed, user_data=attr)

                preview_viewer = ImageViewer("preview_viewer", width=VIEWER_W, height=VIEWER_H,
                                             camera_mode=True)
                preview_viewer._on_camera_change = _update_preview
                dpg.add_text("MidDrag=Orbit | Scroll=Zoom | LeftDrag=Pan | DblClick=Reset",
                             color=(80,80,80))

                # 弹出时的占位提示
                dpg.add_text("[ Preview popped out ]", tag="preview_placeholder",
                             color=(100, 150, 255), show=False)

                # ─── 预设槽位 ────────────────────────────────────────────────
                dpg.add_separator()
                dpg.add_text("Presets", color=(180,200,255))
                with dpg.group(horizontal=True):
                    for i in range(NUM_SLOTS):
                        with dpg.group():
                            dpg.add_image(f"slot_{i}_tex", width=SLOT_TEX_SIZE, height=SLOT_TEX_SIZE)
                            with dpg.group(horizontal=True):
                                dpg.add_button(label=f"  {i+1}", tag=f"slot_{i}_btn",
                                               callback=on_apply_slot, user_data=i,
                                               width=30, height=22)
                                dpg.add_button(label="+", callback=on_save_slot, user_data=i,
                                               width=22, height=22)

                # 免责声明
                dpg.add_spacer(height=4)
                dpg.add_text("Preview is approximate only.\nActual result depends on UE5 engine rendering.",
                             color=(100, 100, 100), wrap=420)

            # ====== 右栏：操作 + 预设 + 日志 ======
            with dpg.child_window(width=-1, height=-1):
                dpg.add_button(label=t("btn_lang"), tag="btn_lang",
                               callback=on_lang_toggle, width=50)
                dpg.add_spacer(height=5)

                dpg.add_text(t("actions"), color=(180,200,255), tag="header_actions")
                dpg.add_separator()
                dpg.add_button(label=t("btn_infer"), tag="btn_infer",
                               callback=on_infer_clicked, width=-1, height=35)
                dpg.add_spacer(height=5)
                with dpg.group(horizontal=True):
                    dpg.add_button(label=t("btn_check_ue"), tag="btn_check_ue",
                                   callback=on_health_check_clicked, width=140)
                    dpg.add_text(t("ue_status_init"), tag="ue_status", color=(150,150,150))
                dpg.add_button(label=t("btn_send_ue"), tag="btn_send_ue",
                               callback=on_send_ue_clicked, width=-1, height=35)

                dpg.add_spacer(height=10)
                dpg.add_separator()
                dpg.add_text(t("style_presets"), color=(180,200,255), tag="header_presets")
                with dpg.group(horizontal=True):
                    dpg.add_input_text(tag="preset_name_input", hint=t("hint_preset_name"), width=160)
                    dpg.add_button(label=t("btn_save"), tag="btn_save_preset",
                                   callback=on_save_preset_clicked, width=60)
                dpg.add_group(tag="preset_list_group")

                dpg.add_spacer(height=10)
                dpg.add_separator()
                dpg.add_text(t("log_title"), color=(180,200,255), tag="header_log")
                with dpg.child_window(tag="log_window", height=-1, border=True):
                    dpg.add_group(tag="log_content")

    _refresh_preset_list()


def run(onnx_path: str = None):
    global popout_viewer, _popout_viewport_id, _popout_last_size

    # 初始化 ModernGL 渲染器（必须在 build_ui 之前，因为缩略图需要）
    print("[GL] Initializing ModernGL renderer...")
    try:
        state.gl = GLRenderer(width=VIEWER_W, height=VIEWER_H)
    except Exception as e:
        print(f"FATAL: GLRenderer init failed: {e}")
        return

    build_ui()

    if onnx_path and os.path.exists(onnx_path):
        _log(init_engine(onnx_path))
    else:
        _log(t("log_model_none"))
    _log(init_ue_client())

    # 用默认基准图初始化预览
    _update_preview()

    _log(t("log_ready"))

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_viewport_resize_callback(lambda: _update_log_wrap())
    dpg.set_primary_window("primary_window", True)

    # 手动渲染循环
    while dpg.is_dearpygui_running():
        # 检测弹出窗口被 OS 关闭
        if popout_viewer and _popout_viewport_id \
           and not dpg.does_item_exist(_popout_viewport_id):
            popout_viewer = None
            _popout_viewport_id = 0
            _popout_last_size = (0, 0)
            if dpg.does_item_exist("preview_placeholder"):
                dpg.configure_item("preview_placeholder", show=False)
            if dpg.does_item_exist("preview_viewer_group"):
                dpg.configure_item("preview_viewer_group", show=True)
            dpg.configure_item("btn_popout", label="Pop Out")
            state._preview_dirty = True
            state._last_change_time = 0

        # 检测弹出窗口 resize（最大化/拖拽边框）
        if popout_viewer and _popout_viewport_id and dpg.does_item_exist(_popout_viewport_id):
            win_w = dpg.get_item_width(_popout_viewport_id)
            win_h = dpg.get_item_height(_popout_viewport_id)
            if win_w and win_h:
                # 内容区域 = 窗口 - padding
                content_w = max(100, win_w - 20)
                content_h = max(100, win_h - 40)
                if (content_w, content_h) != _popout_last_size:
                    _popout_last_size = (content_w, content_h)
                    # 保存相机状态
                    cam_yaw = popout_viewer.camera.yaw
                    cam_pitch = popout_viewer.camera.pitch
                    cam_zoom = popout_viewer.camera.zoom
                    # 重建 drawlist
                    popout_viewer.resize(content_w, content_h)
                    # 恢复相机
                    popout_viewer.camera.yaw = cam_yaw
                    popout_viewer.camera.pitch = cam_pitch
                    popout_viewer.camera.zoom = cam_zoom
                    state._last_render_key = ()  # 使缓存失效（渲染尺寸变了）
                    state._preview_dirty = True
                    state._last_change_time = 0

        _debounce_tick(None, None)
        dpg.render_dearpygui_frame()

    state.gl.cleanup()
    dpg.destroy_context()
