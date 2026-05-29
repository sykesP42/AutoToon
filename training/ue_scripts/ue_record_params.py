"""
ue_record_params.py — 调好参数后，在 UE5 里运行这个脚本
功能：读取当前材质实例的参数值，自动追加到 labels.csv

工作流：
  Step 1: 在 UE5 里用 WBP_MooaToonDebug 调好所有6个参数，觉得"很像参考图了"
  Step 2: 修改下方 IMAGE_FILENAME 为当前参考图文件名
  Step 3: Tools -> Execute Python Script -> 选择本文件
  -> 自动把6个参数追加到 labels.csv

注意：
  - Shadow Color / Specular / Rim Light Width 是图层参数，
    本脚本通过 GetScalarParameterValue 读取（需要材质实例编辑器中的值）
  - Width Scale 在描边材质（MI_UnityChan_Outline_Test）的细节面板里
"""

import unreal
import csv
import os

# ─── 每次运行前修改这里 ──────────────────────────────────────────────────────────
IMAGE_FILENAME = "ref_01.jpg"   # 改成当前对照的参考图文件名

# 主体材质实例路径（读取 Shadow Color / Specular / Rim Light Width）
BODY_MATERIAL_PATH = "/Game/MooaToonSamples/Characters/UnityChanSD/Materials/MI_UnityChan_Body_Blue"

# 描边材质实例路径（读取 Width Scale）
OUTLINE_MATERIAL_PATH = "/Game/MooaToonSamples/Characters/UnityChanSD/Materials/MI_UnityChan_Outline_Test"

LABELS_CSV = "D:/unreal/testcv/labels.csv"

# ─── 逻辑 ───────────────────────────────────────────────────────────────────────

def record():
    mel = unreal.MaterialEditingLibrary

    # 读取主体材质的图层参数
    body_mat = unreal.load_asset(BODY_MATERIAL_PATH)
    if body_mat is None:
        unreal.log_error(f"[MooaToon] 主体材质加载失败: {BODY_MATERIAL_PATH}")
        return

    shadow = mel.get_material_instance_vector_parameter_value(body_mat, "Shadow Color")
    spec   = mel.get_material_instance_scalar_parameter_value(body_mat, "Specular")
    rim    = mel.get_material_instance_scalar_parameter_value(body_mat, "Rim Light Width")

    # 读取描边材质的全局参数
    outline_mat = unreal.load_asset(OUTLINE_MATERIAL_PATH)
    if outline_mat is None:
        unreal.log_warning(f"[MooaToon] 描边材质加载失败，Width Scale 默认 1.0")
        width_scale = 1.0
    else:
        width_scale = mel.get_material_instance_scalar_parameter_value(outline_mat, "Width Scale")

    row = {
        "image_filename":  IMAGE_FILENAME,
        "shadow_r":        round(shadow.r, 4),
        "shadow_g":        round(shadow.g, 4),
        "shadow_b":        round(shadow.b, 4),
        "specular":        round(spec, 4),
        "rim_light_width": round(rim, 4),
        "width_scale":     round(width_scale, 4),
    }

    fieldnames = ["image_filename", "shadow_r", "shadow_g", "shadow_b",
                  "specular", "rim_light_width", "width_scale"]
    file_exists = os.path.exists(LABELS_CSV)

    with open(LABELS_CSV, "a", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    unreal.log(f"[MooaToon] 已记录: {row}")
    unreal.log(f"[MooaToon] 写入: {LABELS_CSV}")

record()
