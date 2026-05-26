using System.Windows;
using System.Windows.Controls;
using Showcase.UI.Models;
using Showcase.UI.Services;

namespace Showcase.UI.Windows;

/// <summary>
/// 検索結果画面。事例カードを 2 列で一覧表示する。
/// </summary>
public partial class SearchResultsWindow : Window
{
    public SearchResultsWindow()
    {
        InitializeComponent();

        var cases = DummyData.GetCases();
        ResultsList.ItemsSource = cases;

        // TODO(Phase 6): 実際の検索クエリ文字列をヘッダーに反映する。
        HeaderText.Text = $"「事例一覧」{cases.Count}件";
    }

    private void OnCardClick(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.ResetIdleTimer();
        if (sender is Button { Tag: string caseId })
        {
            NavigationService.Instance.NavigateTo("Detail", caseId);
        }
    }

    private void OnBackToHome(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.NavigateTo("Home");
    }
}
