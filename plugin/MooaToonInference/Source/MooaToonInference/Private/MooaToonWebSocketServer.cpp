// MooaToon WebSocket Server Implementation
// 简化实现，提供框架接口供后续扩展

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

    // TODO: 实际 WebSocket 服务器实现
    // 当前为框架实现，后续可集成:
    // 1. 使用 UE5 TCP Socket + 自定义 WebSocket 协议
    // 2. 集成 libwebsockets 库
    // 3. 使用第三方 WebSocket 插件
    //
    // Python 客户端连接方式:
    //   import websockets
    //   async with websockets.connect("ws://127.0.0.1:4849") as ws:
    //       await ws.send(json.dumps({"type": "params_update", "params": {...}}))

    bRunning = true;
    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] WebSocket 服务器框架已初始化: ws://127.0.0.1:%d"), Port);
    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] 端口: %d (待实际连接实现)"), Port);
    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] 消息类型: params_update, ping, get_params"));

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
// 参数处理
// =============================================================================

void FMooaToonWebSocketServer::ApplyMaterialParams(const TSharedPtr<FJsonObject>& Params)
{
    if (!Params.IsValid())
    {
        UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] 无效的参数对象"));
        return;
    }

    // 提取参数 (使用 TryGet 以支持可选参数)
    float ShadowR = 0.0f, ShadowG = 0.0f, ShadowB = 0.0f;
    float Specular = 0.5f, Rim = 0.0f, Outline = 1.0f;

    // 读取阴影颜色 - 支持两种格式
    const TSharedPtr<FJsonObject>* ShadowColorObj;
    if (Params->TryGetObjectField(TEXT("shadow_color"), ShadowColorObj))
    {
        (*ShadowColorObj)->TryGetNumberField(TEXT("r"), ShadowR);
        (*ShadowColorObj)->TryGetNumberField(TEXT("g"), ShadowG);
        (*ShadowColorObj)->TryGetNumberField(TEXT("b"), ShadowB);
    }
    else
    {
        // 兼容旧格式
        Params->TryGetNumberField(TEXT("shadow_r"), ShadowR);
        Params->TryGetNumberField(TEXT("shadow_g"), ShadowG);
        Params->TryGetNumberField(TEXT("shadow_b"), ShadowB);
    }

    Params->TryGetNumberField(TEXT("specular"), Specular);
    Params->TryGetNumberField(TEXT("rim"), Rim);
    Params->TryGetNumberField(TEXT("outline"), Outline);

    UE_LOG(LogMooaToonWS, Log,
        TEXT("[WS] 应用参数: Shadow=(%.3f,%.3f,%.3f) Spec=%.3f Rim=%.3f Outline=%.3f"),
        ShadowR, ShadowG, ShadowB, Specular, Rim, Outline);

    // 应用到场景
    FLinearColor ShadowColor(ShadowR, ShadowG, ShadowB, 1.f);
    UMooaToonInferenceLibrary::SetMooaToonParams(
        nullptr, ShadowColor, Specular, Rim, Outline);

    // 触发回调
    OnParamsReceived.Broadcast(Params);
}

FString FMooaToonWebSocketServer::BuildParamsJson(const TSharedPtr<FJsonObject>& Params, const FString& Source)
{
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("params_update"));
    Message->SetObjectField(TEXT("params"), Params);
    Message->SetStringField(TEXT("source"), Source);
    Message->SetNumberField(TEXT("timestamp"), FDateTime::Now().ToUnixTimestamp());

    FString JsonStr;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&JsonStr);
    FJsonSerializer::Serialize(Message.ToSharedRef(), Writer);

    return JsonStr;
}

void FMooaToonWebSocketServer::BroadcastParams(const TSharedPtr<FJsonObject>& Params)
{
    if (!bRunning)
    {
        UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] 服务未运行，无法广播"));
        return;
    }

    if (ConnectedClients.Num() == 0)
    {
        UE_LOG(LogMooaToonWS, Verbose, TEXT("[WS] 无连接客户端"));
        return;
    }

    FString JsonStr = BuildParamsJson(Params, TEXT("ue5"));

    // TODO: 实际发送到客户端
    // 当前为框架实现
    UE_LOG(LogMooaToonWS, Log, TEXT("[WS] 广播参数: %s"), *JsonStr.Left(200));
}
