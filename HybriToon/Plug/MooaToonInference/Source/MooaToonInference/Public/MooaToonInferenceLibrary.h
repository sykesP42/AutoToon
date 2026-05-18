// MooaToon Inference Plugin

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "NNEModelData.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "MooaToonInferenceLibrary.generated.h"

/**
 * MooaToon 材质参数推理库
 * 输入: UNNEModelData (mooatoon_model.onnx)
 * 输出: 材质参数 Shadow Color(RGB) + Specular + Rim Light Width + Width Scale(描边)
 */
USTRUCT(BlueprintType)
struct FMooaToonParams
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "MooaToon")
	float ShadowR = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "MooaToon")
	float ShadowG = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "MooaToon")
	float ShadowB = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "MooaToon")
	float Specular = 0.5f;

	/** Rim Light Width — 图层参数（LayerParameter），范围 0~1 */
	UPROPERTY(BlueprintReadOnly, Category = "MooaToon")
	float RimLightWidth = 0.5f;

	/** Width Scale — 描边材质（MooaOutlineMaterial）的全局参数，范围 0.5~3.0 */
	UPROPERTY(BlueprintReadOnly, Category = "MooaToon")
	float WidthScale = 1.f;
};

/**
 * 由参考图直方图分析得到的"风格化"目标参数。
 * 这些是绝对目标值（Intensity=1 时完全应用，=0 时退化到中性 1.0），
 * 实际写入 PostProcess 时由 ApplyStyleToWorld 内部按 Intensity 做 Lerp。
 */
USTRUCT(BlueprintType)
struct FMooaToonStyleParams
{
	GENERATED_BODY()

	/** 主色调（参考图 RGB 平均值，已归一化到 [0,1]） */
	UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Style")
	FLinearColor DominantColor = FLinearColor::White;

	/** PostProcess.ColorSaturation 目标值（中性 1.0；>1 更鲜艳，<1 更灰） */
	UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Style")
	float TargetSaturation = 1.f;

	/** PostProcess.ColorContrast 目标值（中性 1.0；>1 对比更强） */
	UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Style")
	float TargetContrast = 1.f;

	/** PostProcess.ColorGain 的 RGB 偏色（已归一化保持亮度，A 通道恒为 1） */
	UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Style")
	FLinearColor TargetGain = FLinearColor::White;

	/** 是否已经分析过（false 时 ApplyStyleToWorld 直接走中性参数） */
	UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Style")
	bool bValid = false;
};

