using System.Threading;
using System.Windows;

namespace TeleMind.Desktop;

public partial class App : System.Windows.Application
{
    private const string MutexName = @"Local\TeleMindHubSingleInstance_V1";
    private const string WakeEventName = @"Local\TeleMindHubWakeEvent_V1";

    private Mutex? _instanceMutex;
    private EventWaitHandle? _wakeEvent;

    protected override void OnStartup(StartupEventArgs e)
    {
        _instanceMutex = new Mutex(initiallyOwned: true, MutexName, out bool isPrimary);
        if (!isPrimary)
        {
            try
            {
                using var existingWake = EventWaitHandle.OpenExisting(WakeEventName);
                existingWake.Set();
            }
            catch
            {
                // Primary process already closing
            }
            _instanceMutex.Dispose();
            _instanceMutex = null;
            Shutdown(0);
            return;
        }

        _wakeEvent = new EventWaitHandle(false, EventResetMode.AutoReset, WakeEventName);
        base.OnStartup(e);
    }

    internal WaitHandle? WakeSignal => _wakeEvent;

    protected override void OnExit(ExitEventArgs e)
    {
        _wakeEvent?.Dispose();
        if (_instanceMutex is not null)
        {
            try
            {
                _instanceMutex.ReleaseMutex();
            }
            catch
            {
                // already released
            }
            _instanceMutex.Dispose();
        }
        base.OnExit(e);
    }
}
