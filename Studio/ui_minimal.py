"""
ui_minimal.py — AutoToon Studio 最简版本
只保留核心功能：参数调节 + 球体预览
"""
import os
import time
import numpy as np
import cv2
from typing import Optional

import dearpygui.dearpygui as dpg

from gl_renderer import GLRenderer, Camera, LightParams, RenderParams
from image_viewer import ImageViewer

VIEWER_W, VIEWER_H = 380, 380

# 全局状态
gl: Optional[GLRenderer] = None
preview_viewer: Optional[ImageViewer] = None
cam: Optional[Camera] = None
light: Optional[LightParams] = None

# 参数默认值
params = {
    "shadow_r": 0.3,
    "shadow_g": 0.3,
    "shadow_b": 0.3,
    "specular": 0.5,
    "rim_light": 0.5,
    "outline_width": 1.0,
}


def render_sphere():
    """渲染球体"""
    if gl is None or preview_viewer is None:
        return

    render_params = RenderParams(
        shadow_color=(params["shadow_r"], params["shadow_g"], params["shadow_b"]),
        base_color=(0.85, 0.85, 0.85),
        outline_width=params["outline_width"],
        spec_boost=params["specular"],
        rim_boost=params["rim_light"],
    )

    img = gl.render('sphere', cam, light, render_params)
    preview_viewer.set_image(img)


def on_slider_change(sender, app_data, user_data):
    """滑块回调"""
    param_names = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light", "outline_width"]
    params[param_names[user_data]] = app_data
    dpg.set_value(f"val_{user_data}", f"{app_data:.2f}")
    render_sphere()


def build_ui():
    """构建简化 UI"""
    global preview_viewer

    dpg.create_context()
    dpg.create_viewport(title="AutoToon Studio", width=450, height=500)

    # 暗黑主题
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (30, 30, 30))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (45, 45, 45))
    dpg.bind_theme(theme)

    with dpg.window(tag="main"):
        dpg.add_text("AutoToon Studio — Sphere Preview", color=(100, 150, 255))
        dpg.add_separator()

        # 参数滑块
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
                    width=180,
                    callback=on_slider_change,
                    user_data=i
                )
                dpg.add_text(f"{defaults[i]:.2f}", tag=f"val_{i}")

        dpg.add_separator()

        # 预览区
        dpg.add_text("Preview:", color=(180, 180, 180))
        preview_viewer = ImageViewer("preview", width=VIEWER_W, height=VIEWER_H)

        dpg.add_text("Scroll=Zoom | Drag=Pan", color=(80, 80, 80))


def run():
    """运行程序"""
    global gl, cam, light

    print("[GL] Initializing...")
    gl = GLRenderer(width=VIEWER_W, height=VIEWER_H)
    cam = Camera()
    light = LightParams()

    build_ui()

    # 初始渲染
    print("[Render] Initial sphere...")
    render_sphere()

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)

    print("[Loop] Running...")
    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()

    gl.cleanup()
    dpg.destroy_context()
    print("[Done]")


if __name__ == "__main__":
    run()