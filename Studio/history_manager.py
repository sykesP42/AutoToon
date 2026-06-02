"""
history_manager.py — 操作历史管理器

支持参数快照保存、恢复、对比。用于实现撤销/重做和 A/B 对比功能。

Author: AutoToon Team
"""
from __future__ import annotations

import time
import copy
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import numpy as np


@dataclass
class Snapshot:
    """参数快照"""
    params: Dict[str, float]           # 参数值
    preview_image: Optional[np.ndarray] = None  # 预览图像
    shape_name: str = "sphere"         # 形状名称
    timestamp: float = field(default_factory=time.time)
    label: str = ""                    # 用户标签

    def get_age_seconds(self) -> float:
        """获取快照年龄（秒）"""
        return time.time() - self.timestamp

    def get_age_formatted(self) -> str:
        """获取格式化的年龄"""
        age = self.get_age_seconds()
        if age < 60:
            return f"{int(age)}s"
        elif age < 3600:
            return f"{int(age / 60)}m"
        else:
            return f"{int(age / 3600)}h"


class HistoryManager:
    """
    操作历史管理器

    功能:
        - 保存参数快照
        - 撤销/重做
        - 历史浏览
        - 快照对比

    Example:
        >>> history = HistoryManager(max_snapshots=20)
        >>> history.snap(params, preview_img, "Initial")
        >>> # 修改参数后
        >>> history.snap(params, preview_img, "After adjust")
        >>> # 撤销
        >>> prev = history.undo()
    """

    def __init__(self, max_snapshots: int = 20):
        """
        初始化历史管理器

        Args:
            max_snapshots: 最大快照数量
        """
        self._snapshots: List[Snapshot] = []
        self._max_snapshots = max_snapshots
        self._current_index = -1  # 当前位置指针
        self._undo_stack: List[Snapshot] = []  # 撤销栈

    def snap(
        self,
        params: Dict[str, float],
        preview_image: Optional[np.ndarray] = None,
        shape_name: str = "sphere",
        label: str = ""
    ) -> Snapshot:
        """
        保存快照

        Args:
            params: 参数字典
            preview_image: 预览图像 (可选)
            shape_name: 形状名称
            label: 快照标签

        Returns:
            创建的快照对象
        """
        # 深拷贝参数，防止外部修改
        params_copy = copy.deepcopy(params)

        # 如果有图像，也深拷贝
        img_copy = preview_image.copy() if preview_image is not None else None

        snapshot = Snapshot(
            params=params_copy,
            preview_image=img_copy,
            shape_name=shape_name,
            label=label or f"Snap #{len(self._snapshots) + 1}"
        )

        # 添加到撤销栈
        self._undo_stack.append(snapshot)

        # 添加到历史列表
        self._snapshots.append(snapshot)
        self._current_index = len(self._snapshots) - 1

        # 超出限制时删除最旧的
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots.pop(0)
            self._current_index -= 1

        return snapshot

    def undo(self) -> Optional[Snapshot]:
        """
        撤销到上一个快照

        Returns:
            上一个快照，或 None 如果无法撤销
        """
        if len(self._undo_stack) < 2:
            return None

        # 弹出当前状态
        current = self._undo_stack.pop()

        # 返回上一个状态
        if self._undo_stack:
            self._current_index = len(self._snapshots) - 2
            return self._undo_stack[-1]

        return None

    def redo(self) -> Optional[Snapshot]:
        """
        重做到下一个快照

        Returns:
            下一个快照，或 None 如果无法重做
        """
        if self._current_index >= len(self._snapshots) - 1:
            return None

        self._current_index += 1
        return self._snapshots[self._current_index]

    def get_current(self) -> Optional[Snapshot]:
        """获取当前快照"""
        if self._current_index < 0 or self._current_index >= len(self._snapshots):
            return None
        return self._snapshots[self._current_index]

    def get_prev(self, steps: int = 1) -> Optional[Snapshot]:
        """
        获取前 N 步快照

        Args:
            steps: 步数

        Returns:
            快照对象
        """
        idx = self._current_index - steps
        if idx < 0:
            return None
        return self._snapshots[idx]

    def get_next(self, steps: int = 1) -> Optional[Snapshot]:
        """
        获取后 N 步快照

        Args:
            steps: 步数

        Returns:
            快照对象
        """
        idx = self._current_index + steps
        if idx >= len(self._snapshots):
            return None
        return self._snapshots[idx]

    def get_all(self) -> List[Snapshot]:
        """获取所有快照"""
        return self._snapshots.copy()

    def get_count(self) -> int:
        """获取快照数量"""
        return len(self._snapshots)

    def can_undo(self) -> bool:
        """是否可以撤销"""
        return len(self._undo_stack) >= 2

    def can_redo(self) -> bool:
        """是否可以重做"""
        return self._current_index < len(self._snapshots) - 1

    def clear(self) -> None:
        """清除所有历史"""
        self._snapshots.clear()
        self._undo_stack.clear()
        self._current_index = -1

    def get_labels(self) -> List[str]:
        """获取所有快照标签"""
        return [s.label for s in self._snapshots]

    def find_by_label(self, label: str) -> Optional[Snapshot]:
        """
        按标签查找快照

        Args:
            label: 标签文本

        Returns:
            快照对象
        """
        for s in self._snapshots:
            if s.label == label:
                return s
        return None

    def get_recent(self, count: int = 5) -> List[Snapshot]:
        """
        获取最近的 N 个快照

        Args:
            count: 数量

        Returns:
            快照列表
        """
        start = max(0, len(self._snapshots) - count)
        return self._snapshots[start:]

    def compare(self, idx_a: int, idx_b: int) -> Dict[str, Any]:
        """
        对比两个快照

        Args:
            idx_a: 快照 A 索引
            idx_b: 快照 B 索引

        Returns:
            对比结果字典
        """
        if idx_a < 0 or idx_a >= len(self._snapshots):
            return {}
        if idx_b < 0 or idx_b >= len(self._snapshots):
            return {}

        snap_a = self._snapshots[idx_a]
        snap_b = self._snapshots[idx_b]

        diff = {}
        for key in snap_a.params:
            if key in snap_b.params:
                diff[key] = {
                    "a": snap_a.params[key],
                    "b": snap_b.params[key],
                    "delta": snap_b.params[key] - snap_a.params[key]
                }

        return {
            "snapshot_a": snap_a,
            "snapshot_b": snap_b,
            "param_diff": diff,
            "time_diff": snap_b.timestamp - snap_a.timestamp
        }


# 全局历史管理器实例
_global_history: Optional[HistoryManager] = None


def get_history() -> HistoryManager:
    """获取全局历史管理器"""
    if _global_history is None:
        _global_history = HistoryManager()
    return _global_history


def reset_history() -> None:
    """重置全局历史管理器"""
    global _global_history
    _global_history = HistoryManager()