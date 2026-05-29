# AutoToon

AI 辅助的 UE5 实时风格化工具 — 上传参考图，自动提取风格参数，一键应用到 UE5 场景。

## 项目结构

```
AutoToon/
├── training/               # 模型训练管线
│   ├── train.py            # ResNet18 训练 + ONNX 导出
│   ├── infer_test.py       # 本地推理验证
│   ├── dataset_verify.py   # 数据集检查
│   ├── material_params.py  # 53 维参数体系定义
│   ├── labels.csv          # 训练标签 (198 条)
│   ├── requirements.txt    # 训练依赖
│   └── ue_scripts/         # UE5 Python 脚本
│       ├── ue_record_params.py
│       ├── ue_apply_labels.py
│       └── ue_nne_infer.py
│
├── Studio/                 # 独立程序 (AutoToonStudio)
│   ├── main.py             # 入口
│   ├── engine.py           # ONNX 推理引擎
│   ├── ui.py               # Dear PyGui 界面
│   ├── preview.py          # OpenCV 实时预览
│   ├── ue_client.py        # HTTP 客户端
│   ├── style_manager.py    # 风格预设管理
│   └── requirements.txt    # Studio 依赖
│
├── plugin/                 # UE5 插件
│   └── MooaToonInference/  # NNE推理 + HTTP服务 + 材质控制
│
├── data/                   # 训练数据
│   └── images/             # 参考图片 (222 张)
│
├── presets/                # 风格预设 (.style 文件)
├── docs/                   # 参考文档和截图
│
├── start_autotoon.bat     # 一键启动脚本
├── PRODUCT_SPEC.md         # 产品规格说明书
└── README.md
```

## 快速开始

### 1. 训练模型

```bash
cd training
pip install -r requirements.txt
python dataset_verify.py   # 验证数据集
python train.py            # 训练 + 导出 ONNX
```

### 2. 启动 Studio

```bash
cd Studio
pip install -r requirements.txt
python main.py             # 自动加载模型
```

### 3. 连接 UE5

1. 将 `plugin/MooaToonInference/` 拷贝到 UE5 项目 `Plugins/` 目录
2. 编译 UE5 项目
3. 插件自动在 `127.0.0.1:8080` 启动 HTTP 服务
4. 在 Studio 中点击「检查 UE5 连接」

### 4. 一键启动

双击 `start_autotoon.bat`，自动启动 Studio 并提示打开 UE5。

## 技术栈

| 组件 | 技术 |
|------|------|
| 独立程序 UI | Python + Dear PyGui |
| AI 推理 | onnxruntime (ResNet18) |
| 图像预览 | OpenCV 色调映射 |
| UE5 通信 | HTTP (requests ↔ HttpServer) |
| UE5 插件 | C++ + NNE + Json |
