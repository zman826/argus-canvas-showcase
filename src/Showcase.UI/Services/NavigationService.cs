using System.Windows;
using System.Windows.Threading;
using Showcase.UI.Windows;

namespace Showcase.UI.Services;

/// <summary>
/// 画面遷移と無操作タイマーを一元管理するシングルトン。
/// サイネージは常時 1 ウィンドウ表示とし、遷移時に旧ウィンドウを閉じて新ウィンドウを開く。
/// </summary>
public sealed class NavigationService
{
    private static readonly Lazy<NavigationService> Lazy = new(() => new NavigationService());

    /// <summary>シングルトンインスタンス。</summary>
    public static NavigationService Instance => Lazy.Value;

    private readonly DispatcherTimer _idleTimer;
    private Window? _currentWindow;

    private NavigationService()
    {
        _idleTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(Constants.IdleTimeoutSeconds),
        };
        _idleTimer.Tick += OnIdleTimeout;
    }

    private void OnIdleTimeout(object? sender, EventArgs e)
    {
        // 無操作タイムアウト：待機画面へ自動復帰
        NavigateTo("Standby");
    }

    /// <summary>
    /// 指定ターゲットへ遷移する。
    /// </summary>
    /// <param name="target">"Standby" / "Home" / "SearchResults" / "Detail"。</param>
    /// <param name="parameter">遷移先へ渡すパラメータ（Detail では事例 ID 文字列を想定）。</param>
    public void NavigateTo(string target, object? parameter = null)
    {
        Window next = target switch
        {
            "Standby" => new StandbyWindow(),
            "Home" => new HomeWindow(),
            "SearchResults" => new SearchResultsWindow(),
            "Detail" => new DetailWindow(parameter as string),
            _ => throw new ArgumentOutOfRangeException(
                nameof(target), target, "未知の遷移先です。"),
        };

        var previous = _currentWindow;
        _currentWindow = next;

        // 旧 → 新の順に閉じると待機状態が一瞬発生するため、先に新ウィンドウを表示する
        next.Show();
        previous?.Close();

        // 待機画面ではタイマー停止、それ以外は再起動
        if (target == "Standby")
        {
            StopIdleTimer();
        }
        else
        {
            ResetIdleTimer();
        }
    }

    /// <summary>無操作タイマーを初期化して再カウント開始。操作のたびに呼ぶ。</summary>
    public void ResetIdleTimer()
    {
        _idleTimer.Stop();
        _idleTimer.Start();
    }

    /// <summary>無操作タイマーを停止する（待機画面で使用）。</summary>
    public void StopIdleTimer()
    {
        _idleTimer.Stop();
    }
}
