// MooaToon HTTP Server Implementation

#include "MooaToonHttpServer.h"
#include "MooaToonInferenceLibrary.h"
#include "HttpServerModule.h"
#include "HttpListener.h"
#include "Interfaces/IHttpResponse.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"
#include "Engine/World.h"
#include "EngineUtils.h"

DEFINE_LOG_CATEGORY_STATIC(LogMooaToonHTTP, Log, All);

// =============================================================================
// 启动 / 停止
// =============================================================================

bool FMooaToonHttpServer::Start(int32 Port)
{
	if (bRunning)
	{
		UE_LOG(LogMooaToonHTTP, Warning, TEXT("[HTTP] 服务已在运行中"));
		return true;
	}

	// 获取 HTTP 服务器模块
	FHttpServerModule& HttpServerModule = FHttpServerModule::Get();

	// 创建路由器
	Router = HttpServerModule.GetHttpRouter(Port);
	if (!Router.IsValid())
	{
		UE_LOG(LogMooaToonHTTP, Error, TEXT("[HTTP] 无法创建路由器，端口 %d 可能被占用"), Port);
		return false;
	}

	// 注册路由
	// GET /api/health
	HealthRouteHandle = Router->BindRoute(
		FHttpPath(TEXT("/api/health")),
		EHttpServerRequestVerbs::VERB_GET,
		FHttpRequestHandler::CreateRaw(this, &FMooaToonHttpServer::HandleHealthCheck)
	);

	// POST /api/style
	StyleRouteHandle = Router->BindRoute(
		FHttpPath(TEXT("/api/style")),
		EHttpServerRequestVerbs::VERB_POST,
		FHttpRequestHandler::CreateRaw(this, &FMooaToonHttpServer::HandleStyleApply)
	);

	// 启动监听
	HttpServerModule.StartAllListeners();

	bRunning = true;
	UE_LOG(LogMooaToonHTTP, Log, TEXT("[HTTP] 服务已启动: http://127.0.0.1:%d"), Port);
	UE_LOG(LogMooaToonHTTP, Log, TEXT("[HTTP]   GET  /api/health"));
	UE_LOG(LogMooaToonHTTP, Log, TEXT("[HTTP]   POST /api/style"));

	return true;
}

void FMooaToonHttpServer::Stop()
{
	if (!bRunning)
	{
		return;
	}

	// 解绑路由
	if (Router.IsValid())
	{
		Router->UnbindRoute(HealthRouteHandle);
		Router->UnbindRoute(StyleRouteHandle);
	}

	// 停止监听
	FHttpServerModule::Get().StopAllListeners();

	bRunning = false;
	UE_LOG(LogMooaToonHTTP, Log, TEXT("[HTTP] 服务已停止"));
}

// =============================================================================
// 路由处理
// =============================================================================

bool FMooaToonHttpServer::HandleHealthCheck(
	const FHttpServerRequest& Request,
	const FHttpResultCallback& OnComplete)
{
	UE_LOG(LogMooaToonHTTP, Verbose, TEXT("[HTTP] GET /api/health"));

	OnComplete(MakeJsonResponse(200, TEXT("{\"status\":\"ok\"}")));
	return true;
}

