# HybriToon Dataset — MooaToon 材质参数预测

## 项目概述

训练一个神经网络模型，输入日式风格插画图片，输出 UE5 MooaToon 材质参数：

```
输入：日式风格插画图片（224×224 RGB）
输出：6 个 MooaToon 材质参数
  [0] shadow_r        — 阴影色 R，图层参数
  [1] shadow_g        — 阴影色 G，图层参数
  [2] shadow_b        — 阴影色 B，图层参数
  [3] specular        — 高光强度，图层参数
  [4] rim_light_width — 边缘光宽度，图层参数
  [5] width_scale     — 描边宽度，描边材质全局参数（训练时归一化，UE端反归一化）
```

训练好的模型导出为 ONNX，在 UE5 的 NNE（Neural Network Engine）中加载。
通过 `MooaToonInference` 插件（C++）将推理结果写入材质，实现"给一张参考图自动推理出匹配材质参数"的效果。

---

## 目录结构

```
D:/unreal/testcv/
│
├── images/                   # 参考图片（日式插画，PNG/JPG）
│
├── labels.csv                # 数据集标签文件（6列参数）
│
├── dataset_verify.py         # 数据集验证脚本
├── train.py                  # 模型训练 + ONNX 导出（6个输出）
├── infer_test.py             # 本地推理验证脚本
│
├── ue_record_params.py       # [UE内运行] 调好6个参数后记录到 CSV
├── ue_apply_labels.py        # [UE内运行] 把 CSV 参数写入材质实例
├── ue_nne_infer.py           # [UE内运行] NNE 推理脚本
│
├── mooatoon_model.pth        # PyTorch 模型权重（训练产物）
└── mooatoon_model.onnx       # ONNX 模型（供 UE5 NNE 加载）
```

UE5 插件位置：

```
D:/unreal/MooaToon-Engine-5.5_MooaToonProject/.../Plugins/MooaToonInference/
├── MooaToonInference.uplugin
└── Source/MooaToonInference/
    ├── Public/
    │   ├── MooaToonInferenceLibrary.h   # 蓝图函数库声明（UMooaToonInferenceLibrary）
    │   └── MooaToonDebugWidget.h        # UMG 调试面板 C++ 基类
    └── Private/
        ├── MooaToonInferenceLibrary.cpp
        └── MooaToonDebugWidget.cpp
```

---

## 标签文件格式

`labels.csv` 每行对应一张图片和一组 MooaToon 材质参数：

```csv
image_filename,shadow_r,shadow_g,shadow_b,specular,rim_light_width,width_scale
ref_01.jpg,0.2,0.1,0.3,0.8,0.5,1.5
ref_02.jpg,0.4,0.5,0.6,0.3,0.4,1.2
```

| 列名 | 对应 UE 材质参数 | 写入位置 | 范围 |
|------|----------------|---------|------|
| `shadow_r` | Shadow Color (R) | 主体材质图层参数 | [0, 1] |
| `shadow_g` | Shadow Color (G) | 主体材质图层参数 | [0, 1] |
| `shadow_b` | Shadow Color (B) | 主体材质图层参数 | [0, 1] |
| `specular` | Specular | 主体材质图层参数 | [0, 1] |
| `rim_light_width` | Rim Light Width | 主体材质图层参数 | [0, 1] |
| `width_scale` | Width Scale | 描边材质全局参数 | [0.5, 3.0] |

> `width_scale` 在训练时**归一化到 [0,1]**（Sigmoid输出），UE 插件推理后自动反归一化：
> `width_scale_real = output * 2.5 + 0.5`

---

## 各脚本说明

### `dataset_verify.py` — 数据集验证

**用法**：
```bash
cd D:/unreal/testcv
python dataset_verify.py
```

**检查内容**：CSV 中每个文件名是否存在对应图片、图片能否打开、6列参数值范围是否合理。

**期望输出**：
```
[CSV] 共 38 条记录，列: ['image_filename', 'shadow_r', 'shadow_g', 'shadow_b', 'specular', 'rim_light_width', 'width_scale']
[OK]  38 张图片正常加载
[标签范围检查]
  [shadow_r]        ✓  min=0.060  max=0.500
  [specular]        ✓  min=0.100  max=0.960
  [rim_light_width] ✓  min=0.250  max=0.700
  [width_scale]     ✓  min=0.700  max=1.900
>>> 数据集验证通过，可以开始训练 <<<
```

