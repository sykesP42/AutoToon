"""
ue_apply_labels.py — 在 UE5 Output Log 里运行
功能：读取 labels.csv，把参数批量写入对应的材质实例

用法：
  UE5 菜单栏: Tools -> Execute Python Script -> 选择本文件

两种模式（修改底部 MODE 变量）：
  "read"  -> 读取当前材质参数并打印（默认，方便核对）
  "apply" -> 把 CSV 最后一行的参数写入材质

注意：
  - Shadow Color / Specular / Rim Light Width 写入主体材质图层参数
  - Width Scale 写入描边材质 (MI_UnityChan_Outline_Test) 的全局参数
"""

import unreal
import csv
import os

# ─── 配置 ───────────────────────────────────────────────────────────────────────

LABELS_CSV = "D:/unreal/testcv/labels.csv"

# 主体材质（Shadow Color / Specular / Rim Light Width）
BODY_MATERIAL_PATH = "/Game/MooaToonSamples/Characters/UnityChanSD/Materials/MI_UnityChan_Body_Blue"

# 描边材质（Width Scale）
OUTLINE_MATERIAL_PATH = "/Game/MooaToonSamples/Characters/UnityChanSD/Materials/MI_UnityChan_Outline_Test"

# ─── apply 模式：CSV 最后一行 → 写入材质 ─────────────────────────────────────────

def apply_labels():
    if not os.path.exists(LABELS_CSV):
        unreal.log_error(f"[MooaToon] CSV 不存在: {LABELS_CSV}")
        return

    mel = unreal.MaterialEditingLibrary

    with open(LABELS_CSV, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    if not rows:
        unreal.log_error("[MooaToon] CSV 没有数据行")
        return

    row = rows[-1]
    unreal.log(f"[MooaToon] 应用参数来自: {row['image_filename']}")

    # ── 主体材质：Shadow Color / Specular / Rim Light Width ──────────────────
    body_mat = unreal.load_asset(BODY_MATERIAL_PATH)
    if body_mat:
        r = float(row["shadow_r"])
        g = float(row["shadow_g"])
        b = float(row["shadow_b"])
        color = unreal.LinearColor(r=r, g=g, b=b, a=1.0)
        mel.set_material_instance_vector_parameter_value(body_mat, "Shadow Color", color)
        unreal.log(f"[MooaToon]   Shadow Color = ({r:.3f}, {g:.3f}, {b:.3f})")

        spec = float(row["specular"])
        mel.set_material_instance_scalar_parameter_value(body_mat, "Specular", spec)
        unreal.log(f"[MooaToon]   Specular = {spec:.3f}")

        rim = float(row["rim_light_width"])
        mel.set_material_instance_scalar_parameter_value(body_mat, "Rim Light Width", rim)
        unreal.log(f"[MooaToon]   Rim Light Width = {rim:.3f}")

        unreal.EditorAssetLibrary.save_asset(body_mat.get_path_name())
        unreal.log("[MooaToon]   主体材质已保存 ✓")
    else:
        unreal.log_error(f"[MooaToon] 主体材质加载失败: {BODY_MATERIAL_PATH}")

    # ── 描边材质：Width Scale ─────────────────────────────────────────────────
    outline_mat = unreal.load_asset(OUTLINE_MATERIAL_PATH)
    if outline_mat:
        width = float(row["width_scale"])
        mel.set_material_instance_scalar_parameter_value(outline_mat, "Width Scale", width)
        unreal.log(f"[MooaToon]   Width Scale = {width:.3f}")
        unreal.EditorAssetLibrary.save_asset(outline_mat.get_path_name())
        unreal.log("[MooaToon]   描边材质已保存 ✓")
    else:
        unreal.log_warning(f"[MooaToon] 描边材质加载失败，跳过 Width Scale: {OUTLINE_MATERIAL_PATH}")


# ─── read 模式：读取当前材质参数 ──────────────────────────────────────────────────

def read_current_params():
    mel = unreal.MaterialEditingLibrary

    unreal.log("\n[MooaToon] ── 当前主体材质参数 ──")
    body_mat = unreal.load_asset(BODY_MATERIAL_PATH)
    if body_mat:
        shadow = mel.get_material_instance_vector_parameter_value(body_mat, "Shadow Color")
        spec   = mel.get_material_instance_scalar_parameter_value(body_mat, "Specular")
        rim    = mel.get_material_instance_scalar_parameter_value(body_mat, "Rim Light Width")
        unreal.log(f"  Shadow Color    : R={shadow.r:.4f}  G={shadow.g:.4f}  B={shadow.b:.4f}")
        unreal.log(f"  Specular        : {spec:.4f}")
        unreal.log(f"  Rim Light Width : {rim:.4f}")
        unreal.log(f"  -> CSV格式: {shadow.r:.3f},{shadow.g:.3f},{shadow.b:.3f},{spec:.3f},{rim:.3f}")
    else:
        unreal.log_error(f"  主体材质加载失败: {BODY_MATERIAL_PATH}")

    unreal.log("\n[MooaToon] ── 当前描边材质参数 ──")
    outline_mat = unreal.load_asset(OUTLINE_MATERIAL_PATH)
    if outline_mat:
        width = mel.get_material_instance_scalar_parameter_value(outline_mat, "Width Scale")
        unreal.log(f"  Width Scale     : {width:.4f}")
        unreal.log(f"  -> CSV格式: {width:.3f}")
    else:
        unreal.log_warning(f"  描边材质加载失败: {OUTLINE_MATERIAL_PATH}")


# ─── 入口 ───────────────────────────────────────────────────────────────────────
# "apply" -> 把 CSV 最后一行写入材质
# "read"  -> 读取当前材质参数（调完参数后用这个核对）
MODE = "read"

if MODE == "apply":
    apply_labels()
elif MODE == "read":
    read_current_params()
