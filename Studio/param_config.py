"""
param_config.py — 参数映射配置

定义 UI 参数到渲染参数的映射关系，确保效果变化明显且直观。
所有参数都有详细的文档说明和 UE5 映射信息。

Author: AutoToon Team
"""
from dataclasses import dataclass
from typing import Tuple, Callable


@dataclass
class ParamDefinition:
    """参数定义"""
    name: str                    # 内部名称
    label_zh: str                # 中文标签
    label_en: str                # 英文标签
    ui_min: float                # UI 滑块最小值
    ui_max: float                # UI 滑块最大值
    ui_default: float            # UI 默认值
    ui_step: float               # UI 步进
    render_min: float            # 渲染最小值
    render_max: float            # 渲染最大值
    tooltip_zh: str              # 中文提示
    tooltip_en: str              # 英文提示
    ue_param: str                # 对应的 UE5 参数名
    ue_scale: float = 1.0        # UE5 缩放因子
    ue_offset: float = 0.0       # UE5 偏移


# =============================================================================
# 参数定义表
# =============================================================================

PARAM_DEFINITIONS = {
    # 阴影色 RGB
    "shadow_r": ParamDefinition(
        name="shadow_r",
        label_zh="阴影红",
        label_en="Shadow R",
        ui_min=0.0, ui_max=1.0, ui_default=0.3, ui_step=0.01,
        render_min=0.15, render_max=0.75,  # 映射到更明显的范围
        tooltip_zh="阴影区域的红色分量\n• 0 = 深黑阴影\n• 0.5 = 中性灰\n• 1 = 亮红阴影\n\nUE5 对应: BaseColor Shadow Mix R",
        tooltip_en="Red component of shadow color\n• 0 = Deep black shadow\n• 0.5 = Neutral gray\n• 1 = Bright red shadow\n\nUE5: BaseColor Shadow Mix R",
        ue_param="ShadowColorR",
    ),
    "shadow_g": ParamDefinition(
        name="shadow_g",
        label_zh="阴影绿",
        label_en="Shadow G",
        ui_min=0.0, ui_max=1.0, ui_default=0.3, ui_step=0.01,
        render_min=0.15, render_max=0.75,
        tooltip_zh="阴影区域的绿色分量\n• 0 = 深黑阴影\n• 0.5 = 中性灰\n• 1 = 亮绿阴影\n\nUE5 对应: BaseColor Shadow Mix G",
        tooltip_en="Green component of shadow color\n• 0 = Deep black shadow\n• 0.5 = Neutral gray\n• 1 = Bright green shadow\n\nUE5: BaseColor Shadow Mix G",
        ue_param="ShadowColorG",
    ),
    "shadow_b": ParamDefinition(
        name="shadow_b",
        label_zh="阴影蓝",
        label_en="Shadow B",
        ui_min=0.0, ui_max=1.0, ui_default=0.3, ui_step=0.01,
        render_min=0.15, render_max=0.75,
        tooltip_zh="阴影区域的蓝色分量\n• 0 = 深黑阴影\n• 0.5 = 中性灰\n• 1 = 亮蓝阴影\n\nUE5 对应: BaseColor Shadow Mix B",
        tooltip_en="Blue component of shadow color\n• 0 = Deep black shadow\n• 0.5 = Neutral gray\n• 1 = Bright blue shadow\n\nUE5: BaseColor Shadow Mix B",
        ue_param="ShadowColorB",
    ),

    # 高光强度
    "specular": ParamDefinition(
        name="specular",
        label_zh="高光强度",
        label_en="Specular",
        ui_min=0.0, ui_max=1.0, ui_default=0.5, ui_step=0.01,
        render_min=0.0, render_max=1.0,
        tooltip_zh="高光强度控制\n• 0 = 无高光 (哑光)\n• 0.5 = 柔和高光\n• 1 = 强烈高光\n\nUE5 对应: Specular Intensity",
        tooltip_en="Specular intensity control\n• 0 = No specular (matte)\n• 0.5 = Soft highlight\n• 1 = Strong highlight\n\nUE5: Specular Intensity",
        ue_param="SpecularIntensity",
    ),

    # 边缘光宽度
    "rim_light": ParamDefinition(
        name="rim_light",
        label_zh="边缘光",
        label_en="Rim Light",
        ui_min=0.0, ui_max=1.0, ui_default=0.5, ui_step=0.01,
        render_min=0.0, render_max=1.0,
        tooltip_zh="边缘光 (Rim Light) 强度\n• 0 = 无边缘光\n• 0.5 = 柔和轮廓光\n• 1 = 强烈轮廓光\n\nUE5 对应: Rim Intensity",
        tooltip_en="Rim light intensity\n• 0 = No rim light\n• 0.5 = Soft outline glow\n• 1 = Strong outline glow\n\nUE5: Rim Intensity",
        ue_param="RimIntensity",
    ),

    # 描边宽度
    "outline_width": ParamDefinition(
        name="outline_width",
        label_zh="描边宽度",
        label_en="Outline",
        ui_min=0.5, ui_max=3.0, ui_default=1.0, ui_step=0.05,
        render_min=0.3, render_max=1.8,  # 映射到更明显的范围
        tooltip_zh="描边粗细程度\n• 0.5 = 细线描边\n• 1.0 = 标准描边\n• 2.0 = 粗线描边\n• 3.0 = 很粗描边\n\nUE5 对应: Outline Width",
        tooltip_en="Outline thickness\n• 0.5 = Thin outline\n• 1.0 = Standard outline\n• 2.0 = Thick outline\n• 3.0 = Very thick outline\n\nUE5: Outline Width",
        ue_param="OutlineWidth",
        ue_scale=2.5,
        ue_offset=0.5,
    ),
}


