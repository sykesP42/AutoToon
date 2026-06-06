# AutoToon 实时联动功能设计文档

版本：1.0
日期：2026-06-07
状态：待批准

---

## 背景

当前 AutoToon Studio 与 UE5 的通信采用 HTTP 请求-响应模式，用户每次修改参数后需要手动点击"发送"按钮才能更新 UE5 场景。这导致：

1. **交互不流畅** - 调参时无法实时看到效果
2. **效率低下** - 频繁点击发送按钮
3. **无法双向同步** - UE5 中的修改无法反馈到 Studio

本次设计旨在实现 Studio 与 UE5 之间的实时双向材质参数同步。

---

## 设计目标

### 核心功能

1. **Studio → UE5 实时推送** - 滑块拖动时自动发送参数到 UE5
2. **UE5 → Studio 实时同步** - UE5 中修改材质参数时自动更新 Studio 滑块
3. **连接状态可视化** - 显示 WebSocket 连接状态、延迟等信息
4. **降级兼容** - WebSocket 不可用时降级到现有 HTTP 模式

### 非功能需求

| 指标 | 要求 |
|------|------|
| 延迟 | 参数同步延迟 < 50ms |
| 可靠性 | 断线自动重连，不影响 UI 操作 |
| 兼容性 | UE5.4+，Windows 10/11 |

---

## 架构设计

### 整体架构

```
┌─────────────────────────────────────┐         ┌─────────────────────────────────────┐
│        AutoToon Studio              │         │          UE5 Plugin                  │
│        (Python/DearPyGui)           │         │          (C++ WebSocket)            │
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

### 端口规划

| 服务 | 端口 | 用途 |
|------|------|------|
| HTTP Server | **4848** | 健康检查、手动发送参数（现有功能保留） |
| WebSocket Server | **4849** | 实时双向联动（新增） |

**选择理由**: 4848 = "AT" (AutoToon) 谐音，易记且不常见，避免与其他软件冲突。

---

## 组件设计

### 1. Studio 端

#### 1.1 新增文件: `Studio/ws_client.py`

WebSocket 客户端，负责实时双向通信。

```python
class UE5WebSocketClient:
    """UE5 WebSocket 客户端"""

    def __init__(self, host: str = "127.0.0.1", port: int = 4849):
        self.url = f"ws://{host}:{port}"
        self.connected = False
        self.ws = None
        self.callbacks = []  # 参数更新回调列表

    async def connect(self) -> bool:
        """建立 WebSocket 连接"""
        ...

    async def disconnect(self):
        """断开连接"""
        ...

    async def send_params(self, params: dict):
        """发送材质参数到 UE5"""
        ...

    def on_params_received(self, callback):
        """注册参数接收回调"""
        ...

    async def _receive_loop(self):
        """接收消息循环"""
        ...

    async def _reconnect_loop(self):
        """断线重连机制（每 5 秒尝试重连）"""
        ...
```

**关键特性**:
- 异步非阻塞，不影响 UI 响应
- 自动断线重连
- 支持多个回调监听

#### 1.2 修改文件: `Studio/ue_client.py`

更新默认端口为 4848。

```python
def __init__(self, host: str = "127.0.0.1", port: int = 4848, timeout: float = 3.0):
    ...
```

#### 1.3 修改文件: `Studio/ui_skybox.py`

添加实时联动 UI 和逻辑。

**UI 变更**:
```
┌─────────────────────────────────────┐
│ UE5 Connection                      │
│ ─────────────────────────────────── │
│ [Check UE5]  Status: Connected ✓    │
│                                     │
│ [✓] Real-time Sync (WebSocket)      │
│ ─────────────────────────────────── │
│ WebSocket: Connected ✓              │
│ Latency: 12ms                       │
│                                     │
│ [Send to UE5]  (HTTP fallback)      │
└─────────────────────────────────────┘
```

**逻辑变更**:
1. 添加 `realtime_sync` 开关变量
2. 滑块回调：联动开启时调用 `ws_client.send_params()`
3. 接收回调：收到 UE5 参数时更新滑块值（避免循环触发）
4. 启动时自动连接 WebSocket

---

### 2. UE5 Plugin 端

#### 2.1 新增文件: `MooaToonWebSocketServer.h`

```cpp
#pragma once

#include "CoreMinimal.h"
#include "IWebSocketServer.h"
#include "Containers/Array.h"

