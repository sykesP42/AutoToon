"""
ui.py — AutoToon Studio 主界面

参考图提取风格 → 参数应用到 3D 模型 → 多槽位预览对比

核心改进:
  - 参数映射配置化 (param_config.py)
  - 历史快照管理 (history_manager.py)
  - 增强的参数可视化
"""
from __future__ import annotations

import os
import time
import numpy as np
import cv2
from typing import Optional

import dearpygui.dearpygui as dpg

from engine import InferenceEngine
from preview import apply_style_preview, load_image_bgr
from ue_client import UE5Client
from style_manager import StyleManager
from i18n import t, toggle_lang, get_lang
from image_viewer import ImageViewer
from gl_renderer import GLRenderer, Camera, LightParams, RenderParams
from param_config import (
    PARAM_DEFINITIONS, map_param, get_tooltip, get_label,
    get_defaults, map_all_params
)
from history_manager import HistoryManager, get_history
from compare_view import CompareView, CompareMode

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


# =============================================================================
# 全局状态
# =============================================================================

class AppState:
    """应用全局状态"""

    def __init__(self):
        self.engine: Optional[InferenceEngine] = None
        self.ue_client: Optional[UE5Client] = None
        self.style_mgr = StyleManager()
        self.history = HistoryManager(max_snapshots=20)

        self.ref_image_bgr: Optional[np.ndarray] = None
        self.ref_image_path: str = ""

        # 渲染器
        self.gl: Optional[GLRenderer] = None
        self.shape_name = "sphere"
        self.light = LightParams()

        # UI 参数值 (原始 UI 值，未经映射)
        defaults = get_defaults()
        self.shadow_r = defaults.get("shadow_r", 0.3)
        self.shadow_g = defaults.get("shadow_g", 0.3)
        self.shadow_b = defaults.get("shadow_b", 0.3)
        self.specular = defaults.get("specular", 0.5)
        self.rim_light = defaults.get("rim_light", 0.5)
        self.outline_width = defaults.get("outline_width", 1.0)

        # 兼容旧变量名
        self.rim_light_width = self.rim_light
        self.width_scale = self.outline_width

        # 预设槽位
        self.preset_slots: list[dict] = []
        self.active_slot = -1

        # UE5 连接状态
        self.ue_connected = False
        self.last_health_check = 0.0

        # 渲染缓存
        self._last_render_key: tuple = ()
        self._last_render_img: Optional[np.ndarray] = None

        # 防抖
        self._preview_dirty = True
        self._last_change_time = 0.0

        # 对比模式
        self.compare_mode = False
        self.compare_snapshot_idx = -1

    def get_params_dict(self) -> dict:
        """获取参数字典"""
        return {
            "shadow_r": self.shadow_r,
            "shadow_g": self.shadow_g,
            "shadow_b": self.shadow_b,
            "specular": self.specular,
            "rim_light": self.rim_light,
            "outline_width": self.outline_width,
        }

    def set_params_from_dict(self, params: dict) -> None:
        """从字典设置参数"""
        if "shadow_r" in params:
            self.shadow_r = params["shadow_r"]
        if "shadow_g" in params:
            self.shadow_g = params["shadow_g"]
        if "shadow_b" in params:
            self.shadow_b = params["shadow_b"]
        if "specular" in params:
            self.specular = params["specular"]
        if "rim_light" in params:
            self.rim_light = params["rim_light"]
            self.rim_light_width = params["rim_light"]
        if "outline_width" in params:
            self.outline_width = params["outline_width"]
            self.width_scale = params["outline_width"]


state = AppState()
ref_viewer: Optional[ImageViewer] = None
preview_viewer: Optional[ImageViewer] = None
popout_viewer: Optional[ImageViewer] = None
compare_view: Optional[CompareView] = None
_popout_viewport_id = 0

# 参数定义 (兼容旧代码)
PARAM_DEFS = [
    ("label_shadow_r",    0,   1,    0.01),
    ("label_shadow_g",    0,   1,    0.01),
    ("label_shadow_b",    0,   1,    0.01),
    ("label_specular",    0,   1,    0.01),
    ("label_rim_light",   0,   1,    0.01),
    ("label_outline_width", 0.5, 3.0,  0.05),
]
DEFAULT_VALS = [0.3, 0.3, 0.3, 0.5, 0.5, 1.0]

NUM_SLOTS = 5

# 对比模式状态
_compare_mode = "off"  # off, history, reference
_compare_viewer: Optional[ImageViewer] = None
_compare_snapshot_idx = -1


# =============================================================================
# 对比模式控制
# =============================================================================

def _set_compare_mode(mode: str) -> None:
    """
    设置对比模式

    Args:
        mode: "off" | "history" | "reference"
    """
    global _compare_mode, _compare_snapshot_idx

    _compare_mode = mode
    _compare_snapshot_idx = -1

    # 更新按钮状态
    btn_off_color = (100, 150, 255) if mode == "off" else (200, 200, 200)
    btn_hist_color = (100, 150, 255) if mode == "history" else (200, 200, 200)
    btn_ref_color = (100, 150, 255) if mode == "reference" else (200, 200, 200)

    if dpg.does_item_exist("btn_compare_off"):
        dpg.configure_item("btn_compare_off", color=btn_off_color)
    if dpg.does_item_exist("btn_compare_history"):
        dpg.configure_item("btn_compare_history", color=btn_hist_color)
    if dpg.does_item_exist("btn_compare_ref"):
        dpg.configure_item("btn_compare_ref", color=btn_ref_color)

    # 更新 CompareView 组件模式
    if compare_view is not None:
        if mode == "off":
            compare_view.set_mode(CompareMode.OFF)
        else:
            compare_view.set_mode(CompareMode.SPLIT_H)

    # 更新快照选择器
    _update_compare_snapshot_combo()

    # 触发预览更新
    state._last_render_key = ()
    state._preview_dirty = True
    state._last_change_time = 0

    mode_names = {"off": "Off", "history": "vs History", "reference": "vs Reference"}
    _log(f"Compare mode: {mode_names.get(mode, mode)}")


def _update_compare_snapshot_combo():
    """更新对比快照下拉框"""
    if not dpg.does_item_exist("compare_snapshot_combo"):
        return

    if _compare_mode == "history":
        snapshots = state.history.get_recent(10)
        labels = [f"#{i+1} ({s.get_age_formatted()})" for i, s in enumerate(reversed(snapshots))]
        if labels:
            dpg.configure_item("compare_snapshot_combo", items=labels)
        else:
            dpg.configure_item("compare_snapshot_combo", items=["No history"])
    else:
        dpg.configure_item("compare_snapshot_combo", items=["Latest"])


