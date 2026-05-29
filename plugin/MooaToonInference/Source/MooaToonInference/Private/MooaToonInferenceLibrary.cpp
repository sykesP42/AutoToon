// MooaToon Inference Plugin

#include "MooaToonInferenceLibrary.h"
#include "NNE.h"
#include "NNEModelData.h"
#include "NNERuntimeCPU.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInstance.h"
#include "Materials/MaterialLayersFunctions.h"
#include "MaterialTypes.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/MeshComponent.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Modules/ModuleManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformFileManager.h"
#include "Engine/Texture2D.h"
#include "Engine/Engine.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/World.h"
#include "EngineUtils.h"

DEFINE_LOG_CATEGORY_STATIC(LogMooaToon, Log, All);

bool UMooaToonInferenceLibrary::RunMooaToonInference(
	UNNEModelData* ModelData,
	const TArray<float>& InputPixels,
	FMooaToonParams& OutParams)
{
	// 1. 参数检查
	if (!ModelData)
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] ModelData 为空，请传入 ONNX 资产"));
		return false;
	}

	// 输入应为 224*224*3 = 150528 个 float
	constexpr int32 ExpectedSize = 224 * 224 * 3;
	if (InputPixels.Num() != ExpectedSize)
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] InputPixels 长度应为 %d，实际为 %d"),
			ExpectedSize, InputPixels.Num());
		return false;
	}

	// 2. 获取 CPU Runtime
	TWeakInterfacePtr<INNERuntimeCPU> RuntimeCPU =
		UE::NNE::GetRuntime<INNERuntimeCPU>(TEXT("NNERuntimeORTCpu"));

	if (!RuntimeCPU.IsValid())
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] 找不到 NNERuntimeORTCpu，请确认 NNE 插件已启用"));
		return false;
	}

	// 3. 创建模型实例
	TSharedPtr<UE::NNE::IModelCPU> ModelCPU = RuntimeCPU->CreateModelCPU(ModelData);
	if (!ModelCPU.IsValid())
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] 创建 ModelCPU 失败"));
		return false;
	}

	TSharedPtr<UE::NNE::IModelInstanceCPU> ModelInstance = ModelCPU->CreateModelInstanceCPU();
	if (!ModelInstance.IsValid())
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] 创建 ModelInstance 失败"));
		return false;
	}

	// 4. 设置输入 Shape：[1, 3, 224, 224]
	TArray<uint32> InputShape = { 1, 3, 224, 224 };
	UE::NNE::FTensorShape TensorShape = UE::NNE::FTensorShape::Make(InputShape);

	if (ModelInstance->SetInputTensorShapes({ TensorShape }) !=
		UE::NNE::IModelInstanceCPU::ESetInputTensorShapesStatus::Ok)
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] SetInputTensorShapes 失败"));
		return false;
	}

	// 5. 准备输入/输出 Tensor
	UE::NNE::FTensorBindingCPU InputBinding;
	InputBinding.Data = (void*)InputPixels.GetData();
	InputBinding.SizeInBytes = InputPixels.Num() * sizeof(float);

	// 输出：6 个 float [ShadowR, ShadowG, ShadowB, Specular, RimLightWidth, WidthScale]
	TArray<float> OutputData;
	OutputData.SetNumZeroed(6);

	UE::NNE::FTensorBindingCPU OutputBinding;
	OutputBinding.Data = OutputData.GetData();
	OutputBinding.SizeInBytes = OutputData.Num() * sizeof(float);

	// 6. 推理
	if (ModelInstance->RunSync({ InputBinding }, { OutputBinding }) !=
		UE::NNE::IModelInstanceCPU::ERunSyncStatus::Ok)
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] RunSync 失败"));
		return false;
	}

	// 7. 解析输出，反归一化 WidthScale（训练时归一化到[0,1]，原始范围[0.5, 3.0]）
	OutParams.ShadowR       = OutputData[0];
	OutParams.ShadowG       = OutputData[1];
	OutParams.ShadowB       = OutputData[2];
	OutParams.Specular      = OutputData[3];
	OutParams.RimLightWidth = OutputData[4];
	OutParams.WidthScale    = OutputData[5] * 2.5f + 0.5f;  // 反归一化

	UE_LOG(LogMooaToon, Log, TEXT("[MooaToon] 推理成功: Shadow=(%.3f,%.3f,%.3f) Specular=%.3f RimWidth=%.3f Width=%.3f"),
		OutParams.ShadowR, OutParams.ShadowG, OutParams.ShadowB,
		OutParams.Specular, OutParams.RimLightWidth, OutParams.WidthScale);

	return true;
}

