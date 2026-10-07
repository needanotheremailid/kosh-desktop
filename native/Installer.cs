using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class Installer
{
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 8 * 1024 * 1024, RecursionLimit = 32 };
    static bool Quiet, Shortcuts = true, Launch = false;
    static string Target = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Kosh");
    static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);

    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--quiet") Quiet = true;
                else if (args[i] == "--no-shortcuts") Shortcuts = false;
                else if (args[i] == "--no-launch") Launch = false;
                else if (args[i] == "--launch") Launch = true;
                else if (args[i] == "--install-dir" && i + 1 < args.Length) Target = args[++i];
                else throw new Exception("Unsupported installer argument.");
            }
            if (Quiet) { Install(Target, Shortcuts, Launch, delegate(string status) { }); return 0; }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupForm());
            return 0;
        }
        catch (Exception ex)
        {
            if (!Quiet) MessageBox.Show(ex.Message, "Kosh setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    sealed class SetupForm : Form
    {
        readonly TextBox Folder = new TextBox();
        readonly CheckBox Links = new CheckBox(), Start = new CheckBox();
        readonly Button Go = new Button();
        readonly Label Status = new Label();
        readonly ProgressBar Progress = new ProgressBar();
        bool Busy, Completed;
        public SetupForm()
        {
            Text = "Install Kosh"; ClientSize = new Size(580, 392); FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(247, 245, 240); Font = new Font("Segoe UI", 10);
            var title = new Label { Text = "Your research desk, on this computer.", Location = new Point(24, 22), Size = new Size(530, 40), Font = new Font("Segoe UI", 17, FontStyle.Bold) };
            var detail = new Label { Text = "Installs Kosh and its Python/document runtime. Microsoft Edge is required.\nNew installations only; existing folders and research data are preserved.", Location = new Point(24, 74), Size = new Size(530, 52) };
            var label = new Label { Text = "Install folder", Location = new Point(24, 139), AutoSize = true };
            Folder.SetBounds(24, 167, 434, 28); Folder.Text = Target;
            var browse = new Button { Text = "Browse…", Location = new Point(468, 164), Size = new Size(88, 31) };
            browse.Click += delegate { using (var dialog = new FolderBrowserDialog()) { dialog.Description = "Choose the parent folder. A new Kosh folder will be created there."; if (dialog.ShowDialog(this) == DialogResult.OK) Folder.Text = Path.Combine(dialog.SelectedPath, "Kosh"); } };
            Links.Text = "Create desktop and Start menu shortcuts"; Links.SetBounds(24, 212, 510, 26); Links.Checked = Shortcuts;
            bool existingKosh = File.Exists(Path.Combine(Target, "bin", "ResearchDesktop.exe"));
            Start.Text = "Open Kosh after installation (leave off when upgrading)"; Start.SetBounds(24, 244, 532, 26); Start.Checked = Launch && !existingKosh;
            Progress.SetBounds(24, 283, 532, 10); Progress.Visible = false;
            Status.SetBounds(24, 307, 410, 64); Status.Text = existingKosh ? "Existing Kosh detected. Choose a new folder, then run the documented upgrade before its first launch." : "No account, administrator rights or downloads needed.";
            Go.Text = "Install"; Go.SetBounds(458, 322, 98, 38);
            Go.Click += delegate
            {
                if (Completed) { Close(); return; }
                if (Busy) return;
                string target = Folder.Text; bool links = Links.Checked, start = Start.Checked;
                Busy = true; Go.Enabled = false; Folder.Enabled = false; Links.Enabled = false; Start.Enabled = false; browse.Enabled = false;
                Progress.Visible = true; Progress.Style = ProgressBarStyle.Marquee;
                var worker = new Thread(delegate()
                {
                    try
                    {
                        var warnings = Install(target, links, start, delegate(string message) { BeginInvoke((Action)delegate { Status.Text = message; }); });
                        BeginInvoke((Action)delegate { Busy = false; Completed = true; Progress.Style = ProgressBarStyle.Continuous; Progress.Value = 100; Status.Text = warnings.Count == 0 ? "Installed. Your research library starts empty." : "Installed with warnings. See INSTALL_RESULT.json in the install folder; use bin/ResearchDesktop.exe to open Kosh."; Go.Text = "Close"; Go.Enabled = true; });
                    }
                    catch (Exception ex)
                    {
                        BeginInvoke((Action)delegate { Busy = false; Progress.Visible = false; Status.Text = ex.Message; Go.Enabled = true; Folder.Enabled = true; Links.Enabled = true; Start.Enabled = true; browse.Enabled = true; });
                    }
                });
                worker.IsBackground = true; worker.SetApartmentState(ApartmentState.STA); worker.Start();
            };
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (Busy) e.Cancel = true; };
            Controls.AddRange(new Control[] { title, detail, label, Folder, browse, Links, Start, Progress, Status, Go });
        }
    }

    static string SafePath(string root, string name)
    {
        if (String.IsNullOrEmpty(name) || name.IndexOf('\\') >= 0 || name.StartsWith("/") || name.EndsWith("/")) throw new Exception("Unsafe package path.");
        foreach (string part in name.Split('/'))
        {
            if (part.Length == 0 || part == "." || part == ".." || part.EndsWith(".") || part.EndsWith(" ") || part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0) throw new Exception("Unsafe package filename.");
            string stem = part.Split('.')[0].ToUpperInvariant();
            if (stem == "CON" || stem == "PRN" || stem == "AUX" || stem == "NUL" || (stem.Length == 4 && (stem.StartsWith("COM") || stem.StartsWith("LPT")) && stem[3] >= '1' && stem[3] <= '9')) throw new Exception("Reserved package filename.");
        }
        string target = Path.GetFullPath(Path.Combine(root, name.Replace('/', Path.DirectorySeparatorChar)));
        if (!target.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new Exception("Package path escaped the install folder.");
        return target;
    }

    static string Hex(byte[] value) { return BitConverter.ToString(value).Replace("-", "").ToLowerInvariant(); }
    static string HashFile(string path) { using (var hash = SHA256.Create()) using (var stream = File.OpenRead(path)) return Hex(hash.ComputeHash(stream)); }

    static List<string> Install(string requested, bool shortcuts, bool launch, Action<string> status)
    {
        if (!Path.IsPathRooted(requested)) throw new Exception("Choose an absolute install folder.");
        string target = Path.GetFullPath(requested).TrimEnd(Path.DirectorySeparatorChar);
        if (target.Length <= Path.GetPathRoot(target).Length || Directory.Exists(target) || File.Exists(target)) throw new Exception("Install folder already exists or is a drive root. Choose a new folder; existing files were preserved.");
        if (FindEdge() == null) throw new Exception("Microsoft Edge is required. Install or enable Edge separately, then retry.");
        string parent = Path.GetDirectoryName(target);
        Directory.CreateDirectory(parent);
        string stage = target + ".installing-" + Guid.NewGuid().ToString("N");
        Directory.CreateDirectory(stage);
        var warnings = new List<string>();
        try
        {
            status("Checking the bundled package…");
            using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("Kosh.Payload.zip"))
            {
                if (resource == null) throw new Exception("The bundled payload is missing.");
                using (var archive = new ZipArchive(resource, ZipArchiveMode.Read))
                {
                    var manifestEntry = archive.GetEntry("package-manifest.json");
                    if (manifestEntry == null || manifestEntry.Length > 8 * 1024 * 1024) throw new Exception("The package manifest is missing or oversized.");
                    string manifestText;
                    using (var reader = new StreamReader(manifestEntry.Open(), Utf8)) manifestText = reader.ReadToEnd();
                    var manifest = Json.Deserialize<Dictionary<string, object>>(manifestText);
                    if (Convert.ToInt32(manifest["format"]) != 1 || Convert.ToString(manifest["app"]) != "pg-research-desktop") throw new Exception("Unexpected package identity.");
                    string build = Convert.ToString(manifest["build"]);
                    if (build.Length != 64 || !System.Text.RegularExpressions.Regex.IsMatch(build, "^[a-f0-9]{64}$")) throw new Exception("Invalid source identity.");
                    var expected = new Dictionary<string, Dictionary<string, object>>(StringComparer.OrdinalIgnoreCase);
                    foreach (object item in (System.Collections.IEnumerable)manifest["files"])
                    {
                        var row = (Dictionary<string, object>)item;
                        string name = Convert.ToString(row["path"]); SafePath(stage, name);
                        if (expected.ContainsKey(name)) throw new Exception("Duplicate package path.");
                        long size = Convert.ToInt64(row["size"]);
                        if (size < 0 || size > 256L * 1024 * 1024 || !System.Text.RegularExpressions.Regex.IsMatch(Convert.ToString(row["sha256"]), "^[a-f0-9]{64}$")) throw new Exception("Invalid package file record.");
                        expected.Add(name, row);
                    }
                    if (expected.Count > 20000 || archive.Entries.Count != expected.Count + 1) throw new Exception("Package entry count does not match its manifest.");
                    var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase); long total = 0; int count = 0;
                    foreach (var entry in archive.Entries)
                    {
                        if (entry.FullName == "package-manifest.json") { if (!seen.Add(entry.FullName)) throw new Exception("Duplicate package manifest."); continue; }
                        string path = SafePath(stage, entry.FullName); Dictionary<string, object> row;
                        if (!seen.Add(entry.FullName) || !expected.TryGetValue(entry.FullName, out row) || entry.Length != Convert.ToInt64(row["size"])) throw new Exception("Package entries do not match their records.");
                        total += entry.Length; if (total > 1024L * 1024 * 1024) throw new Exception("Package exceeds the install size limit.");
                        Directory.CreateDirectory(Path.GetDirectoryName(path));
                        using (var input = entry.Open()) using (var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                        {
                            byte[] buffer = new byte[65536]; int read; long copied = 0;
                            while ((read = input.Read(buffer, 0, buffer.Length)) > 0) { copied += read; if (copied > entry.Length) throw new Exception("Package file exceeded its declared size."); output.Write(buffer, 0, read); }
                            if (copied != entry.Length) throw new Exception("Package file was truncated.");
                        }
                        if (HashFile(path) != Convert.ToString(row["sha256"])) throw new Exception("A bundled file failed SHA-256 validation.");
                        count++; if (count % 100 == 0) status("Installing bundled files (" + count + " / " + expected.Count + ")…");
                    }
                    if (seen.Count != expected.Count + 1) throw new Exception("Package files were missing.");
                    foreach (string name in new[] { "runtime/python.exe", "runtime/LICENSE.txt", "bin/ResearchDesktop.exe", "backend.py", "server.py", "agent.py", "literature.py", "folder_edits.py", "native/Launcher.cs", "ui/index.html", "ui/app.js", "ui/app.css", "LICENSE", "THIRD_PARTY.md", "CREDITS.md", "RUNTIME_COMPONENTS.json", "legal/source-receipts.json", "legal/PyMuPDF-COPYING.txt" }) if (!expected.ContainsKey(name)) throw new Exception("A required component or legal notice is missing.");
                    CheckLegal(stage, expected);
                    status("Checking the copied document runtime…");
                    CheckRuntime(stage);
                    File.WriteAllText(Path.Combine(stage, "runtime.json"), Json.Serialize(new Dictionary<string, object> { { "python", Path.Combine(target, "runtime", "python.exe") }, { "build", build } }), Utf8);
                    File.WriteAllText(Path.Combine(stage, "package-manifest.json"), manifestText, Utf8);
                    File.WriteAllText(Path.Combine(stage, "INSTALL_RECEIPT.json"), Json.Serialize(new Dictionary<string, object> { { "app", "Kosh" }, { "installed_utc", DateTime.UtcNow.ToString("o") }, { "build", build }, { "files_verified", expected.Count }, { "payload_bytes", total }, { "runtime_checked", true }, { "installer", "local per-user new installation" } }), Utf8);
                }
            }
            status("Publishing the verified installation…");
            PublishInstallation(stage, target);
            if (shortcuts)
            {
                try { CreateShortcuts(target, warnings); }
                catch (Exception) { warnings.Add("Shortcut support was unavailable. Existing shortcuts were preserved; use bin/ResearchDesktop.exe directly."); }
            }
            if (launch)
            {
                try { Process.Start(new ProcessStartInfo(Path.Combine(target, "bin", "ResearchDesktop.exe")) { WorkingDirectory = target, UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden }); }
                catch (Exception) { warnings.Add("Kosh could not be opened automatically. Use bin/ResearchDesktop.exe directly."); }
            }
            File.WriteAllText(Path.Combine(target, "INSTALL_RESULT.json"), Json.Serialize(new Dictionary<string, object> { { "installed", true }, { "status", warnings.Count == 0 ? "installed" : "installed_with_warnings" }, { "warnings", warnings } }), Utf8);
            return warnings;
        }
        catch (Exception ex)
        {
            if (Directory.Exists(stage)) File.WriteAllText(Path.Combine(stage, "INSTALL_ERROR.txt"), ex.Message, Utf8);
            throw new Exception(ex.Message + (Directory.Exists(stage) ? " Incomplete installation retained at: " + stage : " The installed app remains at: " + target));
        }
    }

    static void PublishInstallation(string stage, string target)
    {
        // A just-exited runtime probe or scanner can briefly hold the verified
        // directory. Retry only this exact rename; never replace a destination.
        for (int attempt = 0; ; attempt++)
        {
            try { Directory.Move(stage, target); return; }
            catch (IOException) { if (attempt >= 9 || Directory.Exists(target) || File.Exists(target)) throw; }
            catch (UnauthorizedAccessException) { if (attempt >= 9 || Directory.Exists(target) || File.Exists(target)) throw; }
            System.Threading.Thread.Sleep(500);
        }
    }

    static void CheckLegal(string stage, Dictionary<string, Dictionary<string, object>> expected)
    {
        var components = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.Combine(stage, "RUNTIME_COMPONENTS.json")));
        var versions = new Dictionary<string, string> { { "python", Convert.ToString(components["python"]) }, { "mupdf", Convert.ToString(components["mupdf"]) } };
        foreach (object item in (System.Collections.IEnumerable)components["packages"])
        {
            var component = (Dictionary<string, object>)item;
            string package = Convert.ToString(component["package"]).ToLowerInvariant().Replace('_', '-');
            versions.Add(package, Convert.ToString(component["version"]));
            foreach (object file in (System.Collections.IEnumerable)component["license_files"])
            {
                string path = "runtime/Lib/site-packages/" + Convert.ToString(file).Replace('\\', '/');
                SafePath(stage, path); if (!expected.ContainsKey(path)) throw new Exception("A copied component licence file is missing.");
            }
        }
        var templates = new Dictionary<string, string> { { "pymupdf", "pymupdf-{0}.tar.gz" }, { "python-docx", "python_docx-{0}.tar.gz" }, { "lxml", "lxml-{0}.tar.gz" }, { "typing-extensions", "typing_extensions-{0}.tar.gz" }, { "python", "Python-{0}.tar.xz" }, { "mupdf", "mupdf-{0}-source.tar.gz" } };
        var receipts = Json.Deserialize<List<Dictionary<string, object>>>(File.ReadAllText(Path.Combine(stage, "legal", "source-receipts.json")));
        if (receipts.Count != templates.Count) throw new Exception("Source receipts do not cover all runtime components.");
        var seen = new HashSet<string>();
        foreach (var row in receipts)
        {
            string package = Convert.ToString(row["package"]).ToLowerInvariant().Replace('_', '-');
            if (!templates.ContainsKey(package) || !versions.ContainsKey(package) || !seen.Add(package) || Convert.ToString(row["version"]) != versions[package]) throw new Exception("Source receipt version does not match the bundled runtime.");
            string file = String.Format(templates[package], versions[package]);
            string path = "legal/" + file; SafePath(stage, path);
            if (Convert.ToString(row["file"]) != file || !expected.ContainsKey(path) || Convert.ToInt64(row["bytes"]) != Convert.ToInt64(expected[path]["size"]) || Convert.ToString(row["sha256"]) != Convert.ToString(expected[path]["sha256"])) throw new Exception("Legal source archive size/hash does not match its receipt.");
        }
        string copying = File.ReadAllText(Path.Combine(stage, "legal", "PyMuPDF-COPYING.txt"));
        if (copying.Length < 30000 || !copying.Contains("GNU AFFERO GENERAL PUBLIC LICENSE")) throw new Exception("The full PyMuPDF AGPL licence text is missing.");
    }

    static void CheckRuntime(string stage)
    {
        var info = new ProcessStartInfo(Path.Combine(stage, "runtime", "python.exe"), "-I -c \"import sys,sqlite3,pymupdf,docx,lxml,typing_extensions; assert sys.version_info[:2]==(3,12); assert sqlite3.connect(':memory:').execute('select 1').fetchone()[0]==1\"");
        info.UseShellExecute = false; info.CreateNoWindow = true; info.WindowStyle = ProcessWindowStyle.Hidden;
        info.RedirectStandardError = true; info.RedirectStandardOutput = true; info.WorkingDirectory = stage;
        using (var process = Process.Start(info))
        {
            if (!process.WaitForExit(60000)) { try { process.Kill(); } catch { } throw new Exception("Copied runtime check timed out. No app data was created."); }
            if (process.ExitCode != 0) throw new Exception("Copied Python/document runtime could not load. The incomplete installation was preserved.");
        }
    }

    static string FindEdge()
    {
        foreach (string basePath in new[] { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) })
        {
            string path = Path.Combine(basePath, "Microsoft", "Edge", "Application", "msedge.exe"); if (File.Exists(path)) return path;
        }
        return null;
    }

    static void SetCom(object value, string property, object content) { value.GetType().InvokeMember(property, BindingFlags.SetProperty, null, value, new object[] { content }); }
    static void CreateShortcuts(string target, List<string> warnings)
    {
        string[] paths = { Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Kosh.lnk"), Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Kosh", "Kosh.lnk") };
        Type type = Type.GetTypeFromProgID("WScript.Shell"); if (type == null) { warnings.Add("Windows shortcut support is unavailable. Use bin/ResearchDesktop.exe directly."); return; }
        object shell = Activator.CreateInstance(type);
        try
        {
            foreach (string path in paths)
            {
                if (File.Exists(path)) { warnings.Add("Existing shortcut preserved: " + path); continue; }
                try
                {
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                string temporary = Path.Combine(target, ".shortcut-" + Guid.NewGuid().ToString("N") + ".lnk");
                object link = type.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { temporary });
                try { SetCom(link, "TargetPath", Path.Combine(target, "bin", "ResearchDesktop.exe")); SetCom(link, "WorkingDirectory", target); SetCom(link, "IconLocation", Path.Combine(target, "assets", "App.ico") + ",0"); SetCom(link, "Description", "Kosh - local research desk"); link.GetType().InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null); }
                finally { System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link); }
                // File.Move refuses a destination created after the earlier
                // preflight. Never let COM Save replace an existing shortcut.
                File.Move(temporary, path);
                }
                catch (IOException) { warnings.Add("Shortcut was not replaced or created: " + path); }
                catch (Exception) { warnings.Add("Shortcut creation was unavailable: " + path + ". Use bin/ResearchDesktop.exe directly."); }
            }
        }
        finally { System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell); }
    }
}