def _on_compare_snapshot_changed(sender, app_data):
    """对比快照选择变化"""
    global _compare_snapshot_idx

    if _compare_mode == "history":
        # 解析选择 (格式: "#N (age)")
        try:
            idx_str = app_data.split()[0]
            idx = int(idx_str.replace("#", "")) - 1
            snapshots = state.history.get_recent(10)
            # 转换索引（列表是倒序的）
            _compare_snapshot_idx = len(snapshots) - 1 - idx
        except (ValueError, IndexError):
            _compare_snapshot_idx = -1

        state._last_render_key = ()
        state._preview_dirty = True
        state._last_change_time = 0


def _get_compare_image() -> Optional[np.ndarray]:
    """
    获取对比图像

    Returns:
        用于对比的图像，或 None
    """
    if _compare_mode == "off":
        return None

    if _compare_mode == "reference" and state.ref_image_bgr is not None:
        # 返回参考图（缩放到预览尺寸）
        h, w = state.ref_image_bgr.shape[:2]
        max_size = 512
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            ref_resized = cv2.resize(state.ref_image_bgr, (int(w * scale), int(h * scale)))
        else:
            ref_resized = state.ref_image_bgr
        return ref_resized

    if _compare_mode == "history":
        # 返回选定的历史快照图像
        snapshots = state.history.get_all()
        if snapshots:
            idx = _compare_snapshot_idx if 0 <= _compare_snapshot_idx < len(snapshots) else len(snapshots) - 2
            if 0 <= idx < len(snapshots):
                snap = snapshots[idx]
                if snap.preview_image is not None:
                    return snap.preview_image

    return None


# =============================================================================
# 初始化
# =============================================================================

def init_engine(onnx_path: str) -> str:
    """初始化推理引擎"""
    try:
        state.engine = InferenceEngine(onnx_path)
        return t("log_model_ok", os.path.basename(onnx_path))
    except Exception as e:
        return t("log_model_fail", e)


def init_ue_client() -> str:
    """初始化 UE5 客户端"""
    try:
        state.ue_client = UE5Client()
        return t("log_ue_ready")
    except Exception as e:
        return t("log_ue_fail", e)


SHAPE_NAMES = ["sphere", "cube", "cylinder", "torus"]
SHAPE_LABELS = {"sphere": "球体", "cube": "立方体", "cylinder": "圆柱体", "torus": "圆环体"}
SHAPE_LABELS_EN = {"sphere": "Sphere", "cube": "Cube", "cylinder": "Cylinder", "torus": "Torus"}

# 灯光预设
LIGHT_PRESETS = {
    "default": {
        "name_zh": "默认", "name_en": "Default",
        "params": LightParams(ambient=0.25, diffuse=0.80, specular_power=40.0, specular_intensity=0.35, rim_intensity=0.15, rim_power=3.0)
    },
    "daylight": {
        "name_zh": "日光", "name_en": "Daylight",
        "params": LightParams(ambient=0.35, diffuse=0.90, specular_power=32.0, specular_intensity=0.45, rim_intensity=0.10, rim_power=4.0)
    },
    "studio": {
        "name_zh": "室内", "name_en": "Studio",
        "params": LightParams(ambient=0.20, diffuse=0.70, specular_power=64.0, specular_intensity=0.25, rim_intensity=0.20, rim_power=2.5)
    },
    "night": {
        "name_zh": "夜景", "name_en": "Night",
        "params": LightParams(ambient=0.10, diffuse=0.50, specular_power=80.0, specular_intensity=0.50, rim_intensity=0.30, rim_power=2.0)
    },
    "anime": {
        "name_zh": "动漫风", "name_en": "Anime",
        "params": LightParams(ambient=0.30, diffuse=0.85, specular_power=48.0, specular_intensity=0.40, rim_intensity=0.25, rim_power=3.5)
    },
}


def on_light_preset_selected(sender, app_data):
    """灯光预设选择回调"""
    preset_keys = list(LIGHT_PRESETS.keys())
    # 找到匹配的预设
    for key in preset_keys:
        preset = LIGHT_PRESETS[key]
        name = preset["name_zh"] if get_lang() == "zh" else preset["name_en"]
        if name == app_data:
            _apply_light_preset(key)
            break


def _apply_light_preset(preset_name: str):
    """应用灯光预设"""
    if preset_name in LIGHT_PRESETS:
        preset = LIGHT_PRESETS[preset_name]
        params = preset["params"]
        # 复制预设参数到 state.light
        state.light.ambient = params.ambient
        state.light.diffuse = params.diffuse
        state.light.specular_power = params.specular_power
        state.light.specular_intensity = params.specular_intensity
        state.light.rim_intensity = params.rim_intensity
        state.light.rim_power = params.rim_power

        # 更新灯光滑块UI（如果有）
        light_attrs = ["ambient", "diffuse", "specular_power", "specular_intensity", "rim_intensity", "rim_power"]
        for attr in light_attrs:
            slider_tag = f"light_slider_{attr}"
            if dpg.does_item_exist(slider_tag):
                dpg.set_value(slider_tag, getattr(state.light, attr))

        state._last_render_key = ()
        state._preview_dirty = True
        state._last_change_time = 0

        preset_name_display = preset["name_zh"] if get_lang() == "zh" else preset["name_en"]
        _log(f"Light preset: {preset_name_display}")


def _create_base_thumbnails():
    """生成材质球缩略图（ModernGL 渲染 → DPG 纹理）"""
    try:
        THUMB = 48
        light_preview = LightParams()
        cam_preview = Camera()
        from gl_renderer import RenderParams

        with dpg.texture_registry():
            for i, name in enumerate(SHAPE_NAMES):
                cam_preview.set_shape(name)
                params = RenderParams(
                    shadow_color=(0.35, 0.35, 0.35),
                    base_color=(0.85, 0.85, 0.85),
                    outline_width=1.0,
                )
                img = state.gl.render(name, cam_preview, light_preview, params, width=THUMB, height=THUMB)
                rgba = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
                                    cv2.COLOR_RGB2RGBA).astype(np.float32) / 255.0
                dpg.add_dynamic_texture(THUMB, THUMB, rgba.ravel().tolist(), tag=f"base_thumb_{i}")
    except Exception as e:
        import traceback
        print(f"_create_base_thumbnails ERROR: {e}")
        traceback.print_exc()
        # 创建占位纹理
        THUMB = 48
        with dpg.texture_registry():
            for i in range(len(SHAPE_NAMES)):
                dpg.add_dynamic_texture(THUMB, THUMB, [0.3]*4*(THUMB*THUMB), tag=f"base_thumb_{i}")


