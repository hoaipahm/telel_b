using System.Drawing;
using System.Windows.Forms;

namespace TeleMind.Desktop;

internal sealed class TrayHost : IDisposable
{
    private readonly NotifyIcon _notifyIcon;
    private readonly ContextMenuStrip _menu;
    private bool _balloonShown;

    public TrayHost(Action onOpen, Action onExit)
    {
        _menu = new ContextMenuStrip();
        _menu.Items.Add("Mở TeleMind Hub", null, (_, _) => onOpen());
        _menu.Items.Add(new ToolStripSeparator());
        _menu.Items.Add("Thoát hẳn (Dừng Bot)", null, (_, _) => onExit());

        Icon? appIcon = null;
        string? exePath = Environment.ProcessPath;
        if (!string.IsNullOrWhiteSpace(exePath))
        {
            appIcon = Icon.ExtractAssociatedIcon(exePath);
        }

        _notifyIcon = new NotifyIcon
        {
            Icon = appIcon ?? SystemIcons.Application,
            Text = "TeleMind Hub — Telegram Bot Cục Bộ",
            ContextMenuStrip = _menu,
            Visible = true,
        };
        _notifyIcon.DoubleClick += (_, _) => onOpen();
    }

    public void NotifyMinimizedToTray()
    {
        if (_balloonShown) return;
        _balloonShown = true;
        _notifyIcon.ShowBalloonTip(
            2500,
            "TeleMind Hub đang chạy nền",
            "Bot Telegram vẫn hoạt động. Nháy đúp biểu tượng khay hệ thống để mở lại.",
            ToolTipIcon.Info);
    }

    public void Dispose()
    {
        _notifyIcon.Visible = false;
        _notifyIcon.Dispose();
        _menu.Dispose();
    }
}