---

### `train.py` — 模型训练 + ONNX 导出

**模型结构**：
```
ResNet18 骨干网络
    ↓
全连接层 (512 → 128 → 6)
    ↓
Sigmoid 激活（6个输出全部压到 [0,1]）
```

**输出顺序（固定，不可改变）**：
```python
LABEL_COLS = ["shadow_r", "shadow_g", "shadow_b", "specular", "rim_light_width", "width_scale"]
```

**用法**：
```bash
cd D:/unreal/testcv
python train.py
```

**期望输出**：
```
Device: cpu
输出参数: ['shadow_r', 'shadow_g', 'shadow_b', 'specular', 'rim_light_width', 'width_scale']
数据集: 38 张图片, 10 个 batch

Epoch [01/20]  Loss: 0.071234
...
Epoch [20/20]  Loss: 0.021456

模型已保存: mooatoon_model.pth
ONNX exported: mooatoon_model.onnx
输出顺序: ['shadow_r', 'shadow_g', 'shadow_b', 'specular', 'rim_light_width', 'width_scale']
```

---

### `infer_test.py` — 本地推理验证

**用法**：
```bash
# 默认取第一张图
python infer_test.py

# 指定图片
python infer_test.py G1T8dBxbQAIa7hM.jpg
```

**期望输出**：
```
图片: G1T8dBxbQAIa7hM.jpg
─────────────────────────────────────────────
  shadow_r                  = 0.2362
  shadow_g                  = 0.1080
  shadow_b                  = 0.1682
  specular                  = 0.6962
  rim_light_width           = 0.4823
  width_scale               = 0.2117

  [UE 写入参数]
  Shadow Color    = (0.236, 0.108, 0.168)
  Specular        = 0.696          [图层参数]
  Rim Light Width = 0.482          [图层参数]
  Width Scale     = 1.029          [描边材质全局参数，反归一化后]
```

---

### `ue_record_params.py` — [UE内运行] 调参记录

**作用**：在 UE5 里通过 `WBP_MooaToonDebug` 调好6个参数后，运行此脚本自动记录到 `labels.csv`。

**每次标注一张图的流程**：

```
1. 打开参考图（副屏）
2. PIE 运行 UE5，用 WBP_MooaToonDebug 面板拖动6个滑条：
   - Slider_R / G / B  → Shadow Color
   - Slider_Specular   → Specular
   - Slider_RimLightWidth → Rim Light Width
   - Slider_WidthScale → Width Scale（描边材质）
3. 达到满意效果后退出 PIE
4. 修改脚本顶部：
   IMAGE_FILENAME = "当前参考图的文件名.jpg"
5. UE5 菜单: Tools → Execute Python Script → 选择本文件
6. Output Log 里看到 "[MooaToon] 已记录" 说明成功
```

> 注意：PIE 退出后材质参数会保留在 MID 实例中，但不影响磁盘上的 .uasset 文件。
> 本脚本读取的是磁盘上材质实例的默认参数值，所以需要在调完参数后先
> 通过「导出CSV」按钮（在 WBP 面板上）直接记录，或手动调整脚本路径。

**需要在 UE5 里启用 Python 插件**：
```
Edit → Plugins → 搜索 "Python Editor Script Plugin" → 勾选 → 重启 UE
```

---

### `ue_apply_labels.py` — [UE内运行] CSV 写入材质

**作用**：把 `labels.csv` 里的参数值写入 UE5 材质实例，用于验证标注是否正确。

**两种运行模式**（修改文件底部的 `MODE` 变量）：

| MODE | 行为 |
|------|------|
| `"read"` | 读取当前6个材质参数，打印到 Output Log（默认） |
| `"apply"` | 把 CSV 最后一行的6个参数写入材质并保存 |

**用法**：
```
UE5: Tools → Execute Python Script → 选择 ue_apply_labels.py
```

---

## UE5 MooaToonInference 插件

### 核心 C++ 类

