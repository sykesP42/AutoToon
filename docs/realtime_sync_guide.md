# AutoToon 实时联动功能使用指南

## 功能概述

AutoToon 提供了 **Studio**（Python 独立应用）与 **UE5**（虚幻引擎插件）之间的实时双向通信功能，包括：

1. **实时参数同步** - Studio 滑块拖动时自动更新 UE5 场景
2. **双向联动** - UE5 中修改材质参数时自动同步到 Studio
3. **实时截图预览** - UE5 视口画面实时显示在 Studio 中

---

## 系统架构

```
┌─────────────────────────────────────┐         ┌─────────────────────────────────────┐
│        AutoToon Studio              │         │          UE5 Plugin                  │
│        (Python/DearPyGui)           │         │          (C++)                       │
│                                     │         │                                     │
│  ┌─────────────┐    ┌────────────┐ │  WS    │  ┌─────────────┐    ┌────────────┐  │
│  │  UI Layer   │←──→│ ws_client  │ │←───────→│  │ WS Server   │←──→│  Material  │  │
│  │ (ui_skybox) │    │   .py      │ │  4849  │  │             │    │  Control   │  │
│  └─────────────┘    └────────────┘ │         │  └─────────────┘    └────────────┘  │
│                                     │         │                                     │
│  ┌─────────────┐    ┌────────────┐ │  HTTP  │  ┌─────────────┐                     │
│  │  HTTP Mode  │←──→│ ue_client  │ │←───────→│  │ HTTP Server │                     │
│  │  (fallback) │    │   .py      │ │  4848  │  │             │                     │
│  └─────────────┘    └────────────┘ │         │  └─────────────┘                     │
│                                     │         │                                     │
└─────────────────────────────────────┘         └─────────────────────────────────────┘
```

### 端口说明

| 服务 | 端口 | 用途 |
|------|------|------|
| HTTP Server | **4848** | 健康检查、手动发送参数 |
| WebSocket Server | **4849** | 实时双向联动、截图传输 |

---

## 快速开始

### 1. 启动 UE5

1. 打开您的 UE5 项目
2. 确保 `MooaToonInference` 插件已启用
3. 编译项目（如果需要）
4. 启动 PIE（Play In Editor）或运行游戏

**确认服务器启动**：
查看 UE5 输出日志，应该看到：
```
[MooaToon] HTTP Server started (port 4848)
[MooaToon] WebSocket Server started (port 4849)
```

### 2. 启动 Studio

```bash
cd Studio
pip install -r requirements.txt  # 首次运行需要安装依赖
python ui_skybox.py
```

### 3. 连接 UE5

在 Studio UI 中：

1. 点击 **"Check UE5"** 按钮 - 验证 HTTP 连接
2. 开启 **"Real-time Sync (WebSocket)"** 开关 - 启动 WebSocket 实时联动
3. 开启 **"UE5 Preview"** 开关 - 启动实时截图预览

---

## 功能详解

### 实时参数同步

**工作流程**：
1. 在 Studio 中拖动材质参数滑块
2. 参数通过 WebSocket 发送到 UE5（JSON 格式）
3. UE5 接收参数并应用到场景材质
4. 延迟 < 50ms

**参数列表**：
- 阴影颜色 (shadow_r, shadow_g, shadow_b)
- 高光强度 (specular)
- 边缘光 (rim)
- 描边宽度 (outline)
- SSS、金属度、粗糙度等

### 双向联动

**工作流程**：
1. UE5 中修改材质参数（通过蓝图或控制台）
2. UE5 通过 WebSocket 广播参数到 Studio
3. Studio 接收参数并更新滑块值
4. **防止循环触发**：Studio 接收更新时不回发

### 实时截图预览

**工作流程**：
1. UE5 捕获视口画面（最大 640x480）
2. 编码为 JPEG（质量 75）
3. 通过 WebSocket 发送二进制数据
4. Studio 解码并显示在预览窗口

**性能配置**：
- 默认帧率：10 FPS（可配置）
- 消息格式：`IMG` + 类型标记 + JPEG 数据

