"""Tests for clipboard answer parsing and safe dictionary-pruning workflows."""

import contextlib
import io
import stat
import subprocess
import tempfile
import unittest
from collections.abc import Callable, Sequence
from pathlib import Path
from unittest.mock import patch

from prune import clipboard, pruner
from prune.transform_text import parse_answer_table, parse_word_block


H_WORDS: Sequence[str] = """ghee heel heeling heinie hell henge hewing hewn high hill hilling hinge
hinging neigh neighing nigh weigh weighing whee wheel wheelie wheeling when whew
while whiling whine whinge whingeing whinging whining""".split()
P_WORDS: Sequence[str] = """alpaca apart appall apparat capital capri carp carpal carpi catalpa clap
claptrap clip crap pact pail pair palapa palatal palatial pall palp papa papal papilla
part partial partita pica piccata pill pillar pipit piratic pita pitapat plait plat
practical prat priapic rapt rattrap tapa tapir tarp tilapia tipi trap trip""".split()


def table(words, pangram):
    """Format words as answer-table rows with one marked pangram."""
    return '\n'.join(f'{word.upper()}\t\t{len(word)}' +
                     ('\t\tpangram' if word == pangram else '') for word in words)


H_TABLE = table(H_WORDS, 'wheeling')
P_TABLE = table(P_WORDS, 'practical')
AMBIGUOUS_TABLE = table(['practical', 'capital', 'clap', 'trap'], 'practical')


class TableTests(unittest.TestCase):
    """Check answer-table parsing and puzzle-letter validation."""

    def test_both_supplied_keys_and_surrounding_quotes(self):
        """Parse both sample puzzles with or without surrounding quotes."""
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

    def test_perfect_pangram_label(self):
        """Accept regular and perfect pangram labels in either table format."""
        words = ['clot', 'coil', 'lilt', 'linocut', 'locution']
        tabbed = ('CLOT\t\t4\nCOIL\t\t4\nLILT\t\t4\n'
                  'LINOCUT\t\t7\t\tperfect pangram\nLOCUTION\t\t8\t\tpangram')
        bare = 'CLOT\nCOIL\nLILT\nLINOCUT Perfect  Pangram\nLOCUTION pangram'
        for text in [tabbed, bare]:
            with self.subTest(text=text):
                parsed = parse_answer_table(text)
                self.assertEqual(parsed.words, tuple(words))
                self.assertEqual(parsed.pangrams, frozenset({'linocut', 'locution'}))
                self.assertEqual(clipboard.puzzle_letters(parsed), (set('cilnotu'), {'l'}))
                self.assertEqual(parse_word_block(text)[:2], ['linocut', 'locution'])
                self.assertEqual(pruner.parse_answers_str(text), set(words))
        self.assertEqual(pruner.parse_answers_str('CLOT\nLINOCUT perfect pangram'),
                         {'clot', 'linocut'})

    def test_invalid_rows(self):
        """Reject malformed, duplicate, or inconsistent answer rows."""
        for text in ['', 'WORD LENGTH', 'GHEE 5', 'GHEE 4\nghee 4',
                     'GHEE 4 extra', 'GHEE 4; touch /tmp/no', 'CAFÉ 4', 'CAT 3',
                     'GHEE 4 perfect', 'LINOCUT 7 imperfect pangram']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_answer_table(text)

    def test_invalid_puzzles(self):
        """Reject tables without a valid seven-letter puzzle and center."""
        for text in ['GHEE 4', 'GHEE 4 pangram',
                     H_TABLE + '\nZEBRA 5', H_TABLE + '\nWINE 4',
                     H_TABLE + '\nPRACTICAL 9 pangram']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                clipboard.puzzle_letters(parse_answer_table(text))

    def test_ambiguous_center_and_invalid_override(self):
        """Prompt again for an invalid center and reject a bad override."""
        with patch.object(pruner, 'prompt_user', side_effect=['zz', 'P']) as prompt:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(clipboard.choose_center({'a', 'p'}, None), 'p')
            self.assertEqual(prompt.call_count, 2)
        with self.assertRaises(ValueError):
            clipboard.choose_center({'p'}, 'a')


