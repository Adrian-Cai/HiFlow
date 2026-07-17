import unittest
from unittest.mock import patch

from local_service.server import effective_target_titles, score_match


class LocalMatchPolicyTests(unittest.TestCase):
    @patch("local_service.server.read_resumes")
    def test_unknown_resume_id_is_rejected_instead_of_using_another_profile(self, read_resumes) -> None:
        read_resumes.return_value = [{"id": "resume_001"}]

        with self.assertRaisesRegex(ValueError, "简历"):
            from local_service.server import pick_resume

            pick_resume("missing_resume")

    def test_malformed_imported_target_titles_fall_back_to_test_roles(self) -> None:
        resume = {
            "target_titles": [
                "具备完整测试设计能力",
                "异常流用例设计覆盖体系",
                "SeleniumBase 等自动化测试框架",
            ],
            "skills": ["Python", "测试开发", "自动化测试"],
        }

        self.assertIn("测试开发", effective_target_titles(resume))

    @patch("local_service.server.append_match_log")
    @patch("local_service.server.pick_resume")
    def test_recommends_suitable_job_at_eighty_percent_threshold(self, pick_resume, _append_log) -> None:
        pick_resume.return_value = {
            "id": "resume_001",
            "summary": "7年测试与测试开发经验",
            "target_titles": ["测试开发"],
            "skills": ["Python", "自动化测试"],
            "exclude_keywords": [],
        }

        result = score_match(
            {
                "resume_id": "resume_001",
                "jd_text": "测试开发工程师，负责 Python 接口自动化、性能测试、测试平台与持续集成建设。" * 2,
                "job_meta": {"title": "测试开发工程师"},
            }
        )

        self.assertGreaterEqual(result["score"], 80)
        self.assertEqual(result["decision"], "RECOMMEND")
        self.assertIn("ruleBaselineScore", result["detail"])
        self.assertNotIn("llmScore", result["detail"])

    @patch("local_service.server.append_match_log")
    @patch("local_service.server.pick_resume")
    def test_title_only_manual_job_does_not_reach_auto_contact_threshold(self, pick_resume, _append_log) -> None:
        pick_resume.return_value = {
            "id": "resume_001",
            "summary": "6年测试开发经验",
            "target_titles": ["测试工程师"],
            "skills": ["Python", "接口自动化", "UI自动化", "性能测试"],
            "exclude_keywords": [],
        }

        result = score_match(
            {
                "resume_id": "resume_001",
                "jd_text": "测试工程师，主要负责执行功能测试、记录结果、整理文档并跟进问题。" * 2,
                "job_meta": {"title": "测试工程师"},
            }
        )

        self.assertLess(result["score"], 90)


if __name__ == "__main__":
    unittest.main()