---

## 消息协议

### 文本消息（JSON）

#### params_update - 参数同步
```json
{
  "type": "params_update",
  "params": {
    "shadow_r": 0.35,
    "shadow_g": 0.35,
    "shadow_b": 0.4,
    "specular": 0.6,
    "rim": 0.5,
    "outline": 2.0
  },
  "source": "studio",
  "timestamp": 1718123456789
}
```

#### ping/pong - 心跳检测
```json
// Ping
{
  "type": "ping",
  "timestamp": 1718123456789
}

// Pong
{
  "type": "pong",
  "timestamp": 1718123456789,
  "server_time": 1718123456789
}
```

#### start_screenshot / stop_screenshot - 截图控制
```json
{
  "type": "start_screenshot",
  "interval": 0.1,
  "timestamp": 1718123456789
}
```

### 二进制消息 - 截图传输

```
字节 0-2: "IMG" (ASCII)
字节 3:   格式类型 (0x01 = JPEG)
字节 4+:  JPEG 数据
```

---

## 测试脚本

### HTTP 通信测试
```bash
cd Studio
python test_http_link.py
```

测试内容：
- 健康检查（`/api/health`）
- 参数发送（`POST /api/style`）
- 多次发送测试

### WebSocket 通信测试
```bash
cd Studio
python test_ws_link.py
```

测试内容：
- WebSocket 连接
- 参数发送
- Ping/Pong 心跳
- 断线重连

---

## 常见问题

### Q: WebSocket 连接失败

**可能原因**：
1. UE5 未启动或插件未加载
2. 端口 4849 被其他程序占用
3. 防火墙阻止连接

**解决方案**：
1. 检查 UE5 输出日志确认服务器启动
2. 使用 `netstat -an | findstr 4849` 检查端口状态
3. 关闭防火墙或添加例外规则

### Q: 实时预览不显示

**可能原因**：
1. WebSocket 未连接
2. 截图功能未启动

**解决方案**：
1. 先开启 "Real-time Sync" 连接 WebSocket
2. 再开启 "UE5 Preview" 启动截图
3. 检查 UE5 是否有视口窗口

### Q: 参数同步延迟高

**可能原因**：
1. 网络延迟
2. UE5 渲染负载高

**解决方案**：
1. 降低截图帧率（默认 10 FPS）
2. 检查网络连接质量
3. 查看 `pong` 消息中的延迟值

---

## 配置说明

### 修改端口

如需修改默认端口：

**UE5 端**：
```cpp
// MooaToonInferenceModule.cpp
HttpServer->Start(4848);      // HTTP 端口
WebSocketServer->Start(4849); // WebSocket 端口
```

**Studio 端**：
```python
# ue_client.py
ue_client = UE5Client(port=4848)

# ws_client.py
ws_client = UE5WebSocketClient(port=4849)
```

### 修改截图参数

**UE5 端**：
```cpp
// MooaToonWebSocketServer.h
int32 MaxScreenshotSize = 640;   // 最大分辨率
int32 JPEGQuality = 75;          // JPEG 质量

// 启动截图
StartPeriodicScreenshot(0.1f);   // 0.1秒 = 10 FPS
```

---

## 版本历史

| 版本 | 功能 |
|------|------|
| v2.3.0 | HTTP 通信、手动参数发送 |
| v2.4.0 | WebSocket 实时参数同步 |
| v2.5.0 | 双向联动、实时截图预览 |

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `Studio/ws_client.py` | WebSocket 客户端 |
| `Studio/ue_client.py` | HTTP 客户端 |
| `Studio/ui_skybox.py` | Studio 主 UI |
| `Studio/test_http_link.py` | HTTP 测试脚本 |
| `Studio/test_ws_link.py` | WebSocket 测试脚本 |
| `plugin/MooaToonWebSocketServer.*` | UE5 WebSocket 服务器 |
| `plugin/MooaToonHttpServer.*` | UE5 HTTP 服务器 |