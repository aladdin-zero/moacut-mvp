import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from server import Trial


class SelectedReviewTests(unittest.TestCase):
    def make_trial(self,folder):
        trial=Trial(Path(folder)/'captures');trial.running=True
        trial.frame=np.zeros((40,60,3),np.uint8)
        for _ in range(8):trial.capture('manual')
        return trial,[g['id'] for g in trial.data['groups']]

    def test_only_explicitly_selected_reviewed_products_become_savable(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial,ids=self.make_trial(folder)
            trial.action({'action':'assign_brand','groups':ids,'brand':'NIKE'})
            with self.assertRaises(ValueError):trial.save_local()
            trial.action({'action':'review_groups','groups':[ids[0]]})
            self.assertTrue(trial.group(ids[0])['reviewed'])
            self.assertFalse(trial.group(ids[1])['reviewed'])
            self.assertEqual([g['id'] for g in trial.export_selection()],[ids[0]])
            destination=trial.save_local()
            self.assertEqual(len(list(destination.rglob('*.jpg'))),4)
            self.assertTrue(all((trial.directory/p['file']).is_file() for g in trial.data['groups'] for p in g['photos']))

    def test_unassigned_and_invalid_selection_never_partially_approves(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial,ids=self.make_trial(folder)
            trial.action({'action':'assign_brand','groups':[ids[0]],'brand':'NIKE'})
            original=copy.deepcopy(trial.data)
            for selection in [ids,[],[ids[0],'unknown'],[ids[0],ids[0]],[None],ids[0]]:
                with self.subTest(selection=selection):
                    with self.assertRaises(ValueError):trial.action({'action':'review_groups','groups':selection})
                    self.assertEqual(trial.data,original)
                    self.assertEqual(json.loads(trial.file.read_text(encoding='utf-8')),original)

    def test_review_is_idempotent_but_brand_change_requires_review_again(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial,ids=self.make_trial(folder)
            trial.action({'action':'assign_brand','groups':ids,'brand':'NIKE'})
            trial.action({'action':'review_groups','groups':ids})
            trial.action({'action':'review_groups','groups':ids})
            self.assertTrue(all(g['reviewed'] for g in trial.data['groups']))
            self.assertEqual(len(trial.export_selection()),2)
            trial.action({'action':'assign_brand','groups':[ids[0]],'brand':'ADIDAS'})
            self.assertFalse(trial.group(ids[0])['reviewed'])
            self.assertTrue(trial.group(ids[1])['reviewed'])
            self.assertEqual([g['id'] for g in trial.export_selection()],[ids[1]])

    def test_failed_review_write_rolls_back_all_review_flags_and_event(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial,ids=self.make_trial(folder)
            trial.action({'action':'assign_brand','groups':ids,'brand':'NIKE'})
            trial.action({'action':'review_groups','groups':[ids[0]]})
            original=copy.deepcopy(trial.data)
            with patch.object(trial,'persist',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):trial.action({'action':'review_groups','groups':ids})
            self.assertEqual(trial.data,original)
            self.assertEqual(json.loads(trial.file.read_text(encoding='utf-8')),original)


if __name__=='__main__':unittest.main()
