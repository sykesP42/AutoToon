"""
ui.py — Dear PyGui 主界面
暗黑主题 UI：图片上传、6 参数滑块、实时预览、推理、发送 UE5、预设管理。
"""
import os
import time
import numpy as np
import cv2

import dearpygui.dearpygui as dpg

from engine import InferenceEngine, PARAM_NAMES
from preview import apply_style_preview, load_image_bgr, bgr_to_rgba
from ue_client import UE5Client
from style_manager import StyleManager


# ─── 全局状态 ────────────────────────────────────────────────────────────────────
class AppState:
    def __init__(self):
        self.engine: InferenceEngine | None = None
        self.ue_client: UE5Client | None = None
        self.style_mgr = StyleManager()

        self.ref_image_bgr: np.ndarray | None = None   # 原始参考图 (BGR)
        self.ref_image_path: str = ""
        self.preview_bgr: np.ndarray | None = None     # 预览图 (BGR)

        # 6 个参数
        self.shadow_r = 0.3
        self.shadow_g = 0.3
        self.shadow_b = 0.3
        self.specular = 0.5
        self.rim_light_width = 0.5
        self.width_scale = 1.0

        # 纹理 ID
        self.ref_texture_tag = "ref_texture"
        self.preview_texture_tag = "preview_texture"

        # UE5 连接状态
        self.ue_connected = False
        self.last_health_check = 0.0


state = AppState()


# ─── 初始化 ──────────────────────────────────────────────────────────────────────
def init_engine(onnx_path: str) -> str:
    """初始化 ONNX 引擎，返回状态消息"""
    try:
        state.engine = InferenceEngine(onnx_path)
        return f"模型加载成功: {os.path.basename(onnx_path)}"
    except Exception as e:
        return f"模型加载失败: {e}"


def init_ue_client() -> str:
    """初始化 UE5 客户端"""
    try:
        state.ue_client = UE5Client()
        return "UE5 客户端就绪"
    except Exception as e:
        return f"UE5 客户端初始化失败: {e}"


# ─── 回调函数 ────────────────────────────────────────────────────────────────────
def on_file_selected(sender, app_data):
    """文件对话框选择图片后"""
    file_path = app_data["file_path_name"]
    if not file_path:
        return

    try:
        state.ref_image_bgr = load_image_bgr(file_path)
        state.ref_image_path = file_path

        # 更新参考图纹理
        _update_texture(state.ref_image_bgr, state.ref_texture_tag)

        # 更新路径显示
        dpg.set_value("path_text", file_path)

        # 自动推理
        if state.engine:
            _run_inference()

        _log(f"已加载图片: {os.path.basename(file_path)}")

    except Exception as e:
        _log(f"加载图片失败: {e}", error=True)


def on_slider_changed(sender, app_data, user_data):
    """滑块值变化"""
    param_idx = user_data
    value = app_data

    if param_idx == 0:
        state.shadow_r = value
    elif param_idx == 1:
        state.shadow_g = value
    elif param_idx == 2:
        state.shadow_b = value
    elif param_idx == 3:
        state.specular = value
    elif param_idx == 4:
        state.rim_light_width = value
    elif param_idx == 5:
        state.width_scale = value

    # 更新数值标签
    dpg.set_value(f"val_{param_idx}", f"{value:.3f}")

    # 实时预览
    _update_preview()


def on_infer_clicked():
    """点击推理按钮"""
    if not state.ref_image_bgr is not None:
        _log("请先上传参考图", error=True)
        return
    _run_inference()


def on_send_ue_clicked():
    """点击发送到 UE5"""
    if state.ue_client is None:
        _log("UE5 客户端未初始化", error=True)
        return

    params = [state.shadow_r, state.shadow_g, state.shadow_b,
              state.specular, state.rim_light_width, state.width_scale]

    result = state.ue_client.send_params(params)
    if result["ok"]:
        _log(f"已发送到 UE5: Shadow=({params[0]:.3f},{params[1]:.3f},{params[2]:.3f}) "
             f"Spec={params[3]:.3f} Rim={params[4]:.3f} Width={params[5]:.3f}")
    else:
        _log(f"发送失败: {result['error']}", error=True)


def on_health_check_clicked():
    """检查 UE5 连接"""
    if state.ue_client is None:
        state.ue_client = UE5Client()

    result = state.ue_client.health_check()
    state.ue_connected = result["ok"]
    state.last_health_check = time.time()

    if result["ok"]:
        _log("UE5 连接正常")
        dpg.set_value("ue_status", "已连接")
        dpg.configure_item("ue_status", color=(100, 255, 100))
    else:
        _log(f"UE5 未连接: {result['error']}", error=True)
        dpg.set_value("ue_status", "未连接")
        dpg.configure_item("ue_status", color=(255, 100, 100))