void UMooaToonInferenceLibrary::ApplyParamsToMaterial(
	UMaterialInstanceDynamic* MaterialInstance,
	const FMooaToonParams& Params)
{
	if (!MaterialInstance)
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] MaterialInstance 为空"));
		return;
	}

	// 写入 Shadow Color（Vector 参数）
	FLinearColor ShadowColor(Params.ShadowR, Params.ShadowG, Params.ShadowB, 1.f);
	MaterialInstance->SetVectorParameterValue(TEXT("Shadow Color"), ShadowColor);

	// 写入标量参数
	MaterialInstance->SetScalarParameterValue(TEXT("Width Scale"), Params.WidthScale);
	MaterialInstance->SetScalarParameterValue(TEXT("Specular"), Params.Specular);

	UE_LOG(LogMooaToon, Log, TEXT("[MooaToon] 材质参数已写入"));
}

void UMooaToonInferenceLibrary::SetMooaToonParams(
	AActor* TargetActor,
	FLinearColor ShadowColor,
	float Specular,
	float RimLightWidth,
	float WidthScale,
	int32 ElementIndex)
{
	if (!TargetActor)
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] SetMooaToonParams: TargetActor 为空"));
		return;
	}

	// 找骨骼网格体组件
	USkeletalMeshComponent* SkelMesh =
		TargetActor->FindComponentByClass<USkeletalMeshComponent>();

	if (!SkelMesh)
	{
		UE_LOG(LogMooaToon, Error,
			TEXT("[MooaToon] SetMooaToonParams: 在 %s 上找不到 SkeletalMeshComponent"),
			*TargetActor->GetName());
		return;
	}

	// =========================================================================
	// 部分 A：写入主体材质槽的图层参数（Shadow Color + Specular + Rim Light Width）
	// =========================================================================
	const int32 NumMaterials = SkelMesh->GetNumMaterials();
	int32 AppliedCount = 0;

	int32 StartIdx = (ElementIndex < 0) ? 0 : ElementIndex;
	int32 EndIdx   = (ElementIndex < 0) ? NumMaterials - 1 : ElementIndex;

	for (int32 Idx = StartIdx; Idx <= EndIdx; ++Idx)
	{
		if (Idx >= NumMaterials) break;

		UMaterialInstanceDynamic* DynMat =
			SkelMesh->CreateAndSetMaterialInstanceDynamic(Idx);

		if (!DynMat) continue;

		// 获取图层数量
		FMaterialLayersFunctions LayerFunctions;
		int32 NumLayers = 1;
		if (DynMat->GetMaterialLayers(LayerFunctions))
		{
			NumLayers = LayerFunctions.Layers.Num();
		}

		for (int32 LayerIdx = 0; LayerIdx < NumLayers; ++LayerIdx)
		{
			// ── Shadow Color（向量，图层参数） ──────────────────────
			FMaterialParameterInfo ShadowColorInfo(
				TEXT("Shadow Color"),
				EMaterialParameterAssociation::LayerParameter,
				LayerIdx);

			FLinearColor ExistingColor;
			if (DynMat->GetVectorParameterValue(ShadowColorInfo, ExistingColor))
			{
				DynMat->SetVectorParameterValueByInfo(ShadowColorInfo, ShadowColor);
			}

			// ── Specular（标量，图层参数） ──────────────────────────
			FMaterialParameterInfo SpecularInfo(
				TEXT("Specular"),
				EMaterialParameterAssociation::LayerParameter,
				LayerIdx);

			float ExistingScalar;
			if (DynMat->GetScalarParameterValue(SpecularInfo, ExistingScalar))
			{
				DynMat->SetScalarParameterValueByInfo(SpecularInfo, Specular);
			}

			// ── Rim Light Width（标量，图层参数） ──────────────────
			FMaterialParameterInfo RimLightWidthInfo(
				TEXT("Rim Light Width"),
				EMaterialParameterAssociation::LayerParameter,
				LayerIdx);

			float ExistingRimWidth;
			if (DynMat->GetScalarParameterValue(RimLightWidthInfo, ExistingRimWidth))
			{
				DynMat->SetScalarParameterValueByInfo(RimLightWidthInfo, RimLightWidth);
			}
		}
		++AppliedCount;

		UE_LOG(LogMooaToon, Log,
			TEXT("[MooaToon] 槽 %d 写入: Shadow=(%.3f,%.3f,%.3f) Spec=%.3f RimWidth=%.3f"),
			Idx, ShadowColor.R, ShadowColor.G, ShadowColor.B, Specular, RimLightWidth);
	}

	// =========================================================================
	// 部分 B：写入描边材质（MooaOutlineMaterial）的 Width Scale 全局参数
	// =========================================================================
	UMaterialInterface* OutlineMat = SkelMesh->GetMooaOutlineMaterial();
	if (OutlineMat)
	{
		// 基于现有描边材质创建 MID（如果已经是 MID 则直接用）
		UMaterialInstanceDynamic* OutlineMID = Cast<UMaterialInstanceDynamic>(OutlineMat);
		if (!OutlineMID)
		{
			OutlineMID = UMaterialInstanceDynamic::Create(OutlineMat, SkelMesh);
			SkelMesh->SetMooaOutlineMaterial(OutlineMID);
		}

		// Width Scale 是描边材质的全局参数（细节面板），直接用 SetScalarParameterValue
		OutlineMID->SetScalarParameterValue(TEXT("Width Scale"), WidthScale);

		UE_LOG(LogMooaToon, Log,
			TEXT("[MooaToon] 描边材质 Width Scale 写入: %.3f"), WidthScale);
	}
	else
	{
		UE_LOG(LogMooaToon, Warning,
			TEXT("[MooaToon] 未找到 MooaOutlineMaterial，跳过 Width Scale 写入"));
	}

	UE_LOG(LogMooaToon, Log,
		TEXT("[MooaToon] SetMooaToonParams 完成: 主体材质 %d/%d 槽"),
		AppliedCount, NumMaterials);
}

