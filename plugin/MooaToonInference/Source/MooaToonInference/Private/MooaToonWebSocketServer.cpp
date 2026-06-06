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
