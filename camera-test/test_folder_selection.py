from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from folder_picker import list_folders
from server import Trial


class FolderSelectionTests(unittest.TestCase):
    def trial(self,folder):
        trial=Trial(Path(folder)/'captures');trial.running=True
        trial.frame=np.zeros((60,80,3),np.uint8)
        trial.action({'action':'brand','brand':'선택 시험'})
        trial.capture('manual');trial.action({'action':'review','group':trial.active_group})
        return trial

    def test_selection_persists_and_old_result_opens_after_location_change(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.trial(folder)
            first=Path(folder)/'첫 위치';first.mkdir()
            second=Path(folder)/'second';second.mkdir()
            trial.set_export_directory(str(first.resolve()))
            saved=trial.save_local()
            self.assertEqual(saved.parent,first.resolve())
            photos=list(saved.rglob('*.jpg'));self.assertEqual(len(photos),1)
            self.assertEqual(photos[0].read_bytes(),next(trial.directory.glob('*.jpg')).read_bytes())
            self.assertEqual(Trial(trial.directory).export_directory,first.resolve())
            trial.set_export_directory(str(second.resolve()))
            with patch('server.os.startfile',create=True) as opened:
                trial.open_export();opened.assert_called_once_with(str(saved))
            self.assertTrue(saved.is_dir())

    def test_cancel_and_invalid_destinations_keep_previous_setting(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.trial(folder);previous=trial.export_directory
            self.assertEqual(trial.export_directory,previous)
            file=Path(folder)/'not-a-folder';file.write_text('keep')
            for bad in [None,'','relative','\\\\server\\share',str(file.resolve()),str((Path(folder)/'missing').resolve())]:
                with self.assertRaises(ValueError):trial.set_export_directory(bad)
            valid=Path(folder).resolve()
            with patch('server.tempfile.TemporaryFile',side_effect=PermissionError('test')):
                with self.assertRaises(ValueError):trial.set_export_directory(str(valid))
            trial.export_lock.acquire()
            try:
                with self.assertRaises(ValueError):trial.set_export_directory(str(valid))
            finally:trial.export_lock.release()
            self.assertEqual(trial.export_directory,previous)
            self.assertNotIn('export_directory',trial.data)

    def test_missing_selected_folder_is_not_recreated_and_failed_setting_rolls_back(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.trial(folder);chosen=Path(folder)/'chosen';chosen.mkdir()
            previous=trial.export_directory
            with patch.object(trial,'persist',side_effect=OSError('test')):
                with self.assertRaises(OSError):trial.set_export_directory(str(chosen.resolve()))
            self.assertEqual(trial.export_directory,previous)
            self.assertNotIn('export_directory',trial.data)
            trial.set_export_directory(str(chosen.resolve()));chosen.rmdir()
            with self.assertRaises(ValueError):trial.save_local()
            self.assertFalse(chosen.exists())

    def test_picker_lists_folders_only_and_rejects_remote_paths(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            base=Path(folder);(base/'선택할 폴더').mkdir();(base/'photo.jpg').write_bytes(b'keep')
            listing=list_folders(str(base.resolve()))
            self.assertEqual([f['name'] for f in listing['folders']],['선택할 폴더'])
            self.assertEqual(listing['path'],str(base.resolve()))
            self.assertEqual(listing['parent'],str(base.resolve().parent))
            self.assertTrue(list_folders()['drives'])
            with self.assertRaises(ValueError):list_folders('relative')
