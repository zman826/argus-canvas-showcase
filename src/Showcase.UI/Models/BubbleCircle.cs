using System.Windows.Shapes;

namespace Showcase.UI.Models;

/// <summary>
/// 円のライフサイクル状態。
/// FadingIn → Displaying → FadingOut → Dead（→ 再初期化）の順に遷移する。
/// </summary>
public enum FadeState
{
    FadingIn,
    Displaying,
    FadingOut,
    Dead
}

/// <summary>
/// 待機画面を漂う円形写真 1 個分のアニメーション状態。
/// 表示要素（<see cref="Element"/>）と、毎フレーム更新する物理パラメータを保持する。
/// </summary>
public sealed class BubbleCircle
{
    /// <summary>画面に配置される円形要素（Ellipse で確実に円形クリップ）。</summary>
    public required Ellipse Element { get; init; }

    /// <summary>現在の中心 X 座標（px）。</summary>
    public double X { get; set; }

    /// <summary>現在の中心 Y 座標（px）。</summary>
    public double Y { get; set; }

    /// <summary>漂いの基準 X 座標（この周りを Sin 波で揺れる）。</summary>
    public double BaseX { get; set; }

    /// <summary>漂いの基準 Y 座標。</summary>
    public double BaseY { get; set; }

    /// <summary>パルス前の基本直径（px）。</summary>
    public double BaseDiameter { get; set; }

    /// <summary>X 方向ドリフトの位相。</summary>
    public double DriftPhaseX { get; set; }

    /// <summary>Y 方向ドリフトの位相。</summary>
    public double DriftPhaseY { get; set; }

    /// <summary>X 方向ドリフトの周波数。</summary>
    public double DriftFrequencyX { get; set; }

    /// <summary>Y 方向ドリフトの周波数。</summary>
    public double DriftFrequencyY { get; set; }

    /// <summary>X 方向ドリフトの振幅（px）。</summary>
    public double DriftAmplitudeX { get; set; }

    /// <summary>Y 方向ドリフトの振幅（px）。</summary>
    public double DriftAmplitudeY { get; set; }

    /// <summary>パルス（拡縮）の位相。</summary>
    public double PulsePhase { get; set; }

    /// <summary>パルスの周波数。</summary>
    public double PulseFrequency { get; set; }

    /// <summary>現在の不透明度（0.0〜1.0）。</summary>
    public double Opacity { get; set; }

    /// <summary>現在のフェード状態。</summary>
    public FadeState State { get; set; }

    /// <summary>現在の状態（Fade/Display）に入ってからの経過秒数。</summary>
    public double FadeTimer { get; set; }

    /// <summary>Displaying 状態を維持する秒数。</summary>
    public double DisplayDuration { get; set; }
}
