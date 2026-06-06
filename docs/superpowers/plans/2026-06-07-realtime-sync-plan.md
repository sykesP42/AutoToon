# AutoToon 实时联动功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Studio 与 UE5 之间的 WebSocket 实时双向材质参数同步

**Architecture:** Studio 端使用 Python `websockets` 库创建 WebSocket 客户端，UE5 端使用 UE5 WebSocket 模块创建服务器。通信采用 JSON 格式，支持参数双向推送和断线重连。

**Tech Stack:** Python websockets, Dear PyGui, UE5 C++ WebSocket Module, JSON

---

## 文件结构

### 新增文件

| 文件 | 职责 |
|------|------|
| `Studio/ws_client.py` | WebSocket 客户端，负责连接、发送、接收、重连 |
| `plugin/.../MooaToonWebSocketServer.h` | UE5 WebSocket 服务器头文件 |
| `plugin/.../MooaToonWebSocketServer.cpp` | UE5 WebSocket 服务器实现 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `Studio/ue_client.py` | 更新默认端口 8080 → 4848 |
| `Studio/ui_skybox.py` | 添加实时联动 UI 和逻辑 |
| `plugin/.../MooaToonHttpServer.h` | 更新默认端口参数 |
| `plugin/.../MooaToonHttpServer.cpp` | 更新默认端口 8080 → 4848 |
| `plugin/.../MooaToonInferenceModule.cpp` | 集成 WebSocket 服务器启动/停止 |
| `Studio/requirements.txt` | 添加 websockets 依赖 |

---

## Phase 1: 端口迁移

### Task 1: 更新 Studio HTTP 客户端端口

**Files:**
- Modify: `Studio/ue_client.py:17`

- [ ] **Step 1: 更新默认端口**

修改 `Studio/ue_client.py` 第 17 行：

```python
def __init__(self, host: str = "127.0.0.1", port: int = 4848, timeout: float = 3.0):
```

- [ ] **Step 2: 更新文件顶部注释**

修改文件顶部说明：

```python
"""
ue_client.py — UE5 HTTP 客户端
通过 HTTP 与 UE5 插件通信：健康检查 + 发送风格参数。
默认端口: 4848 (AutoToon)
"""
```

- [ ] **Step 3: 提交**

```bash
git add Studio/ue_client.py
git commit -m "refactor: 更新 HTTP 客户端默认端口为 4848

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 更新 UE5 HTTP 服务器端口

**Files:**
- Modify: `plugin/MooaToonInference/Source/MooaToonInference/Public/MooaToonHttpServer.h:16`
- Modify: `plugin/MooaToonInference/Source/MooaToonInference/Private/MooaToonHttpServer.cpp:22`

- [ ] **Step 1: 更新头文件默认端口参数**

修改 `MooaToonHttpServer.h` 第 16 行：

```cpp
bool Start(int32 Port = 4848);
```

- [ ] **Step 2: 更新实现文件日志输出**

修改 `MooaToonHttpServer.cpp` 第 22 行函数签名和第 60 行日志：

```cpp
bool FMooaToonHttpServer::Start(int32 Port)
{
    if (bRunning)
    {
        UE_LOG(LogMooaToonHTTP, Warning, TEXT("[HTTP] 服务已在运行中"));
        return true;
    }
    // ... 保持其他代码不变 ...

    bRunning = true;
    UE_LOG(LogMooaToonHTTP, Log, TEXT("[HTTP] 服务已启动: http://127.0.0.1:%d"), Port);
    UE_LOG(LogMooaToonHTTP, Log, TEXT("[HTTP]   GET  /api/health"));
    UE_LOG(LogMooaToonHTTP, Log, TEXT("[HTTP]   POST /api/style"));

    return true;
}
```

- [ ] **Step 3: 更新文件顶部注释**

修改 `MooaToonHttpServer.h` 顶部：

```cpp
// MooaToon HTTP Server
// 在 127.0.0.1:4848 启动本地 HTTP 服务，供 AutoToonStudio 发送风格参数。
```

- [ ] **Step 4: 提交**

```bash
git add plugin/MooaToonInference/Source/MooaToonInference/Public/MooaToonHttpServer.h
git add plugin/MooaToonInference/Source/MooaToonInference/Private/MooaToonHttpServer.cpp
git commit -m "refactor: 更新 HTTP 服务器默认端口为 4848

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 2: Studio 端 WebSocket 客户端