bool UMooaToonInferenceLibrary::InferAndApply(
	UNNEModelData* ModelData,
	const TArray<float>& InputPixels,
	AActor* TargetActor,
	int32 ElementIndex)
{
	// 1. 先推理
	FMooaToonParams Params;
	if (!RunMooaToonInference(ModelData, InputPixels, Params))
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] InferAndApply: 推理失败"));
		return false;
	}

	// 2. 再写入材质
	FLinearColor ShadowColor(Params.ShadowR, Params.ShadowG, Params.ShadowB, 1.f);
	SetMooaToonParams(TargetActor, ShadowColor, Params.Specular, Params.RimLightWidth, Params.WidthScale, ElementIndex);

	UE_LOG(LogMooaToon, Log, TEXT("[MooaToon] InferAndApply 完成"));
	return true;
}

bool UMooaToonInferenceLibrary::LoadImageToPixels(const FString& ImagePath, TArray<float>& OutPixels)
{
	// 1. 读取文件字节
	TArray<uint8> FileData;
	if (!FFileHelper::LoadFileToArray(FileData, *ImagePath))
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] LoadImageToPixels: 无法读取文件 %s"), *ImagePath);
		return false;
	}

	// 2. 解码 PNG/JPG
	IImageWrapperModule& ImageWrapperModule =
		FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));

	EImageFormat Format = ImageWrapperModule.DetectImageFormat(FileData.GetData(), FileData.Num());
	if (Format == EImageFormat::Invalid)
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] LoadImageToPixels: 不支持的图片格式 %s"), *ImagePath);
		return false;
	}

	TSharedPtr<IImageWrapper> Wrapper = ImageWrapperModule.CreateImageWrapper(Format);
	if (!Wrapper.IsValid() || !Wrapper->SetCompressed(FileData.GetData(), FileData.Num()))
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] LoadImageToPixels: 解码失败 %s"), *ImagePath);
		return false;
	}

	TArray<uint8> RawRGBA;
	if (!Wrapper->GetRaw(ERGBFormat::RGBA, 8, RawRGBA))
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] LoadImageToPixels: GetRaw 失败"));
		return false;
	}

	const int32 SrcW = Wrapper->GetWidth();
	const int32 SrcH = Wrapper->GetHeight();

	// 3. 缩放到 224×224（双线性插值）
	constexpr int32 DstSize = 224;
	TArray<uint8> Resized;
	Resized.SetNumUninitialized(DstSize * DstSize * 4);

	for (int32 DstY = 0; DstY < DstSize; ++DstY)
	{
		for (int32 DstX = 0; DstX < DstSize; ++DstX)
		{
			const float SrcXf = (DstX + 0.5f) * SrcW / DstSize - 0.5f;
			const float SrcYf = (DstY + 0.5f) * SrcH / DstSize - 0.5f;

			const int32 X0 = FMath::Clamp((int32)FMath::FloorToFloat(SrcXf), 0, SrcW - 1);
			const int32 Y0 = FMath::Clamp((int32)FMath::FloorToFloat(SrcYf), 0, SrcH - 1);
			const int32 X1 = FMath::Clamp(X0 + 1, 0, SrcW - 1);
			const int32 Y1 = FMath::Clamp(Y0 + 1, 0, SrcH - 1);

			const float Tx = SrcXf - FMath::FloorToFloat(SrcXf);
			const float Ty = SrcYf - FMath::FloorToFloat(SrcYf);

			for (int32 C = 0; C < 3; ++C)
			{
				const float V00 = RawRGBA[(Y0 * SrcW + X0) * 4 + C];
				const float V10 = RawRGBA[(Y0 * SrcW + X1) * 4 + C];
				const float V01 = RawRGBA[(Y1 * SrcW + X0) * 4 + C];
				const float V11 = RawRGBA[(Y1 * SrcW + X1) * 4 + C];
				const float Val = V00 * (1 - Tx) * (1 - Ty)
				                + V10 * Tx * (1 - Ty)
				                + V01 * (1 - Tx) * Ty
				                + V11 * Tx * Ty;
				Resized[(DstY * DstSize + DstX) * 4 + C] = (uint8)FMath::Clamp(Val, 0.f, 255.f);
			}
			Resized[(DstY * DstSize + DstX) * 4 + 3] = 255;
		}
	}

	// 4. HWC → CHW + ImageNet 归一化
	// mean=[0.485,0.456,0.406]  std=[0.229,0.224,0.225]
	static constexpr float Mean[3] = { 0.485f, 0.456f, 0.406f };
	static constexpr float Std[3]  = { 0.229f, 0.224f, 0.225f };

	constexpr int32 PixelCount = DstSize * DstSize;
	OutPixels.SetNumUninitialized(3 * PixelCount);

	for (int32 C = 0; C < 3; ++C)
	{
		for (int32 I = 0; I < PixelCount; ++I)
		{
			const float Normalized = Resized[I * 4 + C] / 255.f;
			OutPixels[C * PixelCount + I] = (Normalized - Mean[C]) / Std[C];
		}
	}

	UE_LOG(LogMooaToon, Log, TEXT("[MooaToon] LoadImageToPixels 成功: %s (%dx%d → 224x224)"),
		*ImagePath, SrcW, SrcH);
	return true;
}

