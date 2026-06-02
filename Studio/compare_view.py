"""
compare_view.py — 对比视图组件

实现左右分屏对比功能，支持：
  - 当前效果 vs 历史快照
  - 当前效果 vs 预设
  - 参考图 vs 渲染效果

Author: AutoToon Team
"""
from __future__ import annotations

import dearpygui.dearpygui as dpg
import numpy as np
import cv2
from typing import Optional, Callable
from enum import Enum


class CompareMode(Enum):
    """对比模式"""
    OFF = "off"              # 关闭对比
    SPLIT_H = "split_h"      # 水平分屏 (左右)
    SPLIT_V = "split_v"      # 垂直分屏 (上下)
    REFERENCE = "reference"  # 与参考图对比
    HISTORY = "history"      # 与历史快照对比
    PRESET = "preset"        # 与预设对比


class CompareView:
    """
    对比视图管理器

    Example:
        >>> compare = CompareView()
        >>> compare.set_mode(CompareMode.SPLIT_H)
        >>> compare.set_left_image(current_img)
        >>> compare.set_right_image(history_img)
    """

    def __init__(
        self,
        name: str = "compare",
        width: int = 380,
        height: int = 380,
        parent: int = 0
    ):
        """
        初始化对比视图

        Args:
            name: 组件名称
            width: 宽度
            height: 高度
            parent: 父容器 ID
        """
        self.name = name
        self.width = width
        self.height = height
        self._parent = parent
        self._mode = CompareMode.OFF

        # 左右图像
        self._left_img: Optional[np.ndarray] = None
        self._right_img: Optional[np.ndarray] = None
        self._left_label = "Current"
        self._right_label = "Previous"

        # 纹理标签
        self._left_tex_tag = f"{name}_left_tex"
        self._right_tex_tag = f"{name}_right_tex"

        # 分割线位置 (0.0 - 1.0)
        self._split_pos = 0.5
        self._dragging_split = False

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        # 创建纹理
        with dpg.texture_registry():
            # 左侧纹理
            dpg.add_dynamic_texture(1, 1, [0.15, 0.15, 0.15, 1.0], tag=self._left_tex_tag)
            # 右侧纹理
            dpg.add_dynamic_texture(1, 1, [0.15, 0.15, 0.15, 1.0], tag=self._right_tex_tag)

        # 主容器
        with dpg.group(parent=self._parent, tag=f"{self.name}_group"):
            # 控制栏
            with dpg.group(horizontal=True, tag=f"{self.name}_controls"):
                dpg.add_text("Compare:", color=(150, 150, 150))
                dpg.add_button(label="Off", tag=f"{self.name}_btn_off",
                              callback=lambda: self.set_mode(CompareMode.OFF), width=40)
                dpg.add_button(label="Split", tag=f"{self.name}_btn_split",
                              callback=lambda: self.set_mode(CompareMode.SPLIT_H), width=45)
                dpg.add_button(label="History", tag=f"{self.name}_btn_history",
                              callback=lambda: self.set_mode(CompareMode.HISTORY), width=55)
                dpg.add_text("", tag=f"{self.name}_status", color=(100, 150, 255))

            # 对比视图区域
            with dpg.drawlist(width=self.width, height=self.height, tag=f"{self.name}_drawlist"):
                # 背景
                dpg.draw_rectangle((0, 0), (self.width, self.height),
                                   fill=(25, 25, 25), tag=f"{self.name}_bg")

                # 左侧图像
                dpg.draw_image(self._left_tex_tag, (0, 0), (self.width // 2, self.height),
                               uv_min=(0, 0), uv_max=(1, 1), tag=f"{self.name}_left_img")

                # 右侧图像
                dpg.draw_image(self._right_tex_tag, (self.width // 2, 0), (self.width, self.height),
                               uv_min=(0, 0), uv_max=(1, 1), tag=f"{self.name}_right_img")

                # 分割线
                split_x = self.width // 2
                dpg.draw_line((split_x, 0), (split_x, self.height),
                              color=(100, 150, 255), thickness=2, tag=f"{self.name}_split_line")

                # 标签
                dpg.draw_text((5, 5), self._left_label, color=(200, 200, 200),
                              size=14, tag=f"{self.name}_left_label")
                dpg.draw_text((split_x + 5, 5), self._right_label, color=(200, 200, 200),
                              size=14, tag=f"{self.name}_right_label")

            # 占位提示
            dpg.add_text("Select a comparison mode above",
                        tag=f"{self.name}_placeholder", color=(80, 80, 80), show=True)

        # 初始隐藏对比视图
        dpg.configure_item(f"{self.name}_drawlist", show=False)

    def set_mode(self, mode: CompareMode) -> None:
        """
        设置对比模式

        Args:
            mode: 对比模式
        """
        self._mode = mode

        # 更新按钮状态
        dpg.configure_item(f"{self.name}_btn_off",
                          color=(100, 150, 255) if mode == CompareMode.OFF else (200, 200, 200))
        dpg.configure_item(f"{self.name}_btn_split",
                          color=(100, 150, 255) if mode == CompareMode.SPLIT_H else (200, 200, 200))
        dpg.configure_item(f"{self.name}_btn_history",
                          color=(100, 150, 255) if mode == CompareMode.HISTORY else (200, 200, 200))

        # 显示/隐藏对比视图
        show_compare = mode != CompareMode.OFF
        dpg.configure_item(f"{self.name}_drawlist", show=show_compare)
        dpg.configure_item(f"{self.name}_placeholder", show=not show_compare)

        # 更新状态文本
        mode_names = {
            CompareMode.OFF: "",
            CompareMode.SPLIT_H: "Split View",
            CompareMode.SPLIT_V: "Vertical Split",
            CompareMode.REFERENCE: "vs Reference",
            CompareMode.HISTORY: "vs History",
            CompareMode.PRESET: "vs Preset",
        }
        dpg.set_value(f"{self.name}_status", mode_names.get(mode, ""))

    def get_mode(self) -> CompareMode:
        """获取当前对比模式"""
        return self._mode

    def set_left_image(self, img: np.ndarray, label: str = "Current") -> None:
        """
        设置左侧图像

        Args:
            img: BGR 图像
            label: 标签文本
        """
        if img is None or img.size == 0:
            return

        self._left_img = img
        self._left_label = label
        self._update_texture(self._left_tex_tag, img)
        self._update_labels()

    def set_right_image(self, img: np.ndarray, label: str = "Previous") -> None:
        """
        设置右侧图像

        Args:
            img: BGR 图像
            label: 标签文本
        """
        if img is None or img.size == 0:
            return

        self._right_img = img
        self._right_label = label
        self._update_texture(self._right_tex_tag, img)
        self._update_labels()

    def _update_texture(self, tag: str, img: np.ndarray) -> None:
        """更新纹理"""
        if not dpg.does_item_exist(tag):
            return

        h, w = img.shape[:2]

        # 限制最大尺寸
        max_size = 512
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)),
                            interpolation=cv2.INTER_AREA)
            h, w = img.shape[:2]

        # BGR → RGBA
        rgba = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
                            cv2.COLOR_RGB2RGBA).astype(np.float32) / 255.0

        # 删除旧纹理，创建新纹理
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        with dpg.texture_registry():
            dpg.add_dynamic_texture(w, h, rgba.ravel().tolist(), tag=tag)

    def _update_labels(self) -> None:
        """更新标签显示"""
        if dpg.does_item_exist(f"{self.name}_left_label"):
            dpg.configure_item(f"{self.name}_left_label", text=self._left_label)
        if dpg.does_item_exist(f"{self.name}_right_label"):
            # 计算右侧标签位置
            split_x = int(self.width * self._split_pos)
            dpg.configure_item(f"{self.name}_right_label",
                              text=self._right_label, pos=(split_x + 5, 5))

    def set_split_position(self, pos: float) -> None:
        """
        设置分割线位置

        Args:
            pos: 位置 (0.0 - 1.0)
        """
        self._split_pos = max(0.1, min(0.9, pos))
        split_x = int(self.width * self._split_pos)

        # 更新分割线
        if dpg.does_item_exist(f"{self.name}_split_line"):
            dpg.configure_item(f"{self.name}_split_line",
                              p1=(split_x, 0), p2=(split_x, self.height))

        # 更新图像区域
        if dpg.does_item_exist(f"{self.name}_left_img"):
            dpg.configure_item(f"{self.name}_left_img", pmax=(split_x, self.height))
        if dpg.does_item_exist(f"{self.name}_right_img"):
            dpg.configure_item(f"{self.name}_right_img",
                              pmin=(split_x, 0), pmax=(self.width, self.height))

        self._update_labels()

    def resize(self, width: int, height: int) -> None:
        """
        调整大小

        Args:
            width: 新宽度
            height: 新高度
        """
        self.width = width
        self.height = height

        if dpg.does_item_exist(f"{self.name}_drawlist"):
            dpg.configure_item(f"{self.name}_drawlist", width=width, height=height)

        # 重新计算分割线位置
        self.set_split_position(self._split_pos)

    def is_active(self) -> bool:
        """是否处于对比模式"""
        return self._mode != CompareMode.OFF