def on_base_select(sender, app_data, user_data):
    """切换材质球形状"""
    shape_idx = user_data
    if 0 <= shape_idx < len(SHAPE_NAMES):
        state.shape_name = SHAPE_NAMES[shape_idx]
        # 更新相机预设
        if preview_viewer and preview_viewer.camera:
            preview_viewer.camera.set_shape(state.shape_name)
        if popout_viewer and popout_viewer.camera:
            popout_viewer.camera.set_shape(state.shape_name)
        # 清除缓存，强制重新渲染
        state._last_render_key = ()
        state._preview_dirty = True
        state._last_change_time = 0
        # 更新按钮高亮
        for i in range(len(SHAPE_NAMES)):
            color = (100, 150, 255) if i == shape_idx else (60, 60, 60)
            dpg.configure_item(f"shape_btn_{i}", color=color)
        _log(f"Shape changed to: {SHAPE_LABELS.get(state.shape_name, state.shape_name)}")


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
    """
    参数滑块回调

    使用增强的参数映射，并自动保存快照。
    """
    # 参数名映射
    param_names = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light", "outline_width"]
    old_names = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light_width", "width_scale"]

    name = param_names[user_data] if user_data < len(param_names) else old_names[user_data]
    setattr(state, name, app_data)
    # 兼容旧变量名
    if name == "rim_light":
        state.rim_light_width = app_data
    if name == "outline_width":
        state.width_scale = app_data

    # 更新显示值
    if dpg.does_item_exist(f"val_{user_data}"):
        dpg.set_value(f"val_{user_data}", f"{app_data:.3f}")

    # 标记需要更新
    state._preview_dirty = True
    state._last_change_time = time.time()
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


# ─── 历史管理 ────────────────────────────────────────────────────────────────
def on_undo_clicked():
    """撤销到上一个快照"""
    prev_snap = state.history.undo()
    if prev_snap:
        state.set_params_from_dict(prev_snap.params)
        # 更新滑块UI
        params_list = [prev_snap.params.get("shadow_r", 0.5),
                       prev_snap.params.get("shadow_g", 0.5),
                       prev_snap.params.get("shadow_b", 0.5),
                       prev_snap.params.get("specular", 0.5),
                       prev_snap.params.get("rim_light", 0.5),
                       prev_snap.params.get("outline_width", 1.0)]
        for i, val in enumerate(params_list):
            if dpg.does_item_exist(f"slider_{i}"):
                dpg.set_value(f"slider_{i}", val)
            if dpg.does_item_exist(f"val_{i}"):
                dpg.set_value(f"val_{i}", f"{val:.3f}")
        state._last_render_key = ()
        state._preview_dirty = True
        _log(f"Undo: restored snapshot ({prev_snap.label})")
        _refresh_history_list()
    else:
        _log("Cannot undo: no previous snapshot", error=True)


def on_redo_clicked():
    """重做到下一个快照"""
    next_snap = state.history.redo()
    if next_snap:
        state.set_params_from_dict(next_snap.params)
        params_list = [next_snap.params.get("shadow_r", 0.5),
                       next_snap.params.get("shadow_g", 0.5),
                       next_snap.params.get("shadow_b", 0.5),
                       next_snap.params.get("specular", 0.5),
                       next_snap.params.get("rim_light", 0.5),
                       next_snap.params.get("outline_width", 1.0)]
        for i, val in enumerate(params_list):
            if dpg.does_item_exist(f"slider_{i}"):
                dpg.set_value(f"slider_{i}", val)
            if dpg.does_item_exist(f"val_{i}"):
                dpg.set_value(f"val_{i}", f"{val:.3f}")
        state._last_render_key = ()
        state._preview_dirty = True
        _log(f"Redo: restored snapshot ({next_snap.label})")
        _refresh_history_list()
    else:
        _log("Cannot redo: no next snapshot", error=True)


def on_history_item_clicked(sender, app_data, user_data):
    """点击历史项恢复参数"""
    idx = user_data
    snapshots = state.history.get_all()
    if 0 <= idx < len(snapshots):
        snap = snapshots[idx]
        state.set_params_from_dict(snap.params)
        params_list = [snap.params.get("shadow_r", 0.5),
                       snap.params.get("shadow_g", 0.5),
                       snap.params.get("shadow_b", 0.5),
                       snap.params.get("specular", 0.5),
                       snap.params.get("rim_light", 0.5),
                       snap.params.get("outline_width", 1.0)]
        for i, val in enumerate(params_list):
            if dpg.does_item_exist(f"slider_{i}"):
                dpg.set_value(f"slider_{i}", val)
            if dpg.does_item_exist(f"val_{i}"):
                dpg.set_value(f"val_{i}", f"{val:.3f}")
        state._last_render_key = ()
        state._preview_dirty = True
        _log(f"Restored: {snap.label}")


def _refresh_history_list():
    """刷新历史列表面板"""
    if not dpg.does_item_exist("history_list_group"):
        return
    dpg.delete_item("history_list_group", children_only=True)
    snapshots = state.history.get_recent(10)
    for i, snap in enumerate(reversed(snapshots)):
        age = snap.get_age_formatted()
        label = f"[{age}] {snap.label}"
        dpg.add_button(label=label, callback=on_history_item_clicked,
                      user_data=len(snapshots) - 1 - i, width=-1,
                      parent="history_list_group")
    # 同时更新对比快照选择器
    _update_compare_snapshot_combo()


# ─── 涂鸦控制 ────────────────────────────────────────────────────────────────
def _set_brush_mode(mode: int):
    """设置涂鸦模式"""
    if ref_viewer:
        ref_viewer.set_brush_mode(mode)
    # 更新按钮状态
    btn_colors = {
        0: (100, 150, 255),  # Off = 蓝色高亮
        1: (200, 200, 200),  # Focus = 普通
        2: (200, 200, 200),  # Ignore = 普通
    }
    if dpg.does_item_exist("btn_brush_off"):
        dpg.configure_item("btn_brush_off", color=btn_colors[0] if mode == 0 else (60, 60, 60))
    if dpg.does_item_exist("btn_brush_focus"):
        dpg.configure_item("btn_brush_focus", color=(50, 200, 50) if mode == 1 else (60, 60, 60))
    if dpg.does_item_exist("btn_brush_ignore"):
        dpg.configure_item("btn_brush_ignore", color=(200, 50, 50) if mode == 2 else (60, 60, 60))
    mode_names = {0: "Off", 1: "Focus (Green)", 2: "Ignore (Red)"}
    _log(f"Brush mode: {mode_names.get(mode, mode)}")


def _clear_brush():
    """清除涂鸦遮罩"""
    if ref_viewer:
        ref_viewer.clear_mask()
        _log("Brush mask cleared")


