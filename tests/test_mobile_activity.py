import unittest

from mobile_automation.activity import ActivityLevel, normalize_activity


class ActivityNormalizationTests(unittest.TestCase):
    def test_real_boss_chinese_activity_labels_are_normalized(self) -> None:
        expected = {
            "在线": ActivityLevel.TODAY,
            "今日活跃": ActivityLevel.TODAY,
            "昨日活跃": ActivityLevel.WITHIN_3_DAYS,
            "3日内活跃": ActivityLevel.WITHIN_3_DAYS,
            "4天前活跃": ActivityLevel.STALE,
        }
        for text, level in expected.items():
            with self.subTest(text=text):
                self.assertEqual(normalize_activity(text), level)

    def test_today_signals_are_normalized(self) -> None:
        for text in (
            "今日活跃",
            "刚刚活跃",
            "在线",
            "2小时前活跃",
            "30分钟前活跃",
            "8分钟前回复",
            "1小时前回复",
            "今日回复10+次",
            "今日回复3次",
        ):
            with self.subTest(text=text):
                self.assertEqual(normalize_activity(text), ActivityLevel.TODAY)

    def test_recent_three_day_signals_are_normalized(self) -> None:
        for text in ("近3日活跃", "3日内活跃", "1天前活跃", "2天前活跃", "3天前活跃"):
            with self.subTest(text=text):
                self.assertEqual(normalize_activity(text), ActivityLevel.WITHIN_3_DAYS)

    def test_stale_and_unknown_signals_are_conservative(self) -> None:
        self.assertEqual(normalize_activity("4天前活跃"), ActivityLevel.STALE)
        self.assertEqual(normalize_activity("本月活跃"), ActivityLevel.STALE)
        self.assertEqual(normalize_activity(""), ActivityLevel.UNKNOWN)
        self.assertEqual(normalize_activity("招聘者"), ActivityLevel.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
