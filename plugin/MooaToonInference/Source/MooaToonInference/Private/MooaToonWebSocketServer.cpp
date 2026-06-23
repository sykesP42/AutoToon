// MooaToon WebSocket Server Implementation
// 使用 UE5 原生 IWebSocketServer API 实现 WebSocket 服务器
// 支持实时截图传输

#include "MooaToonWebSocketServer.h"
#include "MooaToonInferenceLibrary.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "HAL/PlatformTime.h"
#include "Misc/Guid.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY(LogMooaToonWS);

// =============================================================================
// 构造 / 析构
// =============================================================================

FMooaToonWebSocketServer::FMooaToonWebSocketServer()
{
}

FMooaToonWebSocketServer::~FMooaToonWebSocketServer()
{
	Stop();
}

// =============================================================================
// 生命周期管理
// =============================================================================

bool FMooaToonWebSocketServer::Start(int32 Port)
{
	if (bRunning)
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] Server already running on port %d"), ServerPort);
		return true;
	}

	ServerPort = Port;

	// 1. 获取 WebSocketNetworking 模块
	IWebSocketNetworkingModule& WsModule =
		FModuleManager::LoadModuleChecked<IWebSocketNetworkingModule>(TEXT("WebSocketNetworking"));

	// 2. 创建服务器实例
	Server = WsModule.CreateServer();
	if (!Server.IsValid())
	{
		UE_LOG(LogMooaToonWS, Error, TEXT("[WS] Failed to create server instance"));
		return false;
	}

	// 3. 绑定客户端连接回调
	FWebSocketClientConnectedCallBack OnClientConnected;
	OnClientConnected.BindRaw(this, &FMooaToonWebSocketServer::HandleClientConnected);

	// 4. 初始化服务器（监听端口）
	if (!Server->Init(Port, OnClientConnected, BindAddress))
	{
		UE_LOG(LogMooaToonWS, Error, TEXT("[WS] Failed to bind port %d - may be in use"), Port);
		Server.Reset();
		return false;
	}

	bRunning = true;
	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Server started: ws://%s:%d"), *BindAddress, Port);
	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Message types: params_update, ping, get_params"));

	return true;
}

void FMooaToonWebSocketServer::Stop()
{
	if (!bRunning)
	{
		return;
	}

	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Stopping server..."));

	// 1. 关闭所有客户端连接
	{
		FScopeLock Lock(&ClientsLock);
		for (auto& Client : Clients)
		{
			if (Client.WebSocket)
			{
				Client.WebSocket->Close();
			}
		}
		Clients.Empty();
	}

	// 2. 停止服务器
	if (Server.IsValid())
	{
		Server->Stop();
		Server.Reset();
	}

	bRunning = false;
	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Server stopped"));
}

// =============================================================================
// 客户端管理
// =============================================================================

int32 FMooaToonWebSocketServer::GetClientCount() const
{
	FScopeLock Lock(&const_cast<FMooaToonWebSocketServer*>(this)->ClientsLock);
	return Clients.Num();
}

FString FMooaToonWebSocketServer::GenerateClientId() const
{
	return FGuid::NewGuid().ToString(EGuidFormats::Digits);
}

FMooaToonWSClient* FMooaToonWebSocketServer::FindClientBySocket(INetworkingWebSocket* Socket)
{
	for (auto& Client : Clients)
	{
		if (Client.WebSocket == Socket)
		{
			return &Client;
		}
	}
	return nullptr;
}

FMooaToonWSClient* FMooaToonWebSocketServer::FindClientById(const FString& ClientId)
{
	for (auto& Client : Clients)
	{
		if (Client.ClientId == ClientId)
		{
			return &Client;
		}
	}
	return nullptr;
}

void FMooaToonWebSocketServer::RemoveClient(INetworkingWebSocket* Socket)
{
	FScopeLock Lock(&ClientsLock);

	int32 Idx = INDEX_NONE;
	for (int32 i = 0; i < Clients.Num(); i++)
	{
		if (Clients[i].WebSocket == Socket)
		{
			Idx = i;
			break;
		}
	}

	if (Idx != INDEX_NONE)
	{
		FString ClientId = Clients[Idx].ClientId;
		Clients.RemoveAtSwap(Idx);
		UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Client removed: %s"), *ClientId);
	}
}

