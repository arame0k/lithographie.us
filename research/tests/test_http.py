import sys,unittest
from pathlib import Path
from urllib.request import Request
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app import Handler

class HtmlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_address[1]}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def test_observed_report_and_unpoly_fragment(self):
        with urlopen(self.url+'/') as response:
            page=response.read().decode()
        self.assertIn('Commodity comparison',page)
        self.assertIn('452,301,510',page)
        self.assertIn('570,362,693',page)
        request=Request(self.url+'/',headers={'X-Up-Target':'#workspace'})
        with urlopen(request) as response:fragment=response.read().decode()
        self.assertIn('id="workspace"',fragment)
        self.assertNotIn('<!DOCTYPE html>',fragment)
    def test_source_csv_and_bad_filters(self):
        with urlopen(self.url+'/data.csv') as response:body=response.read().decode()
        self.assertTrue(body.startswith('period,port_code,country_code,value_usd'))
        self.assertIn('202401',body)
        with self.assertRaises(HTTPError) as error:urlopen(self.url+'/?hs=000000')
        self.assertEqual(error.exception.code,400)
    def test_evidence_inspector_rejects_invalid_code(self):
        with self.assertRaises(HTTPError) as error:urlopen(self.url+'/evidence?port=<script>&country=1220')
        self.assertEqual(error.exception.code,400)
    def test_renderer_is_explicitly_unavailable_not_fabricated(self):
        import shutil
        if shutil.which('Rscript'):self.skipTest('R is installed')
        with self.assertRaises(HTTPError) as error:urlopen(self.url+'/plot.svg')
        self.assertEqual(error.exception.code,503)

if __name__=='__main__':unittest.main()
