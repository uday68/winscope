using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace WinScope.Collector
{
    // Native Win32 API structures
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    public class MEMORYSTATUSEX
    {
        public uint dwLength;
        public uint dwMemoryLoad;
        public ulong ullTotalPhys;
        public ulong ullAvailPhys;
        public ulong ullTotalPageFile;
        public ulong ullAvailPageFile;
        public ulong ullTotalVirtual;
        public ulong ullAvailVirtual;
        public ulong ullAvailExtendedVirtual;

        public MEMORYSTATUSEX()
        {
            dwLength = (uint)Marshal.SizeOf(typeof(MEMORYSTATUSEX));
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct FILETIME
    {
        public uint dwLowDateTime;
        public uint dwHighDateTime;

        public ulong ToUInt64()
        {
            return ((ulong)dwHighDateTime << 32) | (ulong)dwLowDateTime;
        }
    }

    public static class NativeMethods
    {
        [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GlobalMemoryStatusEx([In, Out] MEMORYSTATUSEX lpBuffer);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetSystemTimes(out FILETIME lpIdleTime, out FILETIME lpKernelTime, out FILETIME lpUserTime);

        [DllImport("kernel32.dll")]
        public static extern ulong GetTickCount64();
    }

    public class Program
    {
        private static volatile bool _keepRunning = true;

        public static int Main(string[] args)
        {
            int intervalMs = 1000;
            int durationSec = 10;
            string outputPath = null;
            int targetPid = Process.GetCurrentProcess().Id;

            // Simple command line parsing
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i].Equals("--interval", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    int.TryParse(args[++i], out intervalMs);
                }
                else if (args[i].Equals("--duration", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    int.TryParse(args[++i], out durationSec);
                }
                else if (args[i].Equals("--output", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    outputPath = args[++i];
                }
                else if (args[i].Equals("--pid", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    int.TryParse(args[++i], out targetPid);
                }
                else if (args[i].Equals("--help", StringComparison.OrdinalIgnoreCase) || args[i].Equals("-h", StringComparison.OrdinalIgnoreCase))
                {
                    PrintHelp();
                    return 0;
                }
            }

            if (intervalMs < 100) intervalMs = 100;

            StreamWriter fileWriter = null;
            if (!string.IsNullOrEmpty(outputPath))
            {
                string dir = Path.GetDirectoryName(outputPath);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                {
                    Directory.CreateDirectory(dir);
                }
                fileWriter = new StreamWriter(new FileStream(outputPath, FileMode.Create, FileAccess.Write, FileShare.Read), new UTF8Encoding(false));
            }

            Action<string> emitLine = line =>
            {
                Console.WriteLine(line);
                if (fileWriter != null)
                {
                    fileWriter.WriteLine(line);
                    fileWriter.Flush();
                }
            };

            Console.CancelKeyPress += (sender, e) =>
            {
                e.Cancel = true;
                _keepRunning = false;
                Console.Error.WriteLine("[WinScope] Cancellation requested. Shutting down cleanly...");
            };

            string sessionId = Guid.NewGuid().ToString();
            DateTime startTime = DateTime.UtcNow;

            // Emit session header
            string headerJson = string.Format(
                CultureInfo.InvariantCulture,
                "{{\"type\":\"session_header\",\"session_id\":\"{0}\",\"start_time\":\"{1}\",\"host_name\":\"{2}\",\"os_version\":\"{3}\",\"sampling_interval_ms\":{4},\"collector_type\":\"WinScope-CSharp-Native\",\"collector_version\":\"1.0.0\",\"schema_version\":\"1.0.0\"}}",
                sessionId,
                startTime.ToString("yyyy-MM-ddTHH:mm:ss.ffffffZ", CultureInfo.InvariantCulture),
                Environment.MachineName,
                Environment.OSVersion.VersionString.Replace("\\", "\\\\").Replace("\"", "\\\""),
                intervalMs
            );
            emitLine(headerJson);

            // CPU measurement state
            FILETIME prevIdle, prevKernel, prevUser;
            NativeMethods.GetSystemTimes(out prevIdle, out prevKernel, out prevUser);

            // Process CPU measurement state
            Process monitoredProcess = null;
            TimeSpan prevProcessCpu = TimeSpan.Zero;
            DateTime prevProcessTime = DateTime.UtcNow;
            try
            {
                monitoredProcess = Process.GetProcessById(targetPid);
                prevProcessCpu = monitoredProcess.TotalProcessorTime;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(string.Format("[WinScope] Notice: Cannot monitor PID {0}: {1}", targetPid, ex.Message));
                monitoredProcess = null;
            }

            DateTime runEnd = durationSec > 0 ? startTime.AddSeconds(durationSec) : DateTime.MaxValue;
            long sampleIndex = 0;

            // Give a brief window to establish the first delta
            Thread.Sleep(100);

            while (_keepRunning && DateTime.UtcNow < runEnd)
            {
                DateTime nowUtc = DateTime.UtcNow;
                string nowIso = nowUtc.ToString("yyyy-MM-ddTHH:mm:ss.ffffffZ", CultureInfo.InvariantCulture);

                // 1. CPU Utilization (Total system)
                FILETIME curIdle, curKernel, curUser;
                if (NativeMethods.GetSystemTimes(out curIdle, out curKernel, out curUser))
                {
                    ulong deltaIdle = curIdle.ToUInt64() - prevIdle.ToUInt64();
                    ulong deltaKernel = curKernel.ToUInt64() - prevKernel.ToUInt64();
                    ulong deltaUser = curUser.ToUInt64() - prevUser.ToUInt64();

                    ulong totalSys = deltaKernel + deltaUser;
                    if (totalSys > 0)
                    {
                        double cpuPct = (1.0 - ((double)deltaIdle / (double)totalSys)) * 100.0;
                        if (cpuPct < 0.0) cpuPct = 0.0;
                        if (cpuPct > 100.0) cpuPct = 100.0;

                        emitLine(FormatMetric(nowIso, "cpu.utilization.pct", cpuPct, "percent", "Win32_GetSystemTimes", null, "ok", null));
                    }
                    else
                    {
                        emitLine(FormatMetric(nowIso, "cpu.utilization.pct", null, "percent", "Win32_GetSystemTimes", null, "unavailable", "Zero elapsed kernel+user time"));
                    }

                    prevIdle = curIdle;
                    prevKernel = curKernel;
                    prevUser = curUser;
                }
                else
                {
                    int err = Marshal.GetLastWin32Error();
                    emitLine(FormatMetric(nowIso, "cpu.utilization.pct", null, "percent", "Win32_GetSystemTimes", null, "error", "Win32 error: " + err));
                }

                // 2. Physical Memory Utilization
                MEMORYSTATUSEX memStatus = new MEMORYSTATUSEX();
                if (NativeMethods.GlobalMemoryStatusEx(memStatus))
                {
                    emitLine(FormatMetric(nowIso, "memory.physical.utilization.pct", (double)memStatus.dwMemoryLoad, "percent", "GlobalMemoryStatusEx", null, "ok", null));
                    emitLine(FormatMetric(nowIso, "memory.physical.available.bytes", (double)memStatus.ullAvailPhys, "bytes", "GlobalMemoryStatusEx", null, "ok", null));
                    emitLine(FormatMetric(nowIso, "memory.physical.total.bytes", (double)memStatus.ullTotalPhys, "bytes", "GlobalMemoryStatusEx", null, "ok", null));
                }
                else
                {
                    int err = Marshal.GetLastWin32Error();
                    emitLine(FormatMetric(nowIso, "memory.physical.utilization.pct", null, "percent", "GlobalMemoryStatusEx", null, "error", "Win32 error: " + err));
                    emitLine(FormatMetric(nowIso, "memory.physical.available.bytes", null, "bytes", "GlobalMemoryStatusEx", null, "error", "Win32 error: " + err));
                }

                // 3. Process CPU and Working Set
                if (monitoredProcess != null)
                {
                    try
                    {
                        monitoredProcess.Refresh();
                        if (monitoredProcess.HasExited)
                        {
                            emitLine(FormatMetric(nowIso, "process.cpu.utilization.pct", null, "percent", "ProcessTimes", "PID:" + targetPid, "unavailable", "Process terminated"));
                            emitLine(FormatMetric(nowIso, "process.memory.working_set.bytes", null, "bytes", "ProcessMemory", "PID:" + targetPid, "unavailable", "Process terminated"));
                            monitoredProcess = null;
                        }
                        else
                        {
                            DateTime curProcessTime = DateTime.UtcNow;
                            TimeSpan curProcessCpu = monitoredProcess.TotalProcessorTime;
                            double elapsedWallMs = (curProcessTime - prevProcessTime).TotalMilliseconds;
                            double elapsedCpuMs = (curProcessCpu - prevProcessCpu).TotalMilliseconds;

                            if (elapsedWallMs > 0)
                            {
                                double procCpuPct = (elapsedCpuMs / (elapsedWallMs * Environment.ProcessorCount)) * 100.0;
                                if (procCpuPct < 0.0) procCpuPct = 0.0;
                                emitLine(FormatMetric(nowIso, "process.cpu.utilization.pct", procCpuPct, "percent", "ProcessTimes", "PID:" + targetPid, "ok", null));
                            }
                            prevProcessTime = curProcessTime;
                            prevProcessCpu = curProcessCpu;

                            long workingSet = monitoredProcess.WorkingSet64;
                            emitLine(FormatMetric(nowIso, "process.memory.working_set.bytes", (double)workingSet, "bytes", "ProcessMemory", "PID:" + targetPid, "ok", null));
                        }
                    }
                    catch (Exception ex)
                    {
                        emitLine(FormatMetric(nowIso, "process.cpu.utilization.pct", null, "percent", "ProcessTimes", "PID:" + targetPid, "error", ex.Message));
                        emitLine(FormatMetric(nowIso, "process.memory.working_set.bytes", null, "bytes", "ProcessMemory", "PID:" + targetPid, "error", ex.Message));
                    }
                }
                else
                {
                    emitLine(FormatMetric(nowIso, "process.cpu.utilization.pct", null, "percent", "ProcessTimes", "PID:" + targetPid, "unavailable", "Process not found or exited"));
                    emitLine(FormatMetric(nowIso, "process.memory.working_set.bytes", null, "bytes", "ProcessMemory", "PID:" + targetPid, "unavailable", "Process not found or exited"));
                }

                // 4. System Uptime
                ulong uptimeMs = NativeMethods.GetTickCount64();
                double uptimeSec = (double)uptimeMs / 1000.0;
                emitLine(FormatMetric(nowIso, "system.uptime.seconds", uptimeSec, "seconds", "GetTickCount64", null, "ok", null));

                // 5. Collector Health
                emitLine(FormatMetric(nowIso, "collector.health.status", 1.0, "status_flag", "WinScope_Watchdog", null, "ok", null));

                sampleIndex++;

                // Sleep remainder of interval
                int elapsed = (int)(DateTime.UtcNow - nowUtc).TotalMilliseconds;
                int sleepTime = intervalMs - elapsed;
                if (sleepTime > 0 && _keepRunning)
                {
                    Thread.Sleep(sleepTime);
                }
            }

            // Emit session footer
            DateTime endTime = DateTime.UtcNow;
            string footerJson = string.Format(
                CultureInfo.InvariantCulture,
                "{{\"type\":\"session_footer\",\"session_id\":\"{0}\",\"end_time\":\"{1}\",\"total_samples\":{2},\"collector_status\":\"completed\"}}",
                sessionId,
                endTime.ToString("yyyy-MM-ddTHH:mm:ss.ffffffZ", CultureInfo.InvariantCulture),
                sampleIndex
            );
            emitLine(footerJson);

            if (fileWriter != null)
            {
                fileWriter.Close();
            }

            return 0;
        }

        private static string FormatMetric(
            string timestamp,
            string metricName,
            double? value,
            string unit,
            string source,
            string targetId,
            string status,
            string errorMessage)
        {
            string valStr = value.HasValue
                ? value.Value.ToString("F4", CultureInfo.InvariantCulture)
                : "null";

            string targetStr = targetId != null
                ? "\"" + Escape(targetId) + "\""
                : "null";

            string errStr = errorMessage != null
                ? "\"" + Escape(errorMessage) + "\""
                : "null";

            return string.Format(
                CultureInfo.InvariantCulture,
                "{{\"timestamp\":\"{0}\",\"time_basis\":\"utc_wall_clock\",\"metric_name\":\"{1}\",\"value\":{2},\"unit\":\"{3}\",\"source\":\"{4}\",\"target_id\":{5},\"status\":\"{6}\",\"error_message\":{7},\"schema_version\":\"1.0.0\"}}",
                timestamp,
                metricName,
                valStr,
                unit,
                source,
                targetStr,
                status,
                errStr
            );
        }

        private static string Escape(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "").Replace("\n", " ");
        }

        private static void PrintHelp()
        {
            Console.WriteLine("WinScope Native Windows Telemetry Collector v1.0.0");
            Console.WriteLine("Usage: WinScope.Collector.exe [options]");
            Console.WriteLine("Options:");
            Console.WriteLine("  --interval <ms>      Sampling interval in milliseconds (default: 1000)");
            Console.WriteLine("  --duration <sec>     Total run duration in seconds (0 = continuous, default: 10)");
            Console.WriteLine("  --output <file>      Path to output JSONL file");
            Console.WriteLine("  --pid <pid>          Target process ID to monitor (default: current process)");
            Console.WriteLine("  --help               Show this help message");
        }
    }
}