// =============================================================================
// 连接处理
// =============================================================================

void FMooaToonWebSocketServer::HandleClientConnected(INetworkingWebSocket* ClientSocket)
{
	if (!ClientSocket)
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] Null client socket received"));
		return;
	}

	FString ClientId = GenerateClientId();

	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Client connecting: %s"), *ClientId);

	// 1. 绑定消息接收回调
	FWebSocketPacketReceivedCallBack OnMessage;
	OnMessage.BindRaw(this, &FMooaToonWebSocketServer::HandleMessageReceived);
	ClientSocket->SetReceiveCallBack(OnMessage);

	// 2. 绑定断开连接回调
	FWebSocketClosedCallBack OnClosed;
	OnClosed.BindLambda([this, ClientSocket](int32 StatusCode, const FString& Reason)
	{
		HandleClientDisconnected(ClientSocket);
	});
	ClientSocket->SetClosedCallBack(OnClosed);

	// 3. 添加到客户端列表
	{
		FScopeLock Lock(&ClientsLock);
		Clients.Emplace(ClientSocket, ClientId);
	}

	// 4. 发送欢迎消息
	SendWelcomeMessage(ClientSocket, ClientId);

	// 5. 触发连接回调
	OnClientConnected.Broadcast(ClientId);

	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Client connected: %s (total: %d)"),
		*ClientId, GetClientCount());
}

void FMooaToonWebSocketServer::HandleClientDisconnected(INetworkingWebSocket* Socket)
{
	FString ClientId;
	{
		FScopeLock Lock(&ClientsLock);
		FMooaToonWSClient* Client = FindClientBySocket(Socket);
		if (Client)
		{
			ClientId = Client->ClientId;
		}
	}

	if (!ClientId.IsEmpty())
	{
		RemoveClient(Socket);
		OnClientDisconnected.Broadcast(ClientId);
		UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Client disconnected: %s"), *ClientId);
	}
}

// =============================================================================
// 消息处理
// =============================================================================

void FMooaToonWebSocketServer::HandleMessageReceived(INetworkingWebSocket* Socket, const TArray<uint8>& Data)
{
	// 将字节数据转换为字符串
	FString Message = FString(UTF8_TO_TCHAR(reinterpret_cast<const char*>(Data.GetData())));

	UE_LOG(LogMooaToonWS, Verbose, TEXT("[WS] Received %d bytes: %s"), Data.Num(), *Message.Left(200));

	ProcessJsonMessage(Message, TEXT(""));
}

void FMooaToonWebSocketServer::ProcessJsonMessage(const FString& JsonStr, const FString& ClientId)
{
	// 解析 JSON
	TSharedPtr<FJsonObject> Json;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonStr);

	if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] JSON parse failed: %s"), *JsonStr.Left(100));
		return;
	}

	// 获取消息类型
	FString Type;
	if (!Json->TryGetStringField(TEXT("type"), Type))
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] Missing 'type' field in message"));
		return;
	}

	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Processing message type: %s"), *Type);

	if (Type == TEXT("params_update"))
	{
		// 获取参数对象
		const TSharedPtr<FJsonObject>* ParamsObj;
		if (Json->TryGetObjectField(TEXT("params"), ParamsObj))
		{
			ApplyMaterialParams(*ParamsObj);
			OnParamsReceived.Broadcast(*ParamsObj, ClientId);
		}
	}
	else if (Type == TEXT("ping"))
	{
		// 获取时间戳并响应 pong
		int64 Timestamp = 0;
		Json->TryGetNumberField(TEXT("timestamp"), Timestamp);

		// 找到发送者并回复
		// Note: 需要知道是哪个客户端发送的，这里简化处理
		FScopeLock Lock(&ClientsLock);
		for (const auto& Client : Clients)
		{
			if (Client.WebSocket)
			{
				FString PongJson = BuildPongJson(Timestamp);
				SendJsonToSocket(Client.WebSocket, PongJson);
				break; // 只回复第一个（假设单客户端）
			}
		}
	}
	else if (Type == TEXT("start_screenshot"))
	{
		// 开始定时截图
		float Interval = 0.1f;
		Json->TryGetNumberField(TEXT("interval"), Interval);
		StartPeriodicScreenshot(Interval);
	}
	else if (Type == TEXT("stop_screenshot"))
	{
		// 停止定时截图
		StopPeriodicScreenshot();
	}
	else
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] Unknown message type: %s"), *Type);
	}
}

