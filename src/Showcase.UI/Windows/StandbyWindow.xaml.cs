using System.Windows;
using Showcase.UI.Services;

namespace Showcase.UI.Windows;

/// <summary>
/// 待機画面。来場者の声かけ・タッチを待つホーム前のアイドル画面。
/// </summary>
public partial class StandbyWindow : Window
{
    public StandbyWindow()
    {
        InitializeComponent();

        // 待機画面では無操作タイマーを止める（ここがアイドルの終着点のため）
        NavigationService.Instance.StopIdleTimer();

        // TODO(Phase 5): FloatingCanvas に円形フローティングアニメーションを生成・開始する。
    }

    private void OnTouch(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.NavigateTo("Home");
    }
}