def create_compare_panel(
    name: str = "compare_panel",
    width: int = 380,
    height: int = 200,
    parent: int = 0,
    on_snapshot_select: Optional[Callable] = None
) -> tuple:
    """
    创建完整的对比面板（包含快照选择器）

    Args:
        name: 组件名称
        width: 宽度
        height: 高度
        parent: 父容器
        on_snapshot_select: 快照选择回调

    Returns:
        (CompareView, snapshot_list_tag)
    """
    # 快照列表
    with dpg.group(parent=parent, tag=f"{name}_snapshot_group"):
        dpg.add_text("Select snapshot to compare:", color=(150, 150, 150))
        dpg.add_combo(tag=f"{name}_snapshot_combo", width=width - 20,
                     callback=lambda s, a: on_snapshot_select and on_snapshot_select(a) if a else None)

    # 对比视图
    compare = CompareView(f"{name}_view", width, height, parent)

    return compare, f"{name}_snapshot_combo"


def update_snapshot_list(combo_tag: str, snapshots: list) -> None:
    """
    更新快照列表

    Args:
        combo_tag: 下拉框标签
        snapshots: 快照列表 [(label, id), ...]
    """
    if not dpg.does_item_exist(combo_tag):
        return

    # 清空并重新填充
    dpg.configure_item(combo_tag, items=[s[0] for s in snapshots])