void FMooaToonWebSocketServer::ApplyMaterialParams(const TSharedPtr<FJsonObject>& Params)
{
	if (!Params.IsValid())
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] Invalid params object"));
		return;
	}

	// 提取参数（带默认值）
	float ShadowR = 0.0f, ShadowG = 0.0f, ShadowB = 0.0f;
	float Specular = 0.5f, Rim = 0.0f, Outline = 1.0f;
	float SSS = 0.0f, Aniso = 0.0f, Metallic = 0.0f, Roughness = 0.5f;

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
		// 兼容扁平格式
		Params->TryGetNumberField(TEXT("shadow_r"), ShadowR);
		Params->TryGetNumberField(TEXT("shadow_g"), ShadowG);
		Params->TryGetNumberField(TEXT("shadow_b"), ShadowB);
	}

	Params->TryGetNumberField(TEXT("specular"), Specular);
	Params->TryGetNumberField(TEXT("rim"), Rim);
	Params->TryGetNumberField(TEXT("outline"), Outline);
	Params->TryGetNumberField(TEXT("sss"), SSS);
	Params->TryGetNumberField(TEXT("aniso"), Aniso);
	Params->TryGetNumberField(TEXT("metallic"), Metallic);
	Params->TryGetNumberField(TEXT("roughness"), Roughness);

	// Clamp 到合理范围
	ShadowR = FMath::Clamp(ShadowR, 0.0f, 1.0f);
	ShadowG = FMath::Clamp(ShadowG, 0.0f, 1.0f);
	ShadowB = FMath::Clamp(ShadowB, 0.0f, 1.0f);
	Specular = FMath::Clamp(Specular, 0.0f, 1.0f);
	Rim = FMath::Clamp(Rim, 0.0f, 1.0f);
	Outline = FMath::Max(0.0f, Outline);
	SSS = FMath::Clamp(SSS, 0.0f, 1.0f);
	Aniso = FMath::Clamp(Aniso, 0.0f, 1.0f);
	Metallic = FMath::Clamp(Metallic, 0.0f, 1.0f);
	Roughness = FMath::Clamp(Roughness, 0.0f, 1.0f);

	UE_LOG(LogMooaToonWS, Log,
		TEXT("[WS] Applying params: Shadow=(%.3f,%.3f,%.3f) Spec=%.3f Rim=%.3f Outline=%.3f"),
		ShadowR, ShadowG, ShadowB, Specular, Rim, Outline);

	// 应用到场景
	FLinearColor ShadowColor(ShadowR, ShadowG, ShadowB, 1.0f);
	UMooaToonInferenceLibrary::SetMooaToonParams(
		nullptr, ShadowColor, Specular, Rim, Outline);
}

// =============================================================================
// 消息发送
// =============================================================================

bool FMooaToonWebSocketServer::SendJsonToSocket(INetworkingWebSocket* Socket, const FString& JsonStr)
{
	if (!Socket)
	{
		return false;
	}

	// 转换为 UTF-8 字节数组
	FTCHARToUTF8 Utf8Converter(*JsonStr);
	TArray<uint8> Data;
	Data.Append(reinterpret_cast<const uint8*>(Utf8Converter.Get()), Utf8Converter.Length());

	Socket->Send(Data);
	return true;
}

void FMooaToonWebSocketServer::SendWelcomeMessage(INetworkingWebSocket* Socket, const FString& ClientId)
{
	TSharedPtr<FJsonObject> Welcome = MakeShareable(new FJsonObject);
	Welcome->SetStringField(TEXT("type"), TEXT("welcome"));
	Welcome->SetStringField(TEXT("client_id"), ClientId);
	Welcome->SetNumberField(TEXT("timestamp"), FDateTime::Now().ToUnixTimestamp());

	FString JsonStr;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&JsonStr);
	FJsonSerializer::Serialize(Welcome.ToSharedRef(), Writer);

	SendJsonToSocket(Socket, JsonStr);
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