bool FMooaToonHttpServer::HandleStyleApply(
	const FHttpServerRequest& Request,
	const FHttpResultCallback& OnComplete)
{
	UE_LOG(LogMooaToonHTTP, Log, TEXT("[HTTP] POST /api/style"));

	// 1. 解析 JSON Body
	FString BodyString = UTF8_TO_TCHAR(
		reinterpret_cast<const char*>(Request.Body.GetData()),
		Request.Body.Num()
	);

	TSharedPtr<FJsonObject> JsonBody;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(BodyString);

	if (!FJsonSerializer::Deserialize(Reader, JsonBody) || !JsonBody.IsValid())
	{
		UE_LOG(LogMooaToonHTTP, Error, TEXT("[HTTP] JSON 解析失败"));
		OnComplete(MakeJsonResponse(400, TEXT("{\"error\":\"Invalid JSON\"}")));
		return true;
	}

	// 2. 读取 params 数组
	const TArray<TSharedPtr<FJsonValue>>* ParamsArray;
	if (!JsonBody->TryGetArrayField(TEXT("params"), ParamsArray))
	{
		UE_LOG(LogMooaToonHTTP, Error, TEXT("[HTTP] 缺少 params 字段"));
		OnComplete(MakeJsonResponse(400, TEXT("{\"error\":\"Missing 'params' field\"}")));
		return true;
	}

	if (ParamsArray->Num() != 6)
	{
		UE_LOG(LogMooaToonHTTP, Error, TEXT("[HTTP] params 数量应为 6，实际为 %d"), ParamsArray->Num());
		OnComplete(MakeJsonResponse(400,
			FString::Printf(TEXT("{\"error\":\"Expected 6 params, got %d\"}"), ParamsArray->Num())));
		return true;
	}

	// 3. 提取 6 个参数
	float ShadowR = (*ParamsArray)[0]->AsNumber();
	float ShadowG = (*ParamsArray)[1]->AsNumber();
	float ShadowB = (*ParamsArray)[2]->AsNumber();
	float Specular = (*ParamsArray)[3]->AsNumber();
	float RimLightWidth = (*ParamsArray)[4]->AsNumber();
	float WidthScale = (*ParamsArray)[5]->AsNumber();

	UE_LOG(LogMooaToonHTTP, Log,
		TEXT("[HTTP] 参数接收: Shadow=(%.3f,%.3f,%.3f) Spec=%.3f Rim=%.3f Width=%.3f"),
		ShadowR, ShadowG, ShadowB, Specular, RimLightWidth, WidthScale);

	// 4. 找到场景中的目标角色并写入材质
	FLinearColor ShadowColor(ShadowR, ShadowG, ShadowB, 1.f);

	// 遍历场景中所有带 SkeletalMeshComponent 的 Actor
	UWorld* World = GEngine->GetWorldFromContextObject(
		GEngine->GetWorldContexts()[0].WorldContextObject,
		EGetWorldErrorMode::ReturnNull
	);

	if (!World)
	{
		// 尝试从任意 GameWorld 获取
		for (const FWorldContext& Context : GEngine->GetWorldContexts())
		{
			if (Context.WorldType == EWorldType::Game || Context.WorldType == EWorldType::PIE)
			{
				World = Context.World();
				break;
			}
		}
	}

	if (World)
	{
		int32 AppliedCount = 0;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			AActor* Actor = *It;
			if (Actor->FindComponentByClass<USkeletalMeshComponent>())
			{
				UMooaToonInferenceLibrary::SetMooaToonParams(
					Actor, ShadowColor, Specular, RimLightWidth, WidthScale);
				AppliedCount++;
			}
		}

		UE_LOG(LogMooaToonHTTP, Log, TEXT("[HTTP] 已应用到 %d 个角色"), AppliedCount);
	}
	else
	{
		UE_LOG(LogMooaToonHTTP, Warning, TEXT("[HTTP] 无法获取 World，参数已接收但未应用"));
	}

	// 5. 返回成功
	OnComplete(MakeJsonResponse(200, TEXT("{\"status\":\"ok\"}")));
	return true;
}

// =============================================================================
// 辅助
// =============================================================================

TUniquePtr<FHttpServerResponse> FMooaToonHttpServer::MakeJsonResponse(
	int32 StatusCode, const FString& JsonBody)
{
	TUniquePtr<FHttpServerResponse> Response = MakeUnique<FHttpServerResponse>();
	Response->Code = EHttpServerResponseCodes::Ok;

	if (StatusCode == 400)
	{
		Response->Code = EHttpServerResponseCodes::BadRequest;
	}
	else if (StatusCode == 500)
	{
		Response->Code = EHttpServerResponseCodes::Error;
	}

	Response->Headers.Add(TEXT("Content-Type"), { TEXT("application/json") });
	Response->Headers.Add(TEXT("Access-Control-Allow-Origin"), { TEXT("*") });

	FTCHARToUTF8 Converter(*JsonBody);
	Response->Body.Append(
		reinterpret_cast<const uint8*>(Converter.Get()),
		Converter.Length()
	);

	return Response;
}
