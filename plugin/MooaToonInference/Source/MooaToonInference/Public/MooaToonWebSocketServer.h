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
