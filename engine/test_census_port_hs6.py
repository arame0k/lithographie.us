"""Contract tests for official US Census Port HS6 monthly ASCII ZIP acquisition."""
import io, json, sqlite3, tempfile, unittest, zipfile
from pathlib import Path
from census_port_hs6 import parse_record, import_archive, initialize, quarter_routes, source_url, evidence_status


def fixture(hs='760110', country='0124', port='2704', period='202501', value=100, vessel=65, container=40, air=10):
    fields=[hs,country,port,period[:4],period[4:],value,air,12,vessel,300,container,190,
            value,air,12,vessel,300,container,190]
    text=''.join(str(x).zfill([6,4,4,4,2][i]) if i<5 else str(x).zfill(15) for i,x in enumerate(fields))
    assert len(text)==230
    return text+'\n'


def make_zip(path,period='202501',flow='M',lines=None):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'DPORTHS6{"I" if flow=="M" else "E"}{period[2:]}.TXT', ''.join(lines or [fixture(period=period)]))


class CensusPortHS6Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.conn=sqlite3.connect(self.path/'evidence.db');self.addCleanup(self.conn.close)
        initialize(self.conn)

    def test_parse_official_230_character_layout(self):
        row=parse_record(fixture().strip(), '202501')
        self.assertEqual((row['hs6'],row['country_code'],row['port_code']),('760110','0124','2704'))
        self.assertEqual((row['value_usd'],row['vessel_value_usd'],row['container_value_usd']),(100,65,40))
        self.assertEqual(row['vessel_weight_kg'],300)
        self.assertEqual(row['container_weight_kg'],190)

    def test_rejects_mode_values_that_exceed_total(self):
        with self.assertRaisesRegex(ValueError,'air.*vessel.*total'):
            parse_record(fixture(value=100,air=80,vessel=65).strip(),'202501')

    def test_port_codes_and_country_codes_preserve_leading_zeroes(self):
        r=parse_record(fixture(country='0036',port='0401').strip(),'202501')
        self.assertEqual(r['country_code'],'0036');self.assertEqual(r['port_code'],'0401')

    def test_import_archive_with_hash_and_official_source(self):
        z=self.path/'PORTHS6MM2501.ZIP';make_zip(z)
        summary=import_archive(self.conn,z,period='202501',flow='M',hs_prefixes=('7601',))
        self.assertEqual(summary['rows_stored'],1)
        self.assertEqual(summary['status'],'filtered')
        self.assertEqual(self.conn.execute('select count(*) from port_hs6').fetchone()[0],1)
        s=self.conn.execute('select sha256,source_url from port_hs6_archives').fetchone()
        self.assertEqual(len(s[0]),64);self.assertEqual(s[1],source_url('202501','M'))
        self.assertEqual(import_archive(self.conn,z,period='202501',flow='M',hs_prefixes=('7601',))['status'],'unchanged')

    def test_invalid_line_and_wrong_period_rejected_atomically(self):
        z=self.path/'bad.zip';make_zip(z,lines=[fixture(),fixture(period='202502')])
        with self.assertRaises(ValueError):import_archive(self.conn,z,'202501','M')
        self.assertEqual(self.conn.execute('select count(*) from port_hs6').fetchone()[0],0)
        self.assertEqual(self.conn.execute('select count(*) from port_hs6_archives').fetchone()[0],0)

    def test_contiguous_230_byte_records_without_newlines(self):
        z=self.path/'packed.zip'
        with zipfile.ZipFile(z,'w') as archive:
            archive.writestr('DPORTHS6I2501.TXT',
                fixture().strip() + fixture(country='0125').strip())
        result=import_archive(self.conn,z,'202501','M')
        self.assertEqual(result['rows_stored'],2)

    def test_real_official_archive_member_spelling_and_crlf(self):
        # Browser-verified 2025-01 ZIP uses dporths6ir2501.txt, not the
        # spelling printed in the legacy Census layout document.
        z=self.path/'PORTHS6MM2501.ZIP'
        with zipfile.ZipFile(z,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('dporths6ir2501.txt',fixture(period='202501',country='1220',port='0701',value=1213537).replace('\n','\r\n'))
        result=import_archive(self.conn,z,'202501','M')
        self.assertEqual(result['physical_rows'],1)
        self.assertEqual(result['rows_stored'],1)
        self.assertEqual(self.conn.execute('SELECT country_code,port_code,value_usd FROM port_hs6').fetchone(),('1220','0701',1213537))

    def test_export_archive_r_variant_supported_without_claiming_verified_export(self):
        # Export R variant acceptance is parser-compatibility coverage;
        # this is a synthetic fixture, not an inspected export archive.
        z=self.path/'PORTHS6XM2501.ZIP'
        with zipfile.ZipFile(z,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('dporths6er2501.txt',fixture(period='202501').replace('\n','\r\n'))
        result=import_archive(self.conn,z,'202501','X')
        self.assertEqual(result['rows_stored'],1)
        self.assertEqual(self.conn.execute('SELECT flow FROM port_hs6').fetchone()[0],'X')

    def test_wrong_direction_archive_member_is_rejected(self):
        z=self.path/'wrongmember.zip'
        with zipfile.ZipFile(z,'w') as archive:
            archive.writestr('dporths6er2501.txt',fixture(period='202501'))
        with self.assertRaises(ValueError):import_archive(self.conn,z,'202501','M')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM port_hs6_archives').fetchone()[0],0)

    def test_duplicate_key_rejected(self):
        z=self.path/'dup.zip';make_zip(z,lines=[fixture(),fixture()])
        with self.assertRaises((ValueError,sqlite3.IntegrityError)):import_archive(self.conn,z,'202501','M')
        self.assertEqual(self.conn.execute('select count(*) from port_hs6').fetchone()[0],0)

    def test_monthly_values_only_and_no_double_count_containers(self):
        z=self.path/'monthly.zip';make_zip(z)
        import_archive(self.conn,z,'202501','M')
        summary=quarter_routes(self.conn,'2025','7601','M')
        self.assertEqual(summary['months'],1);self.assertIsNone(summary['total_usd'])
        self.assertEqual(summary['observed_usd'],100)
        self.assertEqual(summary['routes'],[], 'partial-month routes must not look like a ranked complete quarter')

    def test_exact_quarter_required_for_comparison(self):
        for m in ['01','02','03']:
            period='2025'+m
            z=self.path/f'p{m}.zip';make_zip(z,period=period,lines=[fixture(period=period,value=100)])
            import_archive(self.conn,z,period,'M')
        summary=quarter_routes(self.conn,'2025','7601','M')
        self.assertEqual(summary['months'],3)
        self.assertEqual(summary['total_usd'],300)
        self.assertEqual(summary['routes'][0]['value_usd'],300)
        self.assertEqual(summary['routes'][0]['vessel_value_usd'],195)
        self.assertEqual(summary['routes'][0]['container_value_usd'],120)
        self.assertFalse(summary['coverage_complete'] is False)

    def test_filtered_archive_never_claims_full_coverage(self):
        for m in ['01','02','03']:
            period='2025'+m;z=self.path/f'p{m}.zip';make_zip(z,period=period,lines=[fixture(period=period)])
            import_archive(self.conn,z,period,'M',hs_prefixes=('7601',))
        self.assertFalse(quarter_routes(self.conn,'2025','7601','M')['coverage_complete'])
        self.assertIsNone(quarter_routes(self.conn,'2025','7601','M')['total_usd'])

    def test_no_inferred_company_link(self):
        self.assertFalse(any('company' in t[0].lower() for t in self.conn.execute("select name from sqlite_master where type='view'")))
        status=evidence_status(self.conn)
        self.assertEqual(status['verified_bills_of_lading'],0)
        self.assertEqual(status['company_shipment_edges'],0)

if __name__=='__main__':unittest.main()
