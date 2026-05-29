#include "MooaToonInferenceModule.h"

DEFINE_LOG_CATEGORY_STATIC(LogMooaToonModule, Log, All);

#define LOCTEXT_NAMESPACE "FMooaToonInferenceModule"

void FMooaToonInferenceModule::StartupModule()
{
	// 启动 HTTP 服务
	HttpServer = MakeUnique<FMooaToonHttpServer>();
	if (HttpServer->Start(8080))
	{
		UE_LOG(LogMooaToonModule, Log, TEXT("[MooaToon] HTTP 服务启动成功 (端口 8080)"));
	}
	else
	{
		UE_LOG(LogMooaToonModule, Warning, TEXT("[MooaToon] HTTP 服务启动失败"));
	}
}

void FMooaToonInferenceModule::ShutdownModule()
{
	if (HttpServer.IsValid())
	{
		HttpServer->Stop();
		HttpServer.Reset();
		UE_LOG(LogMooaToonModule, Log, TEXT("[MooaToon] HTTP 服务已停止"));
	}
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FMooaToonInferenceModule, MooaToonInference)