class MOOATOONINFERENCE_API FMooaToonWebSocketServer
{
public:
    /** 启动 WebSocket 服务器 */
    bool Start(int32 Port = 4849);

    /** 停止服务器 */
    void Stop();

    /** 是否正在运行 */
    bool IsRunning() const { return bRunning; }

    /** 发送参数到所有客户端 */
    void BroadcastParams(const TSharedPtr<FJsonObject>& Params);

    /** 设置参数接收回调 */
    void SetOnParamsReceived(TFunction<void(const TSharedPtr<FJsonObject>&)> Callback);

private:
    void OnClientConnected(IWebSocket* Socket);
    void OnClientDisconnected(IWebSocket* Socket);
    void OnMessage(IWebSocket* Socket, const FString& Message);

    TSharedPtr<IWebSocketServer> Server;
    TArray<IWebSocket*> ConnectedClients;
    TFunction<void(const TSharedPtr<FJsonObject>&)> OnParamsReceivedCallback;
    bool bRunning = false;
};
```

#### 2.2 新增文件: `MooaToonWebSocketServer.cpp`

```cpp
#include "MooaToonWebSocketServer.h"
#include "MooaToonInferenceLibrary.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"

bool FMooaToonWebSocketServer::Start(int32 Port)
{
    // 创建 WebSocket 服务器
    Server = IWebSocketServer::Create();
    if (!Server.IsValid())
    {
        return false;
    }

    // 绑定回调
    Server->OnClientConnected().BindRaw(this, &FMooaToonWebSocketServer::OnClientConnected);
    Server->OnClientDisconnected().BindRaw(this, &FMooaToonWebSocketServer::OnClientDisconnected);
    Server->OnMessage().BindRaw(this, &FMooaToonWebSocketServer::OnMessage);

    // 启动监听
    if (!Server->Listen(Port))
    {
        return false;
    }

    bRunning = true;
    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] 服务器已启动: ws://127.0.0.1:%d"), Port);
    return true;
}

void FMooaToonWebSocketServer::OnMessage(IWebSocket* Socket, const FString& Message)
{
    // 解析 JSON
    TSharedPtr<FJsonObject> Json;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);

    if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
    {
        UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] JSON 解析失败"));
        return;
    }

    // 检查消息类型
    FString Type = Json->GetStringField(TEXT("type"));
    if (Type == TEXT("params_update"))
    {
        // 应用材质参数
        const TSharedPtr<FJsonObject>* ParamsObj;
        if (Json->TryGetObjectField(TEXT("params"), ParamsObj))
        {
            ApplyMaterialParams(*ParamsObj);

            // 通知回调
            if (OnParamsReceivedCallback)
            {
                OnParamsReceivedCallback(*ParamsObj);
            }
        }
    }
}

void FMooaToonWebSocketServer::BroadcastParams(const TSharedPtr<FJsonObject>& Params)
{
    // 构建消息
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("params_update"));
    Message->SetObjectField(TEXT("params"), Params);
    Message->SetStringField(TEXT("source"), TEXT("ue5"));

    FString JsonStr;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&JsonStr);
    FJsonSerializer::Serialize(Message.ToSharedRef(), Writer);

    // 广播到所有客户端
    for (IWebSocket* Client : ConnectedClients)
    {
        Client->Send(JsonStr);
    }
}
```

#### 2.3 修改文件: `MooaToonHttpServer.cpp`

更新默认端口为 4848。

```cpp
bool FMooaToonHttpServer::Start(int32 Port = 4848)
{
    ...
}
```

#### 2.4 修改文件: `MooaToonInferenceLibrary.h/cpp`

添加材质参数变化监听，用于 UE5 → Studio 同步。

```cpp
// 当材质参数被修改时调用
void OnMaterialParamsChanged(USkeletalMeshComponent* Component)
{
    // 收集当前参数
    TSharedPtr<FJsonObject> Params = CollectCurrentParams(Component);

    // 通过 WebSocket 广播
    if (WebSocketServer && WebSocketServer->IsRunning())
    {
        WebSocketServer->BroadcastParams(Params);
    }
}
```

---

## 通信协议

### 消息格式

所有消息使用 JSON 格式：

```json
{
  "type": "params_update",
  "params": {
    "shadow_r": 0.35,
    "shadow_g": 0.35,
    "shadow_b": 0.4,
    "specular": 0.6,
    "rim": 0.5,
    "outline": 2.0,
    "sss": 0.3,
    "aniso": 0.2,
    "metallic": 0.0,
    "roughness": 0.5
  },
  "source": "studio" | "ue5",
  "timestamp": 1717834567890
}
```

### 消息类型

| type | 方向 | 说明 |
|------|------|------|
| `params_update` | 双向 | 材质参数更新 |
| `ping` | Studio → UE5 | 心跳检测 |
| `pong` | UE5 → Studio | 心跳响应 |

### 防止循环触发

当 Studio 收到 UE5 的参数更新时，需要更新滑块值但不触发发送：

```python
# ui_skybox.py
def on_ws_params_received(params):
    """WebSocket 参数接收回调"""
    global _updating_from_ue5
    _updating_from_ue5 = True  # 设置标志

    # 更新滑块值
    dpg.set_value("slider_shadow_r", params["shadow_r"])
    # ... 其他参数

    _updating_from_ue5 = False  # 清除标志

