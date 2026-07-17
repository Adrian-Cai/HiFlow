import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MOBILE_ROOT = REPO_ROOT / "mobile_automation"


class PowerShellScriptContractTests(unittest.TestCase):
    def test_one_click_script_defaults_to_verify_and_requires_explicit_auto(self) -> None:
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
        self.assertIn("[ValidateSet('verify', 'auto')]", script)
        self.assertIn("PositionalBinding = $false", script)
        self.assertIn("ValueFromRemainingArguments", script)
        self.assertIn("[string]$Mode = 'verify'", script)
        self.assertIn("if ($Mode -eq 'auto')", script)
        self.assertIn("& $RunScript $Mode", script)

    def test_verify_dependency_branch_does_not_start_match_service(self) -> None:
        script = (MOBILE_ROOT / "start.ps1").read_text(encoding="utf-8")
        auto_branch = script.index("if ($Mode -eq 'auto')")
        matcher_start = script.index("正在启动本地岗位匹配服务")
        appium_start = script.index("正在启动 Appium 手机自动化服务")

        self.assertGreater(matcher_start, auto_branch)
        self.assertGreater(appium_start, matcher_start)

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
