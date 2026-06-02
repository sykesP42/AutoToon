"""
i18n.py — 中英双语国际化模块
用法: from i18n import t, set_lang, get_lang
      t("btn_upload")  → "上传图片" 或 "Upload Image"
"""
import json
import os
from pathlib import Path

# ─── 翻译字典 ────────────────────────────────────────────────────────────────────
TRANSLATIONS = {
    "zh": {
        # 视窗
        "window_title": "AutoToon Studio",

        # 左栏
        "ref_image": "参考图",
        "btn_upload": "上传图片",
        "file_filter": "图片{.png,.jpg,.jpeg,.bmp}",
        "btn_reset": "重置",
        "btn_brush": "涂鸦",
        "brush_focus": "重点",
        "brush_ignore": "忽略",
        "brush_clear": "清除",
        "brush_size": "画笔大小",

        # 中栏
        "param_adjust": "参数调节",
        "label_shadow_r": "阴影红",
        "label_shadow_g": "阴影绿",
        "label_shadow_b": "阴影蓝",
        "label_specular": "高光强度",
        "label_rim_light": "边缘光",
        "label_outline_width": "描边宽度",
        "live_preview": "实时预览",
        "shape_select": "形状选择",
        "shape_sphere": "球体",
        "shape_cube": "立方体",
        "shape_cylinder": "圆柱体",
        "shape_torus": "圆环体",

        # 灯光
        "lighting": "灯光",
        "light_preset": "灯光预设",
        "light_default": "默认",
        "light_daylight": "日光",
        "light_studio": "室内",
        "light_night": "夜景",
        "light_anime": "动漫风",
        "light_ambient": "环境光",
        "light_diffuse": "漫反射",
        "light_specular_power": "高光锐度",
        "light_specular_intensity": "高光强度",
        "light_rim_intensity": "边缘光强度",
        "light_rim_power": "边缘光范围",

        # 右栏
        "actions": "操作",
        "btn_infer": "AI 分析",
        "btn_check_ue": "检查连接",
        "btn_send_ue": "发送到 UE5",
        "ue_status_ok": "已连接",
        "ue_status_fail": "未连接",
        "ue_status_init": "未检查",
        "style_presets": "风格预设",
        "hint_preset_name": "预设名称",
        "btn_save": "保存",
        "log_title": "日志",
        "btn_lang": "EN",

        # 导出/导入
        "export_json": "导出 JSON",
        "export_csv": "导出 CSV",
        "import_json": "导入 JSON",
        "export_tip": "导出当前参数到JSON文件\n包含材质和灯光参数",
        "csv_tip": "导出为MooaToon CSV格式\n可用于训练数据",
        "import_tip": "从JSON文件导入参数\n恢复之前保存的设置",

        # 批量处理
        "batch_process": "批量处理",
        "batch_import": "批量导入",
        "batch_export_json": "导出JSON",
        "batch_tip": "批量导入多张参考图\n自动提取参数并导出到CSV",
        "batch_progress": "处理进度",

        # 随机生成
        "random_generator": "随机生成",
        "random_tip": "随机生成参数用于探索\n或批量生成训练数据",
        "randomize": "随机参数",
        "generate_training": "生成训练数据",
        "training_count": "样本数量",

        # 历史管理
        "history": "历史",
        "history_tip": "点击恢复历史参数设置",
        "undo": "撤销",
        "redo": "重做",

        # 对比视图
        "compare": "对比",
        "compare_off": "关闭",
        "compare_history": "历史",
        "compare_reference": "参考图",
        "compare_tip": "与历史快照对比\n选择下方快照进行对比",

        # 关于
        "about": "关于",
        "about_title": "AutoToon Studio",
        "about_version": "版本",
        "about_author": "作者",
        "about_shortcuts": "快捷键",
        "about_desc": "AI 风格化实时预览工具\n基于 MooaToon 参数体系",

        # 提示信息
        "tip_shadow": "阴影区域颜色\n• 0 = 深色阴影\n• 1 = 亮色阴影",
        "tip_specular": "高光强度\n• 0 = 无高光\n• 1 = 强高光",
        "tip_rim": "边缘光强度\n• 0 = 无边缘光\n• 1 = 强边缘光",
        "tip_outline": "描边粗细\n• 0.5 = 细线\n• 3.0 = 粗线",

        # 日志 - 初始化
        "log_model_ok": "模型加载成功: {}",
        "log_model_fail": "模型加载失败: {}",
        "log_model_none": "ONNX 模型未指定，推理功能不可用（可稍后加载）",
        "log_ue_ready": "UE5 客户端就绪",
        "log_ue_fail": "UE5 客户端初始化失败: {}",
        "log_ready": "AutoToon Studio 就绪",

        # 日志 - 操作
        "log_img_loaded": "已加载图片: {}",
        "log_img_fail": "加载图片失败: {}",
        "log_no_image": "请先上传参考图",
        "log_ue_not_init": "UE5 客户端未初始化",
        "log_sent_ok": "已发送到 UE5: Shadow=({},{},{}) Spec={} Rim={} Width={}",
        "log_sent_fail": "发送失败: {}",
        "log_ue_ok": "UE5 连接正常",
        "log_ue_fail2": "UE5 未连接: {}",
        "log_no_preset_name": "请输入预设名称",
        "log_preset_saved": "预设已保存: {}",
        "log_preset_save_fail": "保存失败: {}",
        "log_preset_loaded": "已加载预设: {}",
        "log_preset_load_fail": "加载失败: {}",
        "log_infering": "正在推理...",
        "log_infer_ok": "推理完成: Shadow=({},{},{}) Spec={} Rim={} Width={}",
        "log_infer_fail": "推理失败: {}",
        "log_params_reset": "参数已重置为默认",
        "log_view_reset": "视图已重置",
        "log_fit_window": "适应窗口",
    },

    "en": {
        # Window
        "window_title": "AutoToon Studio",

        # Left panel
        "ref_image": "Reference Image",
        "btn_upload": "Upload Image",
        "file_filter": "Images{.png,.jpg,.jpeg,.bmp}",
        "btn_reset": "Reset",
        "btn_brush": "Brush",
        "brush_focus": "Focus",
        "brush_ignore": "Ignore",
        "brush_clear": "Clear",
        "brush_size": "Brush Size",

        # Center panel
        "param_adjust": "Parameter Adjustment",
        "label_shadow_r": "Shadow R",
        "label_shadow_g": "Shadow G",
        "label_shadow_b": "Shadow B",
        "label_specular": "Specular",
        "label_rim_light": "Rim Light",
        "label_outline_width": "Outline",
        "live_preview": "Live Preview",
        "shape_select": "Shape Select",
        "shape_sphere": "Sphere",
        "shape_cube": "Cube",
        "shape_cylinder": "Cylinder",
        "shape_torus": "Torus",

        # Lighting
        "lighting": "Lighting",
        "light_preset": "Light Preset",
        "light_default": "Default",
        "light_daylight": "Daylight",
        "light_studio": "Studio",
        "light_night": "Night",
        "light_anime": "Anime",
        "light_ambient": "Ambient",
        "light_diffuse": "Diffuse",
        "light_specular_power": "Specular Power",
        "light_specular_intensity": "Specular Intensity",
        "light_rim_intensity": "Rim Intensity",
        "light_rim_power": "Rim Power",

        # Right panel
        "actions": "Actions",
        "btn_infer": "AI Analyze",
        "btn_check_ue": "Check Connection",
        "btn_send_ue": "Send to UE5",
        "ue_status_ok": "Connected",
        "ue_status_fail": "Disconnected",
        "ue_status_init": "Not Checked",
        "style_presets": "Style Presets",
        "hint_preset_name": "Preset Name",
        "btn_save": "Save",
        "log_title": "Log",
        "btn_lang": "中",

        # Export/Import
        "export_json": "Export JSON",
        "export_csv": "Export CSV",
        "import_json": "Import JSON",
        "export_tip": "Export current params to JSON\nIncludes material and light params",
        "csv_tip": "Export as MooaToon CSV format\nCan be used for training data",
        "import_tip": "Import params from JSON file\nRestore previously saved settings",

        # Batch Process
        "batch_process": "Batch Process",
        "batch_import": "Batch Import",
        "batch_export_json": "Export JSON",
        "batch_tip": "Batch import multiple reference images\nAuto extract params and export to CSV",
        "batch_progress": "Progress",

        # Random Generator
        "random_generator": "Random Generator",
        "random_tip": "Random params for exploration\nOr batch generate training data",
        "randomize": "Randomize",
        "generate_training": "Generate Training",
        "training_count": "Count",

        # History
        "history": "History",
        "history_tip": "Click to restore parameter settings",
        "undo": "Undo",
        "redo": "Redo",

        # Compare View
        "compare": "Compare",
        "compare_off": "Off",
        "compare_history": "History",
        "compare_reference": "Reference",
        "compare_tip": "Compare with history snapshot\nSelect snapshot below to compare",

        # About
        "about": "About",
        "about_title": "AutoToon Studio",
        "about_version": "Version",
        "about_author": "Author",
        "about_shortcuts": "Shortcuts",
        "about_desc": "AI Style Real-time Preview Tool\nBased on MooaToon parameter system",

        # Tooltips
        "tip_shadow": "Shadow area color\n• 0 = Dark shadow\n• 1 = Bright shadow",
        "tip_specular": "Specular intensity\n• 0 = No specular\n• 1 = Strong specular",
        "tip_rim": "Rim light intensity\n• 0 = No rim\n• 1 = Strong rim",
        "tip_outline": "Outline thickness\n• 0.5 = Thin\n• 3.0 = Thick",

        # Log - Init
        "log_model_ok": "Model loaded: {}",
        "log_model_fail": "Model load failed: {}",
        "log_model_none": "No ONNX model specified, inference unavailable (can load later)",
        "log_ue_ready": "UE5 client ready",
        "log_ue_fail": "UE5 client init failed: {}",
        "log_ready": "AutoToon Studio ready",

        # Log - Actions
        "log_img_loaded": "Image loaded: {}",
        "log_img_fail": "Image load failed: {}",
        "log_no_image": "Please upload a reference image first",
        "log_ue_not_init": "UE5 client not initialized",
        "log_sent_ok": "Sent to UE5: Shadow=({},{},{}) Spec={} Rim={} Width={}",
        "log_sent_fail": "Send failed: {}",
        "log_ue_ok": "UE5 connection OK",
        "log_ue_fail2": "UE5 not connected: {}",
        "log_no_preset_name": "Please enter a preset name",
        "log_preset_saved": "Preset saved: {}",
        "log_preset_save_fail": "Save failed: {}",
        "log_preset_loaded": "Preset loaded: {}",
        "log_preset_load_fail": "Load failed: {}",
        "log_infering": "Running inference...",
        "log_infer_ok": "Inference done: Shadow=({},{},{}) Spec={} Rim={} Width={}",
        "log_infer_fail": "Inference failed: {}",
        "log_params_reset": "Params reset to defaults",
        "log_view_reset": "View reset",
        "log_fit_window": "Fit to window",
    },
}