FString FMooaToonWebSocketServer::BuildPongJson(int64 Timestamp)
{
	TSharedPtr<FJsonObject> Pong = MakeShareable(new FJsonObject);
	Pong->SetStringField(TEXT("type"), TEXT("pong"));
	Pong->SetNumberField(TEXT("timestamp"), Timestamp);
	Pong->SetNumberField(TEXT("server_time"), FDateTime::Now().ToUnixTimestamp());

	FString JsonStr;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&JsonStr);
	FJsonSerializer::Serialize(Pong.ToSharedRef(), Writer);

	return JsonStr;
}

void FMooaToonWebSocketServer::BroadcastParams(const TSharedPtr<FJsonObject>& Params)
{
	if (!bRunning || !Params.IsValid())
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] Cannot broadcast - server not running or invalid params"));
		return;
	}

	FScopeLock Lock(&ClientsLock);

	if (Clients.Num() == 0)
	{
		UE_LOG(LogMooaToonWS, Verbose, TEXT("[WS] No clients connected, skipping broadcast"));
		return;
	}

	FString JsonStr = BuildParamsJson(Params, TEXT("ue5"));

	int32 SuccessCount = 0;
	for (const auto& Client : Clients)
	{
		if (Client.WebSocket && SendJsonToSocket(Client.WebSocket, JsonStr))
		{
			SuccessCount++;
		}
	}

	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Broadcasted to %d/%d clients"), SuccessCount, Clients.Num());
}

bool FMooaToonWebSocketServer::SendToClient(const FString& ClientId, const FString& Message)
{
	FScopeLock Lock(&ClientsLock);

	FMooaToonWSClient* Client = FindClientById(ClientId);
	if (Client && Client->WebSocket)
	{
		return SendJsonToSocket(Client->WebSocket, Message);
	}

	UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] Client not found: %s"), *ClientId);
	return false;
}

// =============================================================================
// 实时截图功能
// =============================================================================

void FMooaToonWebSocketServer::CaptureAndSendScreenshot()
{
	if (!bRunning || GetClientCount() == 0)
	{
		return;
	}

	// 1. 获取游戏视口
	UGameViewportClient* ViewportClient = GEngine ? GEngine->GameViewport : nullptr;
	if (!ViewportClient || !ViewportClient->Viewport)
	{
		UE_LOG(LogMooaToonWS, Verbose, TEXT("[WS] No viewport available for screenshot"));
		return;
	}

	FViewport* Viewport = ViewportClient->Viewport;
	FIntPoint ViewportSize = Viewport->GetSizeXY();

	if (ViewportSize.X <= 0 || ViewportSize.Y <= 0)
	{
		return;
	}

	// 2. 计算缩放（限制最大分辨率）
	int32 CaptureWidth = ViewportSize.X;
	int32 CaptureHeight = ViewportSize.Y;

	if (CaptureWidth > MaxScreenshotSize || CaptureHeight > MaxScreenshotSize)
	{
		float Scale = (float)MaxScreenshotSize / FMath::Max(CaptureWidth, CaptureHeight);
		CaptureWidth = FMath::RoundToInt(CaptureWidth * Scale);
		CaptureHeight = FMath::RoundToInt(CaptureHeight * Scale);
	}

	// 3. 读取像素数据
	TArray<FColor> Bitmap;
	FReadSurfaceDataFlags ReadFlags(RCM_UNorm, CubeFace_MAX);
	ReadFlags.SetLinearToGamma(false);

	if (!Viewport->ReadPixels(Bitmap, ReadFlags))
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] ReadPixels failed"));
		return;
	}

	// 4. 编码为 JPEG
	TArray<uint8> JPEGData;
	if (!EncodeScreenshotToJPEG(Bitmap, CaptureWidth, CaptureHeight, JPEGData))
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] JPEG encoding failed"));
		return;
	}

	// 5. 构建二进制消息包（IMG + 类型 + 数据）
	TArray<uint8> Packet;
	Packet.Add('I');
	Packet.Add('M');
	Packet.Add('G');
	Packet.Add(0x01);  // 0x01 = JPEG
	Packet.Append(JPEGData);

	// 6. 广播到所有客户端
	BroadcastBinaryMessage(Packet);

	UE_LOG(LogMooaToonWS, Verbose, TEXT("[WS] Sent screenshot: %dx%d, %d bytes"),
		CaptureWidth, CaptureHeight, JPEGData.Num());
}

