// SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
// Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
//
// Klassenbildung.exe – startet das mitgelieferte Python mit "skf app" im selben Fenster.
// Ohne Argumente: Bedienoberfläche. Mit Befehl (z.B. "rechnen schule.yaml kinder.csv"):
// Kommandozeile. Gebaut mit dem csc.exe des .NET Framework, das auf jedem Windows 10/11 liegt.
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;

class Starter
{
    static int Main(string[] args)
    {
        string ordner = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(ordner, "python", "python.exe");
        if (!File.Exists(python))
        {
            Console.Error.WriteLine("Python fehlt: " + python + " – bitte neu installieren.");
            return 2;
        }
        bool befehl = args.Length > 0 && !args[0].StartsWith("-");
        var teile = new[] { "-m", "skf" }.Concat(befehl ? args : new[] { "app" }.Concat(args));
        var start = new ProcessStartInfo(python, string.Join(" ", teile.Select(Zitat)))
        {
            UseShellExecute = false,
            WorkingDirectory = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
        };
        start.EnvironmentVariables["PYTHONUTF8"] = "1";
        start.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
        Console.Title = "Klassenbildung – zum Beenden dieses Fenster schliessen";
        using (var p = Process.Start(start))
        {
            p.WaitForExit();
            return p.ExitCode;
        }
    }

    static string Zitat(string s)
    {
        if (s.Length > 0 && s.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return s;
        string innen = s.Replace("\"", "\\\"");
        if (innen.EndsWith("\\")) innen += "\\";  // abschliessender Backslash vor dem Anführungszeichen
        return "\"" + innen + "\"";
    }
}
