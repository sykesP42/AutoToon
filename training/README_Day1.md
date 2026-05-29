
# HybriToon - Day1 完成报告

## 日期
2026-04-06

## 完成任务

### ✅ 1. 研究MooaToon材质参数列表

基于以下来源进行了深入研究：
- MooaToon官方文档 (https://mooatoon.com/docs/)
- MToon (VRM标准着色器) 参考实现
- Unity Toon Shader (UTS) 文档
- 卡通渲染行业最佳实践

### ✅ 2. 设计参数向量结构

设计了完整的 **53维参数向量**，包含以下8个模块：

| 模块 | 参数数量 | 主要功能 |
|------|---------|---------|
| ColorParams | 11 | 基础色偏移、阴影色、高光色、描边色 |
| ShadingParams | 5 | 阴影阈值、柔和度、偏移、二值/三色阶 |
| SpecularParams | 5 | 高光强度、范围、柔和度、各向异性 |
| HairParams | 14 | Kajiya-Kay头发高光（主/次高光） |
| OutlineParams | 7 | 描边宽度、Z偏移、屏幕空间描边 |
| RimLightParams | 6 | 边缘光强度、范围、颜色 |
| GIParams | 3 | GI强度、方向性、反射强度 |
| PostProcessParams | 4 | 曝光、饱和度、对比度、伽马 |
| **总计** | **53** | |

### ✅ 3. 搭建Python环境

创建了完整的环境配置文件：
- `requirements.txt`: Python 3.12 + PyTorch 2.7.0 依赖
- 支持ONNX导出和推理
- 包含完整的数据处理和可视化工具

---

## 文件结构

```
HybriToon/
├── material_params.py       # 完整的材质参数定义（含8个dataclass）
├── requirements.txt         # Python依赖配置
└── README_Day1.md          # 本文件
```

---

## 参数设计亮点

### 1. 分层模块化设计
使用Python dataclass实现参数的模块化管理，便于扩展和维护。

### 2. 归一化/反归一化
- 自动处理不同参数的范围差异
- 神经网络输出统一归一化到 [0, 1]
- 推理时自动反归一化到实际物理范围

### 3. 预设风格
内置4种风格预设：
- `default`: 默认参数
- `anime`: 日本动画风格（高对比、硬阴影）
- `cartoon`: 美国卡通风格（柔和阴影、高GI）
- `watercolor`: 水彩风格（超柔和、高饱和）

### 4. 序列化支持
- `to_vector()`: 参数 → numpy向量
- `from_vector()`: numpy向量 → 参数对象
- 便于与神经网络接口集成

---

## 使用示例

```python
from material_params import MooaToonMaterialParams, get_anime_style_preset

# 获取日本动画风格预设
params = get_anime_style_preset()

# 转换为神经网络输出向量
vec = params.to_vector(normalize=True)
print(f"参数向量形状: {vec.shape}")  # (53,)

# 从向量重建
reconstructed = MooaToonMaterialParams.from_vector(vec, denormalize=True)
```

---

## MooaToon 核心技术总结

### 1. Ramp光照
- 将PBR兰伯特漫反射替换为Ramp光照
- 支持二值化、三色阶、自定义Ramp图
- Global Ramp Atlas完美支持多光源

### 2. 平滑法线烘焙
- 一键工具将平滑法线存储到UV2/UV3通道
- 曲率加权控制平滑程度
- 消除硬边阴影断裂

### 3. 描边系统
- 传统背面描边
- 屏幕空间深度-法线卷积描边
- 支持Velocity输出配合TSR抗锯齿

### 4. Lumen集成
- 可自由控制GI强度和混合
- GI方向性调节（均匀球谐 ↔ Lumen）
- 反射强度控制

---

## 下一步计划（Day2）

1. 收集/准备训练数据集
2. 实现数据加载器
3. 数据预处理（resize、归一化）

---

## 参考资料

1. MooaToon官方文档: https://mooatoon.com/docs/
2. MooaToon GitHub: https://github.com/JasonMa0012/MooaToon
3. VRM MToon标准: https://github.com/vrm-c/UniVRM
4. Unity Toon Shader: https://docs.unity3d.com/Packages/com.unity.toonshader

