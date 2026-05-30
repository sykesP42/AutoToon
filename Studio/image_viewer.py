"""
image_viewer.py — 图片查看器组件
两种模式：
  模式 1（默认）：2D 图片缩放/平移
  模式 2（camera_mode）：3D 相机轨道旋转（仿 Blender）
"""
import time
import dearpygui.dearpygui as dpg
import numpy as np
import cv2
from gl_renderer import Camera

MAX_TEX = 512
RENDER_THROTTLE = 0.05  # 50ms 最小渲染间隔


class ImageViewer:
    def __init__(self, name: str, width: int = 380, height: int = 380,
                 parent: int = 0, camera_mode: bool = False):
        self.name = name
        self.width = width
        self.height = height
        self.camera_mode = camera_mode
        self.camera = Camera() if camera_mode else None
        self._parent = parent  # 保存 parent 用于 resize 重建

        self.tex_tag = f"{name}_tex"
        self.tex_w = 1
        self.tex_h = 1
        self._has_image = False

        # 2D 模式的缩放/平移
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

        self._dragging = False
        self._drag_button = -1
        self._drag_start = (0, 0)
        self._pan_start = (0, 0)
        self._camera_start = None

        # 预分配纹理
        init_data = [0.15, 0.15, 0.15, 1.0] * (MAX_TEX * MAX_TEX)
        with dpg.texture_registry():
            dpg.add_dynamic_texture(MAX_TEX, MAX_TEX, init_data, tag=self.tex_tag)

        with dpg.group(parent=parent, tag=f"{name}_group"):
            with dpg.drawlist(width=width, height=height, tag=f"{name}_drawlist"):
                dpg.draw_rectangle((0, 0), (width, height), fill=(25, 25, 25), tag=f"{name}_bg")
                dpg.draw_image(self.tex_tag, (0, 0), (width, height),
                               uv_min=(0, 0), uv_max=(0, 0), tag=f"{name}_img")
                dpg.draw_text((width // 2 - 40, height // 2 - 8), "No Image",
                              color=(80, 80, 80), size=14, tag=f"{name}_placeholder")

        with dpg.handler_registry(tag=f"{name}_handlers"):
            dpg.add_mouse_wheel_handler(callback=self._on_mouse_wheel)
            dpg.add_mouse_drag_handler(button=0, callback=self._on_left_drag)
            dpg.add_mouse_drag_handler(button=1, callback=self._on_right_drag)
            dpg.add_mouse_drag_handler(button=2, callback=self._on_middle_drag)
            dpg.add_mouse_release_handler(callback=self._on_mouse_release)
            dpg.add_mouse_double_click_handler(button=dpg.mvMouseButton_Left,
                                                callback=self._on_double_click)

        # 相机变化回调 + 节流
        self._on_camera_change = None
        self._last_render_time = 0.0

    def _fire_camera_change(self, force: bool = False):
        """节流触发相机变化回调"""
        now = time.time()
        if force or (now - self._last_render_time) > RENDER_THROTTLE:
            self._last_render_time = now
            if self._on_camera_change:
                self._on_camera_change()

    def set_image(self, img_bgr: np.ndarray, fit: bool = True):
        if img_bgr is None or img_bgr.size == 0:
            return
        h, w = img_bgr.shape[:2]
        h, w = min(h, MAX_TEX), min(w, MAX_TEX)
        self.tex_w, self.tex_h = w, h
        self._has_image = True

        img_crop = img_bgr[:h, :w]
        rgba = cv2.cvtColor(cv2.cvtColor(img_crop, cv2.COLOR_BGR2RGB),
                            cv2.COLOR_RGB2RGBA).astype(np.float32) / 255.0

        # 预分配 + 就地写入（避免每次创建新数组）
        if not hasattr(self, '_tex_buf') or self._tex_buf.shape[:2] != (MAX_TEX, MAX_TEX):
            self._tex_buf = np.full((MAX_TEX, MAX_TEX, 4), [0.15, 0.15, 0.15, 1.0], dtype=np.float32)
        else:
            self._tex_buf[:, :, :] = 0.15
            self._tex_buf[:, :, 3] = 1.0
        self._tex_buf[:h, :w, :] = rgba
        dpg.set_value(self.tex_tag, self._tex_buf.ravel(order="C").tolist())

        if dpg.does_item_exist(f"{self.name}_placeholder"):
            dpg.configure_item(f"{self.name}_placeholder", show=False)

        if fit and not self.camera_mode:
            self._fit_to_window()
        self._update_draw()

    def reset_view(self):
        if self.camera_mode and self.camera:
            self.camera.reset()
            self._fire_camera_change(force=True)
        else:
            self._fit_to_window()
            self._update_draw()

    def resize(self, new_w: int, new_h: int):
        """重建 drawlist 到新尺寸（DearPyGui 不支持动态 resize drawlist）"""
        self.width = new_w
        self.height = new_h
        # 删除旧的 group（包含 drawlist + 所有子元素）
        old_group = f"{self.name}_group"
        old_handlers = f"{self.name}_handlers"
        if dpg.does_item_exist(old_group):
            dpg.delete_item(old_group)
        if dpg.does_item_exist(old_handlers):
            dpg.delete_item(old_handlers)
        # 重建 drawlist + handlers（使用保存的 parent）
        with dpg.group(parent=self._parent, tag=f"{self.name}_group"):
            with dpg.drawlist(width=new_w, height=new_h, tag=f"{self.name}_drawlist"):
                dpg.draw_rectangle((0, 0), (new_w, new_h), fill=(25, 25, 25), tag=f"{self.name}_bg")
                dpg.draw_image(self.tex_tag, (0, 0), (new_w, new_h),
                               uv_min=(0, 0), uv_max=(0, 0), tag=f"{self.name}_img")
                if self._has_image:
                    self._update_draw()
                else:
                    dpg.draw_text((new_w // 2 - 40, new_h // 2 - 8), "No Image",
                                  color=(80, 80, 80), size=14, tag=f"{self.name}_placeholder")

        with dpg.handler_registry(tag=f"{self.name}_handlers"):
            dpg.add_mouse_wheel_handler(callback=self._on_mouse_wheel)
            dpg.add_mouse_drag_handler(button=0, callback=self._on_left_drag)
            dpg.add_mouse_drag_handler(button=1, callback=self._on_right_drag)
            dpg.add_mouse_drag_handler(button=2, callback=self._on_middle_drag)
            dpg.add_mouse_release_handler(callback=self._on_mouse_release)
            dpg.add_mouse_double_click_handler(button=dpg.mvMouseButton_Left,
                                                callback=self._on_double_click)

    def _fit_to_window(self):
        if self.tex_w <= 0 or self.tex_h <= 0:
            return
        sx = self.width / self.tex_w
        sy = self.height / self.tex_h
        self.zoom = min(sx, sy)
        dw = self.tex_w * self.zoom
        dh = self.tex_h * self.zoom
        self.pan_x = (self.width - dw) / 2
        self.pan_y = (self.height - dh) / 2

    def _update_draw(self):
        if not dpg.does_item_exist(f"{self.name}_img"):
            return
        x0, y0 = self.pan_x, self.pan_y
        x1 = x0 + self.tex_w * self.zoom
        y1 = y0 + self.tex_h * self.zoom
        uv_max = (self.tex_w / MAX_TEX, self.tex_h / MAX_TEX)
        dpg.configure_item(f"{self.name}_img",
                           pmin=(x0, y0), pmax=(x1, y1),
                           uv_min=(0, 0), uv_max=uv_max)

    # ─── 鼠标事件 ────────────────────────────────────────────────────────────
    def _on_mouse_wheel(self, sender, app_data):
        if not self._is_mouse_over():
            return
        if self.camera_mode and self.camera:
            self.camera.zoom *= (1.15 if app_data > 0 else 1 / 1.15)
            self.camera.zoom = max(0.2, min(5.0, self.camera.zoom))
            if self._on_camera_change:
                self._fire_camera_change()
        else:
            pos = dpg.get_mouse_pos(local=False)
            factor = 1.15 if app_data > 0 else 1 / 1.15
            old_zoom = self.zoom
            self.zoom = max(0.05, min(50.0, self.zoom * factor))
            rx = (pos[0] - self.pan_x) / (self.tex_w * old_zoom) if old_zoom > 0 else 0.5
            ry = (pos[1] - self.pan_y) / (self.tex_h * old_zoom) if old_zoom > 0 else 0.5
            self.pan_x = pos[0] - rx * self.tex_w * self.zoom
            self.pan_y = pos[1] - ry * self.tex_h * self.zoom
            self._update_draw()

    def _on_left_drag(self, sender, app_data):
        if not self._is_mouse_over():
            return
        if self.camera_mode and self.camera:
            # 左键拖拽 = 平移相机
            self._start_drag(0)
            cur = dpg.get_mouse_pos(local=False)
            dx = cur[0] - self._drag_start[0]
            dy = cur[1] - self._drag_start[1]
            self.camera.pan_x = self._pan_start[0] + dx
            self.camera.pan_y = self._pan_start[1] + dy
            if self._on_camera_change:
                self._fire_camera_change()
        else:
            self._do_pan()

    def _on_middle_drag(self, sender, app_data):
        """中键拖拽 = 轨道旋转（Orbit）"""
        if not self._is_mouse_over():
            return
        if self.camera_mode and self.camera:
            self._start_drag(2)
            cur = dpg.get_mouse_pos(local=False)
            dx = cur[0] - self._drag_start[0]
            dy = cur[1] - self._drag_start[1]
            self.camera.yaw = self._camera_start.yaw + dx * 0.5
            self.camera.pitch = self._camera_start.pitch + dy * 0.5
            self.camera.pitch = max(-89, min(89, self.camera.pitch))
            if self._on_camera_change:
                self._fire_camera_change()
        else:
            self._do_pan()

    def _on_right_drag(self, sender, app_data):
        pass  # 保留给未来右键菜单

    def _start_drag(self, button):
        if not self._dragging:
            self._dragging = True
            self._drag_button = button
            self._drag_start = dpg.get_mouse_pos(local=False)
            self._pan_start = (self.camera.pan_x, self.camera.pan_y) if self.camera else (self.pan_x, self.pan_y)
            if self.camera:
                from gl_renderer import Camera
                self._camera_start = Camera()
                self._camera_start.yaw = self.camera.yaw
                self._camera_start.pitch = self.camera.pitch

    def _do_pan(self):
        if not self._dragging:
            self._start_drag(0)
        cur = dpg.get_mouse_pos(local=False)
        self.pan_x = self._pan_start[0] + cur[0] - self._drag_start[0]
        self.pan_y = self._pan_start[1] + cur[1] - self._drag_start[1]
        self._update_draw()

    def _on_mouse_release(self, sender, app_data):
        self._dragging = False
        self._drag_button = -1

    def _on_double_click(self, sender, app_data):
        if self._is_mouse_over():
            self.reset_view()

    def _is_mouse_over(self) -> bool:
        pos = dpg.get_mouse_pos(local=False)
        if not dpg.does_item_exist(f"{self.name}_drawlist"):
            return False
        rect = dpg.get_item_rect_min(f"{self.name}_drawlist")
        return (rect[0] <= pos[0] <= rect[0] + self.width and
                rect[1] <= pos[1] <= rect[1] + self.height)
