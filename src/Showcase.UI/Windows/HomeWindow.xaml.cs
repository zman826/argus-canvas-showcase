using System.Windows;
using Showcase.UI.Services;

namespace Showcase.UI.Windows;

/// <summary>
/// ホーム画面。検索手段（音声 / キーワード / カテゴリ）を選択する。
/// </summary>
public partial class HomeWindow : Window
{
    public HomeWindow()
    {
        InitializeComponent();
    }

    private void OnSearchByVoice(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.ResetIdleTimer();
        // TODO(Phase 6): 音声入力フロー（Whisper → intent 分類 → RAG）を起動する。
        NavigationService.Instance.NavigateTo("SearchResults");
    }

    private void OnSearchByKeyword(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.ResetIdleTimer();
        // TODO(Phase 5): キーワード入力 UI を表示する。
        NavigationService.Instance.NavigateTo("SearchResults");
    }

    private void OnSearchByCategory(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.ResetIdleTimer();
        // TODO(Phase 5): カテゴリ選択 UI を表示する。
        NavigationService.Instance.NavigateTo("SearchResults");
    }

    private void OnBack(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.NavigateTo("Standby");
    }
}