# ─── 全局状态 ────────────────────────────────────────────────────────────────────
_current_lang = "zh"
_config_path = str(Path(__file__).parent / ".autotoon_lang.json")


def _load_saved_lang():
    """从配置文件加载上次保存的语言"""
    global _current_lang
    try:
        if os.path.exists(_config_path):
            with open(_config_path, "r") as f:
                data = json.load(f)
                if data.get("lang") in TRANSLATIONS:
                    _current_lang = data["lang"]
    except Exception:
        pass


def _save_lang():
    """保存当前语言到配置文件"""
    try:
        with open(_config_path, "w") as f:
            json.dump({"lang": _current_lang}, f)
    except Exception:
        pass


# ─── 公开接口 ────────────────────────────────────────────────────────────────────
def t(key: str, *args) -> str:
    """
    获取翻译文本。
    t("btn_upload")         → "上传图片" 或 "Upload Image"
    t("log_img_loaded", name) → "已加载图片: xxx.png"
    """
    text = TRANSLATIONS.get(_current_lang, TRANSLATIONS["zh"]).get(key, key)
    if args:
        try:
            return text.format(*args)
        except (IndexError, KeyError):
            return text
    return text


def set_lang(lang: str):
    """切换语言 ("zh" / "en")"""
    global _current_lang
    if lang in TRANSLATIONS:
        _current_lang = lang
        _save_lang()


def get_lang() -> str:
    """获取当前语言代码"""
    return _current_lang


def toggle_lang():
    """中英切换"""
    set_lang("en" if _current_lang == "zh" else "zh")


# 启动时自动加载
_load_saved_lang()
