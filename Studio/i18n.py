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

        # 中栏
        "param_adjust": "参数调节",
        "label_shadow_r": "Shadow R",
        "label_shadow_g": "Shadow G",
        "label_shadow_b": "Shadow B",
        "label_specular": "高光强度",
        "label_rim_light": "边缘光宽度",
        "label_width_scale": "描边宽度",
        "live_preview": "实时预览",

        # 右栏
        "actions": "操作",
        "btn_infer": "推理 (AI 分析)",
        "btn_check_ue": "检查 UE5 连接",
        "btn_send_ue": "发送到 UE5",
        "ue_status_ok": "已连接",
        "ue_status_fail": "未连接",
        "ue_status_init": "未检查",
        "style_presets": "风格预设",
        "hint_preset_name": "预设名称",
        "btn_save": "保存",
        "log_title": "日志",
        "btn_lang": "EN",

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
    },

    "en": {
        # Window
        "window_title": "AutoToon Studio",

        # Left panel
        "ref_image": "Reference Image",
        "btn_upload": "Upload Image",
        "file_filter": "Images{.png,.jpg,.jpeg,.bmp}",

        # Center panel
        "param_adjust": "Parameter Adjustment",
        "label_shadow_r": "Shadow R",
        "label_shadow_g": "Shadow G",
        "label_shadow_b": "Shadow B",
        "label_specular": "Specular",
        "label_rim_light": "Rim Light Width",
        "label_width_scale": "Width Scale",
        "live_preview": "Live Preview",

        # Right panel
        "actions": "Actions",
        "btn_infer": "Infer (AI Analysis)",
        "btn_check_ue": "Check UE5 Connection",
        "btn_send_ue": "Send to UE5",
        "ue_status_ok": "Connected",
        "ue_status_fail": "Disconnected",
        "ue_status_init": "Not Checked",
        "style_presets": "Style Presets",
        "hint_preset_name": "Preset Name",
        "btn_save": "Save",
        "log_title": "Log",
        "btn_lang": "中",

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
