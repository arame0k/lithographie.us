import sqlite3,tempfile,unittest
from pathlib import Path
from db_safety import assert_safe_to_rebuild
from census_port_hs6 import initialize
class GuardTests(unittest.TestCase):
 def test_rejects_destroying_imported_archives(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'e.db'
   c=sqlite3.connect(p);initialize(c)
   c.execute("INSERT INTO port_hs6_archives VALUES('202501','M','a','https://www.census.gov','layout',1,1,1,'complete_file','2026-10-24')")
   c.commit();c.close()
   with self.assertRaises(ValueError):assert_safe_to_rebuild(p)
 def test_no_archive_can_rebuild(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'e.db'
   c=sqlite3.connect(p);initialize(c);c.close()
   assert_safe_to_rebuild(p)
if __name__=='__main__':unittest.main()
