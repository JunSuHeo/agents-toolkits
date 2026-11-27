import unittest

from app import report_name


class ReportNameTest(unittest.TestCase):
    def test_normalizes_name(self):
        self.assertEqual(report_name("  My  Report  "), "my report")