bool UMooaToonInferenceLibrary::InferFromExampleDir(
	UNNEModelData* ModelData,
	AActor* TargetActor,
	int32 ElementIndex)
{
	// example 目录固定为项目根目录下的 example/
	const FString ExampleDir = FPaths::ConvertRelativePathToFull(
		FPaths::Combine(FPaths::ProjectDir(), TEXT("example")));

	// 找第一张支持的图片，用 IterateDirectory 代替 FindFiles 通配符
	TArray<FString> FoundFiles;
	IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
	PF.IterateDirectory(*ExampleDir, [&FoundFiles](const TCHAR* Path, bool bIsDir) -> bool
	{
		if (!bIsDir)
		{
			const FString Ext = FPaths::GetExtension(FString(Path)).ToLower();
			if (Ext == TEXT("png") || Ext == TEXT("jpg") || Ext == TEXT("jpeg"))
				FoundFiles.Add(FString(Path));
		}
		return true;
	});

	if (FoundFiles.Num() == 0)
	{
		UE_LOG(LogMooaToon, Error,
			TEXT("[MooaToon] InferFromExampleDir: 在 %s 中找不到任何 PNG/JPG 图片"), *ExampleDir);
		return false;
	}

	FoundFiles.Sort();  // 按完整路径升序，确保"第一张"确定
	const FString ImagePath = FoundFiles[0];  // IterateDirectory 已返回全路径
	UE_LOG(LogMooaToon, Log, TEXT("[MooaToon] InferFromExampleDir: 使用图片 %s"), *ImagePath);

	// 读取并归一化
	TArray<float> InputPixels;
	if (!LoadImageToPixels(ImagePath, InputPixels))
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] InferFromExampleDir: LoadImageToPixels 失败"));
		return false;
	}

	// 推理 + 写入材质
	return InferAndApply(ModelData, InputPixels, TargetActor, ElementIndex);
}

