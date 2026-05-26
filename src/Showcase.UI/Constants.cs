namespace Showcase.UI;

/// <summary>
/// Phase 4 で TBD だった 10 項目を定数化したもの。
/// UI レイアウト・遷移・将来のデータ連携で参照する共通値を集約する。
/// </summary>
public static class Constants
{
    /// <summary>CIMA ブランドカラー（プライマリ）。</summary>
    public const string CimaBrandColorHex = "#0066CC";

    /// <summary>テキストロゴ文言。</summary>
    public const string LogoText = "CIMA";

    /// <summary>動画ファイルの基準ディレクトリ（リポジトリルートからの相対）。</summary>
    public const string VideoBaseDirectory = @"data\cases\videos\";

    /// <summary>待機画面タッチ時の遷移先。</summary>
    public const string StandbyTouchTarget = "HomeWindow";

    /// <summary>無操作で待機画面へ自動復帰するまでの秒数。</summary>
    public const int IdleTimeoutSeconds = 60;

    /// <summary>検索結果の列数。</summary>
    public const int SearchResultColumns = 2;

    /// <summary>カード写真のアスペクト比（幅）。</summary>
    public const double CardPhotoAspectWidth = 4.0;

    /// <summary>カード写真のアスペクト比（高さ）。</summary>
    public const double CardPhotoAspectHeight = 3.0;

    /// <summary>外部 URL ボタンを表示するか（完全オフライン運用のため既定 false）。</summary>
    public const bool ShowExternalUrlButton = false;

    /// <summary>事例画像の基準ディレクトリ（リポジトリルートからの相対）。</summary>
    public const string CaseImageBaseDirectory = @"data\cases\images\";

    /// <summary>UI の既定フォントファミリ。</summary>
    public const string PrimaryFontFamily = "Yu Gothic UI";

    /// <summary>関連事例の最小表示件数。</summary>
    public const int RelatedCaseMinCount = 3;

    /// <summary>関連事例の最大表示件数。</summary>
    public const int RelatedCaseMaxCount = 5;

    // --- FloatingCanvas（待機画面の円形フローティング演出。アニメ本体は Phase 5）---

    /// <summary>フローティング円の個数。</summary>
    public const int FloatingCircleCount = 25;

    /// <summary>フローティング円の最小直径(px)。</summary>
    public const double FloatingCircleMinDiameter = 50;

    /// <summary>フローティング円の最大直径(px)。</summary>
    public const double FloatingCircleMaxDiameter = 250;

    /// <summary>フローティング円の FadeIn/Out 秒数。</summary>
    public const double FloatingCircleFadeSeconds = 1.5;
}
