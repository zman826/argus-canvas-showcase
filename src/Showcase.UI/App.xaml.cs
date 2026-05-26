using System.Windows;
using Showcase.UI.Services;

namespace Showcase.UI;

/// <summary>
/// アプリケーションエントリポイント。起動時に待機画面を表示する。
/// </summary>
public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // 最初の画面は待機画面。以降の遷移は NavigationService が管理する。
        NavigationService.Instance.NavigateTo("Standby");
    }
}