// =============================================================================
// 风格化：直方图分析 + PostProcess 应用
// =============================================================================

bool UMooaToonInferenceLibrary::AnalyzeImageStyle(const FString& ImagePath, FMooaToonStyleParams& OutStyle)
{
	OutStyle = FMooaToonStyleParams{};

	// 1. 读取文件 + 解码（与 LoadImageToPixels 同套流程，但跳过 ImageNet 归一化）
	TArray<uint8> FileData;
	if (!FFileHelper::LoadFileToArray(FileData, *ImagePath))
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] AnalyzeImageStyle: 无法读取 %s"), *ImagePath);
		return false;
	}

	IImageWrapperModule& ImageWrapperModule =
		FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));

	const EImageFormat Format = ImageWrapperModule.DetectImageFormat(FileData.GetData(), FileData.Num());
	if (Format == EImageFormat::Invalid)
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] AnalyzeImageStyle: 不支持的格式 %s"), *ImagePath);
		return false;
	}

	TSharedPtr<IImageWrapper> Wrapper = ImageWrapperModule.CreateImageWrapper(Format);
	if (!Wrapper.IsValid() || !Wrapper->SetCompressed(FileData.GetData(), FileData.Num()))
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] AnalyzeImageStyle: 解码失败 %s"), *ImagePath);
		return false;
	}

	TArray<uint8> Raw;
	if (!Wrapper->GetRaw(ERGBFormat::RGBA, 8, Raw))
	{
		UE_LOG(LogMooaToon, Error, TEXT("[MooaToon] AnalyzeImageStyle: GetRaw 失败"));
		return false;
	}

	const int32 SrcW = Wrapper->GetWidth();
	const int32 SrcH = Wrapper->GetHeight();
	if (SrcW <= 0 || SrcH <= 0)
	{
		return false;
	}

	// 2. 用步进采样代替缩放：均匀取 ~64×64 个像素，避免完整 resize 的开销
	constexpr int32 SampleSide = 64;
	const int32 StepX = FMath::Max(1, SrcW / SampleSide);
	const int32 StepY = FMath::Max(1, SrcH / SampleSide);

	double SumR = 0.0, SumG = 0.0, SumB = 0.0;
	double SumLum = 0.0, SumLumSq = 0.0;
	double SumChromaRange = 0.0;  // max(R,G,B) - min(R,G,B)，HSV 饱和度的近似分子
	int32  N = 0;

	for (int32 Y = 0; Y < SrcH; Y += StepY)
	{
		for (int32 X = 0; X < SrcW; X += StepX)
		{
			const int32 Idx = (Y * SrcW + X) * 4;
			const float R = Raw[Idx + 0] / 255.f;
			const float G = Raw[Idx + 1] / 255.f;
			const float B = Raw[Idx + 2] / 255.f;

			SumR += R;
			SumG += G;
			SumB += B;

			const float Lum = 0.299f * R + 0.587f * G + 0.114f * B;
			SumLum   += Lum;
			SumLumSq += Lum * Lum;

			const float MaxC = FMath::Max3(R, G, B);
			const float MinC = FMath::Min3(R, G, B);
			SumChromaRange += (MaxC - MinC);

			++N;
		}
	}

	if (N == 0)
	{
		return false;
	}

	const double InvN = 1.0 / N;
	const float MeanR = static_cast<float>(SumR * InvN);
	const float MeanG = static_cast<float>(SumG * InvN);
	const float MeanB = static_cast<float>(SumB * InvN);
	const float MeanLum = static_cast<float>(SumLum * InvN);
	const float VarLum = FMath::Max(0.f, static_cast<float>(SumLumSq * InvN) - MeanLum * MeanLum);
	const float StdLum = FMath::Sqrt(VarLum);            // 自然范围 ~[0, 0.5]
	const float MeanChroma = static_cast<float>(SumChromaRange * InvN);  // ~[0, 1]

	// 3. 把统计量映射到 PostProcess 目标值
	//    饱和度：参考图越多彩 → 目标饱和度越高。MeanChroma 的常见范围约 0~0.5，乘以 2 后再围绕 1.0 摆动。
	OutStyle.TargetSaturation = FMath::Clamp(0.5f + MeanChroma * 2.0f, 0.5f, 1.8f);

	//    对比度：亮度标准差越大 → 原图对比度越高，按比例增强。
	OutStyle.TargetContrast = FMath::Clamp(0.7f + StdLum * 2.5f, 0.7f, 1.6f);

	//    主色调：RGB 均值；TargetGain 归一化到平均亮度，避免整体变暗/变亮，只保留色偏。
	OutStyle.DominantColor = FLinearColor(MeanR, MeanG, MeanB, 1.f);
	const float SafeLum = FMath::Max(MeanLum, 1e-3f);
	OutStyle.TargetGain = FLinearColor(
		MeanR / SafeLum,
		MeanG / SafeLum,
		MeanB / SafeLum,
		1.f);

	OutStyle.bValid = true;

	UE_LOG(LogMooaToon, Log,
		TEXT("[MooaToon] AnalyzeImageStyle: Dom=(%.3f,%.3f,%.3f) Sat=%.3f Con=%.3f Gain=(%.3f,%.3f,%.3f)"),
		MeanR, MeanG, MeanB,
		OutStyle.TargetSaturation, OutStyle.TargetContrast,
		OutStyle.TargetGain.R, OutStyle.TargetGain.G, OutStyle.TargetGain.B);

	return true;
}