**`UMooaToonInferenceLibrary`**（蓝图函数库）

| 函数 | 分类 | 说明 |
|------|------|------|
| `SetMooaToonParams` | MooaToon | 手填6个参数直接写入材质 |
| `RunMooaToonInference` | MooaToon\|Inference | NNE 推理，返回 FMooaToonParams（含6个字段） |
| `LoadImageToPixels` | MooaToon\|Inference | 读取图片 → 224×224 → ImageNet归一化 → CHW float |
| `InferAndApply` | MooaToon | 完整链路：读图+推理+写入材质 |

**`FMooaToonParams` 结构体字段**：

```cpp
float ShadowR       // [0, 1]  图层参数
float ShadowG       // [0, 1]  图层参数
float ShadowB       // [0, 1]  图层参数
float Specular      // [0, 1]  图层参数
float RimLightWidth // [0, 1]  图层参数
float WidthScale    // [0.5, 3.0]  描边材质全局参数（已反归一化）
```

**`SetMooaToonParams` 函数签名**：

```cpp
static void SetMooaToonParams(
    AActor* TargetActor,
    FLinearColor ShadowColor,
    float Specular      = 0.5f,   // 图层参数
    float RimLightWidth = 0.5f,   // 图层参数
    float WidthScale    = 1.0f,   // 描边材质全局参数
    int32 ElementIndex  = -1      // -1 = 写入全部材质槽
);
```

**`UMooaToonDebugWidget`**（UMG 调试面板 C++ 基类）

在 UE5 Widget Blueprint 中以此类为父类创建 `WBP_MooaToonDebug`，
面板包含6个参数的滑条，拖动即实时写入材质，并可导出 CSV 作为训练标签。

---

## 完整数据流

```
【标注阶段】

参考图片 (images/)
    ↓ 在 WBP_MooaToonDebug 面板拖动6个滑条调参
    ↓ 点击「导出 CSV」按钮
labels.csv  ← 6列参数（含 rim_light_width / width_scale）


【训练阶段】

labels.csv + images/
    ↓ python train.py
mooatoon_model.onnx（6个输出）
    ↓ python infer_test.py 验证输出正常


【推理阶段 - UE5】

mooatoon_model.uasset（导入到 Content Browser）
    ↓ WBP_MooaToonDebug 面板点击「ONNX推理」
    ↓ C++ UMooaToonInferenceLibrary::InferAndApply
        → Shadow Color / Specular / Rim Light Width → 主体材质图层参数
        → Width Scale（反归一化）→ 描边材质（MooaOutlineMaterial）全局参数
    ↓
角色材质实时生效
```

---

## 环境依赖

```bash
pip install torch torchvision pillow pandas onnx onnxruntime
```

| 包 | 用途 |
|----|------|
| torch / torchvision | 训练、ONNX 导出 |
| Pillow | 图片读取 |
| pandas | CSV 读写 |
| onnx | ONNX 格式校验 |
| onnxruntime | 本地推理验证 |

Python 版本：3.11（Windows）

---

## UE5 环境

| 项目 | 路径 |
|------|------|
| MooaToon 引擎 | `E:/MooaToon-Engine-5.5/MooaToon-Engine-5.5/` |
| MooaToon 项目 | `D:/unreal/MooaToon-Engine-5.5_MooaToonProject/` |
| ONNX 资产位置 | `Content/NNE/mooatoon_model.uasset` |
| 插件位置 | `Plugins/MooaToonInference/` |
| 主体材质 | `MI_UnityChan_Body_Blue`（Shadow Color / Specular / Rim Light Width） |
| 描边材质 | `MI_UnityChan_Outline_Test`（Width Scale） |

---

## 已确认的 MooaToon 材质参数

| UE 参数名 | 类型 | 命名空间 | 所在材质 |
|-----------|------|---------|---------|
| `Shadow Color` | Vector (RGB) | LayerParameter | 主体材质 |
| `Specular` | Scalar | LayerParameter | 主体材质 |
| `Rim Light Width` | Scalar | LayerParameter | 主体材质 |
| `Width Scale` | Scalar | GlobalParameter | 描边材质（MooaOutlineMaterial） |