UCLASS()
class MOOATOONINFERENCE_API UMooaToonInferenceLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * 用 ONNX 模型推理材质参数
	 * @param ModelData   Content Browser 里导入的 mooatoon_model.onnx 资产
	 * @param InputPixels 224x224 RGB 图片像素，已归一化为 float（CHW 格式，长度 150528）
	 * @param OutParams   推理结果：阴影色 + 描边宽度 + 高光强度
	 * @return 推理是否成功
	 */
	UFUNCTION(BlueprintCallable, Category = "MooaToon|Inference")
	static bool RunMooaToonInference(
		UNNEModelData* ModelData,
		const TArray<float>& InputPixels,
		FMooaToonParams& OutParams
	);

	/**
	 * 把推理结果写入材质实例参数
	 * @param MaterialInstance 目标材质实例
	 * @param Params           RunMooaToonInference 的输出
	 */
	UFUNCTION(BlueprintCallable, Category = "MooaToon|Inference")
	static void ApplyParamsToMaterial(
		UMaterialInstanceDynamic* MaterialInstance,
		const FMooaToonParams& Params
	);

	/**
	 * 一步到位：直接修改场景中角色的材质参数（手填数值，不经过 ONNX）
	 * @param TargetActor     要修改材质的角色（从场景拖入）
	 * @param ShadowColor     阴影色 RGB（线性颜色，范围 0~1）
	 * @param Specular        高光强度（范围 0~1），图层参数
	 * @param RimLightWidth   边缘光宽度（范围 0~1），图层参数
	 * @param WidthScale      描边宽度（范围 0.5~3.0），MooaOutlineMaterial 的全局参数
	 * @param ElementIndex    材质槽位索引（默认 -1 写入全部）
	 */
	UFUNCTION(BlueprintCallable, Category = "MooaToon", meta = (AdvancedDisplay = "ElementIndex"))
	static void SetMooaToonParams(
		AActor* TargetActor,
		FLinearColor ShadowColor,
		float Specular       = 0.5f,
		float RimLightWidth  = 0.5f,
		float WidthScale     = 1.0f,
		int32 ElementIndex   = -1
	);

	/**
	 * 从磁盘读取 PNG/JPG，缩放到 224×224，做 ImageNet 归一化，输出 CHW float 数组
	 * @param ImagePath   绝对路径，例如 "D:/unreal/.../Content/images/xxx.png"
	 * @param OutPixels   输出 float 数组，长度 150528（3×224×224）
	 * @return 是否成功
	 */
	UFUNCTION(BlueprintCallable, Category = "MooaToon|Inference")
	static bool LoadImageToPixels(const FString& ImagePath, TArray<float>& OutPixels);

	/**
	 * 完整推理链路：ONNX 推理图片 → 自动写入角色材质
	 * 蓝图一个节点完成全流程
	 * @param ModelData    Content Browser 里的 mooatoon_model 资产
	 * @param InputPixels  224x224 RGB 图片，ImageNet 归一化后的 CHW float 数组（长度 150528）
	 * @param TargetActor  要修改材质的角色
	 * @param ElementIndex 材质槽位索引（默认 -1 写入全部）
	 * @return 推理是否成功
	 */
	UFUNCTION(BlueprintCallable, Category = "MooaToon", meta = (AdvancedDisplay = "ElementIndex"))
	static bool InferAndApply(
		UNNEModelData* ModelData,
		const TArray<float>& InputPixels,
		AActor* TargetActor,
		int32 ElementIndex = -1
	);

	/**
	 * 从 example 目录自动读取第一张图片并推理，写入角色材质
	 * 图片目录固定为项目根目录下的 example/ 文件夹
	 * @param ModelData    Content Browser 里的 mooatoon_model 资产
	 * @param TargetActor  要修改材质的角色
	 * @param ElementIndex 材质槽位索引（默认 -1 写入全部）
	 * @return 推理是否成功
	 */
	UFUNCTION(BlueprintCallable, Category = "MooaToon", meta = (AdvancedDisplay = "ElementIndex"))
	static bool InferFromExampleDir(
		UNNEModelData* ModelData,
		AActor* TargetActor,
		int32 ElementIndex = -1
	);

	/**
	 * 用简单颜色直方图分析参考图，提取主色调 + 推断目标饱和度/对比度。
	 * 算法（保持简单）：
	 *   - 缩放到 64×64
	 *   - 累计 RGB 均值     → DominantColor
	 *   - 累计 max-min       → 目标饱和度（HSV 风格的近似值）
	 *   - 累计亮度均值/方差   → 目标对比度（基于亮度标准差）
	 *   - DominantColor 归一化到平均亮度 → TargetGain（避免整体变暗/变亮）
	 *
	 * @param ImagePath 参考图绝对路径（PNG / JPG）
	 * @param OutStyle  分析得到的目标值；bValid=true 表示成功
	 */
	UFUNCTION(BlueprintCallable, Category = "MooaToon|Style")
	static bool AnalyzeImageStyle(const FString& ImagePath, FMooaToonStyleParams& OutStyle);

	/**
	 * 把风格参数写入场景里所有的 PostProcessVolume。
	 * 找不到任何 PPV 时，自动 Spawn 一个 Unbound 的（Tag = MooaToonAutoPPV），方便后续清理/复用。
	 *
	 * @param WorldContextObject 任何能拿到 World 的对象（widget / actor 都行）
	 * @param Style              AnalyzeImageStyle 的结果
	 * @param Intensity          0~1；0 = 完全中性（ColorGrading 关闭 override），1 = 完全应用 Style
	 */
	UFUNCTION(BlueprintCallable, Category = "MooaToon|Style", meta = (WorldContext = "WorldContextObject"))
	static void ApplyStyleToWorld(
		UObject* WorldContextObject,
		const FMooaToonStyleParams& Style,
		float Intensity = 1.f
	);
};