# ─── 弹出预览窗口 ────────────────────────────────────────────────────────────────
_popout_last_size = (0, 0)  # 上一次检测到的弹出窗口尺寸
_popout_maximized = False   # 是否最大化状态
_popout_saved_size = (0, 0) # 最大化前保存的窗口尺寸（用于还原）
_popout_user_size = None    # 用户上次选择的窗口尺寸（记住偏好）


def _get_screen_size():
    """获取屏幕尺寸"""
    try:
        import tkinter as tk
        root = tk.Tk()
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        root.destroy()
        return screen_w, screen_h
    except Exception:
        return 1920, 1080


def on_popout_maximize():
    """最大化/还原弹出窗口"""
    global _popout_maximized, _popout_saved_size, _popout_last_size

    if not popout_viewer or not _popout_viewport_id:
        return
    if not dpg.does_item_exist(_popout_viewport_id):
        return

    screen_w, screen_h = _get_screen_size()

    if _popout_maximized:
        # 还原到保存的尺寸
        if _popout_saved_size[0] > 0:
            restore_w, restore_h = _popout_saved_size
        else:
            restore_w, restore_h = 900, 900
        dpg.set_item_width(_popout_viewport_id, restore_w + 20)
        dpg.set_item_height(_popout_viewport_id, restore_h + 40)
        dpg.configure_item("btn_popout_max", label="Max")
        _popout_maximized = False
        _log(f"Preview window restored to {restore_w}x{restore_h}")
    else:
        # 保存当前尺寸
        current_w = dpg.get_item_width(_popout_viewport_id)
        current_h = dpg.get_item_height(_popout_viewport_id)
        _popout_saved_size = (max(100, current_w - 20), max(100, current_h - 40))
        # 最大化到屏幕尺寸（留出任务栏空间）
        max_w = screen_w - 20
        max_h = screen_h - 80
        dpg.set_item_width(_popout_viewport_id, max_w)
        dpg.set_item_height(_popout_viewport_id, max_h)
        dpg.configure_item("btn_popout_max", label="Restore")
        _popout_maximized = True
        _log(f"Preview window maximized to {max_w}x{max_h}")

    # 重置视图以适应新尺寸
    state._last_render_key = ()
    state._preview_dirty = True
    state._last_change_time = 0


def on_popout_toggle():
    """弹出/收回预览窗口"""
    global popout_viewer, _popout_viewport_id, _popout_last_size
    global _popout_maximized, _popout_saved_size, _popout_user_size

    if popout_viewer is not None:
        # 收回：保存用户偏好尺寸，关闭弹出 viewport，恢复主窗口预览
        current_w = dpg.get_item_width(_popout_viewport_id) if _popout_viewport_id else 0
        current_h = dpg.get_item_height(_popout_viewport_id) if _popout_viewport_id else 0
        if current_w > 100 and current_h > 100:
            _popout_user_size = (current_w - 20, current_h - 40)

        if _popout_viewport_id and dpg.does_item_exist(_popout_viewport_id):
            dpg.delete_item(_popout_viewport_id)
        popout_viewer = None
        _popout_viewport_id = 0
        _popout_last_size = (0, 0)
        _popout_maximized = False
        _popout_saved_size = (0, 0)
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

        screen_w, screen_h = _get_screen_size()

        # 使用用户上次选择的尺寸，或默认屏幕 70%
        if _popout_user_size and _popout_user_size[0] > 100:
            POP_W, POP_H = _popout_user_size
        else:
            POP_W = max(800, int(screen_w * 0.7))
            POP_H = max(800, int(screen_h * 0.7))

        _popout_viewport_id = dpg.add_window(
            label="AutoToon — Preview",
            width=POP_W + 20, height=POP_H + 40,
            on_close=lambda: on_popout_toggle(),
        )

        # 控制按钮栏
        with dpg.group(horizontal=True, parent=_popout_viewport_id):
            dpg.add_button(label="Max", tag="btn_popout_max",
                          callback=on_popout_maximize, width=60)
            dpg.add_button(label="Reset View",
                          callback=lambda: _reset_popout_camera(), width=80)
            # 对比模式按钮
            dpg.add_text("  Compare:", color=(150, 150, 150))
            dpg.add_button(label="Off", tag="btn_popout_compare_off",
                          callback=lambda: _set_compare_mode("off"), width=35)
            dpg.add_button(label="Hist", tag="btn_popout_compare_hist",
                          callback=lambda: _set_compare_mode("history"), width=40)
            dpg.add_button(label="Ref", tag="btn_popout_compare_ref",
                          callback=lambda: _set_compare_mode("reference"), width=35)

        # 操作提示
        dpg.add_text("  MidDrag=Orbit | Scroll=Zoom | LeftDrag=Pan | DblClick=Reset",
                    color=(100, 100, 100), parent=_popout_viewport_id)

        popout_viewer = ImageViewer(
            "popout_viewer", width=POP_W, height=POP_H,
            parent=_popout_viewport_id, camera_mode=True,
        )
        _popout_last_size = (POP_W, POP_H)
        _popout_maximized = False

        # 应用当前形状的预设视角
        popout_viewer.camera.set_shape(state.shape_name)

        # 根据窗口大小调整缩放
        scale_factor = min(POP_W, POP_H) / 380.0
        popout_viewer.camera.zoom *= scale_factor
        popout_viewer.camera.pan_x = 0
        popout_viewer.camera.pan_y = 0

        popout_viewer._on_camera_change = _update_preview

        dpg.configure_item("btn_popout", label="Dock")
        state._preview_dirty = True
        state._last_change_time = 0
        state._last_render_key = ()  # 强制重新渲染
        _log(f"Preview popped out ({POP_W}x{POP_H})")


def _reset_popout_camera():
    """重置弹出窗口的相机视角"""
    if popout_viewer and popout_viewer.camera:
        popout_viewer.camera.reset(state.shape_name)
        state._last_render_key = ()
        state._preview_dirty = True
        state._last_change_time = 0


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


# =============================================================================
# 内部函数
# =============================================================================

def _get_params() -> list:
    """获取参数列表（兼容旧接口）"""
    return [state.shadow_r, state.shadow_g, state.shadow_b,
            state.specular, state.rim_light, state.outline_width]


def _get_active_viewer() -> Optional[ImageViewer]:
    """返回当前活跃的预览器（弹出窗口优先）"""
    if popout_viewer is not None:
        return popout_viewer
    return preview_viewer