def on_save_preset_clicked():
    """保存当前参数为预设"""
    name = dpg.get_value("preset_name_input")
    if not name.strip():
        _log("请输入预设名称", error=True)
        return

    params = [state.shadow_r, state.shadow_g, state.shadow_b,
              state.specular, state.rim_light_width, state.width_scale]

    try:
        path = state.style_mgr.save(name, params)
        _log(f"预设已保存: {path}")
        _refresh_preset_list()
    except Exception as e:
        _log(f"保存失败: {e}", error=True)


def on_load_preset_clicked(sender, app_data, user_data):
    """加载预设"""
    file_path = user_data
    try:
        preset = state.style_mgr.load(file_path)
        params = preset["params"]
        _apply_params(params)
        _log(f"已加载预设: {preset['name']}")
    except Exception as e:
        _log(f"加载失败: {e}", error=True)


# ─── 内部函数 ────────────────────────────────────────────────────────────────────
def _run_inference():
    """执行 ONNX 推理"""
    if state.engine is None or state.ref_image_bgr is None:
        return

    _log("正在推理...")
    try:
        # 保存临时图用于推理
        tmp_path = os.path.join(os.path.dirname(__file__), "_tmp_infer.png")
        cv2.imwrite(tmp_path, state.ref_image_bgr)

        result = state.engine.infer(tmp_path)
        params = result["params"]

        # 更新滑块和状态
        _apply_params(params)

        _log(f"推理完成: Shadow=({params[0]:.3f},{params[1]:.3f},{params[2]:.3f}) "
             f"Spec={params[3]:.3f} Rim={params[4]:.3f} Width={result['width_scale_ue']:.3f}")

        # 清理临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    except Exception as e:
        _log(f"推理失败: {e}", error=True)


def _apply_params(params: list):
    """将 6 参数应用到滑块和状态"""
    state.shadow_r = params[0]
    state.shadow_g = params[1]
    state.shadow_b = params[2]
    state.specular = params[3]
    state.rim_light_width = params[4]
    state.width_scale = params[5]

    for i, val in enumerate(params):
        dpg.set_value(f"slider_{i}", val)
        dpg.set_value(f"val_{i}", f"{val:.3f}")

    _update_preview()


def _update_preview():
    """更新实时预览"""
    if state.ref_image_bgr is None:
        return

    state.preview_bgr = apply_style_preview(
        state.ref_image_bgr,
        state.shadow_r, state.shadow_g, state.shadow_b,
        state.specular, state.rim_light_width, state.width_scale,
    )

    _update_texture(state.preview_bgr, state.preview_texture_tag)


def _update_texture(img_bgr: np.ndarray, tag: str):
    """更新 Dear PyGui 纹理"""
    rgba = bgr_to_rgba(img_bgr)
    h, w = rgba.shape[:2]
    flat = rgba.flatten().tolist()

    if dpg.does_item_exist(tag):
        dpg.delete_item(tag)

    with dpg.texture_registry():
        dpg.add_dynamic_texture(w, h, flat, tag=tag)

    # 更新对应的 image 控件
    img_widget = f"{tag}_widget"
    if dpg.does_item_exist(img_widget):
        dpg.configure_item(img_widget, texture_tag=tag)


def _log(msg: str, error: bool = False):
    """输出日志"""
    timestamp = time.strftime("%H:%M:%S")
    prefix = "[ERR]" if error else "[LOG]"
    color = [255, 100, 100] if error else [200, 200, 200]

    log_text = dpg.get_value("log_area") or ""
    new_line = f"[{timestamp}] {prefix} {msg}\n"
    dpg.set_value("log_area", log_text + new_line)

    # 自动滚到底部
    if dpg.does_item_exist("log_window"):
        dpg.set_y_scroll("log_window", -1.0)


def _refresh_preset_list():
    """刷新预设列表"""
    # 删除旧的预设按钮
    if dpg.does_item_exist("preset_list_group"):
        dpg.delete_item("preset_list_group", children_only=True)

    presets = state.style_mgr.list_presets()
    for preset in presets:
        dpg.add_button(
            label=preset["name"],
            callback=on_load_preset_clicked,
            user_data=preset["file_path"],
            width=-1,
            parent="preset_list_group",
        )


def _create_placeholder_texture(tag: str, w: int = 384, h: int = 384):
    """创建占位纹理（灰底）"""
    placeholder = np.full((h, w, 4), [0.15, 0.15, 0.15, 1.0], dtype=np.float32)
    flat = placeholder.flatten().tolist()

    with dpg.texture_registry():
        dpg.add_dynamic_texture(w, h, flat, tag=tag)


