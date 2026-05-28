using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Showcase.UI.Models;
using Showcase.UI.Services;
using Ellipse = System.Windows.Shapes.Ellipse;

namespace Showcase.UI.Windows;

/// <summary>
/// 待機画面。来場者の声かけ・タッチを待つホーム前のアイドル画面。
/// 背面で円形写真フローティングアニメーション（Phase 5）を再生する。
/// </summary>
public partial class StandbyWindow : Window
{
    private readonly List<BubbleCircle> _bubbles = new();
    private readonly List<string> _imagePaths = new();
    private readonly Random _random = new();
    private readonly Dictionary<string, BitmapImage> _imageCache = new();
    private DispatcherTimer? _animationTimer;
    private DateTime _lastFrame;

    public StandbyWindow()
    {
        InitializeComponent();

        // 待機画面では無操作タイマーを止める（ここがアイドルの終着点のため）
        NavigationService.Instance.StopIdleTimer();

        Loaded += (_, _) => InitializeAnimation();
    }

    private void OnTouch(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.NavigateTo("Home");
    }

    /// <summary>
    /// 円の生成とアニメーションループの開始。ウィンドウ Loaded 後に 1 回呼ぶ。
    /// </summary>
    private void InitializeAnimation()
    {
        LoadImagePaths();

        double canvasW = AnimationCanvas.ActualWidth;
        double canvasH = AnimationCanvas.ActualHeight;

        for (int i = 0; i < Constants.CircleCount; i++)
        {
            string? imagePath = _imagePaths.Count > 0
                ? _imagePaths[_random.Next(_imagePaths.Count)]
                : null;

            var element = CreateBubbleElement(imagePath);
            var bubble = new BubbleCircle { Element = element };

            ResetBubble(bubble, canvasW, canvasH);

            // 起動時の見た目分散：フェードイン開始を i * 0.3 秒ずつ遅らせ、
            // 全円が同時に湧き出さないようカスケード表示にする。
            bubble.FadeTimer = -(i * 0.3);
            bubble.Element.Opacity = 0;

            _bubbles.Add(bubble);
        }

        _lastFrame = DateTime.Now;
        _animationTimer = new DispatcherTimer(DispatcherPriority.Background)
        {
            Interval = TimeSpan.FromMilliseconds(1000.0 / Constants.AnimationFps)
        };
        _animationTimer.Tick += OnAnimationTick;
        _animationTimer.Start();
    }

    /// <summary>
    /// <see cref="Constants.ImagesDirectory"/> を再帰スキャンし、写真パスを収集する。
    /// 写真が見つからない場合は空のまま（フォールバック色で動作）。
    /// </summary>
    private void LoadImagePaths()
    {
        _imagePaths.Clear();

        string? dir = ResolveImagesDirectory();
        if (dir is null || !Directory.Exists(dir))
        {
            return;
        }

        string[] extensions = { ".jpg", ".jpeg", ".png" };
        foreach (var path in Directory.EnumerateFiles(dir, "*.*", SearchOption.AllDirectories))
        {
            if (extensions.Contains(Path.GetExtension(path).ToLowerInvariant()))
            {
                _imagePaths.Add(path);
            }
        }
    }