def on_slider_changed(sender, value):
    """滑块变化回调"""
    if _updating_from_ue5:
        return  # 来自 UE5 的更新，不回发

    # 联动开启时发送到 UE5
    if realtime_sync and ws_client.connected:
        ws_client.send_params(material)
```

---

## 错误处理

### 连接失败

| 场景 | 处理方式 |
|------|----------|
| UE5 未启动 | 显示 "Disconnected"，每 5 秒自动重连 |
| 连接中断 | 自动重连，不中断 UI 操作 |
| 端口被占用 | 显示错误提示，建议检查端口 |

### 消息处理

| 场景 | 处理方式 |
|------|----------|
| JSON 格式错误 | 忽略该消息，记录日志 |
| 缺少必要字段 | 忽略该消息，记录日志 |
| 参数值越界 | Clamp 到有效范围 |

### 降级机制

```
┌────────────────┐
│ 启动 Studio    │
└───────┬────────┘
        ▼
┌────────────────┐
│ 尝试 WS 连接   │
└───────┬────────┘
        │
   ┌────┴────┐
   ▼         ▼
 连接成功   连接失败
   │         │
   ▼         ▼
实时联动   降级到 HTTP
模式       模式
```

---

## 开发顺序

### Phase 1: 端口迁移
1. 更新 `ue_client.py` 默认端口 → 4848
2. 更新 `MooaToonHttpServer.cpp` 默认端口 → 4848
3. 测试现有 HTTP 功能正常

### Phase 2: Studio 端 WebSocket 客户端
1. 创建 `ws_client.py`
2. 实现连接、发送、接收、重连逻辑
3. 单元测试

### Phase 3: UE5 端 WebSocket 服务器
1. 创建 `MooaToonWebSocketServer.h/cpp`
2. 集成到 `MooaToonInferenceModule`
3. 测试连接和消息收发

### Phase 4: UI 集成
1. 修改 `ui_skybox.py` 添加实时联动开关
2. 实现滑块自动发送
3. 实现参数接收更新

### Phase 5: 测试与优化
1. 端到端测试
2. 延迟测试
3. 断线重连测试
4. 性能优化

---

## 验收标准

1. ✅ 启动 Studio 后自动连接 UE5 WebSocket
2. ✅ 拖动滑块时 UE5 场景实时更新（延迟 < 50ms）
3. ✅ UE5 中修改材质参数时 Studio 滑块同步更新
4. ✅ 显示 WebSocket 连接状态和延迟
5. ✅ 断线后自动重连
6. ✅ WebSocket 不可用时降级到 HTTP 模式
7. ✅ 现有 HTTP 功能（健康检查、手动发送）保持可用

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| UE5 WebSocket 模块不稳定 | 低 | 高 | 充分测试，准备 HTTP 降级 |
| 异步操作导致 UI 卡顿 | 中 | 中 | 使用独立线程，确保回调在主线程执行 |
| 参数循环触发 | 中 | 高 | 使用标志位防止回传 |
| 端口冲突 | 低 | 低 | 文档说明如何修改端口 |

---

## 未来扩展

1. **实时截图** - UE5 定时发送场景截图到 Studio
2. **多客户端支持** - 多个 Studio 实例连接同一 UE5
3. **参数录制** - 记录参数变化时间线，支持回放
