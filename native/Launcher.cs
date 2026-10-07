using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class Launcher
{
    sealed class StaleBuildException : Exception { public StaleBuildException(string message) : base(message) {} }
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    static string Root;
    [STAThread]
    public static void Main()
    {
        Application.EnableVisualStyles();
        Root = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, ".."));
        try { Open(); }
        catch (Exception ex) { MessageBox.Show(ex.Message + "\n\nYour workspace files remain in the app's data folder.", "Kosh — could not open", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }

    static void Open()
    {
        string data = Path.Combine(Root, "data");
        string ready = Path.Combine(data, "server.json");
        Directory.CreateDirectory(data);
        using (var guard = new Mutex(false, "Local\\PGResearchDesktopLauncher"))
        {
            bool acquired = false;
            try { acquired = guard.WaitOne(25000); } catch (AbandonedMutexException) { acquired = true; }
            if (!acquired) throw new Exception("Another launch is still starting. Try again shortly.");
            try
            {
                int port = ReadPort(ready);
                if (port == 0)
                {
                    string python = Path.Combine(Root, "runtime.json");
                    if (!File.Exists(python)) throw new Exception("Run build.ps1 once to configure the installed Python runtime.");
                    var cfg = Json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(File.ReadAllText(python));
                    string exe = Convert.ToString(cfg["python"]);
                    if (!File.Exists(exe)) throw new Exception("Configured Python runtime is missing. Run build.ps1 again.");
                    var psi = new ProcessStartInfo(exe, "-E -s \"" + Path.Combine(Root, "server.py") + "\" --data-dir \"" + data + "\" --ready-file \"" + ready + "\"");
                    psi.WorkingDirectory = Root;
                    psi.UseShellExecute = false;
                    psi.CreateNoWindow = true;
                    psi.WindowStyle = ProcessWindowStyle.Hidden;
                    var child = Process.Start(psi);
                    for (int i = 0; i < 200 && port == 0; i++)
                    {
                        Thread.Sleep(100);
                        if (child.HasExited) throw new Exception("The local service failed to start. Run python server.py to inspect the error.");
                        port = ReadPort(ready);
                    }
                    if (port == 0) throw new Exception("The local service did not become ready within 20 seconds.");
                }
                string edge = FindEdge();
                if (edge == null) throw new Exception("Microsoft Edge is required for the desktop window.");
                string profile = Path.Combine(data, "edge-profile");
                var ui = new ProcessStartInfo(edge, "--app=http://127.0.0.1:" + port + "/ --user-data-dir=\"" + profile + "\" --no-first-run --disable-background-networking --disable-component-update --disable-sync");
                ui.UseShellExecute = false;
                ui.CreateNoWindow = true;
                Process.Start(ui);
            }
            finally { guard.ReleaseMutex(); }
        }
    }

    static int ReadPort(string ready)
    {
        try
        {
            if (!File.Exists(ready)) return 0;
            var obj = Json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(File.ReadAllText(ready));
            if (Convert.ToString(obj["app"]) != "pg-research-desktop") return 0;
            int port = Convert.ToInt32(obj["port"]);
            if (port < 1024 || port > 65535) return 0;
            var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/health");
            request.Proxy = null;
            request.Timeout = 1000;
            using (var response = request.GetResponse())
            using (var reader = new StreamReader(response.GetResponseStream()))
            {
                var health = Json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(reader.ReadToEnd());
                if (Convert.ToString(health["app"]) != "pg-research-desktop") return 0;
                if (Convert.ToString(health["build"]) != Convert.ToString(obj["build"])) return 0;
                string runtime = Path.Combine(Root, "runtime.json");
                if (File.Exists(runtime))
                {
                    var config = Json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(File.ReadAllText(runtime));
                    if (config.ContainsKey("build") && Convert.ToString(config["build"]) != Convert.ToString(health["build"]))
                        throw new StaleBuildException("An earlier app build is still running. Use Quit app in that window, then reopen Research Desktop.");
                }
            }
            return port;
        }
        catch (StaleBuildException) { throw; }
        catch { return 0; }
    }

    static string FindEdge()
    {
        foreach (string basePath in new[] { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) })
        {
            string path = Path.Combine(basePath, "Microsoft", "Edge", "Application", "msedge.exe");
            if (File.Exists(path)) return path;
        }
        return null;
    }
}