void UMooaToonInferenceLibrary::ApplyStyleToWorld(
	UObject* WorldContextObject,
	const FMooaToonStyleParams& Style,
	float Intensity)
{
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (!World)
	{
		UE_LOG(LogMooaToon, Warning, TEXT("[MooaToon] ApplyStyleToWorld: 拿不到 World"));
		return;
	}

	const float T = FMath::Clamp(Intensity, 0.f, 1.f);

	// Style 无效时，等同于 Intensity=0：所有目标都退化到中性 1.0
	const float TargetSat = Style.bValid ? Style.TargetSaturation : 1.f;
	const float TargetCon = Style.bValid ? Style.TargetContrast   : 1.f;
	const FLinearColor TargetGain = Style.bValid ? Style.TargetGain : FLinearColor::White;

	const float ApplySat = FMath::Lerp(1.f, TargetSat, T);
	const float ApplyCon = FMath::Lerp(1.f, TargetCon, T);
	const FLinearColor ApplyGain(
		FMath::Lerp(1.f, TargetGain.R, T),
		FMath::Lerp(1.f, TargetGain.G, T),
		FMath::Lerp(1.f, TargetGain.B, T),
		1.f);

	auto WriteToVolume = [&](APostProcessVolume* PPV)
	{
		if (!PPV) return;
		FPostProcessSettings& S = PPV->Settings;

		S.bOverride_ColorSaturation = true;
		S.ColorSaturation = FVector4(ApplySat, ApplySat, ApplySat, 1.f);

		S.bOverride_ColorContrast = true;
		S.ColorContrast = FVector4(ApplyCon, ApplyCon, ApplyCon, 1.f);

		S.bOverride_ColorGain = true;
		S.ColorGain = FVector4(ApplyGain.R, ApplyGain.G, ApplyGain.B, 1.f);
	};

	// 1. 写入场景里所有现成的 PPV
	int32 Count = 0;
	APostProcessVolume* AutoPPV = nullptr;
	static const FName AutoPPVTag(TEXT("MooaToonAutoPPV"));

	for (TActorIterator<APostProcessVolume> It(World); It; ++It)
	{
		APostProcessVolume* PPV = *It;
		WriteToVolume(PPV);
		++Count;
		if (PPV->ActorHasTag(AutoPPVTag))
		{
			AutoPPV = PPV;
		}
	}

	// 2. 一个 PPV 都没有 → spawn 一个 Unbound 的兜底
	if (Count == 0)
	{
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AutoPPV = World->SpawnActor<APostProcessVolume>(APostProcessVolume::StaticClass(), FTransform::Identity, Params);
		if (AutoPPV)
		{
			AutoPPV->bUnbound = true;
			AutoPPV->Priority = 1.f;
			AutoPPV->Tags.Add(AutoPPVTag);
			WriteToVolume(AutoPPV);
			++Count;
			UE_LOG(LogMooaToon, Log, TEXT("[MooaToon] ApplyStyleToWorld: 场景无 PPV，已自动创建 Unbound PPV"));
		}
	}

	UE_LOG(LogMooaToon, Log,
		TEXT("[MooaToon] ApplyStyleToWorld: Intensity=%.2f → Sat=%.3f Con=%.3f Gain=(%.3f,%.3f,%.3f)，写入 %d 个 PPV"),
		T, ApplySat, ApplyCon, ApplyGain.R, ApplyGain.G, ApplyGain.B, Count);
}
