using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Interop;
using Microsoft.Web.WebView2.Core;

namespace TeleMind.Desktop;

public partial class MainWindow : Window
{
    private const int DwmwaUseImmutableDarkMode = 20;
    private static readonly HashSet<string> AllowedMethods = new(StringComparer.OrdinalIgnoreCase)
    {
        "GET", "POST", "PUT", "DELETE",
    };

    private readonly CancellationTokenSource _shutdownCts = new();
    private readonly HttpClient _httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
    private readonly string _sessionToken = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));

    private TrayHost? _tray;
    private Process? _backendProcess;
    private int _backendPort;
    private string _workspaceRoot = string.Empty;
    private bool _allowExit;

    public MainWindow()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);

    private void ApplyTitleBarTheme(bool dark)
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        if (hwnd == IntPtr.Zero) return;
        int val = dark ? 1 : 0;
        _ = DwmSetWindowAttribute(hwnd, DwmwaUseImmutableDarkMode, ref val, sizeof(int));
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        ApplyTitleBarTheme(dark: true);
        _tray = new TrayHost(RestoreFromTray, ExitFromTray);
        StartWakeListener();
        try
        {
            _workspaceRoot = ResolveWorkspaceRoot();
            string uiDir = Path.Combine(_workspaceRoot, "frontend", "out");
            string pythonExe = Path.Combine(_workspaceRoot, "backend", ".venv", "Scripts", "python.exe");
            string backendDir = Path.Combine(_workspaceRoot, "backend");

            if (!Directory.Exists(uiDir) || !File.Exists(Path.Combine(uiDir, "index.html")))
            {
                throw new DirectoryNotFoundException($"Missing static UI bundle at: {uiDir}");
            }
            if (!File.Exists(pythonExe))
            {
                throw new FileNotFoundException($"Missing Python venv at: {pythonExe}");
            }

            _backendPort = FindFreeLoopbackPort();
            StartBackendProcess(pythonExe, backendDir);

            SplashStatus.Text = "Đang chờ TeleMind Backend sẵn sàng...";
            bool ready = await WaitForBackendAsync(_shutdownCts.Token);
            if (!ready)
            {
                throw new TimeoutException("Backend engine did not become healthy within 15 seconds.");
            }

            SplashStatus.Text = "Đang nạp giao diện cục bộ...";
            await InitializeWebViewAsync(uiDir);
        }
        catch (Exception ex)
        {
            System.Windows.MessageBox.Show(
                this,
                $"Không thể khởi chạy TeleMind Hub:\n\n{ex.Message}",
                "TeleMind Hub Error",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
            _allowExit = true;
            Close();
        }
    }

    private void StartWakeListener()
    {
        if (System.Windows.Application.Current is not App app || app.WakeSignal is null)
        {
            return;
        }
        WaitHandle signal = app.WakeSignal;
        _ = Task.Run(() =>
        {
            WaitHandle[] handles = [signal, _shutdownCts.Token.WaitHandle];
            while (!_shutdownCts.IsCancellationRequested)
            {
                int idx = WaitHandle.WaitAny(handles);
                if (idx != 0) break;
                Dispatcher.Invoke(RestoreFromTray);
            }
        });
    }

    private void RestoreFromTray()
    {
        Show();
        if (WindowState == WindowState.Minimized)
        {
            WindowState = WindowState.Normal;
        }
        Activate();
        Topmost = true;
        Topmost = false;
    }

    private void ExitFromTray()
    {
        _allowExit = true;
        Close();
    }

    private static string ResolveWorkspaceRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (int i = 0; i < 8 && dir is not null; i++)
        {
            string pyMain = Path.Combine(dir.FullName, "backend", "app", "main.py");
            string uiIdx = Path.Combine(dir.FullName, "frontend", "out", "index.html");
            if (File.Exists(pyMain) && File.Exists(uiIdx))
            {
                return dir.FullName;
            }
            dir = dir.Parent;
        }
        throw new DirectoryNotFoundException("Could not locate workspace containing backend/ and frontend/out/.");
    }

    private static int FindFreeLoopbackPort()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    private void StartBackendProcess(string pythonExe, string backendDir)
    {
        var psi = new ProcessStartInfo
        {
            FileName = pythonExe,
            Arguments = $"-m uvicorn app.main:create_app --factory --host 127.0.0.1 --port {_backendPort}",
            WorkingDirectory = backendDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        psi.Environment["WEB_ADMIN_TOKEN"] = _sessionToken;
        psi.Environment["API_HOST"] = "127.0.0.1";
        psi.Environment["API_PORT"] = _backendPort.ToString();
        psi.Environment["DATA_DIR"] = Path.Combine(backendDir, "data");
        psi.Environment["ALLOWED_ORIGINS"] = "https://telemind.local";

        var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (_, _) => { };
        proc.ErrorDataReceived += (_, _) => { };
        if (!proc.Start())
        {
            throw new InvalidOperationException("Failed to start Python backend process.");
        }
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
        _backendProcess = proc;
    }

    private async Task<bool> WaitForBackendAsync(CancellationToken ct)
    {
        string url = $"http://127.0.0.1:{_backendPort}/health";
        for (int i = 0; i < 75; i++)
        {
            ct.ThrowIfCancellationRequested();
            if (_backendProcess is { HasExited: true })
            {
                return false;
            }
            try
            {
                using var resp = await _httpClient.GetAsync(url, ct);
                if (resp.IsSuccessStatusCode)
                {
                    return true;
                }
            }
            catch (HttpRequestException)
            {
                // backend still booting
            }
            await Task.Delay(200, ct);
        }
        return false;
    }

    private async Task InitializeWebViewAsync(string uiDir)
    {
        string userDataDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "TeleMindHub",
            "WebView2");
        Directory.CreateDirectory(userDataDir);

        var env = await CoreWebView2Environment.CreateAsync(userDataFolder: userDataDir);
        await WebView.EnsureCoreWebView2Async(env);

        var core = WebView.CoreWebView2;
        core.Settings.AreDefaultContextMenusEnabled = false;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.AreBrowserAcceleratorKeysEnabled = false;
        core.Settings.IsZoomControlEnabled = false;

        core.SetVirtualHostNameToFolderMapping(
            "telemind.local",
            uiDir,
            CoreWebView2HostResourceAccessKind.DenyCors);

        core.NavigationStarting += (_, args) =>
        {
            if (!args.Uri.StartsWith("https://telemind.local/", StringComparison.OrdinalIgnoreCase))
            {
                args.Cancel = true;
            }
        };

        core.NewWindowRequested += (_, args) =>
        {
            args.Handled = true;
            if (Uri.TryCreate(args.Uri, UriKind.Absolute, out Uri? uri)
                && (uri.Scheme == Uri.UriSchemeHttps || uri.Scheme == Uri.UriSchemeHttp))
            {
                Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true });
            }
        };

        core.WebMessageReceived += OnWebMessageReceived;
        core.NavigationCompleted += (_, _) =>
        {
            SplashOverlay.Visibility = Visibility.Collapsed;
            WebView.Visibility = Visibility.Visible;
        };

        core.Navigate("https://telemind.local/index.html");
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        string id = string.Empty;
        try
        {
            using var doc = JsonDocument.Parse(e.WebMessageAsJson);
            var root = doc.RootElement;
            string type = root.TryGetProperty("type", out var tEl) ? tEl.GetString() ?? "" : "";

            if (type == "theme_mode")
            {
                string mode = root.TryGetProperty("mode", out var mEl) ? mEl.GetString() ?? "dark" : "dark";
                ApplyTitleBarTheme(mode != "light");
                return;
            }

            if (type != "api_request")
            {
                return;
            }

            id = root.TryGetProperty("id", out var idEl) ? idEl.GetString() ?? "" : "";
            string method = root.TryGetProperty("method", out var metEl) ? metEl.GetString() ?? "GET" : "GET";
            string relPath = root.TryGetProperty("path", out var pEl) ? pEl.GetString() ?? "" : "";
            string? body = root.TryGetProperty("body", out var bEl) && bEl.ValueKind == JsonValueKind.String
                ? bEl.GetString()
                : null;

            if (!AllowedMethods.Contains(method) || !IsSafeApiPath(relPath))
            {
                PostError(id, 403, "FORBIDDEN_IPC", "Disallowed desktop IPC request.");
                return;
            }

            string targetUrl = $"http://127.0.0.1:{_backendPort}/{relPath.TrimStart('/')}";
            using var req = new HttpRequestMessage(new HttpMethod(method.ToUpperInvariant()), targetUrl);
            req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _sessionToken);
            if (body is not null && method is "POST" or "PUT")
            {
                req.Content = new StringContent(body, Encoding.UTF8, "application/json");
            }

            using var resp = await _httpClient.SendAsync(req, _shutdownCts.Token);
            string respText = await resp.Content.ReadAsStringAsync(_shutdownCts.Token);
            object? parsedError = null;
            if (!resp.IsSuccessStatusCode)
            {
                try
                {
                    using var errDoc = JsonDocument.Parse(respText);
                    if (errDoc.RootElement.TryGetProperty("error", out var errObj))
                    {
                        parsedError = JsonSerializer.Deserialize<object>(errObj.GetRawText());
                    }
                }
                catch
                {
                    // non-JSON upstream error
                }
            }

            string replyJson = JsonSerializer.Serialize(new
            {
                type = "api_response",
                id,
                ok = resp.IsSuccessStatusCode,
                status = (int)resp.StatusCode,
                text = respText,
                error = parsedError,
            });
            WebView.CoreWebView2.PostWebMessageAsJson(replyJson);
        }
        catch (Exception ex)
        {
            if (!string.IsNullOrEmpty(id))
            {
                PostError(id, 500, "DESKTOP_IPC_ERROR", ex.Message);
            }
        }
    }

    private void PostError(string id, int status, string code, string message)
    {
        string json = JsonSerializer.Serialize(new
        {
            type = "api_response",
            id,
            ok = false,
            status,
            text = string.Empty,
            error = new { code, message },
        });
        WebView.CoreWebView2?.PostWebMessageAsJson(json);
    }

    private static bool IsSafeApiPath(string rawPath)
    {
        if (string.IsNullOrWhiteSpace(rawPath) || rawPath.Contains("..") || rawPath.Contains('\\'))
        {
            return false;
        }
        string clean = rawPath.TrimStart('/');
        return clean == "health" || clean == "ready" || clean.StartsWith("api/v1/", StringComparison.Ordinal);
    }

    protected override void OnClosing(CancelEventArgs e)
    {
        if (!_allowExit && _tray is not null)
        {
            e.Cancel = true;
            Hide();
            _tray.NotifyMinimizedToTray();
            return;
        }
        base.OnClosing(e);
    }

    protected override void OnClosed(EventArgs e)
    {
        _shutdownCts.Cancel();
        _tray?.Dispose();
        try
        {
            if (_backendProcess is { HasExited: false })
            {
                _backendProcess.Kill(entireProcessTree: true);
                _backendProcess.WaitForExit(2000);
            }
        }
        catch
        {
            // ignore shutdown cleanup race
        }
        finally
        {
            _backendProcess?.Dispose();
            _httpClient.Dispose();
            _shutdownCts.Dispose();
        }
        base.OnClosed(e);
    }
}