class WorkflowTests(unittest.TestCase):
    """Exercise clipboard-driven dictionary updates and their safeguards."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.dictionary = self.directory / 'words.txt'
        self.original_words = (set(H_WORDS) - {'wheeling'}) | {'hhhh', 'zebra'}
        self.dictionary.write_text('\n'.join(sorted(self.original_words)) + '\n')
        self.dictionary.chmod(0o640)
        self.original = self.dictionary.read_bytes()

    def run_cli(self, *args, text=H_TABLE,
                response: str | Callable[[str], str] | type[BaseException] = 'n'):
        """Run the CLI with mocked clipboard and prompt, capturing its output."""
        out = io.StringIO()
        with patch.object(clipboard, 'read_clipboard', return_value=text) as read:
            with patch.object(
                pruner, 'prompt_user',
                side_effect=response if callable(response) else None,
                return_value=response,
            ) as prompt:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    code = clipboard.main(['--dict', str(self.dictionary), *args])
        self.assertEqual(read.call_count, 1)
        return code, out.getvalue(), prompt.call_count

    def backups(self):
        """List backups of the temporary dictionary."""
        return list(self.directory.glob('words.txt.bak-*'))

    def test_preview_then_decline(self):
        """Keep the dictionary unchanged for a dry run or declined update."""
        for args, responses in [(('--dry-run',), 0), ((), 1)]:
            code, output, prompts = self.run_cli(*args)
            self.assertEqual(code, 0)
            self.assertEqual(prompts, responses)
            self.assertIn('Add: 1', output)
            self.assertIn('Remove: 1', output)
            self.assertEqual(self.dictionary.read_bytes(), self.original)
            self.assertEqual(self.backups(), [])

    def test_center_option_resolves_ambiguity(self):
        """Use the selected center and reject overrides outside the puzzle."""
        self.dictionary.write_text('carat\n')
        for center, removals in [('p', 0), ('A', 1)]:
            with self.subTest(center=center):
                code, output, prompts = self.run_cli(
                    '--dry-run', '--center', center, text=AMBIGUOUS_TABLE,
                )
                self.assertEqual((code, prompts), (0, 0))
                self.assertIn(f'Center: {center.upper()}', output)
                self.assertIn('Add: 4', output)
                self.assertIn(f'Remove: {removals}', output)
        code, output, prompts = self.run_cli(
            '--center', 'x', text=AMBIGUOUS_TABLE, response='y',
        )
        self.assertEqual((code, prompts), (1, 0))
        self.assertIn('center must be', output)
        self.assertEqual(self.dictionary.read_text(), 'carat\n')
        self.assertEqual(self.backups(), [])

    def test_blank_center_cancels(self):
        """Cancel without writing when no center is selected."""
        code, output, prompts = self.run_cli(
            text=AMBIGUOUS_TABLE, response='',
        )
        self.assertEqual((code, prompts), (1, 1))
        self.assertIn('No center selected', output)
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertEqual(self.backups(), [])

    def test_interrupt_at_confirmation_exits_130(self):
        """Leave the dictionary intact on a confirmation interrupt."""
        code, output, prompts = self.run_cli(response=KeyboardInterrupt)
        self.assertEqual((code, prompts), (130, 1))
        self.assertIn('Cancelled', output)
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertEqual(self.backups(), [])

    def test_apply_backup_permissions_and_idempotence(self):
        """Back up before applying changes and avoid repeat writes."""
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
        """Fail before prompting or writing when clipboard data is invalid."""
        code, _, prompts = self.run_cli(text='GHEE 5', response='y')
        self.assertEqual((code, prompts), (1, 0))
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertEqual(self.backups(), [])

    def test_missing_conservative_dictionary_stops(self):
        """Require an existing system dictionary in conservative mode."""
        with self.assertRaises(SystemExit):
            self.run_cli(
                '--conservative', '--system-dict', str(self.directory / 'missing'),
                response='y',
            )
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertEqual(self.backups(), [])

    def test_conservative_preserves_system_words(self):
        """Preserve system words that would otherwise be removed."""
        system = self.directory / 'system.txt'
        system.write_text('hhhh\n')
        code, output, _ = self.run_cli('--conservative', '--system-dict', str(system), response='y')
        self.assertEqual(code, 0)
        self.assertIn('Remove: 0', output)
        self.assertEqual(pruner.read_words(self.dictionary), set(H_WORDS) | {'hhhh', 'zebra'})

    def test_changed_dictionary_requires_new_preview(self):
        """Refuse to overwrite a dictionary changed after the preview."""
        def change_during_review(_):
            """Simulate a concurrent edit before confirming the update."""
            self.dictionary.write_bytes(self.original + b'newword\n')
            return 'y'
        code, output, _ = self.run_cli(response=change_during_review)
        self.assertEqual(code, 1)
        self.assertIn('changed after the preview', output)
        self.assertEqual(self.dictionary.read_bytes(), self.original + b'newword\n')
        self.assertEqual(self.backups(), [])

    def test_failed_backup_prevents_write(self):
        """Leave the original intact if creating its backup fails."""
        with patch.object(pruner, 'backup_file', side_effect=OSError('backup failed')):
            code, output, _ = self.run_cli(response='y')
        self.assertEqual(code, 1)
        self.assertIn('backup failed', output)
        self.assertEqual(self.dictionary.read_bytes(), self.original)

    def test_failed_replace_preserves_original_and_backup(self):
        """Retain the original and backup when atomic replacement fails."""
        with patch.object(pruner.os, 'replace', side_effect=OSError('replace failed')):
            code, _, _ = self.run_cli(response='y')
        self.assertEqual(code, 1)
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertEqual(self.backups()[0].read_bytes(), self.original)
        self.assertEqual(list(self.directory.glob('*.tmp')), [])

    def test_backups_are_unique(self):
        """Create distinct backup paths without changing their contents."""
        first = pruner.backup_file(self.dictionary)
        second = pruner.backup_file(self.dictionary)
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_answers_override_fakes_and_empty_diff_does_not_fall_back(self):
        """Honor explicit answers even when the fake-word source is missing."""
        self.assertEqual(pruner.compute_changes({'ghee'}, {'ghee'}, {'ghee'}), (set(), set()))
        output = self.directory / 'output.txt'
        output.write_text('ghee\n')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pruner.main([
                '--dict', str(self.dictionary), '--answers-str', 'ghee', '--output', str(output),
                '--fakes', str(self.directory / 'missing'),
            ]), 0)


class ClipboardReadTests(unittest.TestCase):
    """Check clipboard subprocess execution and failure handling."""

    def test_reads_data_without_a_shell(self):
        """Read clipboard text through pbpaste without a shell."""
        with patch.object(
            subprocess, 'run',
            return_value=subprocess.CompletedProcess([], 0, H_TABLE),
        ) as run:
            self.assertEqual(clipboard.read_clipboard(), H_TABLE)
        self.assertEqual(run.call_args.args[0], ['/usr/bin/pbpaste'])
        self.assertFalse(run.call_args.kwargs.get('shell', False))

    def test_clipboard_failure(self):
        """Report a missing clipboard command as invalid input."""
        with patch.object(subprocess, 'run', side_effect=FileNotFoundError):
            with self.assertRaises(ValueError):
                clipboard.read_clipboard()


if __name__ == '__main__':
    unittest.main()
