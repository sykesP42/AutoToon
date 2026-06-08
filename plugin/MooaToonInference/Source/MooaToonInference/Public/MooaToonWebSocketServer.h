// MooaToon WebSocket Server
// 在 127.0.0.1:4849 启动 WebSocket 服务，实现实时双向通信。
//
// 注意: UE5 的 WebSocket 模块主要用于客户端连接。
// 服务器端需要使用 TCP Server 或第三方库。
// 此实现提供一个简化的接口框架，可扩展为完整实现。

#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Containers/Array.h"

DECLARE_LOG_CATEGORY_EXTERN(LogMooaToonWS, Log, All);

/**
 * MooaToon WebSocket 服务器
 *
 * 提供与 Python Studio 的实时双向通信。
 *
 * 协议:
 * - 端口: 4849
 * - 消息格式: JSON
 *
 * 消息类型:
 * - params_update: 材质参数更新
 * - ping/pong: 心跳检测
 * - welcome: 连接欢迎消息
 */
class MOOATOONINFERENCE_API FMooaToonWebSocketServer
{
public:
    FMooaToonWebSocketServer();
    ~FMooaToonWebSocketServer();

    // 禁用拷贝
    FMooaToonWebSocketServer(const FMooaToonWebSocketServer&) = delete;
    FMooaToonWebSocketServer& operator=(const FMooaToonWebSocketServer&) = delete;

    /** 启动 WebSocket 服务器 */
    bool Start(int32 Port = 4849);

    /** 停止服务器 */
    void Stop();

    /** 是否正在运行 */
    bool IsRunning() const { return bRunning; }

    /** 获取服务器端口 */
    int32 GetPort() const { return ServerPort; }

    /** 发送参数到所有客户端 */
    void BroadcastParams(const TSharedPtr<FJsonObject>& Params);

    /** 注册参数更新回调 */
    DECLARE_MULTICAST_DELEGATE_OneParam(FOnParamsReceived, const TSharedPtr<FJsonObject>&);
    FOnParamsReceived OnParamsReceived;

private:
    /** 应用材质参数到场景 */
    void ApplyMaterialParams(const TSharedPtr<FJsonObject>& Params);

    /** 构建 JSON 响应 */
    FString BuildParamsJson(const TSharedPtr<FJsonObject>& Params, const FString& Source);

    /** 内部连接信息 */
    struct FClientConnection
    {
        FString ClientId;
        double ConnectTime;
    };

    TArray<FClientConnection> ConnectedClients;
    bool bRunning = false;
    int32 ServerPort = 4849;
};