# ─── 构建 UI ─────────────────────────────────────────────────────────────────────
def build_ui():
    """构建 Dear PyGui 界面"""
    dpg.create_context()
    dpg.create_viewport(title="AutoToon Studio", width=1280, height=800)

    # 全局主题：暗黑风格
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (30, 30, 30), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (20, 20, 20), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (40, 40, 40), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (45, 45, 45), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Button, (60, 60, 60), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 80, 80), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (100, 150, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (120, 170, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Header, (50, 50, 50), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (35, 35, 35), category=dpg.mvThemeCat_Core)

    dpg.bind_theme(global_theme)

    # 创建占位纹理
    _create_placeholder_texture(state.ref_texture_tag)
    _create_placeholder_texture(state.preview_texture_tag)

    # 文件对话框
    with dpg.file_dialog(
        directory_selector=False,
        show=False,
        callback=on_file_selected,
        tag="file_dialog",
        width=600,
        height=400,
    ):
        dpg.add_file_extension("图片{.png,.jpg,.jpeg,.bmp}", color=(100, 200, 255))

    # ─── 主窗口 ──────────────────────────────────────────────────────────────────
    with dpg.window(tag="primary_window"):
        with dpg.group(horizontal=True):

            # ====== 左栏：参考图 ======
            with dpg.child_window(width=400, height=-1):
                dpg.add_text("参考图", color=(180, 200, 255))
                dpg.add_separator()

                with dpg.group(horizontal=True):
                    dpg.add_button(label="上传图片", callback=lambda: dpg.show_item("file_dialog"), width=120)
                    dpg.add_text("", tag="path_text", color=(120, 120, 120))

                dpg.add_image(state.ref_texture_tag, tag=f"{state.ref_texture_tag}_widget",
                              width=380, height=380)

            # ====== 中栏：参数调节 + 预览 ======
            with dpg.child_window(width=430, height=-1):
                dpg.add_text("参数调节", color=(180, 200, 255))
                dpg.add_separator()

                param_labels = [
                    ("Shadow R", 0, 1, 0.01),
                    ("Shadow G", 0, 1, 0.01),
                    ("Shadow B", 0, 1, 0.01),
                    ("Specular", 0, 1, 0.01),
                    ("Rim Light Width", 0, 1, 0.01),
                    ("Width Scale", 0.5, 3.0, 0.05),
                ]

                for i, (label, mn, mx, step) in enumerate(param_labels):
                    with dpg.group(horizontal=True):
                        dpg.add_text(f"{label}:", width=120)
                        dpg.add_slider_float(
                            tag=f"slider_{i}",
                            default_value=state.shadow_r if i == 0 else (
                                state.shadow_g if i == 1 else (
                                state.shadow_b if i == 2 else (
                                state.specular if i == 3 else (
                                state.rim_light_width if i == 4 else state.width_scale)))),
                            min_value=mn,
                            max_value=mx,
                            width=200,
                            callback=on_slider_changed,
                            user_data=i,
                        )
                        dpg.add_text(
                            f"{state.shadow_r:.3f}" if i == 0 else (
                            f"{state.shadow_g:.3f}" if i == 1 else (
                            f"{state.shadow_b:.3f}" if i == 2 else (
                            f"{state.specular:.3f}" if i == 3 else (
                            f"{state.rim_light_width:.3f}" if i == 4 else f"{state.width_scale:.3f}")))),
                            tag=f"val_{i}",
                            width=50,
                        )

                dpg.add_separator()
                dpg.add_text("实时预览", color=(180, 200, 255))

                dpg.add_image(state.preview_texture_tag, tag=f"{state.preview_texture_tag}_widget",
                              width=400, height=300)

            # ====== 右栏：操作 + 预设 + 日志 ======
            with dpg.child_window(width=-1, height=-1):
                dpg.add_text("操作", color=(180, 200, 255))
                dpg.add_separator()

                dpg.add_button(label="推理 (AI 分析)", callback=on_infer_clicked, width=-1, height=35)

                dpg.add_spacer(height=5)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="检查 UE5 连接", callback=on_health_check_clicked, width=140)
                    dpg.add_text("未检查", tag="ue_status", color=(150, 150, 150))

                dpg.add_button(label="发送到 UE5", callback=on_send_ue_clicked, width=-1, height=35)

                dpg.add_spacer(height=10)
                dpg.add_separator()

                # 预设管理
                dpg.add_text("风格预设", color=(180, 200, 255))
                with dpg.group(horizontal=True):
                    dpg.add_input_text(tag="preset_name_input", hint="预设名称", width=160)
                    dpg.add_button(label="保存", callback=on_save_preset_clicked, width=60)

                dpg.add_group(tag="preset_list_group")

                dpg.add_spacer(height=10)
                dpg.add_separator()

                # 日志
                dpg.add_text("日志", color=(180, 200, 255))
                with dpg.child_window(tag="log_window", height=-1, border=True):
                    dpg.add_text("", tag="log_area")

    # 加载已有预设
    _refresh_preset_list()


def run(onnx_path: str = None):
    """启动 AutoToon Studio"""
    build_ui()

    # 初始化引擎
    if onnx_path and os.path.exists(onnx_path):
        msg = init_engine(onnx_path)
        _log(msg)
    else:
        _log("ONNX 模型未指定，推理功能不可用（可稍后加载）")

    # 初始化 UE5 客户端
    ue_msg = init_ue_client()
    _log(ue_msg)

    _log("AutoToon Studio 就绪")

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("primary_window", True)
    dpg.start_dearpygui()
    dpg.destroy_context()
