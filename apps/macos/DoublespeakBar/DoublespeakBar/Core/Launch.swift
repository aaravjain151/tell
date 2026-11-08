import Foundation

/// Builds the exact commands the app runs. Pure, so tests can assert the arguments.
/// The app never opens, reads or prints `.env`: it only checks the file exists and hands uvicorn `--env-file`.
enum LaunchPlan {
    static let model = "Sadanie/pellav2-audio-deepfake-detector"
    static let defaultRepo = "/Users/aarav/Downloads/tell"
    static let uiPort = 5173

    static func python(_ repo: String) -> String { repo + "/.venv/bin/python" }
    static func tapBinary(_ repo: String) -> String { repo + "/tools/macos/tap_audio/.build/release/tap_audio" }
    static func hubCacheDir(home: String) -> String { home + "/.cache/huggingface/hub/models--Sadanie--pellav2-audio-deepfake-detector" }

    static func baseEnvironment(home: String) -> [String: String] {
        ["HOME": home, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
         "PYTHONUNBUFFERED": "1"]
    }

    static func engine(repo: String, port: Int, weightsCached: Bool, envFileExists: Bool, home: String) -> LaunchSpec {
        var args = ["-m", "uvicorn", "doublespeak.main:app", "--host", "127.0.0.1", "--port", String(port)]
        if envFileExists { args += ["--env-file", repo + "/.env"] }
        var env = baseEnvironment(home: home)
        if weightsCached { env["PELLA_MODEL"] = model; env["PELLA_DEVICE"] = "mps" }
        return LaunchSpec(name: "engine", executable: python(repo), arguments: args,
                          cwd: repo + "/services/api", environment: env)
    }

    static func listener(repo: String, port: Int, home: String) -> LaunchSpec {
        LaunchSpec(name: "listener", executable: python(repo),
                   arguments: [repo + "/tools/macos/listen.py", "--watch", "--i-understand",
                               "--no-notify",                       // the app posts the notification itself
                               "--url", "http://127.0.0.1:\(port)"],
                   cwd: repo, environment: baseEnvironment(home: home), stopSignal: SIGINT)
    }

    /// Serves apps/web on loopback so "Open Doublespeak" works without `make web`.
    static func page(repo: String, home: String) -> LaunchSpec {
        LaunchSpec(name: "page", executable: python(repo),
                   arguments: ["-m", "http.server", String(uiPort), "--bind", "127.0.0.1", "--directory", repo + "/apps/web"],
                   cwd: repo, environment: baseEnvironment(home: home))
    }

    /// Problems the user can fix, in plain words; nil when the repo looks usable.
    static func repoProblem(_ repo: String, fm: FileManager = .default) -> String? {
        if !fm.isExecutableFile(atPath: python(repo)) { return "No Python found at \(python(repo)). Set the Doublespeak folder in Settings." }
        if !fm.fileExists(atPath: repo + "/services/api/doublespeak/main.py") { return "That folder is not a Doublespeak checkout." }
        if !fm.fileExists(atPath: repo + "/tools/macos/listen.py") { return "tools/macos/listen.py is missing in that folder." }
        if !fm.isExecutableFile(atPath: tapBinary(repo)) {
            return "The audio tap is not built. Run: cd tools/macos/tap_audio && swift build -c release"
        }
        return nil
    }
}
