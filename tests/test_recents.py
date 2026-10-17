import os
import tempfile
import unittest

from scripts import recents


class TestRecents(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_local_appdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self.temp.name
        self.image = os.path.join(self.temp.name, "evidence.img")
        with open(self.image, "wb") as handle:
            handle.write(b"test")

    def tearDown(self):
        if self.old_local_appdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.old_local_appdata
        self.temp.cleanup()

    def test_recents_are_upserted_in_private_appdata_database(self):
        recents.remember(self.image, "TVT")
        recents.remember(self.image, "TVT", "result.db", "tvt_logs")
        rows = recents.recent()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].times, 2)
        self.assertEqual(rows[0].table_name, "tvt_logs")
        self.assertTrue(rows[0].exists)
        self.assertTrue(str(recents.db_path()).startswith(self.temp.name))
        self.assertEqual(recents.clear(), 1)


if __name__ == "__main__":
    unittest.main()
