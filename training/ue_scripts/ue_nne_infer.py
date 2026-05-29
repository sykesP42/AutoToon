"""
ue_nne_infer.py — 在 UE5 Output Log 里运行
功能：用 NNE 加载 mooatoon_model.onnx，对一张图推理，把6个参数写入材质实例

注意：
  现在推理输出6个参数，顺序为：
  [0] shadow_r
  [1] shadow_g
  [2] shadow_b
  [3] specular
  [4] rim_light_width
  [5] width_scale  (模型输出 [0,1]，写入前乘2.5+0.5还原到[0.5,3.0])

  Shadow Color / Specular / Rim Light Width -> 主体材质图层参数
  Width Scale -> 描边材质全局参数
"""

import unreal
import os

# ─── 配置 ───────────────────────────────────────────────────────────────────────
NNE_ASSET_PATH     = "/Game/ONNX/mooatoon_model"
INFER_IMAGE        = "D:/unreal/testcv/images/G1T8dBxbQAIa7hM.jpg"
BODY_MATERIAL_PATH = "/Game/MooaToonSamples/Characters/UnityChanSD/Materials/MI_UnityChan_Body_Blue"
OUTLINE_MATERIAL_PATH = "/Game/MooaToonSamples/Characters/UnityChanSD/Materials/MI_UnityChan_Outline_Test"

# 输出参数顺序（与训练时 LABEL_COLS 一致）
PARAM_NAMES = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light_width", "width_scale"]

# ─── NNE 推理 ──────────────────────────────────────────────────────────────────

def run_inference():
    nne_asset = unreal.load_asset(NNE_ASSET_PATH)
    if nne_asset is None:
        unreal.log_error(f"[NNE] 资产加载失败: {NNE_ASSET_PATH}")
        return

    unreal.log("[NNE] 模型加载成功，开始推理...")

    try:
        from PIL import Image as PILImage
        import struct, array

        img = PILImage.open(INFER_IMAGE).convert("RGB").resize((224, 224))
        pixels = list(img.getdata())

        mean = [0.485, 0.456, 0.406]
        std  = [0.229, 0.224, 0.225]

        tensor = []
        for c in range(3):
            for r, g, b in pixels:
                vals = [r/255.0, g/255.0, b/255.0]
                tensor.append((vals[c] - mean[c]) / std[c])

        input_data = array.array('f', tensor)
        unreal.log(f"[NNE] 图片预处理完成，tensor 长度: {len(tensor)}")

    except ImportError:
        unreal.log_error("[NNE] PIL 未安装，无法预处理图片")
        return

    try:
        model_instance = unreal.NNEModelData(nne_asset)
        model_instance.set_inputs([input_data.tobytes()])
        model_instance.run()
        output = model_instance.get_outputs()[0]

        # 解析6个float32
        results = struct.unpack('6f', output[:24])
        unreal.log("[NNE] 推理结果:")
        for name, val in zip(PARAM_NAMES, results):
            unreal.log(f"  {name}: {val:.4f}")

        apply_to_material(results)

    except Exception as e:
        unreal.log_error(f"[NNE] 推理失败: {e}")


def apply_to_material(results):
    shadow_r, shadow_g, shadow_b, specular, rim_light_width, width_scale_norm = results
    # width_scale 反归一化
    width_scale = width_scale_norm * 2.5 + 0.5

    mel = unreal.MaterialEditingLibrary

    # ── 主体材质：Shadow Color / Specular / Rim Light Width ──────────────────
    body_mat = unreal.load_asset(BODY_MATERIAL_PATH)
    if body_mat:
        color = unreal.LinearColor(r=shadow_r, g=shadow_g, b=shadow_b, a=1.0)
        mel.set_material_instance_vector_parameter_value(body_mat, "Shadow Color", color)
        mel.set_material_instance_scalar_parameter_value(body_mat, "Specular", specular)
        mel.set_material_instance_scalar_parameter_value(body_mat, "Rim Light Width", rim_light_width)
        unreal.EditorAssetLibrary.save_asset(body_mat.get_path_name())
        unreal.log(f"[NNE] 主体材质已写入:")
        unreal.log(f"  Shadow Color    = ({shadow_r:.3f}, {shadow_g:.3f}, {shadow_b:.3f})")
        unreal.log(f"  Specular        = {specular:.3f}")
        unreal.log(f"  Rim Light Width = {rim_light_width:.3f}")

    # ── 描边材质：Width Scale ─────────────────────────────────────────────────
    outline_mat = unreal.load_asset(OUTLINE_MATERIAL_PATH)
    if outline_mat:
        mel.set_material_instance_scalar_parameter_value(outline_mat, "Width Scale", width_scale)
        unreal.EditorAssetLibrary.save_asset(outline_mat.get_path_name())
        unreal.log(f"  Width Scale     = {width_scale:.3f}  (原始 [0,1]={width_scale_norm:.3f})")


run_inference()
