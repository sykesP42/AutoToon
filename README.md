# AutoToon

[中文](#autotoon-1) | [English](#autotoon-en)

AI-assisted UE5 real-time stylization tool — upload a reference image, automatically extract style parameters, and apply to your UE5 scene in one click.

**Current Version: v2.1.0**

---

<a name="autotoon-1"></a>
## AutoToon

AI 辅助的 UE5 实时风格化工具 — 上传参考图，自动提取风格参数，一键应用到 UE5 场景。

### Features

- **AI Style Extraction** - Upload reference image, auto-extract toon style parameters
- **Multi-Shape Preview** - Sphere, Cube, Cylinder, Torus, Cone, Icosahedron (6 shapes)
- **9 Skybox Presets** - Studio Gray, Warm Sunset, Cool Dawn, HDR White, etc. + Custom Image Support
- **Advanced Rendering** - SSS, Anisotropic Specular, Metallic, Roughness parameters
- **Camera Control** - Mouse drag rotation + slider controls
- **Style Presets** - Save/Load material configurations
- **UE5 Integration** - HTTP communication with UE5 plugin
- **Batch Processing** - Folder-based AI inference for multiple images
- **Keyboard Shortcuts** - 1-6 shapes, R reset camera, M reset material, Space auto-rotate
- **Screenshot Export** - PNG with timestamp

### Project Structure

```
AutoToon/
├── training/               # Model training pipeline
│   ├── train.py            # ResNet18 training + ONNX export
│   ├── infer_test.py       # Local inference validation
│   ├── dataset_verify.py   # Dataset integrity check
│   ├── material_params.py  # 53-dim parameter system
│   ├── labels.csv          # Training labels (198 entries)
│   ├── requirements.txt    # Training dependencies
│   └── ue_scripts/         # UE5 Python scripts
│       ├── ue_record_params.py
│       ├── ue_apply_labels.py
│       └── ue_nne_infer.py
│
├── Studio/                 # Standalone app (AutoToonStudio)
│   ├── main.py             # Entry point
│   ├── engine.py           # ONNX inference engine
│   ├── ui.py               # Dear PyGui UI (full version)
│   ├── ui_skybox.py        # Skybox v2.1 + Multi-shape + UE5
│   ├── ui_fast.py          # Fast CPU rendering version
│   ├── ui_minimal.py       # Minimal version
│   ├── gl_renderer.py      # ModernGL GPU renderer
│   ├── image_viewer.py     # 2D/3D image viewer
│   ├── i18n.py             # Chinese/English i18n
│   ├── preview.py          # OpenCV real-time preview
│   ├── ue_client.py        # HTTP client
│   ├── style_manager.py    # Style preset manager
│   └── requirements.txt    # Studio dependencies
│
├── plugin/                 # UE5 plugin
│   └── MooaToonInference/  # NNE inference + HTTP server + material control
│
├── data/                   # Training data
│   └── images/             # Reference images (222)
│
├── presets/                # Style presets (.style files)
├── docs/                   # Docs and screenshots
│
├── start_autotoon.bat      # One-click launcher
├── PRODUCT_SPEC.md         # Product specification
└── README.md
```

### Quick Start

#### 1. Train the Model

```bash
cd training
pip install -r requirements.txt
python dataset_verify.py   # Validate dataset
python train.py            # Train + export ONNX
```

#### 2. Launch Studio

```bash
cd Studio
pip install -r requirements.txt
python main.py             # Full version
# Or run alternative versions:
python ui_skybox.py        # Skybox + Multi-shape version
python ui_fast.py          # Fast CPU rendering
```

#### 3. Connect UE5

1. Copy `plugin/MooaToonInference/` into your UE5 project `Plugins/` directory
2. Build the UE5 project
3. The plugin auto-starts an HTTP server at `127.0.0.1:8080`
4. Click "Check UE5 Connection" in Studio

#### 4. One-Click Launch

Double-click `start_autotoon.bat` to launch Studio and get prompted to open UE5.

### Tech Stack

| Component | Technology |
|-----------|------------|
| Standalone UI | Python + Dear PyGui |
| GPU Rendering | ModernGL (Phong shader) |
| CPU Rendering | NumPy vectorized computation |
| AI Inference | onnxruntime (ResNet18) |
| Image Preview | OpenCV tone mapping |
| UE5 Communication | HTTP (requests ↔ HttpServer) |
| UE5 Plugin | C++ + NNE + Json |
| i18n | Chinese / English |

---

<a name="autotoon-en"></a>
## AutoToon (English)

AI-assisted UE5 real-time stylization tool — upload a reference image, automatically extract style parameters, and apply to your UE5 scene in one click.

**Current Version: v2.1.0**

### Features

- **AI Style Extraction** - Upload reference image, auto-extract toon style parameters
- **Multi-Shape Preview** - Sphere, Cube, Cylinder, Torus, Cone, Icosahedron (6 shapes)
- **9 Skybox Presets** - Studio Gray, Warm Sunset, Cool Dawn, HDR White, etc. + Custom Image Support
- **Advanced Rendering** - SSS, Anisotropic Specular, Metallic, Roughness parameters
- **Camera Control** - Mouse drag rotation + slider controls
- **Style Presets** - Save/Load material configurations
- **UE5 Integration** - HTTP communication with UE5 plugin
- **Batch Processing** - Folder-based AI inference for multiple images
- **Keyboard Shortcuts** - 1-6 shapes, R reset camera, M reset material, Space auto-rotate
- **Screenshot Export** - PNG with timestamp

### Project Structure

```
AutoToon/
├── training/               # Model training pipeline
│   ├── train.py            # ResNet18 training + ONNX export
│   ├── infer_test.py       # Local inference validation
│   ├── dataset_verify.py   # Dataset integrity check
│   ├── material_params.py  # 53-dim parameter system
│   ├── labels.csv          # Training labels (198 entries)
│   ├── requirements.txt    # Training dependencies
│   └── ue_scripts/         # UE5 Python scripts
│       ├── ue_record_params.py
│       ├── ue_apply_labels.py
│       └── ue_nne_infer.py
│
├── Studio/                 # Standalone app (AutoToonStudio)
│   ├── main.py             # Entry point
│   ├── engine.py           # ONNX inference engine
│   ├── ui.py               # Dear PyGui UI (full version)
│   ├── ui_skybox.py        # Skybox + Multi-shape version
│   ├── ui_fast.py          # Fast CPU rendering version
│   ├── ui_minimal.py       # Minimal version
│   ├── gl_renderer.py      # ModernGL GPU renderer
│   ├── image_viewer.py     # 2D/3D image viewer
│   ├── i18n.py             # Chinese/English i18n
│   ├── preview.py          # OpenCV real-time preview
│   ├── ue_client.py        # HTTP client
│   ├── style_manager.py    # Style preset manager
│   └── requirements.txt    # Studio dependencies
│
├── plugin/                 # UE5 plugin
│   └── MooaToonInference/  # NNE inference + HTTP server + material control
│
├── data/                   # Training data
│   └── images/             # Reference images (222)
│
├── presets/                # Style presets (.style files)
├── docs/                   # Docs and screenshots
│
├── start_autotoon.bat      # One-click launcher
├── PRODUCT_SPEC.md         # Product specification
└── README.md
```

### Quick Start

#### 1. Train the Model

```bash
cd training
pip install -r requirements.txt
python dataset_verify.py   # Validate dataset
python train.py            # Train + export ONNX
```

#### 2. Launch Studio

```bash
cd Studio
pip install -r requirements.txt
python main.py             # Full version
# Or run alternative versions:
python ui_skybox.py        # Skybox + Multi-shape version
python ui_fast.py          # Fast CPU rendering
```

#### 3. Connect UE5

1. Copy `plugin/MooaToonInference/` into your UE5 project `Plugins/` directory
2. Build the UE5 project
3. The plugin auto-starts an HTTP server at `127.0.0.1:8080`
4. Click "Check UE5 Connection" in Studio

#### 4. One-Click Launch

Double-click `start_autotoon.bat` to launch Studio and get prompted to open UE5.

### Tech Stack

| Component | Technology |
|-----------|------------|
| Standalone UI | Python + Dear PyGui |
| GPU Rendering | ModernGL (Phong shader) |
| CPU Rendering | NumPy vectorized computation |
| AI Inference | onnxruntime (ResNet18) |
| Image Preview | OpenCV tone mapping |
| UE5 Communication | HTTP (requests ↔ HttpServer) |
| UE5 Plugin | C++ + NNE + Json |
| i18n | Chinese / English |