    /// <summary>
    /// 実行ディレクトリ（bin 配下）から親方向へ辿り、画像ディレクトリの実在パスを探す。
    /// 見つからなければ null。
    /// </summary>
    private static string? ResolveImagesDirectory()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            string candidate = Path.Combine(dir.FullName, Constants.ImagesDirectory);
            if (Directory.Exists(candidate))
            {
                return candidate;
            }
            dir = dir.Parent;
        }
        return null;
    }

    /// <summary>
    /// 円形要素（Ellipse）を生成し、写真は ImageBrush、なければ単色塗りで Canvas に追加する。
    /// Ellipse は形状自体が楕円のため、子要素クリップ問題なしに確実に円形になる。
    /// </summary>
    private Ellipse CreateBubbleElement(string? imagePath)
    {
        var ellipse = new Ellipse();

        if (imagePath is not null)
        {
            ellipse.Fill = new ImageBrush
            {
                ImageSource = GetCachedImage(imagePath),
                Stretch = Stretch.UniformToFill
            };
        }
        else
        {
            string hex = Constants.FallbackColors[_random.Next(Constants.FallbackColors.Length)];
            ellipse.Fill = new SolidColorBrush(
                (Color)ColorConverter.ConvertFromString(hex));
        }

        AnimationCanvas.Children.Add(ellipse);
        return ellipse;
    }

    /// <summary>BitmapImage を OnLoad で事前デコードし、同一パスはキャッシュで使い回す。</summary>
    private BitmapImage GetCachedImage(string path)
    {
        if (_imageCache.TryGetValue(path, out var cached))
        {
            return cached;
        }

        var bitmap = new BitmapImage();
        bitmap.BeginInit();
        bitmap.CacheOption = BitmapCacheOption.OnLoad;
        bitmap.UriSource = new Uri(path, UriKind.Absolute);
        bitmap.EndInit();
        bitmap.Freeze();

        _imageCache[path] = bitmap;
        return bitmap;
    }

    /// <summary>
    /// 円を新しいランダムパラメータで初期化（再出現含む）。
    /// </summary>
    private void ResetBubble(BubbleCircle bubble, double canvasW, double canvasH)
    {
        // キャンバスが未レイアウト（0 幅）の場合のフォールバック寸法。
        if (canvasW <= 0) canvasW = 1920;
        if (canvasH <= 0) canvasH = 1080;

        bubble.BaseX = _random.NextDouble() * canvasW;
        bubble.BaseY = _random.NextDouble() * canvasH;
        bubble.BaseDiameter = Lerp(Constants.MinDiameter, Constants.MaxDiameter, _random.NextDouble());

        bubble.DriftFrequencyX = Lerp(0.3, 1.0, _random.NextDouble());
        bubble.DriftFrequencyY = Lerp(0.3, 1.0, _random.NextDouble());
        bubble.PulseFrequency = Lerp(0.3, 1.0, _random.NextDouble());

        bubble.DriftAmplitudeX = bubble.BaseDiameter * Lerp(0.5, 1.5, _random.NextDouble());
        bubble.DriftAmplitudeY = bubble.BaseDiameter * Lerp(0.5, 1.5, _random.NextDouble());

        bubble.DriftPhaseX = _random.NextDouble() * Math.PI * 2;
        bubble.DriftPhaseY = _random.NextDouble() * Math.PI * 2;
        bubble.PulsePhase = _random.NextDouble() * Math.PI * 2;

        // 写真があれば別の写真へ差し替える（ImageBrush の ImageSource を差し替え）。
        if (_imagePaths.Count > 0 && bubble.Element.Fill is ImageBrush brush)
        {
            brush.ImageSource = GetCachedImage(_imagePaths[_random.Next(_imagePaths.Count)]);
        }

        bubble.State = FadeState.FadingIn;
        bubble.FadeTimer = 0;
        bubble.Opacity = 0;
        bubble.DisplayDuration = Lerp(Constants.MinDisplaySec, Constants.MaxDisplaySec, _random.NextDouble());

        bubble.X = bubble.BaseX;
        bubble.Y = bubble.BaseY;
    }

    /// <summary>毎フレーム：寿命・漂い・拡縮を進め、要素へ反映する。</summary>
    private void OnAnimationTick(object? sender, EventArgs e)
    {
        var now = DateTime.Now;
        double delta = (now - _lastFrame).TotalSeconds;
        _lastFrame = now;
        if (delta <= 0) return;

        double canvasW = AnimationCanvas.ActualWidth;
        double canvasH = AnimationCanvas.ActualHeight;

        foreach (var bubble in _bubbles)
        {
            bubble.FadeTimer += delta;

            // --- 寿命（フェード）状態機械 ---
            switch (bubble.State)
            {
                case FadeState.FadingIn:
                    // 負の FadeTimer は起動時ディレイ：その間は不可視のまま待機。
                    if (bubble.FadeTimer < 0)
                    {
                        bubble.Opacity = 0;
                    }
                    else if (bubble.FadeTimer >= Constants.FadeDurationSec)
                    {
                        bubble.Opacity = 1;
                        bubble.State = FadeState.Displaying;
                        bubble.FadeTimer = 0;
                    }
                    else
                    {
                        bubble.Opacity = bubble.FadeTimer / Constants.FadeDurationSec;
                    }
                    break;

                case FadeState.Displaying:
                    bubble.Opacity = 1;
                    if (bubble.FadeTimer >= bubble.DisplayDuration)
                    {
                        bubble.State = FadeState.FadingOut;
                        bubble.FadeTimer = 0;
                    }
                    break;

                case FadeState.FadingOut:
                    if (bubble.FadeTimer >= Constants.FadeDurationSec)
                    {
                        bubble.Opacity = 0;
                        bubble.State = FadeState.Dead;
                    }
                    else
                    {
                        bubble.Opacity = 1 - (bubble.FadeTimer / Constants.FadeDurationSec);
                    }
                    break;

                case FadeState.Dead:
                    ResetBubble(bubble, canvasW, canvasH);
                    break;
            }

            // --- 漂い（Sin 波ドリフト）---
            bubble.DriftPhaseX += delta * bubble.DriftFrequencyX * Constants.DriftSpeed * Math.PI * 2;
            bubble.DriftPhaseY += delta * bubble.DriftFrequencyY * Constants.DriftSpeed * Math.PI * 2;
            bubble.X = bubble.BaseX + Math.Sin(bubble.DriftPhaseX) * bubble.DriftAmplitudeX;
            bubble.Y = bubble.BaseY + Math.Sin(bubble.DriftPhaseY) * bubble.DriftAmplitudeY;

            // --- 拡縮（Sin 波パルス）---
            bubble.PulsePhase += delta * bubble.PulseFrequency * Constants.PulseSpeed * Math.PI * 2;
            double midScale = (Constants.MinScale + Constants.MaxScale) / 2.0;
            double ampScale = (Constants.MaxScale - Constants.MinScale) / 2.0;
            double scale = midScale + Math.Sin(bubble.PulsePhase) * ampScale;
            double diameter = bubble.BaseDiameter * scale;

            // --- 要素へ反映（中心座標 → 左上座標へ変換）---
            // Ellipse は Width = Height のとき自動的に正円になるため CornerRadius は不要。
            var el = bubble.Element;
            el.Width = diameter;
            el.Height = diameter;
            el.Opacity = bubble.Opacity;
            Canvas.SetLeft(el, bubble.X - diameter / 2.0);
            Canvas.SetTop(el, bubble.Y - diameter / 2.0);
        }
    }

    protected override void OnClosed(EventArgs e)
    {
        if (_animationTimer is not null)
        {
            _animationTimer.Stop();
            _animationTimer.Tick -= OnAnimationTick;
            _animationTimer = null;
        }
        base.OnClosed(e);
    }

    /// <summary>線形補間。</summary>
    private static double Lerp(double a, double b, double t) => a + (b - a) * t;
}
