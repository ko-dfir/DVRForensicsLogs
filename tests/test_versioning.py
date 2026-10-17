import unittest

from scripts.versioning import get_version, version_info, windows_version_tuple


class TestVersioning(unittest.TestCase):
    def test_version_json_is_the_application_source_of_truth(self):
        self.assertEqual(get_version(), "1.01")
        self.assertEqual(version_info()["build"], 101)
        self.assertEqual(version_info()["product_name"], "CCTV Log Analyzer")
        self.assertEqual(windows_version_tuple(), (1, 1, 0, 0))


if __name__ == "__main__":
    unittest.main()