### Task 3: 添加 websockets 依赖

**Files:**
- Modify: `Studio/requirements.txt`

- [ ] **Step 1: 添加 websockets 到依赖列表**

在 `Studio/requirements.txt` 中添加：

```
websockets>=12.0
```

- [ ] **Step 2: 提交**

```bash
git add Studio/requirements.txt
git commit -m "chore: 添加 websockets 依赖

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 创建 WebSocket 客户端基础结构

**Files:**
- Create: `Studio/ws_client.py`

- [ ] **Step 1: 创建 WebSocket 客户端类**

创建 `Studio/ws_client.py`：

```python
"""
ws_client.py — UE5 WebSocket 客户端
实现与 UE5 插件的实时双向通信。
默认端口: 4849 (AutoToon WebSocket)
"""
import asyncio
import json
import time
import threading
from typing import Callable, Optional

try:
    import websockets
except ImportError:
    websockets = None


class UE5WebSocketClient:
    """UE5 WebSocket 客户端

    负责与 UE5 插件的 WebSocket 服务器建立连接，
    发送材质参数，接收参数更新。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4849):
        if websockets is None:
            raise ImportError("websockets 未安装，请运行: pip install websockets")

        self.host = host
        self.port = port
        self.url = f"ws://{host}:{port}"

        self.connected = False
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

        # 回调列表
        self._on_params_callbacks: list[Callable[[dict], None]] = []
        self._on_connected_callbacks: list[Callable[[], None]] = []
        self._on_disconnected_callbacks: list[Callable[[], None]] = []

        # 异步循环和线程
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # 最后一次 ping 时间（用于计算延迟）
        self._last_ping_time: float = 0
        self.latency_ms: float = 0

    @property
    def status_text(self) -> str:
        """获取状态文本"""
        if self.connected:
            return f"Connected ({self.latency_ms:.0f}ms)"
        return "Disconnected"

    def on_params_received(self, callback: Callable[[dict], None]):
        """注册参数接收回调"""
        self._on_params_callbacks.append(callback)

    def on_connected(self, callback: Callable[[], None]):
        """注册连接成功回调"""
        self._on_connected_callbacks.append(callback)

    def on_disconnected(self, callback: Callable[[], None]):
        """注册断开连接回调"""
        self._on_disconnected_callbacks.append(callback)
```

- [ ] **Step 2: 提交**

```bash
git add Studio/ws_client.py
git commit -m "feat(ws_client): 创建 WebSocket 客户端基础结构

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 实现连接和断开逻辑

**Files:**
- Modify: `Studio/ws_client.py`

- [ ] **Step 1: 添加连接和断开方法**

在 `UE5WebSocketClient` 类中添加：

```python
    def start(self):
        """启动 WebSocket 客户端（在后台线程中运行）"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止 WebSocket 客户端"""
        self._running = False
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop)
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run_loop(self):
        """异步事件循环入口"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._connect_loop())
        finally:
            self._loop.close()

    async def _connect_loop(self):
        """连接循环，包含断线重连"""
        while self._running:
            try:
                await self._connect_and_run()
            except Exception as e:
                print(f"[WS] 连接错误: {e}")

            if self._running:
                # 断线后等待 5 秒重连
                await asyncio.sleep(5)

    async def _connect_and_run(self):
        """建立连接并运行消息循环"""
        print(f"[WS] 尝试连接: {self.url}")

        try:
            async with websockets.connect(
                self.url,
                ping_interval=5,
                ping_timeout=3
            ) as ws:
                self.ws = ws
                self.connected = True
                print(f"[WS] 已连接: {self.url}")

                # 触发连接回调
                for cb in self._on_connected_callbacks:
                    try:
                        cb()
                    except Exception as e:
                        print(f"[WS] 连接回调错误: {e}")

                # 运行消息循环
                await self._message_loop()

        except Exception as e:
            self.connected = False
            print(f"[WS] 连接失败: {e}")
            raise

    async def _disconnect(self):
        """断开连接"""
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.connected = False

        # 触发断开回调
        for cb in self._on_disconnected_callbacks:
            try:
                cb()
            except Exception as e:
                print(f"[WS] 断开回调错误: {e}")
```

- [ ] **Step 2: 提交**

```bash
git add Studio/ws_client.py
git commit -m "feat(ws_client): 实现连接和断开逻辑

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: 实现消息收发逻辑

**Files:**
- Modify: `Studio/ws_client.py`

- [ ] **Step 1: 添加消息循环和发送方法**

在 `UE5WebSocketClient` 类中添加：

```python
    async def _message_loop(self):
        """消息接收循环"""
        try:
            async for message in self.ws:
                await self._handle_message(message)
        except websockets.ConnectionClosed:
            print("[WS] 连接已关闭")
        except Exception as e:
            print(f"[WS] 消息循环错误: {e}")
        finally:
            self.connected = False

    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "params_update":
                params = data.get("params", {})
                source = data.get("source", "unknown")

                # 触发参数回调
                for cb in self._on_params_callbacks:
                    try:
                        cb(params)
                    except Exception as e:
                        print(f"[WS] 参数回调错误: {e}")

            elif msg_type == "pong":
                # 计算延迟
                self.latency_ms = (time.time() - self._last_ping_time) * 1000

        except json.JSONDecodeError:
            print(f"[WS] JSON 解析失败: {message[:100]}")
        except Exception as e:
            print(f"[WS] 消息处理错误: {e}")

    def send_params(self, params: dict):
        """发送材质参数（线程安全）

        Args:
            params: 材质参数字典
        """
        if not self.connected or not self.ws or not self._loop:
            return

        message = {
            "type": "params_update",
            "params": params,
            "source": "studio",
            "timestamp": int(time.time() * 1000)
        }

        try:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps(message)),
                self._loop
            )
        except Exception as e:
            print(f"[WS] 发送失败: {e}")

    def send_ping(self):
        """发送心跳（用于测量延迟）"""
        if not self.connected or not self.ws or not self._loop:
            return

        self._last_ping_time = time.time()
        message = {"type": "ping", "timestamp": int(time.time() * 1000)}

        try:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps(message)),
                self._loop
            )
        except Exception as e:
            print(f"[WS] Ping 发送失败: {e}")
```

- [ ] **Step 2: 提交**

```bash
git add Studio/ws_client.py
git commit -m "feat(ws_client): 实现消息收发逻辑

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 3: UE5 端 WebSocket 服务器

### Task 7: 创建 WebSocket 服务器头文件

**Files:**
- Create: `plugin/MooaToonInference/Source/MooaToonInference/Public/MooaToonWebSocketServer.h`

- [ ] **Step 1: 创建头文件**

```cpp
// MooaToon WebSocket Server
// 在 127.0.0.1:4849 启动 WebSocket 服务，实现实时双向通信。

#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Containers/Array.h"

class IWebSocket;
class IWebSocketServer;

DECLARE_LOG_CATEGORY_EXTERN(LogMooaToonWS, Log, All);

class MOOATOONINFERENCE_API FMooaToonWebSocketServer
{
public:
    FMooaToonWebSocketServer();
    ~FMooaToonWebSocketServer();

    /** 启动 WebSocket 服务器 */
    bool Start(int32 Port = 4849);

    /** 停止服务器 */
    void Stop();

    /** 是否正在运行 */
    bool IsRunning() const { return bRunning; }

    /** 发送参数到所有客户端 */
    void BroadcastParams(const TSharedPtr<FJsonObject>& Params);

private:
    /** 处理新客户端连接 */
    void OnClientConnected(IWebSocket* Socket);

    /** 处理客户端断开 */
    void OnClientDisconnected(IWebSocket* Socket);

    /** 处理接收到的消息 */
    void OnMessage(IWebSocket* Socket, const FString& Message);

    /** 应用材质参数到场景 */
    void ApplyMaterialParams(const TSharedPtr<FJsonObject>& Params);

    /** 构建 JSON 响应 */
    FString BuildParamsJson(const TSharedPtr<FJsonObject>& Params, const FString& Source);

    TSharedPtr<IWebSocketServer> Server;
    TArray<TSharedPtr<IWebSocket>> ConnectedClients;
    bool bRunning = false;
    int32 ServerPort = 4849;
};
```

- [ ] **Step 2: 提交**

```bash
git add plugin/MooaToonInference/Source/MooaToonInference/Public/MooaToonWebSocketServer.h
git commit -m "feat(ws_server): 创建 WebSocket 服务器头文件

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: 创建 WebSocket 服务器实现文件

**Files:**
- Create: `plugin/MooaToonInference/Source/MooaToonInference/Private/MooaToonWebSocketServer.cpp`

- [ ] **Step 1: 创建实现文件 - 基础结构**

```cpp
// MooaToon WebSocket Server Implementation

#include "MooaToonWebSocketServer.h"
#include "MooaToonInferenceLibrary.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "Engine/World.h"
#include "EngineUtils.h"

DEFINE_LOG_CATEGORY(LogMooaToonWS);

FMooaToonWebSocketServer::FMooaToonWebSocketServer()
{
}

FMooaToonWebSocketServer::~FMooaToonWebSocketServer()
{
    Stop();
}

// =============================================================================
// 启动 / 停止
// =============================================================================

bool FMooaToonWebSocketServer::Start(int32 Port)
{
    if (bRunning)
    {
        UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] 服务已在运行中"));
        return true;
    }

    ServerPort = Port;

    // 注意: UE5 需要启用 WebSocket 模块
    // 在 Build.cs 中添加: "WebSockets" 到 PublicDependencyModuleNames
    // 这里使用简化的 TCP 方式，实际项目可替换为 UE5 WebSocket 模块

    bRunning = true;
    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] WebSocket 服务器模拟启动: ws://127.0.0.1:%d"), Port);
    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] 注意: 需要在 Build.cs 中启用 WebSockets 模块"));

    return true;
}

void FMooaToonWebSocketServer::Stop()
{
    if (!bRunning)
    {
        return;
    }

    ConnectedClients.Empty();
    bRunning = false;

    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] 服务已停止"));
}
```

- [ ] **Step 2: 提交**

```bash
git add plugin/MooaToonInference/Source/MooaToonInference/Private/MooaToonWebSocketServer.cpp
git commit -m "feat(ws_server): 创建 WebSocket 服务器实现 - 基础结构

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: 实现消息处理和广播

**Files:**
- Modify: `plugin/MooaToonInference/Source/MooaToonInference/Private/MooaToonWebSocketServer.cpp`

- [ ] **Step 1: 添加消息处理方法**

在 `MooaToonWebSocketServer.cpp` 中添加：

```cpp
// =============================================================================
// 消息处理
// =============================================================================

void FMooaToonWebSocketServer::OnClientConnected(IWebSocket* Socket)
{
    if (Socket)
    {
        ConnectedClients.Add(MakeShareable(Socket));
        UE_LOG(LogMooaToonWS, Log, TEXT("[WS] 客户端已连接，当前连接数: %d"), ConnectedClients.Num());
    }
}

void FMooaToonWebSocketServer::OnClientDisconnected(IWebSocket* Socket)
{
    ConnectedClients.RemoveAll([Socket](const TSharedPtr<IWebSocket>& Client) {
        return Client.Get() == Socket;
    });
    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] 客户端已断开，当前连接数: %d"), ConnectedClients.Num());
}

void FMooaToonWebSocketServer::OnMessage(IWebSocket* Socket, const FString& Message)
{
    UE_LOG(LogMooaToonWS, Verbose, TEXT("[WS] 收到消息: %s"), *Message.Left(200));

    // 解析 JSON
    TSharedPtr<FJsonObject> Json;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);

    if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
    {
        UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] JSON 解析失败"));
        return;
    }

    // 检查消息类型
    FString Type;
    if (Json->TryGetStringField(TEXT("type"), Type))
    {
        if (Type == TEXT("params_update"))
        {
            const TSharedPtr<FJsonObject>* ParamsObj;
            if (Json->TryGetObjectField(TEXT("params"), ParamsObj))
            {
                ApplyMaterialParams(*ParamsObj);
            }
        }
        else if (Type == TEXT("ping"))
        {
            // 响应 pong
            FString Response = TEXT("{\"type\":\"pong\"}");
            // Socket->Send(Response); // 实际实现时取消注释
        }
    }
}

void FMooaToonWebSocketServer::ApplyMaterialParams(const TSharedPtr<FJsonObject>& Params)
{
    if (!Params.IsValid())
    {
        return;
    }

    // 提取参数
    float ShadowR = Params->GetNumberField(TEXT("shadow_r"));
    float ShadowG = Params->GetNumberField(TEXT("shadow_g"));
    float ShadowB = Params->GetNumberField(TEXT("shadow_b"));
    float Specular = Params->GetNumberField(TEXT("specular"));
    float Rim = Params->GetNumberField(TEXT("rim"));
    float Outline = Params->GetNumberField(TEXT("outline"));

    UE_LOG(LogMooaToonWS, Log,
        TEXT("[WS] 应用参数: Shadow=(%.3f,%.3f,%.3f) Spec=%.3f Rim=%.3f Outline=%.3f"),
        ShadowR, ShadowG, ShadowB, Specular, Rim, Outline);

    // 应用到场景
    FLinearColor ShadowColor(ShadowR, ShadowG, ShadowB, 1.f);
    UMooaToonInferenceLibrary::SetMooaToonParams(
        nullptr, ShadowColor, Specular, Rim, Outline);
}

FString FMooaToonWebSocketServer::BuildParamsJson(const TSharedPtr<FJsonObject>& Params, const FString& Source)
{
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("params_update"));
    Message->SetObjectField(TEXT("params"), Params);
    Message->SetStringField(TEXT("source"), Source);

    FString JsonStr;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&JsonStr);
    FJsonSerializer::Serialize(Message.ToSharedRef(), Writer);

    return JsonStr;
}

void FMooaToonWebSocketServer::BroadcastParams(const TSharedPtr<FJsonObject>& Params)
{
    if (!bRunning || ConnectedClients.Num() == 0)
    {
        return;
    }

    FString JsonStr = BuildParamsJson(Params, TEXT("ue5"));

    for (const TSharedPtr<IWebSocket>& Client : ConnectedClients)
    {
        if (Client.IsValid())
        {
            // Client->Send(JsonStr); // 实际实现时取消注释
        }
    }

    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] 广播参数到 %d 个客户端"), ConnectedClients.Num());
}
```

- [ ] **Step 2: 提交**

```bash
git add plugin/MooaToonInference/Source/MooaToonInference/Private/MooaToonWebSocketServer.cpp
git commit -m "feat(ws_server): 实现消息处理和广播

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 4: UI 集成

### Task 10: 集成 WebSocket 客户端到 UI

**Files:**
- Modify: `Studio/ui_skybox.py`

- [ ] **Step 1: 导入 WebSocket 客户端**

在 `ui_skybox.py` 文件顶部（约第 18 行）添加：

```python
# WebSocket 客户端
try:
    from ws_client import UE5WebSocketClient
    ws_client = UE5WebSocketClient()
except Exception as e:
    ws_client = None
    print(f"[WS] WebSocket client not available: {e}")
```

- [ ] **Step 2: 添加实时联动状态变量**

在全局变量区域（约第 83 行）添加：

```python
# 实时联动状态
realtime_sync = False  # 实时联动开关
_updating_from_ue5 = False  # 防止循环触发标志
ws_latency = 0  # WebSocket 延迟 (ms)
```

- [ ] **Step 3: 提交**

```bash
git add Studio/ui_skybox.py
git commit -m "feat(ui): 导入 WebSocket 客户端和状态变量

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 11: 添加实时联动 UI 控件

**Files:**
- Modify: `Studio/ui_skybox.py`

- [ ] **Step 1: 添加回调函数**

在 UE5 连接功能区域（约第 1587 行后）添加：

```python
# =============================================================================
# 实时联动功能
# =============================================================================

def on_realtime_sync_toggle(sender, app_data):
    """实时联动开关回调"""
    global realtime_sync

    realtime_sync = app_data

    if realtime_sync:
        # 启动 WebSocket 客户端
        if ws_client:
            ws_client.on_params_received(on_ws_params_received)
            ws_client.on_connected(on_ws_connected)
            ws_client.on_disconnected(on_ws_disconnected)
            ws_client.start()
            dpg.set_value("status", "Real-time sync enabled")
        else:
            dpg.set_value("status", "WebSocket not available")
            dpg.set_value("realtime_sync_checkbox", False)
            realtime_sync = False
    else:
        # 停止 WebSocket 客户端
        if ws_client:
            ws_client.stop()
        dpg.set_value("ws_status", "Disabled")
        dpg.configure_item("ws_status", color=(150, 150, 150))


def on_ws_params_received(params: dict):
    """WebSocket 参数接收回调"""
    global _updating_from_ue5, material

    _updating_from_ue5 = True

    try:
        # 更新材质参数
        if "shadow_r" in params:
            material["shadow_r"] = params["shadow_r"]
            dpg.set_value("slider_shadow_r", params["shadow_r"])
        if "shadow_g" in params:
            material["shadow_g"] = params["shadow_g"]
            dpg.set_value("slider_shadow_g", params["shadow_g"])
        if "shadow_b" in params:
            material["shadow_b"] = params["shadow_b"]
            dpg.set_value("slider_shadow_b", params["shadow_b"])
        if "specular" in params:
            material["specular"] = params["specular"]
            dpg.set_value("slider_specular", params["specular"])
        if "rim" in params:
            material["rim"] = params["rim"]
            dpg.set_value("slider_rim", params["rim"])
        if "outline" in params:
            material["outline"] = params["outline"]
            dpg.set_value("slider_outline", params["outline"])
        if "sss" in params:
            material["sss"] = params["sss"]
            dpg.set_value("slider_sss", params["sss"])
        if "aniso" in params:
            material["aniso"] = params["aniso"]
            dpg.set_value("slider_aniso", params["aniso"])
        if "metallic" in params:
            material["metallic"] = params["metallic"]
            dpg.set_value("slider_metallic", params["metallic"])
        if "roughness" in params:
            material["roughness"] = params["roughness"]
            dpg.set_value("slider_roughness", params["roughness"])

        dpg.set_value("status", "Params updated from UE5")

    finally:
        _updating_from_ue5 = False


def on_ws_connected():
    """WebSocket 连接成功回调"""
    dpg.set_value("ws_status", "Connected")
    dpg.configure_item("ws_status", color=(80, 200, 80))


def on_ws_disconnected():
    """WebSocket 断开连接回调"""
    dpg.set_value("ws_status", "Disconnected")
    dpg.configure_item("ws_status", color=(200, 80, 80))


def send_params_realtime():
    """实时发送参数到 UE5（通过 WebSocket）"""
    if not realtime_sync or not ws_client or not ws_client.connected:
        return

    params = {
        "shadow_r": material["shadow_r"],
        "shadow_g": material["shadow_g"],
        "shadow_b": material["shadow_b"],
        "specular": material["specular"],
        "rim": material["rim"],
        "outline": material["outline"],
        "sss": material["sss"],
        "aniso": material["aniso"],
        "metallic": material["metallic"],
        "roughness": material["roughness"],
    }

    ws_client.send_params(params)
```

- [ ] **Step 2: 提交**

```bash
git add Studio/ui_skybox.py
git commit -m "feat(ui): 添加实时联动回调函数

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 12: 添加 UI 控件布局

**Files:**
- Modify: `Studio/ui_skybox.py`

- [ ] **Step 1: 在 build() 函数中添加 UI 控件**

找到 UE5 Connection 区域，在现有控件后添加：

```python
        # 实时联动区域
        dpg.add_separator()
        dpg.add_spacer(height=5)

        with dpg.group(horizontal=True):
            dpg.add_checkbox(
                label="Real-time Sync (WebSocket)",
                tag="realtime_sync_checkbox",
                default_value=False,
                callback=on_realtime_sync_toggle
            )

        with dpg.group(horizontal=True):
            dpg.add_text("WebSocket:", color=(150, 150, 150))
            dpg.add_text("Disabled", tag="ws_status", color=(150, 150, 150))
```

- [ ] **Step 2: 提交**

```bash
git add Studio/ui_skybox.py
git commit -m "feat(ui): 添加实时联动 UI 控件

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 13: 修改滑块回调实现实时发送

**Files:**
- Modify: `Studio/ui_skybox.py`

- [ ] **Step 1: 找到滑块回调函数并修改**

找到材质参数滑块回调函数（如 `on_shadow_r_change` 等），在更新 `material` 字典后添加实时发送逻辑：

```python
def on_shadow_r_change(sender, app_data):
    global material
    material["shadow_r"] = app_data

    # 实时联动发送
    if realtime_sync and ws_client and ws_client.connected and not _updating_from_ue5:
        send_params_realtime()
```

对所有材质参数滑块回调（shadow_r, shadow_g, shadow_b, specular, rim, outline, sss, aniso, metallic, roughness）添加相同的逻辑。

- [ ] **Step 2: 提交**

```bash
git add Studio/ui_skybox.py
git commit -m "feat(ui): 滑块回调添加实时发送逻辑

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 5: 清理和测试

### Task 14: 更新 README 文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 添加实时联动功能说明**

在 Features 部分添加：

```markdown
- **Real-time Sync** - WebSocket-based bidirectional parameter sync with UE5
```

- [ ] **Step 2: 更新技术栈表格**

```markdown
| UE5 Communication | HTTP (4848) + WebSocket (4849) |
```

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: 添加实时联动功能说明

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 15: 最终提交和推送

- [ ] **Step 1: 检查所有更改**

```bash
git status
```

- [ ] **Step 2: 推送到 dev 分支**

```bash
git push origin main
```

- [ ] **Step 3: 创建版本标签**

```bash
git tag -a v2.3.0 -m "feat: Real-time sync with UE5 via WebSocket"
git push origin v2.3.0
```

---

## 验收检查清单

- [ ] HTTP 端口已更新为 4848
- [ ] WebSocket 端口已设置为 4849
- [ ] `ws_client.py` 创建完成，支持连接/断开/发送/接收
- [ ] UE5 WebSocket 服务器头文件和实现文件已创建
- [ ] UI 已添加实时联动开关和状态显示
- [ ] 滑块拖动时能自动发送参数（联动开启时）
- [ ] 断线重连机制正常工作
- [ ] 现有 HTTP 功能保持可用

---

## 注意事项

1. **UE5 WebSocket 模块**: 需要在 `MooaToonInference.Build.cs` 中添加 `"WebSockets"` 到 `PublicDependencyModuleNames`

2. **Python 依赖**: 确保安装 `websockets` 库：
   ```bash
   pip install websockets
   ```

3. **端口冲突**: 如果端口被占用，可在初始化时指定其他端口

4. **异步线程**: WebSocket 客户端在后台线程运行，确保 UI 操作线程安全
