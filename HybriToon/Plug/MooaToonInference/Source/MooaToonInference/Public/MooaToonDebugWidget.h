// MooaToon Inference Plugin

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Components/Slider.h"
#include "Components/TextBlock.h"
#include "Components/Button.h"
#include "Components/EditableTextBox.h"
#include "Components/Image.h"
#include "NNEModelData.h"
#include "MooaToonInferenceLibrary.h"
#include "MooaToonDebugWidget.generated.h"

/**
 * MooaToon 材质参数调试面板（训练数据采集用）
 *
 * ─── 使用方式 ───────────────────────────────────────────────────────────────
 *  1. 在 UMG 中新建 Widget Blueprint，父类选择 UMooaToonDebugWidget
 *  2. 按照下方 meta=(BindWidget) 的变量名，在 Designer 中创建同名控件
 *  3. 把 WBP 添加到视口（见 AddToViewport 蓝图节点 或 C++ 侧调用）
 *  4. 在 Details 面板或蓝图中把 TargetActor / ModelData / ImagePath 赋值
 *  5. 拖动滑条 → 实时修改材质 → 满意后点 "导出 CSV" 保存参数
 *
 * ─── 控件命名规范 ──────────────────────────────────────────────────────────
 *  Slider:         Slider_R / Slider_G / Slider_B / Slider_Specular
 *  数值显示 Text:  Text_R   / Text_G   / Text_B   / Text_Specular
 *  颜色预览 Image: Img_ColorPreview
 *  状态栏 Text:    Text_Status
 *  图片路径输入:   TextBox_ImagePath
 *  按钮:           Btn_Apply / Btn_Reset / Btn_RunInference / Btn_ExportCSV
 * ───────────────────────────────────────────────────────────────────────────
 */
UCLASS(Abstract, BlueprintType)
class MOOATOONINFERENCE_API UMooaToonDebugWidget : public UUserWidget
{
    GENERATED_BODY()

    // =========================================================================
    // 区域 1：外部依赖（Details 面板 / 蓝图 / C++ 赋值）
    // =========================================================================
public:

    /** 要控制材质的目标角色（把场景里的角色拖进来，支持运行时切换） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MooaToon|Setup")
    TObjectPtr<AActor> TargetActor = nullptr;

    /** Content Browser 里导入的 mooatoon_model.onnx 资产（ONNX 推理用） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MooaToon|Setup")
    TObjectPtr<UNNEModelData> ModelData = nullptr;

    /** 传给 LoadImageToPixels 的参考图绝对路径（支持 PNG / JPG） */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MooaToon|Setup")
    FString ImagePath;

    /**
     * 导出 CSV 的存放目录（绝对路径）
     * 留空则自动使用 [项目根]/Saved/MooaToonParams/
     */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MooaToon|Setup")
    FString ExportDir;

    // =========================================================================
    // 区域 2：当前参数（只读，由滑条驱动；蓝图可绑定显示）
    // =========================================================================

    UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Params")
    float ShadowR = 0.3f;

    UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Params")
    float ShadowG = 0.3f;

    UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Params")
    float ShadowB = 0.3f;

    UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Params")
    float Specular = 0.5f;

    UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Params")
    float RimLightWidth = 0.5f;

    UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Params")
    float WidthScale = 1.0f;

    /** 后处理风格强度：0=不影响后处理，1=完全应用参考图风格 */
    UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Params")
    float StyleIntensity = 0.5f;

    /** 上一次 AnalyzeImageStyle 的结果；点击"分析参考图"按钮后填充 */
    UPROPERTY(BlueprintReadOnly, Category = "MooaToon|Params")
    FMooaToonStyleParams CachedStyle;

    // =========================================================================
    // 区域 3：BindWidget 控件
    // =========================================================================

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<USlider> Slider_R;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<USlider> Slider_G;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<USlider> Slider_B;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<USlider> Slider_Specular;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<USlider> Slider_RimLightWidth;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<USlider> Slider_WidthScale;

