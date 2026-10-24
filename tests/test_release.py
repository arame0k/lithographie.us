"""Minimal release gate: the static GitHub Pages entry stays valid."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.refresh = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and 'href' in a:
            self.links.append(a['href'])
        if tag == 'meta' and a.get('http-equiv', '').lower() == 'refresh':
            self.refresh.append(a.get('content'))


class ReleaseTest(unittest.TestCase):
    def test_ggplot_svg_uses_base_r_device(self):
        # Avoid a hidden svglite dependency at chart-render time.
        script = (ROOT / 'research' / 'chart.R').read_text(encoding='utf-8')
        self.assertIn('device=grDevices::svg', script)
        self.assertNotIn("device='svg'", script)

    def test_static_entry_points_to_existing_workbench(self):
        landing = ROOT / 'index.html'
        parser = Links()
        parser.feed(landing.read_text(encoding='utf-8'))
        target = './Lithographie_Research_Workbench.html'
        self.assertTrue((ROOT / target).is_file())
        self.assertIn(target, parser.links)
        self.assertEqual(parser.refresh, [f'0; url={target}'])


if __name__ == '__main__':
    unittest.main()