# =============================================================================
# 映射函数
# =============================================================================

def map_param(name: str, ui_value: float) -> float:
    """
    将 UI 值映射到渲染值

    Args:
        name: 参数名称
        ui_value: UI 滑块值

    Returns:
        渲染器使用的值
    """
    if name not in PARAM_DEFINITIONS:
        return ui_value

    p = PARAM_DEFINITIONS[name]

    # 线性映射: ui_value ∈ [ui_min, ui_max] → render_value ∈ [render_min, render_max]
    t = (ui_value - p.ui_min) / (p.ui_max - p.ui_min)
    return p.render_min + t * (p.render_max - p.render_min)


def map_to_ue(name: str, ui_value: float) -> float:
    """
    将 UI 值映射到 UE5 参数值

    Args:
        name: 参数名称
        ui_value: UI 滑块值

    Returns:
        UE5 使用的值
    """
    if name not in PARAM_DEFINITIONS:
        return ui_value

    p = PARAM_DEFINITIONS[name]
    return ui_value * p.ue_scale + p.ue_offset


def get_tooltip(name: str, lang: str = "zh") -> str:
    """
    获取参数提示文本

    Args:
        name: 参数名称
        lang: 语言 ("zh" 或 "en")

    Returns:
        提示文本
    """
    if name not in PARAM_DEFINITIONS:
        return ""

    p = PARAM_DEFINITIONS[name]
    return p.tooltip_zh if lang == "zh" else p.tooltip_en


def get_label(name: str, lang: str = "zh") -> str:
    """
    获取参数标签

    Args:
        name: 参数名称
        lang: 语言

    Returns:
        标签文本
    """
    if name not in PARAM_DEFINITIONS:
        return name

    p = PARAM_DEFINITIONS[name]
    return p.label_zh if lang == "zh" else p.label_en


def get_all_params() -> list:
    """获取所有参数名称列表"""
    return list(PARAM_DEFINITIONS.keys())


def get_defaults() -> dict:
    """获取所有参数默认值"""
    return {name: p.ui_default for name, p in PARAM_DEFINITIONS.items()}


# =============================================================================
# 批量映射
# =============================================================================

def map_all_params(ui_values: dict) -> dict:
    """
    批量映射所有参数

    Args:
        ui_values: {name: value} 字典

    Returns:
        {name: render_value} 字典
    """
    return {name: map_param(name, value) for name, value in ui_values.items()}


def map_all_to_ue(ui_values: dict) -> dict:
    """
    批量映射到 UE5 参数

    Args:
        ui_values: {name: value} 字典

    Returns:
        {ue_param: ue_value} 字典
    """
    result = {}
    for name, value in ui_values.items():
        if name in PARAM_DEFINITIONS:
            p = PARAM_DEFINITIONS[name]
            result[p.ue_param] = map_to_ue(name, value)
    return result