    /** 后处理风格强度（0~1） */
    UPROPERTY(meta = (BindWidgetOptional))
    TObjectPtr<USlider> Slider_StyleIntensity;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UTextBlock> Text_R;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UTextBlock> Text_G;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UTextBlock> Text_B;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UTextBlock> Text_Specular;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UTextBlock> Text_RimLightWidth;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UTextBlock> Text_WidthScale;

    UPROPERTY(meta = (BindWidgetOptional))
    TObjectPtr<UTextBlock> Text_StyleIntensity;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UImage> Img_ColorPreview;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UTextBlock> Text_Status;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UEditableTextBox> TextBox_ImagePath;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UButton> Btn_Apply;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UButton> Btn_Reset;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UButton> Btn_RunInference;

    UPROPERTY(meta = (BindWidget))
    TObjectPtr<UButton> Btn_ExportCSV;

    /** 点击后扫描参考图直方图 → 立即按当前 StyleIntensity 写入 PostProcess */
    UPROPERTY(meta = (BindWidgetOptional))
    TObjectPtr<UButton> Btn_AnalyzeStyle;

    // =========================================================================
    // 区域 4：蓝图可调用接口
    // =========================================================================

    UFUNCTION(BlueprintCallable, Category = "MooaToon|Debug")
    void SetAndApply(float R, float G, float B, float Spec, float RimWidth, float OutlineWidth);

    UFUNCTION(BlueprintCallable, Category = "MooaToon|Debug")
    void ApplyCurrentParams();

    UFUNCTION(BlueprintCallable, Category = "MooaToon|Debug")
    bool RunInference();

    UFUNCTION(BlueprintCallable, Category = "MooaToon|Debug")
    bool ExportParamsToCSV();

    UFUNCTION(BlueprintCallable, Category = "MooaToon|Debug")
    void SetTargetActor(AActor* NewActor);

    // =========================================================================
    // 区域 5：蓝图事件
    // =========================================================================

    UFUNCTION(BlueprintImplementableEvent, Category = "MooaToon|Debug")
    void OnParamsUpdated(float R, float G, float B, float Spec, float RimWidth, float OutlineWidth);

    UFUNCTION(BlueprintImplementableEvent, Category = "MooaToon|Debug")
    void OnInferenceResult(const FString& StatusText, bool bSuccess);

    UFUNCTION(BlueprintImplementableEvent, Category = "MooaToon|Debug")
    void OnCSVExported(const FString& FilePath, bool bSuccess);

    // =========================================================================
    // 区域 6：UUserWidget 生命周期
    // =========================================================================
protected:
    virtual void NativeConstruct() override;
    virtual void NativeDestruct() override;

    // =========================================================================
    // 区域 7：内部实现
    // =========================================================================
private:
    void Internal_ApplyToMaterial();
    void Internal_ApplyStyle();
    void Internal_RefreshUI();
    void Internal_SetStatus(const FString& Msg, bool bError = false);

    UFUNCTION()
    void OnSlider_R_Changed(float Value);
    UFUNCTION()
    void OnSlider_G_Changed(float Value);
    UFUNCTION()
    void OnSlider_B_Changed(float Value);
    UFUNCTION()
    void OnSlider_Specular_Changed(float Value);
    UFUNCTION()
    void OnSlider_RimLightWidth_Changed(float Value);
    UFUNCTION()
    void OnSlider_WidthScale_Changed(float Value);
    UFUNCTION()
    void OnSlider_StyleIntensity_Changed(float Value);

    UFUNCTION()
    void OnBtn_Apply_Clicked();
    UFUNCTION()
    void OnBtn_Reset_Clicked();
    UFUNCTION()
    void OnBtn_RunInference_Clicked();
    UFUNCTION()
    void OnBtn_ExportCSV_Clicked();
    UFUNCTION()
    void OnBtn_AnalyzeStyle_Clicked();

    UFUNCTION()
    void OnTextBox_ImagePath_Changed(const FText& Text);
};
