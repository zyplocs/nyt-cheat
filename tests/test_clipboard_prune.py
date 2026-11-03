import contextlib
import io
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prune import clipboard, pruner
from prune.transform_text import parse_answer_table, parse_word_block


H_WORDS = """ghee heel heeling heinie hell henge hewing hewn high hill hilling hinge
hinging neigh neighing nigh weigh weighing whee wheel wheelie wheeling when whew
while whiling whine whinge whingeing whinging whining""".split()
P_WORDS = """alpaca apart appall apparat capital capri carp carpal carpi catalpa clap
claptrap clip crap pact pail pair palapa palatal palatial pall palp papa papal papilla
part partial partita pica piccata pill pillar pipit piratic pita pitapat plait plat
practical prat priapic rapt rattrap tapa tapir tarp tilapia tipi trap trip""".split()


def table(words, pangram):
    return '\n'.join(f'{word.upper()}\t\t{len(word)}' +
                     ('\t\tpangram' if word == pangram else '') for word in words)


H_TABLE = table(H_WORDS, 'wheeling')
P_TABLE = table(P_WORDS, 'practical')


class TableTests(unittest.TestCase):
    def test_both_supplied_keys_and_surrounding_quotes(self):
        for text, words, pangram, letters, center in [
            (H_TABLE, H_WORDS, 'wheeling', 'eghilnw', 'h'),
            (P_TABLE, P_WORDS, 'practical', 'acilprt', 'p'),
        ]:
            for quoted in [text, '"' + text + '"', '“' + text + '”']:
                with self.subTest(center=center, quoted=quoted[:1]):
                    parsed = parse_answer_table(quoted)
                    self.assertEqual(set(parsed.words), set(words))
                    self.assertEqual(clipboard.puzzle_letters(parsed), (set(letters), {center}))
                    self.assertEqual(parse_word_block(quoted)[0], pangram)
        self.assertEqual(pruner.parse_answers_str(H_TABLE), set(H_WORDS))
        self.assertEqual(pruner.parse_answers_str(P_TABLE), set(P_WORDS))

    def test_invalid_rows(self):
        for text in ['', 'WORD LENGTH', 'GHEE 5', 'GHEE 4\nghee 4',
                     'GHEE 4 extra', 'GHEE 4; touch /tmp/no', 'CAFÉ 4', 'CAT 3']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_answer_table(text)

    def test_invalid_puzzles(self):
        for text in ['GHEE 4', 'GHEE 4 pangram',
                     H_TABLE + '\nZEBRA 5', H_TABLE + '\nWINE 4',
                     H_TABLE + '\nPRACTICAL 9 pangram']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                clipboard.puzzle_letters(parse_answer_table(text))

    def test_ambiguous_center_and_invalid_override(self):
        with patch.object(pruner, 'prompt_user', side_effect=['zz', 'P']) as prompt:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(clipboard.choose_center({'a', 'p'}, None), 'p')
            self.assertEqual(prompt.call_count, 2)
        with self.assertRaises(ValueError):
            clipboard.choose_center({'p'}, 'a')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.dictionary = self.directory / 'words.txt'
        self.original_words = (set(H_WORDS) - {'wheeling'}) | {'hhhh', 'zebra'}
        self.dictionary.write_text('\n'.join(sorted(self.original_words)) + '\n')
        self.dictionary.chmod(0o640)
        self.original = self.dictionary.read_bytes()

    def run_cli(self, *args, text=H_TABLE, response='n'):
        out = io.StringIO()
        with patch.object(clipboard, 'read_clipboard', return_value=text) as read:
            with patch.object(pruner, 'prompt_user', side_effect=response if callable(response) else None,
                              return_value=response) as prompt:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    code = clipboard.main(['--dict', str(self.dictionary), *args])
        self.assertEqual(read.call_count, 1)
        return code, out.getvalue(), prompt.call_count

    def backups(self):
        return list(self.directory.glob('words.txt.bak-*'))

    def test_preview_then_decline(self):
        for args, responses in [(('--dry-run',), 0), ((), 1)]:
            code, output, prompts = self.run_cli(*args)
            self.assertEqual(code, 0)
            self.assertEqual(prompts, responses)
            self.assertIn('Add: 1', output)
            self.assertIn('Remove: 1', output)
            self.assertEqual(self.dictionary.read_bytes(), self.original)
            self.assertEqual(self.backups(), [])

    def test_apply_backup_permissions_and_idempotence(self):
        code, output, prompts = self.run_cli(response='y')
        self.assertEqual((code, prompts), (0, 1))
        self.assertIn('Applied: added 1, removed 1.', output)
        self.assertEqual(pruner.read_words(self.dictionary), set(H_WORDS) | {'zebra'})
        self.assertEqual(stat.S_IMODE(self.dictionary.stat().st_mode), 0o640)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(self.backups()[0].read_bytes(), self.original)
        code, output, prompts = self.run_cli(response='y')
        self.assertEqual((code, prompts), (0, 0))
        self.assertIn('already matches', output)
        self.assertEqual(len(self.backups()), 1)

    def test_invalid_input_never_prompts_or_writes(self):
        code, _, prompts = self.run_cli(text='GHEE 5', response='y')
        self.assertEqual((code, prompts), (1, 0))
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertEqual(self.backups(), [])

    def test_missing_conservative_dictionary_stops(self):
        with self.assertRaises(SystemExit):
            self.run_cli('--conservative', '--system-dict', str(self.directory / 'missing'), response='y')
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertEqual(self.backups(), [])

    def test_conservative_preserves_system_words(self):
        system = self.directory / 'system.txt'
        system.write_text('hhhh\n')
        code, output, _ = self.run_cli('--conservative', '--system-dict', str(system), response='y')
        self.assertEqual(code, 0)
        self.assertIn('Remove: 0', output)
        self.assertEqual(pruner.read_words(self.dictionary), set(H_WORDS) | {'hhhh', 'zebra'})

    def test_changed_dictionary_requires_new_preview(self):
        def change_during_review(message):
            self.dictionary.write_bytes(self.original + b'newword\n')
            return 'y'
        code, output, _ = self.run_cli(response=change_during_review)
        self.assertEqual(code, 1)
        self.assertIn('changed after the preview', output)
        self.assertEqual(self.dictionary.read_bytes(), self.original + b'newword\n')
        self.assertEqual(self.backups(), [])

    def test_failed_backup_prevents_write(self):
        with patch.object(pruner, 'backup_file', side_effect=OSError('backup failed')):
            code, output, _ = self.run_cli(response='y')
        self.assertEqual(code, 1)
        self.assertIn('backup failed', output)
        self.assertEqual(self.dictionary.read_bytes(), self.original)

    def test_failed_replace_preserves_original_and_backup(self):
        with patch.object(pruner.os, 'replace', side_effect=OSError('replace failed')):
            code, _, _ = self.run_cli(response='y')
        self.assertEqual(code, 1)
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertEqual(self.backups()[0].read_bytes(), self.original)
        self.assertEqual(list(self.directory.glob('*.tmp')), [])

    def test_backups_are_unique(self):
        first = pruner.backup_file(self.dictionary)
        second = pruner.backup_file(self.dictionary)
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_answers_override_fakes_and_empty_diff_does_not_fall_back(self):
        self.assertEqual(pruner.compute_changes({'ghee'}, {'ghee'}, {'ghee'}), (set(), set()))
        output = self.directory / 'output.txt'
        output.write_text('ghee\n')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pruner.main([
                '--dict', str(self.dictionary), '--answers-str', 'ghee', '--output', str(output),
                '--fakes', str(self.directory / 'missing'),
            ]), 0)


class ClipboardReadTests(unittest.TestCase):
    def test_reads_data_without_a_shell(self):
        with patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, H_TABLE)) as run:
            self.assertEqual(clipboard.read_clipboard(), H_TABLE)
        self.assertEqual(run.call_args.args[0], ['/usr/bin/pbpaste'])
        self.assertFalse(run.call_args.kwargs.get('shell', False))

    def test_clipboard_failure(self):
        with patch.object(subprocess, 'run', side_effect=FileNotFoundError):
            with self.assertRaises(ValueError):
                clipboard.read_clipboard()


if __name__ == '__main__':
    unittest.main()
