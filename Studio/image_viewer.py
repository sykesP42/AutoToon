"""
image_viewer.py — 图片查看器组件
两种模式：
  模式 1（默认）：2D 图片缩放/平移
  模式 2（camera_mode）：3D 相机轨道旋转（仿 Blender）

额外功能：
  - 涂鸦遮罩：在图片上绘制重点/忽略区域

性能优化：
  - 按需创建纹理（不预分配固定大小）
  - 渲染节流防止过度重绘
"""
import time
import dearpygui.dearpygui as dpg
import numpy as np
import cv2
from gl_renderer import Camera

# 渲染节流间隔（秒）
RENDER_THROTTLE = 0.033  # ~30fps


class ImageViewer:
    def __init__(self, name: str, width: int = 380, height: int = 380,
                 parent: int = 0, camera_mode: bool = False, enable_brush: bool = False):
        self.name = name
        self.width = width
        self.height = height
        self.camera_mode = camera_mode
        self.camera = Camera() if camera_mode else None
        self._parent = parent
        self.enable_brush = enable_brush

        self.tex_tag = f"{name}_tex"
        self.tex_w = 1
        self.tex_h = 1
        self._has_image = False
        self._tex_created = False

        # 2D 模式的缩放/平移
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

        self._dragging = False
        self._drag_button = -1
        self._drag_start = (0, 0)
        self._pan_start = (0, 0)
        self._camera_start = None

        # 涂鸦相关
        self._brush_mode = 0  # 0=禁用, 1=绿色(重点), 2=红色(忽略)
        self._brush_size = 20
        self._mask: Optional[np.ndarray] = None  # 涂鸦遮罩
        self._original_image: Optional[np.ndarray] = None  # 原始图像

        # 占位纹理（1x1 像素，几乎不占内存）
        with dpg.texture_registry():
            dpg.add_dynamic_texture(1, 1, [0.15, 0.15, 0.15, 1.0], tag=self.tex_tag)

        with dpg.group(parent=parent, tag=f"{name}_group"):
            with dpg.drawlist(width=width, height=height, tag=f"{name}_drawlist"):
                dpg.draw_rectangle((0, 0), (width, height), fill=(25, 25, 25), tag=f"{name}_bg")
                dpg.draw_image(self.tex_tag, (0, 0), (width, height),
                               uv_min=(0, 0), uv_max=(1, 1), tag=f"{name}_img")
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
        """设置图像（按需创建合适大小的纹理）"""
        if img_bgr is None or img_bgr.size == 0:
            return

        h, w = img_bgr.shape[:2]
        # 限制最大尺寸（防止内存爆炸）
        max_size = 1024
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)),
                                  interpolation=cv2.INTER_AREA)
            h, w = img_bgr.shape[:2]

        self.tex_w, self.tex_h = w, h
        self._has_image = True

        # 保存原始图像（用于涂鸦）
        self._original_image = img_bgr.copy()

        # 初始化涂鸦遮罩
        if self.enable_brush:
            self._mask = np.zeros((h, w), dtype=np.uint8)

        # BGR → RGBA float32
        rgba = cv2.cvtColor(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB),
                            cv2.COLOR_RGB2RGBA).astype(np.float32) / 255.0

        # 直接设置纹理值（假设纹理已存在）
        if dpg.does_item_exist(self.tex_tag):
            dpg.set_value(self.tex_tag, rgba.ravel().tolist())
        else:
            # 纹理不存在，创建新的
            with dpg.texture_registry():
                dpg.add_dynamic_texture(w, h, rgba.ravel().tolist(), tag=self.tex_tag)
            self._tex_created = True

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
        """重建 drawlist 到新尺寸"""
        self.width = new_w
        self.height = new_h
        old_group = f"{self.name}_group"
        old_handlers = f"{self.name}_handlers"
        if dpg.does_item_exist(old_group):
            dpg.delete_item(old_group)
        if dpg.does_item_exist(old_handlers):
            dpg.delete_item(old_handlers)

        with dpg.group(parent=self._parent, tag=f"{self.name}_group"):
            with dpg.drawlist(width=new_w, height=new_h, tag=f"{self.name}_drawlist"):
                dpg.draw_rectangle((0, 0), (new_w, new_h), fill=(25, 25, 25), tag=f"{self.name}_bg")
                dpg.draw_image(self.tex_tag, (0, 0), (new_w, new_h),
                               uv_min=(0, 0), uv_max=(1, 1), tag=f"{self.name}_img")
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
        dpg.configure_item(f"{self.name}_img",
                           pmin=(x0, y0), pmax=(x1, y1),
                           uv_min=(0, 0), uv_max=(1, 1))

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
            self._start_drag(0)
            cur = dpg.get_mouse_pos(local=False)
            dx = cur[0] - self._drag_start[0]
            dy = cur[1] - self._drag_start[1]
            self.camera.pan_x = self._pan_start[0] + dx
            self.camera.pan_y = self._pan_start[1] + dy
            if self._on_camera_change:
                self._fire_camera_change()
        else:
            # 涂鸦模式
            if self._brush_mode > 0 and self._mask is not None and self.enable_brush:
                cur = dpg.get_mouse_pos(local=False)
                # 计算在图像上的坐标
                img_x = int((cur[0] - self.pan_x) / self.zoom)
                img_y = int((cur[1] - self.pan_y) / self.zoom)
                if 0 <= img_x < self.tex_w and 0 <= img_y < self.tex_h:
                    self._draw_brush(img_x, img_y)
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
        pass

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

    # ─── 涂鸦功能 ────────────────────────────────────────────────────────────
    def set_brush_mode(self, mode: int):
        """设置涂鸦模式: 0=禁用, 1=绿色(重点), 2=红色(忽略)"""
        self._brush_mode = mode

    def set_brush_size(self, size: int):
        """设置画笔大小"""
        self._brush_size = max(5, min(100, size))

    def clear_mask(self):
        """清除涂鸦遮罩"""
        self._mask = None
        if self._original_image is not None:
            self.set_image(self._original_image, fit=False)

    def get_mask(self) -> Optional[np.ndarray]:
        """获取涂鸦遮罩（与原图同尺寸）"""
        return self._mask

    def _draw_brush(self, x: int, y: int):
        """在指定位置绘制画笔"""
        if self._mask is None or self._brush_mode == 0:
            return

        # 在遮罩上绘制
        cv2.circle(self._mask, (x, y), self._brush_size, self._brush_mode, -1)

        # 更新显示
        self._update_display_with_mask()

    def _update_display_with_mask(self):
        """更新显示图像（叠加涂鸦）"""
        if self._original_image is None or self._mask is None:
            return

        # 复制原图
        display = self._original_image.copy()

        # 缩放遮罩到显示尺寸
        if self._mask.shape[:2] != display.shape[:2]:
            mask_resized = cv2.resize(self._mask, (display.shape[1], display.shape[0]),
                                      interpolation=cv2.INTER_NEAREST)
        else:
            mask_resized = self._mask

        # 绿色 = 重点区域 (值=1)
        green = (mask_resized == 1)
        display[green] = (display[green] * 0.6 + np.array([100, 255, 0]) * 0.4).astype(np.uint8)

        # 红色 = 忽略区域 (值=2)
        red = (mask_resized == 2)
        display[red] = (display[red] * 0.6 + np.array([0, 50, 255]) * 0.4).astype(np.uint8)

        # 更新纹理
        rgba = cv2.cvtColor(cv2.cvtColor(display, cv2.COLOR_BGR2RGB),
                            cv2.COLOR_RGB2RGBA).astype(np.float32) / 255.0
        if dpg.does_item_exist(self.tex_tag):
            dpg.set_value(self.tex_tag, rgba.ravel().tolist())