def _render_preview(params: list = None) -> Optional[np.ndarray]:
    """
    ModernGL GPU 渲染（带缓存）

    使用增强的参数映射，让效果变化更明显。

    Args:
        params: [shadow_r, shadow_g, shadow_b, specular, rim_light, outline_width]

    Returns:
        BGR numpy 数组或 None
    """
    try:
        if params is None:
            params = _get_params()

        viewer = _get_active_viewer()
        cam = viewer.camera if viewer else Camera()
        cam_key = (round(cam.yaw, 2), round(cam.pitch, 2), round(cam.zoom, 3),
                   round(cam.pan_x, 1), round(cam.pan_y, 1))
        light = state.light
        light_key = (round(light.ambient, 2), round(light.diffuse, 2),
                     round(light.specular_power, 1), round(light.specular_intensity, 2),
                     round(light.rim_intensity, 2), round(light.rim_power, 1))

        # 弹出窗口渲染尺寸
        rw = viewer.width if popout_viewer and viewer else 0
        rh = viewer.height if popout_viewer and viewer else 0

        # 缓存键
        cache_key = (state.shape_name, light_key, cam_key,
                     tuple(round(p, 3) for p in params), rw, rh)

        if cache_key == state._last_render_key and state._last_render_img is not None:
            return state._last_render_img

        # 解析 UI 参数 (已与 MooaToon CSV 范围对齐)
        shadow_r, shadow_g, shadow_b = params[0], params[1], params[2]
        specular = params[3]
        rim_light = params[4]
        outline_width = params[5]

        # 参数映射 (param_config.py 已修正为直接映射)
        # 阴影色: UI [0,1] → 渲染 [0,1] (与 MooaToon Shadow Color 一致)
        render_shadow_r = map_param("shadow_r", shadow_r)
        render_shadow_g = map_param("shadow_g", shadow_g)
        render_shadow_b = map_param("shadow_b", shadow_b)

        # 描边宽度: UI [0.5,3.0] → 渲染 [0.5,3.0] (与 MooaToon Width Scale 一致)
        render_outline = map_param("outline_width", outline_width)

        # 高光和边缘光 (与 MooaToon Specular/RimLightWidth 一致)
        render_spec = map_param("specular", specular)
        render_rim = map_param("rim_light", rim_light)

        # 创建渲染参数
        render_params = RenderParams(
            shadow_color=(render_shadow_r, render_shadow_g, render_shadow_b),
            base_color=(0.88, 0.88, 0.88),  # 更亮的基色，对比更明显
            outline_width=render_outline,
            outline_color=(0.02, 0.02, 0.05),  # 更深的描边
            spec_boost=render_spec * 1.2,  # 增强 20%
            rim_boost=render_rim * 1.3,    # 增强 30%
            shade_levels=3 if shadow_r > 0.35 else 2,
        )

        # 渲染
        img = state.gl.render(
            state.shape_name, cam, state.light, render_params,
            width=rw, height=rh
        )

        state._last_render_key = cache_key
        state._last_render_img = img
        return img
    except Exception as e:
        import traceback
        print(f"_render_preview ERROR: {e}")
        traceback.print_exc()
        return None


