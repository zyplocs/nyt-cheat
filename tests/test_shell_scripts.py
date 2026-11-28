import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DERIVE = ROOT / 'prune' / 'derive_fakes.sh'
BATCH = ROOT / 'prune' / 'batch_prune.sh'
BASH = shutil.which('bash')


@unittest.skipUnless(BASH, 'bash not available')
class ShellScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / 'data'
        self.data.mkdir()
        self.dictionary = Path(self.temp.name) / 'words.txt'
        self.dictionary.write_text('ghee\nhhhh\nzebra\n')
        self.original = self.dictionary.read_bytes()

    def run_script(self, script, *args):
        return subprocess.run(
            ['bash', str(script), *args],
            capture_output=True, text=True, check=False,
        )

    def test_derive_fakes(self):
        (self.data / 'output_111426.txt').write_text('ghee\nzebra\nhhhh\nghee\n')
        (self.data / 'answers_111426.txt').write_text('ghee\n')
        result = self.run_script(
            DERIVE, '--data-dir', str(self.data), '111426',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.data / 'fakes_111426.txt').read_text(),
            'hhhh\nzebra\n',
        )
        self.assertIn('2 candidate fakes', result.stdout)

    def test_derive_invalid_dates(self):
        for args in [
            ('--data-dir', str(self.data), '12345'),
            ('--data-dir', str(self.data), 'abcdef'),
            ('--data-dir', str(self.data)),
        ]:
            with self.subTest(args=args):
                self.assertEqual(self.run_script(DERIVE, *args).returncode, 2)

    def test_derive_missing_files(self):
        cases = [
            ('answers_111426.txt', 'output_111426.txt'),
            ('output_111426.txt', 'answers_111426.txt'),
        ]
        for present, missing in cases:
            with self.subTest(missing=missing):
                for path in self.data.iterdir():
                    path.unlink()
                (self.data / present).write_text('ghee\n')
                result = self.run_script(
                    DERIVE, '--data-dir', str(self.data), '111426',
                )
                self.assertEqual(result.returncode, 1)
                self.assertFalse((self.data / 'fakes_111426.txt').exists())

    def test_batch_unknown_argument(self):
        result = self.run_script(
            BATCH, '--data-dir', str(self.data), '--dict',
            str(self.dictionary), '--bogus',
        )
        self.assertEqual(result.returncode, 2)

    def prepare_batch(self):
        (self.data / 'answers_111426.txt').write_text('ghee\nwheeling\n')
        (self.data / 'output_111426.txt').write_text('ghee\nhhhh\n')
        (self.data / 'answers_111326.txt').write_text('ghee\n')

    def test_batch_dry_run(self):
        self.prepare_batch()
        result = self.run_script(
            BATCH, '--data-dir', str(self.data), '--dict', str(self.dictionary),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('=== Date 111426 ===', result.stdout)
        self.assertNotIn('111326', result.stdout)
        self.assertIn('Dry-run mode', result.stdout)
        self.assertEqual((self.data / 'fakes_111426.txt').read_text(), 'hhhh\n')
        self.assertEqual(self.dictionary.read_bytes(), self.original)

    def test_batch_apply(self):
        self.prepare_batch()
        result = self.run_script(
            BATCH, '--data-dir', str(self.data), '--dict', str(self.dictionary),
            '--apply', '--yes',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.dictionary.read_text().splitlines(),
            ['ghee', 'wheeling', 'zebra'],
        )

    def test_batch_empty_data_directory(self):
        result = self.run_script(
            BATCH, '--data-dir', str(self.data), '--dict', str(self.dictionary),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('No answers_*.txt files found', result.stderr)


if __name__ == '__main__':
    unittest.main()
