#include "MooaToonInferenceModule.h"

DEFINE_LOG_CATEGORY_STATIC(LogMooaToonModule, Log, All);

#define LOCTEXT_NAMESPACE "FMooaToonInferenceModule"

// 静态成员初始化
FMooaToonInferenceModule* FMooaToonInferenceModule::ModuleInstance = nullptr;

FMooaToonWebSocketServer* FMooaToonInferenceModule::GetWebSocketServer()
{
	return ModuleInstance ? ModuleInstance->WebSocketServer.Get() : nullptr;
}

void FMooaToonInferenceModule::StartupModule()
{
	ModuleInstance = this;

	// 启动 HTTP 服务 (端口 4848)
	HttpServer = MakeUnique<FMooaToonHttpServer>();
	if (HttpServer->Start(4848))
	{
		UE_LOG(LogMooaToonModule, Log, TEXT("[MooaToon] HTTP Server started (port 4848)"));
	}
	else
	{
		UE_LOG(LogMooaToonModule, Warning, TEXT("[MooaToon] HTTP Server failed to start on port 4848"));
	}

	// 启动 WebSocket 服务 (端口 4849)
	WebSocketServer = MakeUnique<FMooaToonWebSocketServer>();
	if (WebSocketServer->Start(4849))
	{
		UE_LOG(LogMooaToonModule, Log, TEXT("[MooaToon] WebSocket Server started (port 4849)"));
	}
	else
	{
		UE_LOG(LogMooaToonModule, Warning, TEXT("[MooaToon] WebSocket Server failed to start on port 4849"));
	}
}

void FMooaToonInferenceModule::ShutdownModule()
{
	// 先停止 WebSocket 服务
	if (WebSocketServer.IsValid())
	{
		WebSocketServer->Stop();
		WebSocketServer.Reset();
		UE_LOG(LogMooaToonModule, Log, TEXT("[MooaToon] WebSocket Server stopped"));
	}

	// 再停止 HTTP 服务
	if (HttpServer.IsValid())
	{
		HttpServer->Stop();
		HttpServer.Reset();
		UE_LOG(LogMooaToonModule, Log, TEXT("[MooaToon] HTTP Server stopped"));
	}

	ModuleInstance = nullptr;
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FMooaToonInferenceModule, MooaToonInference)
