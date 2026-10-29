import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from package_assets import create_assets


class AssetTests(unittest.TestCase):
    def test_standard_zip_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root=Path(directory);app=root/'MOACUT-test';app.mkdir()
            (app/'파일.txt').write_text('portable sample',encoding='utf-8')
            output=root/'assets'
            records=create_assets(app,output)
            part=output/records[0]['name']
            self.assertEqual(hashlib.sha256(part.read_bytes()).hexdigest(),records[0]['sha256'])
            with zipfile.ZipFile(part) as archive:
                self.assertEqual(archive.read('MOACUT-test/파일.txt').decode(),'portable sample')
            self.assertEqual(json.loads((output/'assets.json').read_text()),records)
            self.assertIn(records[0]['sha256'],(output/'Install-MOACUT.cmd').read_text())
            with self.assertRaises(FileExistsError):create_assets(app,output)


if __name__=='__main__':unittest.main()
