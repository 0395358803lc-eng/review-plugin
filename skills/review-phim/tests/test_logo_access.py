import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts" / "plan_logo_access.py"
spec = importlib.util.spec_from_file_location('review_phim_logo_access', HERE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class LogoAccessTests(unittest.TestCase):
    def test_adds_only_selected_windows_logo_folder_without_changing_previous_entries(self):
        original = [r'D:\Phim\phim-2', r'C:\Users\Public\Assets']
        result = mod.plan_logo_access({'allowedDirectories': original}, r'D:\logo\New folder')
        self.assertTrue(result['requires_config_change'])
        self.assertEqual(result['allowedDirectories'], [*original, r'D:\logo\New folder'])
        self.assertEqual(original, [r'D:\Phim\phim-2', r'C:\Users\Public\Assets'])
        self.assertNotIn('D:\\', result['allowedDirectories'])

    def test_unicode_and_spaces_selected_folder(self):
        result = mod.plan_logo_access({'allowedDirectories': [r'D:\phim']}, r'E:\Ảnh logo\Mẫu mới')
        self.assertEqual(result['allowedDirectories'][-1], r'E:\Ảnh logo\Mẫu mới')

    def test_existing_parent_already_allows_logo_folder(self):
        r = mod.plan_logo_access({'allowedDirectories': [r'd:\LOGO']}, r'D:\logo\New folder')
        self.assertFalse(r['requires_config_change'])
        self.assertEqual(r['status'], 'already_allowed')

    def test_existing_exact_logo_case_insensitive(self):
        r = mod.plan_logo_access({'allowedDirectories': [r'd:\logo\NEW FOLDER']}, r'D:\logo\New folder')
        self.assertEqual(r['status'], 'already_allowed')

    def test_sibling_directory_is_not_permission(self):
        r = mod.plan_logo_access({'allowedDirectories': [r'D:\logo\Old folder']}, r'D:\logo\New folder')
        self.assertTrue(r['requires_config_change'])
        self.assertEqual(len(r['allowedDirectories']), 2)

    def test_unrestricted_existing_empty_list_never_reset_or_expand(self):
        r = mod.plan_logo_access({'allowedDirectories': []}, r'D:\logo\New folder')
        self.assertEqual(r['status'], 'already_unrestricted')
        self.assertFalse(r['requires_config_change'])
        self.assertEqual(r['allowedDirectories'], [])

    def test_missing_or_invalid_configuration_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'DC_CONFIG_UNVERIFIED'):
            mod.plan_logo_access({}, r'D:\logo\New folder')
        with self.assertRaisesRegex(ValueError, 'DC_CONFIG_INVALID'):
            mod.plan_logo_access({'allowedDirectories': 'D:\\film'}, r'D:\logo\New folder')

    def test_drive_root_and_relative_rejected(self):
        for value in ['D:\\', r'..\logo', 'logo', '/', 'C:relative\logo']:
            with self.subTest(path=value), self.assertRaises(ValueError):
                mod.plan_logo_access({'allowedDirectories': [r'D:\film']}, value)

    def test_unc_path_adds_exact_folder_not_share_root(self):
        new = r'\\server\share\Brand assets'
        r = mod.plan_logo_access({'allowedDirectories': [r'D:\film']}, new)
        self.assertEqual(r['allowedDirectories'][-1],new)
        with self.assertRaisesRegex(ValueError, 'LOGO_PATH_TOO_BROAD'):
            mod.plan_logo_access({'allowedDirectories': [r'D:\film']},r'\\server\share')

    def test_preexisting_drive_root_covers_chosen_logo_without_expansion(self):
        r = mod.plan_logo_access({'allowedDirectories': ['D:\\']}, r'D:\logo\New folder')
        self.assertEqual(r['status'], 'already_allowed')
        self.assertFalse(r['requires_config_change'])

    def test_preexisting_posix_root_covers_logo_without_expansion(self):
        r = mod.plan_logo_access({'allowedDirectories': ['/']}, '/mnt/logos/brand')
        self.assertEqual(r['status'], 'already_allowed')

    def test_posix_path_and_existing_parent(self):
        r = mod.plan_logo_access({'allowedDirectories': ['/mnt/videos']}, '/mnt/logos/Brand')
        self.assertEqual(r['allowedDirectories'], ['/mnt/videos','/mnt/logos/Brand'])
        r2 = mod.plan_logo_access({'allowedDirectories': ['/mnt/logos']}, '/mnt/logos/Brand')
        self.assertFalse(r2['requires_config_change'])


if __name__ == '__main__':
    unittest.main()
