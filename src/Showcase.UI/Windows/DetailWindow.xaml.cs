using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;
using Showcase.UI.Models;
using Showcase.UI.Services;

namespace Showcase.UI.Windows;

/// <summary>
/// 詳細画面。1 事例の写真・説明・関連事例を表示する。
/// </summary>
public partial class DetailWindow : Window
{
    private const int ThumbnailCount = 5;

    public DetailWindow(string? caseId)
    {
        InitializeComponent();

        var item = caseId is null ? null : DummyData.GetCaseById(caseId);
        if (item is null)
        {
            // データ未取得時のフォールバック表示
            TitleText.Text = "事例が見つかりませんでした";
            return;
        }

        TitleText.Text = item.Title;
        SubTitleText.Text = item.SubTitle;
        YearText.Text = $"{item.Year}年";
        CategoryText.Text = item.Category;
        DescriptionText.Text = item.Description;

        BuildThumbnails();
        BuildRelatedCases(item.CaseId);
    }

    /// <summary>サムネイル（W80 H60）を 5 件分プレースホルダ生成する。</summary>
    private void BuildThumbnails()
    {
        for (var i = 0; i < ThumbnailCount; i++)
        {
            ThumbnailPanel.Children.Add(new Rectangle
            {
                Width = 80,
                Height = 60,
                Fill = new SolidColorBrush(Color.FromRgb(0xE8, 0xEE, 0xF7)),
                Margin = new Thickness(0, 0, 8, 0),
            });
            // TODO(Phase 6): data\cases\images 配下の実サムネイルを読み込む。
        }
    }

    /// <summary>関連事例カード（W200）を横並びで生成する。</summary>
    private void BuildRelatedCases(string currentCaseId)
    {
        foreach (var related in DummyData.GetRelatedCases(currentCaseId))
        {
            var card = new Button
            {
                Tag = related.CaseId,
                Width = 200,
                Margin = new Thickness(0, 0, 16, 0),
                Padding = new Thickness(0),
                Background = Brushes.White,
                BorderBrush = new SolidColorBrush(Color.FromRgb(0xDD, 0xDD, 0xDD)),
                BorderThickness = new Thickness(1),
                Cursor = System.Windows.Input.Cursors.Hand,
            };
            card.Click += OnRelatedClick;

            var panel = new StackPanel();
            panel.Children.Add(new Rectangle
            {
                Height = 120,
                Fill = new SolidColorBrush(Color.FromRgb(0xE8, 0xEE, 0xF7)),
            });
            panel.Children.Add(new TextBlock
            {
                Text = related.Title,
                FontSize = 15,
                FontWeight = FontWeights.Bold,
                Foreground = new SolidColorBrush(Color.FromRgb(0x22, 0x22, 0x22)),
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(10, 8, 10, 10),
            });
            card.Content = panel;

            RelatedPanel.Children.Add(card);
        }
    }

    private void OnRelatedClick(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.ResetIdleTimer();
        if (sender is Button { Tag: string caseId })
        {
            NavigationService.Instance.NavigateTo("Detail", caseId);
        }
    }

    private void OnBackToResults(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.NavigateTo("SearchResults");
    }

    private void OnHome(object sender, RoutedEventArgs e)
    {
        NavigationService.Instance.NavigateTo("Home");
    }
}
