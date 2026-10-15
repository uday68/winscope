using System;
using System.Threading;

namespace WinScope.Diagnostics
{
    /// <summary>
    /// Intentionally faulty target application for WinDbg / dump analysis triage.
    /// Demonstrates Access Violation (AV) crash and thread synchronization deadlock.
    /// </summary>
    public class CrashApp
    {
        private static readonly object LockA = new object();
        private static readonly object LockB = new object();

        public static int Main(string[] args)
        {
            if (args.Length == 0)
            {
                Console.WriteLine("WinScope Diagnostic Test App");
                Console.WriteLine("Usage: CrashApp.exe [--crash | --deadlock]");
                return 0;
            }

            string mode = args[0].ToLowerInvariant();

            if (mode == "--crash")
            {
                Console.WriteLine("[WinScope Diagnostics] Triggering intentional Null Reference / Access Violation...");
                TriggerAccessViolation();
            }
            else if (mode == "--deadlock")
            {
                Console.WriteLine("[WinScope Diagnostics] Triggering intentional inverted lock deadlock...");
                TriggerDeadlock();
            }
            else
            {
                Console.WriteLine("Unknown argument: " + mode);
                return 1;
            }

            return 0;
        }

        private static void TriggerAccessViolation()
        {
            string nullString = null;
            // Deliberate null reference exception to trigger crash triage in WinDbg
            Console.WriteLine(nullString.Length);
        }

        private static void TriggerDeadlock()
        {
            Thread thread1 = new Thread(() =>
            {
                lock (LockA)
                {
                    Console.WriteLine("[Thread 1] Acquired Lock A, waiting for Lock B...");
                    Thread.Sleep(500);
                    lock (LockB)
                    {
                        Console.WriteLine("[Thread 1] Acquired Lock B");
                    }
                }
            })
            { Name = "WorkerThread-1" };

            Thread thread2 = new Thread(() =>
            {
                lock (LockB)
                {
                    Console.WriteLine("[Thread 2] Acquired Lock B, waiting for Lock A...");
                    Thread.Sleep(500);
                    lock (LockA)
                    {
                        Console.WriteLine("[Thread 2] Acquired Lock A");
                    }
                }
            })
            { Name = "WorkerThread-2" };

            thread1.Start();
            thread2.Start();

            thread1.Join();
            thread2.Join();
        }
    }
}
