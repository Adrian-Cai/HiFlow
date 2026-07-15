import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MOBILE_ROOT = REPO_ROOT / "mobile_automation"


class PowerShellScriptContractTests(unittest.TestCase):
    def test_one_click_script_starts_dependencies_and_runs_auto(self) -> None:
        script = (MOBILE_ROOT / "start.ps1").read_text(encoding="utf-8")

        self.assertIn("http://127.0.0.1:8787/health", script)
        self.assertIn("http://127.0.0.1:4723/status", script)
        self.assertIn("Start-Process", script)
        self.assertIn("-WindowStyle Hidden", script)
        self.assertIn("run.ps1", script)
        self.assertIn("auto", script)
        self.assertIn("resume_001", script)
        self.assertIn("CheckOnly", script)
        self.assertIn("Write-Stage '启动'", script)
        self.assertIn("Write-Stage '日志'", script)

    def test_one_click_script_avoids_powershell_redirect_bug_with_duplicate_path_keys(self) -> None:
        script = (MOBILE_ROOT / "start.ps1").read_text(encoding="utf-8")

        self.assertNotIn("-RedirectStandardOutput", script)
        self.assertNotIn("-RedirectStandardError", script)

    def test_appium_script_keeps_debug_detail_in_file_and_quiets_console(self) -> None:
        script = (MOBILE_ROOT / "start-appium.ps1").read_text(encoding="utf-8")

        self.assertIn("--log-level", script)
        self.assertIn("error:debug", script)
        self.assertIn("--log", script)
        self.assertIn("--log-no-colors", script)
        self.assertIn("[日志]", script)


if __name__ == "__main__":
    unittest.main()
