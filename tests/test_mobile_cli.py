import unittest

from mobile_automation.cli import build_parser, doctor_result


class CliContractTests(unittest.TestCase):
    def test_auto_contract_uses_confirmed_streaming_defaults(self) -> None:
        args = build_parser().parse_args(["auto", "--resume-id", "resume_001"])

        self.assertEqual(args.command, "auto")
        self.assertEqual(args.minimum_salary_k, 15)
        self.assertEqual(args.threshold, 90)
        self.assertEqual(args.batch_size, 5)
        self.assertEqual(args.cooldown_seconds, 120)
        self.assertEqual(args.daily_limit, 150)

    def test_scan_contract(self) -> None:
        args = build_parser().parse_args(["scan", "--resume-id", "resume_001"])
        self.assertEqual(args.command, "scan")
        self.assertEqual(args.resume_id, "resume_001")
        self.assertEqual(args.threshold, 80)
        self.assertEqual(args.candidate_limit, 5)

    def test_batch_commands_require_batch_id(self) -> None:
        for command in ("apply", "resume", "status"):
            with self.subTest(command=command):
                args = build_parser().parse_args([command, "--batch-id", "batch-123"])
                self.assertEqual(args.batch_id, "batch-123")

    def test_doctor_requires_authorized_device_and_python_client(self) -> None:
        pending = doctor_result(["SERIAL authorizing product:phone"], client_installed=False)
        ready = doctor_result(["SERIAL device product:phone"], client_installed=True)

        self.assertFalse(pending["ok"])
        self.assertEqual(pending["deviceState"], "authorizing")
        self.assertTrue(ready["ok"])
        self.assertEqual(ready["deviceState"], "device")


if __name__ == "__main__":
    unittest.main()