bool FMooaToonWebSocketServer::EncodeScreenshotToJPEG(
	TArray<FColor>& Bitmap, int32 Width, int32 Height, TArray<uint8>& OutData)
{
	if (Bitmap.Num() == 0 || Width <= 0 || Height <= 0)
	{
		return false;
	}

	// 获取 ImageWrapper 模块
	IImageWrapperModule& ImageWrapperModule =
		FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));

	TSharedPtr<IImageWrapper> ImageWrapper =
		ImageWrapperModule.CreateImageWrapper(EImageFormat::JPEG);

	if (!ImageWrapper.IsValid())
	{
		return false;
	}

	// 转换 FColor (BGRA) 到原始数据
	TArray<uint8> RawData;
	int32 PixelCount = Bitmap.Num();
	RawData.SetNumUninitialized(PixelCount * 4);

	for (int32 i = 0; i < PixelCount; i++)
	{
		RawData[i * 4 + 0] = Bitmap[i].B;
		RawData[i * 4 + 1] = Bitmap[i].G;
		RawData[i * 4 + 2] = Bitmap[i].R;
		RawData[i * 4 + 3] = Bitmap[i].A;
	}

	// 设置原始数据
	if (!ImageWrapper->SetRaw(RawData.GetData(), RawData.Num(), Width, Height, ERGBFormat::BGRA, 8))
	{
		return false;
	}

	// 压缩为 JPEG
	OutData = ImageWrapper->GetCompressed(JPEGQuality);

	return OutData.Num() > 0;
}

void FMooaToonWebSocketServer::BroadcastBinaryMessage(const TArray<uint8>& Data)
{
	if (!bRunning || Data.Num() == 0)
	{
		return;
	}

	FScopeLock Lock(&ClientsLock);

	int32 SuccessCount = 0;
	for (const auto& Client : Clients)
	{
		if (Client.WebSocket)
		{
			Client.WebSocket->Send(Data);
			SuccessCount++;
		}
	}

	UE_LOG(LogMooaToonWS, Verbose, TEXT("[WS] Binary broadcast: %d bytes to %d clients"),
		Data.Num(), SuccessCount);
}

void FMooaToonWebSocketServer::StartPeriodicScreenshot(float IntervalSeconds)
{
	if (bScreenshotEnabled)
	{
		UE_LOG(LogMooaToonWS, Warning, TEXT("[WS] Screenshot already enabled"));
		return;
	}

	bScreenshotEnabled = true;
	ScreenshotInterval = FMath::Clamp(IntervalSeconds, 0.033f, 1.0f);

	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Starting periodic screenshot: %.3f sec interval"),
		ScreenshotInterval);

	// 使用全局定时器管理器
	if (GEngine && GEngine->GetWorld())
	{
		GEngine->GetWorld()->GetTimerManager().SetTimer(
			ScreenshotTimerHandle,
			FTimerDelegate::CreateRaw(this, &FMooaToonWebSocketServer::CaptureAndSendScreenshot),
			ScreenshotInterval,
			true  // 循环
		);
	}
}

void FMooaToonWebSocketServer::StopPeriodicScreenshot()
{
	if (!bScreenshotEnabled)
	{
		return;
	}

	bScreenshotEnabled = false;

	UE_LOG(LogMooaToonWS, Log, TEXT("[WS] Stopped periodic screenshot"));

	if (GEngine && GEngine->GetWorld())
	{
		GEngine->GetWorld()->GetTimerManager().ClearTimer(ScreenshotTimerHandle);
	}
}