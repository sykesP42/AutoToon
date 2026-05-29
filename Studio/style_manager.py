"""
style_manager.py — 风格预设管理
.save / .load / .list 风格预设文件（JSON 格式）。
"""
import json
import os
from pathlib import Path
from datetime import datetime


# 默认预设目录
DEFAULT_PRESET_DIR = Path(__file__).parent.parent / "presets"


class StyleManager:
    """风格预设管理器"""

    def __init__(self, preset_dir: str = None):
        self.preset_dir = Path(preset_dir) if preset_dir else DEFAULT_PRESET_DIR
        self.preset_dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, params: list[float], description: str = "") -> str:
        """
        保存风格预设为 .style JSON 文件。

        Args:
            name: 预设名称（不含扩展名）
            params: 6 个参数 [shadow_r, shadow_g, shadow_b, specular, rim_light_width, width_scale]
            description: 可选描述

        Returns:
            保存的文件路径
        """
        if len(params) != 6:
            raise ValueError(f"参数数量应为 6，实际为 {len(params)}")

        safe_name = "".join(c for c in name if c.isalnum() or c in "-_ ").strip()
        if not safe_name:
            safe_name = "unnamed"

        file_path = self.preset_dir / f"{safe_name}.style"

        data = {
            "name": name,
            "description": description,
            "params": {
                "ShadowR": round(params[0], 4),
                "ShadowG": round(params[1], 4),
                "ShadowB": round(params[2], 4),
                "Specular": round(params[3], 4),
                "RimLightWidth": round(params[4], 4),
                "WidthScale": round(params[5], 4),
            },
            "created_at": datetime.now().isoformat(),
            "version": "1.0",
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return str(file_path)

    def load(self, file_path: str) -> dict:
        """
        加载 .style 预设文件。

        Returns:
            {
                "name": "宫崎骏风格",
                "params": [0.2, 0.1, 0.3, 0.8, 0.5, 1.5],
                "description": "..."
            }
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        p = data["params"]
        params = [
            p["ShadowR"], p["ShadowG"], p["ShadowB"],
            p["Specular"], p["RimLightWidth"], p["WidthScale"],
        ]

        return {
            "name": data.get("name", Path(file_path).stem),
            "params": params,
            "description": data.get("description", ""),
            "file_path": file_path,
        }

    def list_presets(self) -> list[dict]:
        """
        列出所有可用预设。

        Returns:
            [{"name": "...", "file_path": "...", "description": "..."}, ...]
        """
        presets = []
        for f in sorted(self.preset_dir.glob("*.style")):
            try:
                data = self.load(str(f))
                presets.append({
                    "name": data["name"],
                    "file_path": str(f),
                    "description": data["description"],
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return presets

    def delete(self, file_path: str) -> bool:
        """删除预设文件"""
        try:
            os.remove(file_path)
            return True
        except OSError:
            return False