def _run_inference():
    if state.engine is None or state.ref_image_bgr is None:
        return
    _log(t("log_infering"))
    try:
        # 获取涂鸦遮罩
        mask = None
        if ref_viewer and ref_viewer.enable_brush:
            mask = ref_viewer.get_mask()
            if mask is not None and mask.any():
                _log("Using brush mask for inference")

        tmp = os.path.join(os.path.dirname(__file__), "_tmp.png")
        cv2.imwrite(tmp, state.ref_image_bgr)
        result = state.engine.infer(tmp, mask)
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
    """
    渲染预览并同步到所有活跃的查看器

    在对比模式下，使用 CompareView 组件进行分屏对比
    """
    try:
        preview = _render_preview()
        if preview is None:
            return

        # 处理对比模式（使用 CompareView 组件）
        if compare_view is not None and compare_view.is_active():
            # 设置左侧图像（当前渲染）
            compare_view.set_left_image(preview, "Current")

            # 获取对比图像并设置右侧
            compare_img = _get_compare_image()
            if compare_img is not None:
                label = "History" if _compare_mode == "history" else "Reference"
                compare_view.set_right_image(compare_img, label)

            # CompareView 自己处理显示，不需要单独更新 preview_viewer
        else:
            # 正常模式：直接显示到 preview_viewer
            display_img = preview

            # 更新到查看器
            if preview_viewer is not None and dpg.does_item_exist("preview_viewer_group") \
               and dpg.is_item_visible("preview_viewer_group"):
                preview_viewer.set_image(display_img)

        # 更新弹出窗口（始终显示当前渲染，或带对比的拼接图）
        if popout_viewer is not None and dpg.does_item_exist(f"{popout_viewer.name}_group"):
            if compare_view is not None and compare_view.is_active():
                # 弹出窗口显示拼接对比图
                compare_img = _get_compare_image()
                if compare_img is not None:
                    h1, w1 = preview.shape[:2]
                    h2, w2 = compare_img.shape[:2]
                    if h2 != h1:
                        scale = h1 / h2
                        compare_img = cv2.resize(compare_img, (int(w2 * scale), h1))
                    split_line = np.zeros((h1, 4, 3), dtype=np.uint8)
                    split_line[:, :] = (100, 150, 255)
                    label_bar1 = np.full((25, w1, 3), (35, 35, 35), dtype=np.uint8)
                    label_bar2 = np.full((25, w2 if w2 == w1 else int(w2 * scale), 3), (35, 35, 35), dtype=np.uint8)
                    cv2.putText(label_bar1, "Current", (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                    label_text = "History" if _compare_mode == "history" else "Reference"
                    cv2.putText(label_bar2, label_text, (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                    display_img = np.hstack([np.vstack([label_bar1, preview]), split_line, np.vstack([label_bar2, compare_img])])
                    popout_viewer.set_image(display_img)
                else:
                    popout_viewer.set_image(preview)
            else:
                popout_viewer.set_image(preview)

        # 自动保存快照（当参数变化时）
        current_params = state.get_params_dict()
        current_snap = state.history.get_current()
        if state.history.get_count() == 0 or \
           (current_snap and current_snap.params != current_params):
            state.history.snap(
                current_params,
                preview.copy(),
                state.shape_name,
                f"Params {time.strftime('%H:%M:%S')}"
            )
            _refresh_history_list()
    except Exception as e:
        import traceback
        print(f"_update_preview ERROR: {e}")
        traceback.print_exc()


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

                # 涂鸦控制
                with dpg.group(horizontal=True):
                    dpg.add_text("Brush:", color=(150, 150, 150))
                    dpg.add_button(label="Off", tag="btn_brush_off",
                                  callback=lambda: _set_brush_mode(0), width=35)
                    dpg.add_button(label="Focus", tag="btn_brush_focus",
                                  callback=lambda: _set_brush_mode(1), width=45)
                    dpg.add_button(label="Ignore", tag="btn_brush_ignore",
                                  callback=lambda: _set_brush_mode(2), width=50)
                    dpg.add_button(label="Clear", callback=lambda: _clear_brush(), width=40)
                with dpg.group(horizontal=True):
                    dpg.add_text("Size:", color=(150, 150, 150))
                    dpg.add_slider_int(tag="brush_size_slider", default_value=20,
                                       min_value=5, max_value=50, width=150,
                                       callback=lambda s, a: ref_viewer.set_brush_size(a) if ref_viewer else None)

                ref_viewer = ImageViewer("ref_viewer", width=VIEWER_W, height=VIEWER_H, enable_brush=True)
                dpg.add_text("Scroll=Zoom | Drag=Pan | DblClick=Fit", color=(80,80,80))

            # ====== 中栏：参数 + 预览 + 槽位 ======
            with dpg.child_window(width=460, height=-1):
                # 参数调节
                dpg.add_text(t("param_adjust"), color=(180,200,255), tag="header_param")
                dpg.add_separator()

                # 参数滑块（带悬停提示）
                param_names = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light", "outline_width"]
                for i, (key, mn, mx, step) in enumerate(PARAM_DEFS):
                    param_name = param_names[i] if i < len(param_names) else key.replace("label_", "")
                    tooltip_text = get_tooltip(param_name, get_lang())

                    with dpg.group(horizontal=True):
                        # 参数标签（带提示图标）
                        label_text = f"{t(key)}:"
                        dpg.add_text(label_text, tag=f"slider_label_{i}")

                        # 滑块
                        slider_tag = f"slider_{i}"
                        dpg.add_slider_float(
                            tag=slider_tag,
                            default_value=DEFAULT_VALS[i],
                            min_value=mn, max_value=mx,
                            width=180,
                            callback=on_slider_changed,
                            user_data=i
                        )

                        # 当前值显示
                        dpg.add_text(f"{DEFAULT_VALS[i]:.3f}", tag=f"val_{i}")

                        # 悬停提示（如果可用）
                        if tooltip_text:
                            with dpg.tooltip(parent=slider_tag):
                                dpg.add_text(tooltip_text, wrap=280, color=(200, 200, 200))

                dpg.add_separator()
                # 预览区标题 + 重置 + 弹出
                with dpg.group(horizontal=True):
                    dpg.add_text(t("live_preview"), color=(180,200,255), tag="header_preview")
                    reset_btn = dpg.add_button(label="Reset", callback=lambda: preview_viewer.reset_view() if preview_viewer else None, width=50)
                    with dpg.tooltip(parent=reset_btn):
                        reset_tip = get_lang() == "zh" and "重置相机到默认视角" or "Reset camera to default view"
                        dpg.add_text(reset_tip, color=(200, 200, 200))
                    popout_btn = dpg.add_button(label="Pop Out", tag="btn_popout", callback=on_popout_toggle, width=70)
                    with dpg.tooltip(parent=popout_btn):
                        popout_tip = get_lang() == "zh" and "弹出独立预览窗口\n可最大化、调整大小" or "Open independent preview window\nCan maximize and resize"
                        dpg.add_text(popout_tip, wrap=250, color=(200, 200, 200))

                # 材质球形状选择
                dpg.add_text("Shape:", color=(150, 150, 150))
                with dpg.group(horizontal=True):
                    for i, name in enumerate(SHAPE_NAMES):
                        label = SHAPE_LABELS.get(name, name) if get_lang() == "zh" else SHAPE_LABELS_EN.get(name, name)
                        btn_color = (100, 150, 255) if name == state.shape_name else (60, 60, 60)
                        dpg.add_button(label=label, tag=f"shape_btn_{i}",
                                      callback=on_base_select, user_data=i,
                                      width=70, color=btn_color)

                # 灯光参数调节
                with dpg.tree_node(label="Lighting", default_open=False):
                    # 灯光预设选择
                    with dpg.group(horizontal=True):
                        dpg.add_text("Preset:", color=(150, 150, 150))
                        preset_labels = [LIGHT_PRESETS[k]["name_zh"] if get_lang() == "zh" else LIGHT_PRESETS[k]["name_en"] for k in LIGHT_PRESETS.keys()]
                        dpg.add_combo(items=preset_labels, tag="light_preset_combo",
                                     default_value=preset_labels[0], width=120,
                                     callback=_on_light_preset_selected)

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
                                                 width=160, callback=on_light_changed, user_data=attr,
                                                 tag=f"light_slider_{attr}")

                preview_viewer = ImageViewer("preview_viewer", width=VIEWER_W, height=VIEWER_H,
                                             camera_mode=True)
                preview_viewer._on_camera_change = _update_preview
                dpg.add_text("MidDrag=Orbit | Scroll=Zoom | LeftDrag=Pan | DblClick=Reset",
                             color=(80,80,80))

                # 弹出时的占位提示
                dpg.add_text("[ Preview popped out ]", tag="preview_placeholder",
                             color=(100, 150, 255), show=False)

                # ─── CompareView 分屏对比组件 ───────────────────────────────────
                global compare_view
                compare_view = CompareView("main_compare", width=VIEWER_W, height=VIEWER_H)

                # ─── 对比视图控制 ────────────────────────────────────────────────
                dpg.add_separator()
                with dpg.group(horizontal=True):
                    dpg.add_text("Compare:", color=(150, 150, 150))
                    dpg.add_button(label="Off", tag="btn_compare_off",
                                  callback=lambda: _set_compare_mode("off"), width=35)
                    dpg.add_button(label="History", tag="btn_compare_history",
                                  callback=lambda: _set_compare_mode("history"), width=55)
                    dpg.add_button(label="Reference", tag="btn_compare_ref",
                                  callback=lambda: _set_compare_mode("reference"), width=60)
                # 历史快照选择器
                with dpg.group(horizontal=True):
                    dpg.add_text("vs:", color=(120, 120, 120))
                    dpg.add_combo(["Latest"], tag="compare_snapshot_combo",
                                  default_value="Latest", width=150,
                                  callback=_on_compare_snapshot_changed)
                with dpg.tooltip(parent="btn_compare_history"):
                    compare_tip = get_lang() == "zh" and "与历史快照对比\n选择下方快照进行对比" or "Compare with history snapshot\nSelect snapshot below to compare"
                    dpg.add_text(compare_tip, color=(200, 200, 200))

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
                # 语言切换按钮
                lang_btn = dpg.add_button(label=t("btn_lang"), tag="btn_lang",
                                          callback=on_lang_toggle, width=50)
                with dpg.tooltip(parent=lang_btn):
                    dpg.add_text("切换语言: 中文 ↔ English\nSwitch language", color=(200, 200, 200))

                dpg.add_spacer(height=5)

                dpg.add_text(t("actions"), color=(180,200,255), tag="header_actions")
                dpg.add_separator()

                # AI 推理按钮
                infer_btn = dpg.add_button(label=t("btn_infer"), tag="btn_infer",
                                            callback=on_infer_clicked, width=-1, height=35)
                infer_tip = get_lang() == "zh" and "分析参考图，自动提取风格参数\n建议：先上传清晰的风格化参考图" or "Analyze reference image, extract style parameters\nTip: Use clear stylized reference image"
                with dpg.tooltip(parent=infer_btn):
                    dpg.add_text(infer_tip, wrap=280, color=(200, 200, 200))

                dpg.add_spacer(height=5)

                # ─── 撤销/重做 ────────────────────────────────────────────────
                with dpg.group(horizontal=True):
                    undo_btn = dpg.add_button(label="↶ Undo", tag="btn_undo",
                                             callback=on_undo_clicked, width=80)
                    redo_btn = dpg.add_button(label="↷ Redo", tag="btn_redo",
                                             callback=on_redo_clicked, width=80)
                    with dpg.tooltip(parent=undo_btn):
                        undo_tip = get_lang() == "zh" and "撤销到上一步参数设置" or "Undo to previous parameter settings"
                        dpg.add_text(undo_tip, color=(200, 200, 200))
                    with dpg.tooltip(parent=redo_btn):
                        redo_tip = get_lang() == "zh" and "重做下一步参数设置" or "Redo to next parameter settings"
                        dpg.add_text(redo_tip, color=(200, 200, 200))

                dpg.add_spacer(height=5)

                with dpg.group(horizontal=True):
                    check_btn = dpg.add_button(label=t("btn_check_ue"), tag="btn_check_ue",
                                               callback=on_health_check_clicked, width=140)
                    ue_tip = get_lang() == "zh" and "检查 UE5 插件连接状态\n确保 UE5 已启动插件 HTTP 服务" or "Check UE5 plugin connection\nEnsure UE5 has started plugin HTTP server"
                    with dpg.tooltip(parent=check_btn):
                        dpg.add_text(ue_tip, wrap=280, color=(200, 200, 200))
                    dpg.add_text(t("ue_status_init"), tag="ue_status", color=(150,150,150))

                # 发送到 UE5 按钮
                send_btn = dpg.add_button(label=t("btn_send_ue"), tag="btn_send_ue",
                                          callback=on_send_ue_clicked, width=-1, height=35)
                send_tip = get_lang() == "zh" and "将当前参数发送到 UE5\nUE5 材质会实时更新效果" or "Send current parameters to UE5\nMaterial updates in real-time"
                with dpg.tooltip(parent=send_btn):
                    dpg.add_text(send_tip, wrap=280, color=(200, 200, 200))

                # ─── 参数导出/导入 ────────────────────────────────────────────────
                dpg.add_spacer(height=5)
                with dpg.group(horizontal=True):
                    export_btn = dpg.add_button(label="Export JSON", callback=on_export_params, width=100)
                    csv_btn = dpg.add_button(label="Export CSV", callback=on_export_csv, width=100)
                    with dpg.tooltip(parent=export_btn):
                        export_tip = get_lang() == "zh" and "导出当前参数到JSON文件\n包含材质和灯光参数" or "Export current params to JSON\nIncludes material and light params"
                        dpg.add_text(export_tip, wrap=280, color=(200, 200, 200))
                    with dpg.tooltip(parent=csv_btn):
                        csv_tip = get_lang() == "zh" and "导出为MooaToon CSV格式\n可用于训练数据" or "Export as MooaToon CSV format\nCan be used for training data"
                        dpg.add_text(csv_tip, wrap=280, color=(200, 200, 200))

                # 导入文件对话框
                with dpg.file_dialog(directory_selector=False, show=False,
                                     callback=on_import_params, tag="import_dialog",
                                     width=500, height=300):
                    dpg.add_file_extension(".json", color=(100, 200, 255))

                import_btn = dpg.add_button(label="Import JSON",
                                            callback=lambda: dpg.show_item("import_dialog"),
                                            width=-1)
                with dpg.tooltip(parent=import_btn):
                    import_tip = get_lang() == "zh" and "从JSON文件导入参数\n恢复之前保存的设置" or "Import params from JSON file\nRestore previously saved settings"
                    dpg.add_text(import_tip, wrap=280, color=(200, 200, 200))

                dpg.add_spacer(height=10)
                dpg.add_separator()
                dpg.add_text(t("style_presets"), color=(180,200,255), tag="header_presets")
                with dpg.group(horizontal=True):
                    dpg.add_input_text(tag="preset_name_input", hint=t("hint_preset_name"), width=160)
                    dpg.add_button(label=t("btn_save"), tag="btn_save_preset",
                                   callback=on_save_preset_clicked, width=60)
                dpg.add_group(tag="preset_list_group")

                # ─── 历史快照 ────────────────────────────────────────────────
                dpg.add_spacer(height=10)
                dpg.add_separator()
                hist_header = dpg.add_text("History", color=(180,200,255), tag="header_history")
                with dpg.tooltip(parent=hist_header):
                    hist_tip = get_lang() == "zh" and "点击恢复历史参数设置" or "Click to restore parameter settings"
                    dpg.add_text(hist_tip, color=(200, 200, 200))
                with dpg.child_window(tag="history_list_group", height=100, border=True):
                    dpg.add_text("No history yet", color=(100, 100, 100))

                dpg.add_spacer(height=10)
                dpg.add_separator()
                dpg.add_text(t("log_title"), color=(180,200,255), tag="header_log")
                with dpg.child_window(tag="log_window", height=-1, border=True):
                    dpg.add_group(tag="log_content")

    _refresh_preset_list()

    # ─── 键盘快捷键 ────────────────────────────────────────────────────────────
    with dpg.handler_registry(tag="global_key_handlers"):
        # Ctrl+Z: 撤销
        dpg.add_key_press_handler(key=dpg.mvKey_Z, callback=lambda: on_undo_clicked() if dpg.is_key_down(dpg.mvKey_Control) else None)
        # Ctrl+Y: 重做
        dpg.add_key_press_handler(key=dpg.mvKey_Y, callback=lambda: on_redo_clicked() if dpg.is_key_down(dpg.mvKey_Control) else None)
        # Space: 重置视图
        dpg.add_key_press_handler(key=dpg.mvKey_Space, callback=_on_space_pressed)
        # R: 重置参数到默认
        dpg.add_key_press_handler(key=dpg.mvKey_R, callback=_on_reset_params)
        # F: 适应窗口
        dpg.add_key_press_handler(key=dpg.mvKey_F, callback=_on_fit_to_window)


def _on_space_pressed():
    """空格键：重置预览相机视角"""
    if preview_viewer and preview_viewer.camera:
        preview_viewer.camera.reset(state.shape_name)
        state._last_render_key = ()
        state._preview_dirty = True
        state._last_change_time = 0
        _log("View reset (Space)")


def _on_reset_params():
    """R键：重置参数到默认值"""
    defaults = get_defaults()
    state.set_params_from_dict(defaults)
    params_list = [defaults.get("shadow_r", 0.5),
                   defaults.get("shadow_g", 0.5),
                   defaults.get("shadow_b", 0.5),
                   defaults.get("specular", 0.5),
                   defaults.get("rim_light", 0.5),
                   defaults.get("outline_width", 1.0)]
    for i, val in enumerate(params_list):
        if dpg.does_item_exist(f"slider_{i}"):
            dpg.set_value(f"slider_{i}", val)
        if dpg.does_item_exist(f"val_{i}"):
            dpg.set_value(f"val_{i}", f"{val:.3f}")
    state._last_render_key = ()
    state._preview_dirty = True
    state._last_change_time = 0
    _log("Params reset to defaults (R)")


def _on_fit_to_window():
    """F键：适应窗口"""
    if ref_viewer:
        ref_viewer.reset_view()
    if preview_viewer:
        preview_viewer.reset_view()
    _log("Fit to window (F)")


# ─── 参数导出/导入 ────────────────────────────────────────────────────────────
import json


def on_export_params():
    """导出当前参数到JSON文件"""
    import os
    from datetime import datetime

    params = state.get_params_dict()
    export_data = {
        "timestamp": datetime.now().isoformat(),
        "shape": state.shape_name,
        "params": params,
        "light": {
            "ambient": state.light.ambient,
            "diffuse": state.light.diffuse,
            "specular_power": state.light.specular_power,
            "specular_intensity": state.light.specular_intensity,
            "rim_intensity": state.light.rim_intensity,
            "rim_power": state.light.rim_power,
        },
        # MooaToon CSV 格式兼容
        "mooatoon_csv": {
            "ShadowR": params.get("shadow_r", 0.5),
            "ShadowG": params.get("shadow_g", 0.5),
            "ShadowB": params.get("shadow_b", 0.5),
            "Specular": params.get("specular", 0.5),
            "RimLightWidth": params.get("rim_light", 0.5),
            "WidthScale": params.get("outline_width", 1.0),
        }
    }

    # 保存到文件
    export_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(export_dir, exist_ok=True)
    filename = f"params_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(export_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    _log(f"Params exported: {filename}")
    return filepath


def on_import_params(sender, app_data):
    """从JSON文件导入参数"""
    import os

    filepath = app_data["file_path_name"]
    if not filepath or not os.path.exists(filepath):
        _log("Import failed: file not found", error=True)
        return

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 导入材质参数
        if "params" in data:
            state.set_params_from_dict(data["params"])
            params_list = [
                data["params"].get("shadow_r", 0.5),
                data["params"].get("shadow_g", 0.5),
                data["params"].get("shadow_b", 0.5),
                data["params"].get("specular", 0.5),
                data["params"].get("rim_light", 0.5),
                data["params"].get("outline_width", 1.0),
            ]
            for i, val in enumerate(params_list):
                if dpg.does_item_exist(f"slider_{i}"):
                    dpg.set_value(f"slider_{i}", val)
                if dpg.does_item_exist(f"val_{i}"):
                    dpg.set_value(f"val_{i}", f"{val:.3f}")

        # 导入灯光参数
        if "light" in data:
            light_data = data["light"]
            state.light.ambient = light_data.get("ambient", 0.25)
            state.light.diffuse = light_data.get("diffuse", 0.80)
            state.light.specular_power = light_data.get("specular_power", 40.0)
            state.light.specular_intensity = light_data.get("specular_intensity", 0.35)
            state.light.rim_intensity = light_data.get("rim_intensity", 0.15)
            state.light.rim_power = light_data.get("rim_power", 3.0)

        state._last_render_key = ()
        state._preview_dirty = True
        state._last_change_time = 0

        _log(f"Params imported: {os.path.basename(filepath)}")
    except Exception as e:
        _log(f"Import failed: {e}", error=True)


def on_export_csv():
    """导出参数为MooaToon CSV格式"""
    import os
    import csv
    from datetime import datetime

    params = state.get_params_dict()

    export_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(export_dir, exist_ok=True)
    filename = f"mooatoon_params_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(export_dir, filename)

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "ShadowR", "ShadowG", "ShadowB", "Specular", "RimLightWidth", "WidthScale"])
        writer.writerow([
            datetime.now().strftime("%Y%m%d_%H%M%S"),
            f"{params.get('shadow_r', 0.5):.6f}",
            f"{params.get('shadow_g', 0.5):.6f}",
            f"{params.get('shadow_b', 0.5):.6f}",
            f"{params.get('specular', 0.5):.6f}",
            f"{params.get('rim_light', 0.5):.6f}",
            f"{params.get('outline_width', 1.0):.6f}",
        ])

    _log(f"CSV exported: {filename}")
    return filepath


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
                    old_size = _popout_last_size if _popout_last_size[0] > 0 else (380, 380)
                    _popout_last_size = (content_w, content_h)
                    # 保存相机状态
                    cam_yaw = popout_viewer.camera.yaw
                    cam_pitch = popout_viewer.camera.pitch
                    cam_zoom = popout_viewer.camera.zoom
                    # 根据尺寸变化调整 zoom，保持模型视觉大小
                    scale_change = min(content_w, content_h) / min(old_size[0], old_size[1])
                    new_zoom = cam_zoom * scale_change
                    # 限制 zoom 范围
                    new_zoom = max(0.2, min(5.0, new_zoom))
                    # 重建 drawlist
                    popout_viewer.resize(content_w, content_h)
                    # 恢复相机
                    popout_viewer.camera.yaw = cam_yaw
                    popout_viewer.camera.pitch = cam_pitch
                    popout_viewer.camera.zoom = new_zoom
                    state._last_render_key = ()  # 使缓存失效（渲染尺寸变了）
                    state._preview_dirty = True
                    state._last_change_time = 0

        _debounce_tick(None, None)
        dpg.render_dearpygui_frame()

    state.gl.cleanup()
    dpg.destroy_context()
