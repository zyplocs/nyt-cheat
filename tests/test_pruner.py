"""Tests for dictionary-pruning helpers and command-line behavior."""

import contextlib
import io
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

from prune import pruner


class PrunerFunctionTests(unittest.TestCase):
    """Check answer parsing, dictionary I/O, and pruner helpers."""

    def test_parse_answers_str(self):
        """Normalize answer formats while rejecting malformed tables."""
        cases = [
            ('["Ghee","hell"]', {'ghee', 'hell'}),
            ('"ghee"', {'ghee'}),
            ('ghee, hell', {'ghee', 'hell'}),
            ('ghee\nhell', {'ghee', 'hell'}),
            ('  ghee!! (HELL) ', {'ghee', 'hell'}),
            ('12 34', set()),
            ('{"a": 1}', set()),
            ('NaN', {'nan'}),
            ('42', set()),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(pruner.parse_answers_str(text), expected)
        with self.assertRaises(ValueError):
            pruner.parse_answers_str('GHEE 5')

    def test_parse_json_literals_as_words(self):
        """Treat bare JSON keywords as literal candidate words."""
        self.assertEqual(pruner.parse_answers_str('true'), {'true'})
        self.assertEqual(pruner.parse_answers_str('null'), {'null'})

    def test_read_words(self):
        """Normalize word files and report missing or undecodable files."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'words.txt'
            path.write_text('Ghee\n  heel \n\nHILL\n')
            self.assertEqual(pruner.read_words(path), {'ghee', 'heel', 'hill'})
            with self.assertRaises(SystemExit):
                pruner.read_words(root / 'missing')
            invalid = root / 'invalid'
            invalid.write_bytes(b'\xff\xfe\xfa')
            with self.assertRaises(SystemExit):
                pruner.read_words(invalid)

    def test_load_system_words(self):
        """Load system words while tolerating absent optional sources."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'system.txt'
            path.write_text('Ghee\nheel\n')
            self.assertEqual(pruner.load_system_words(None), set())
            self.assertEqual(pruner.load_system_words(root / 'missing'), set())
            self.assertEqual(pruner.load_system_words(path), {'ghee', 'heel'})

    def test_preview(self):
        """Show sorted, bounded preview entries and handle an empty set."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            pruner.preview('Add', {'b', 'a', 'c'}, 2)
        self.assertEqual(stdout.getvalue(), '\nAdd: 3\n  - a\n  - b\n  ... and 1 more\n')
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            pruner.preview('Add', [], 5)
        self.assertEqual(stdout.getvalue(), '\nAdd: 0\n')

    def test_compute_changes(self):
        """Keep official answers while removing only present fake words."""
        self.assertEqual(
            pruner.compute_changes(
                {'ghee', 'hhhh', 'zebra'},
                {'ghee', 'wheeling'},
                {'hhhh', 'ghee', 'notindict'},
            ),
            ({'wheeling'}, {'hhhh'}),
        )

    def test_write_words_atomic(self):
        """Write sorted words atomically with restrictive permissions."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'new' / 'w.txt'
            pruner.write_words_atomic(path, {'b', 'a'})
            self.assertEqual(path.read_text(), 'a\nb\n')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(path.parent.glob('*.tmp')), [])

    def test_prompt_user_terminal(self):
        """Read confirmation from interactive stdin."""
        stdin = Mock()
        stdin.isatty.return_value = True
        with patch.object(pruner.sys, 'stdin', stdin), patch(
            'builtins.input', return_value='y',
        ) as user_input:
            self.assertEqual(pruner.prompt_user('Continue? '), 'y')
        user_input.assert_called_once_with('Continue? ')

    def test_prompt_user_tty_does_not_consume_stdin(self):
        """Use the terminal for prompts without consuming piped input."""
        stdin = io.StringIO('piped answers')
        opened = mock_open(read_data='yes\n')
        with patch.object(pruner.sys, 'stdin', stdin), patch(
            'builtins.open', opened,
        ):
            self.assertEqual(pruner.prompt_user('Continue? '), 'yes')
        self.assertEqual(
            [call.args[:2] for call in opened.call_args_list],
            [('/dev/tty', 'w'), ('/dev/tty', 'r')],
        )
        opened().write.assert_called_with('Continue? ')
        self.assertEqual(stdin.read(), 'piped answers')


class PrunerMainTests(unittest.TestCase):
    """Exercise pruner CLI previews, updates, and failure handling."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dictionary = self.root / 'words.txt'
        self.original_words = {'ghee', 'heel', 'hill', 'hhhh', 'heeling', 'zebra'}
        self.dictionary.write_text('\n'.join(sorted(self.original_words)) + '\n')
        self.original = self.dictionary.read_bytes()
        self.answers = self.root / 'answers.txt'
        self.answers.write_text('ghee\nheel\nhill\nwheeling\n')
        self.fakes = self.root / 'fakes.txt'
        self.fakes.write_text('hhhh\nheeling\nnotindict\n')
        self.data = self.root / 'data'
        self.data.mkdir()
        (self.data / 'answers_111426.txt').write_bytes(self.answers.read_bytes())
        (self.data / 'fakes_111426.txt').write_bytes(self.fakes.read_bytes())

    def run_cli(self, *args, prompt=None, stdin=None):
        """Invoke the pruner with a mocked prompt and captured output."""
        output = io.StringIO()
        input_stream = io.StringIO(stdin) if stdin is not None else pruner.sys.stdin
        prompt_kwargs = (
            {'side_effect': prompt}
            if isinstance(prompt, type) and issubclass(prompt, BaseException)
            else {'return_value': prompt}
        )
        with patch.object(pruner, 'prompt_user', **prompt_kwargs), patch.object(
            pruner.sys, 'stdin', input_stream,
        ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = pruner.main(['--dict', str(self.dictionary), *args])
        return code, output.getvalue()

    def reset(self):
        """Restore the temporary dictionary and clear its backups."""
        self.dictionary.write_bytes(self.original)
        for path in self.root.glob('words.txt.bak-*'):
            path.unlink()

    def test_dry_run_files_and_date(self):
        """Preview file and date-based inputs without changing the dictionary."""
        cases = [
            ('--answers', str(self.answers), '--fakes', str(self.fakes)),
            ('--date', '111426', '--data-dir', str(self.data)),
        ]
        for args in cases:
            with self.subTest(args=args):
                code, output = self.run_cli(*args)
                self.assertEqual(code, 0)
                self.assertIn('Missing true in dict   : 1', output)
                self.assertIn('Removable candidates   : 2', output)
                self.assertIn('Dry-run mode', output)
                self.assertEqual(self.dictionary.read_bytes(), self.original)

    def test_invalid_dates_and_missing_dictionary(self):
        """Reject invalid date tokens and nonexistent dictionaries."""
        for token in ('12345', 'abcdef'):
            with self.subTest(token=token), self.assertRaises(SystemExit) as raised:
                self.run_cli('--date', token, '--data-dir', str(self.data))
            self.assertIn('6 digits', str(raised.exception))
        with self.assertRaises(SystemExit) as raised:
            pruner.main([
                '--dict', str(self.root / 'missing'), '--answers', str(self.answers),
                '--fakes', str(self.fakes), '--data-dir', str(self.data),
            ])
        self.assertIn('dictionary not found', str(raised.exception))

    def test_apply_with_and_without_backup(self):
        """Apply additions and removals with optional backups."""
        expected = {'ghee', 'heel', 'hill', 'wheeling', 'zebra'}
        for backup in (True, False):
            with self.subTest(backup=backup):
                self.reset()
                args = [
                    '--answers', str(self.answers), '--fakes', str(self.fakes),
                    '--apply', '--yes',
                ]
                if backup:
                    args.append('--backup')
                code, output = self.run_cli(*args)
                self.assertEqual(code, 0)
                self.assertEqual(pruner.read_words(self.dictionary), expected)
                self.assertIn('New size : 5', output)
                backups = list(self.root.glob('words.txt.bak-*'))
                self.assertEqual(len(backups), int(backup))
                if backup:
                    self.assertEqual(backups[0].read_bytes(), self.original)

    def test_prompt_responses(self):
        """Accept affirmative replies and abort on refusal or EOF."""
        base = [
            '--answers', str(self.answers), '--fakes', str(self.fakes), '--apply',
        ]
        for response in ('n', '', EOFError):
            with self.subTest(response=response):
                self.reset()
                code, output = self.run_cli(*base, prompt=response)
                self.assertEqual(code, 1)
                self.assertIn('Aborted', output)
                self.assertEqual(self.dictionary.read_bytes(), self.original)
        for response in ('y', ' YES '):
            with self.subTest(response=response):
                self.reset()
                code, _ = self.run_cli(*base, prompt=response)
                self.assertEqual(code, 0)
                self.assertEqual(
                    pruner.read_words(self.dictionary),
                    {'ghee', 'heel', 'hill', 'wheeling', 'zebra'},
                )

    def test_no_add_and_no_remove(self):
        """Honor flags that disable additions or removals independently."""
        cases = [
            ('--no-add', {'ghee', 'heel', 'hill', 'zebra'}),
            ('--no-remove', self.original_words | {'wheeling'}),
        ]
        for flag, expected in cases:
            with self.subTest(flag=flag):
                self.reset()
                code, _ = self.run_cli(
                    '--answers', str(self.answers), '--fakes', str(self.fakes),
                    '--apply', '--yes', flag,
                )
                self.assertEqual(code, 0)
                self.assertEqual(pruner.read_words(self.dictionary), expected)

    def test_conservative(self):
        """Protect system words and require the configured system dictionary."""
        system = self.root / 'system.txt'
        system.write_text('heeling\n')
        code, output = self.run_cli(
            '--answers', str(self.answers), '--fakes', str(self.fakes),
            '--conservative', '--system-dict', str(system), '--apply', '--yes',
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            pruner.read_words(self.dictionary),
            {'ghee', 'heel', 'heeling', 'hill', 'wheeling', 'zebra'},
        )
        self.assertIn('After conservative check: 1', output)
        self.reset()
        with self.assertRaises(SystemExit) as raised:
            self.run_cli(
                '--answers', str(self.answers), '--fakes', str(self.fakes),
                '--conservative', '--system-dict', str(self.root / 'missing'),
                '--apply', '--yes',
            )
        self.assertIn('system dictionary not found', str(raised.exception))
        self.assertEqual(self.dictionary.read_bytes(), self.original)

    def test_nothing_to_change(self):
        """Skip backup and write operations when the diff is empty."""
        code, output = self.run_cli(
            '--answers-str', 'ghee', '--apply', '--yes', '--backup',
        )
        self.assertEqual(code, 0)
        self.assertIn('No changes necessary', output)
        self.assertEqual(list(self.root.glob('words.txt.bak-*')), [])
        self.assertEqual(self.dictionary.read_bytes(), self.original)

    def test_answers_stdin_and_output(self):
        """Combine piped answers with a file of removal candidates."""
        output_path = self.root / 'output.txt'
        output_path.write_text('8 words found:\nghee\nhhhh\nheeling\nhill\n')
        code, output = self.run_cli(
            '--answers-stdin', '--output', str(output_path), '--apply', '--yes',
            stdin='ghee hill wheeling',
        )
        self.assertEqual(code, 0)
        self.assertIn('Bad/Fakes provided     : 2', output)
        self.assertEqual(
            pruner.read_words(self.dictionary),
            {'ghee', 'heel', 'hill', 'wheeling', 'zebra'},
        )

    def test_invalid_answers_table(self):
        """Exit with an argument error for an invalid answer table."""
        with self.assertRaises(SystemExit) as raised:
            self.run_cli('--answers-str', 'GHEE 5')
        self.assertEqual(raised.exception.code, 2)

    def test_script_mode_parses_answer_tables(self):
        """Parse answer tables when running the pruner as a script."""
        result = subprocess.run(
            [sys.executable, pruner.__file__, '--dict', str(self.dictionary),
             '--answers-str', 'GHEE 4\nWHEELING 8 pangram'],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('True answers provided  : 2', result.stdout)
        self.assertIn('Missing true in dict   : 1', result.stdout)
        self.assertEqual(self.dictionary.read_bytes(), self.original)

    def test_show_limit(self):
        """Bound the number of previewed removals."""
        code, output = self.run_cli(
            '--answers', str(self.answers), '--fakes', str(self.fakes), '--show', '1',
        )
        self.assertEqual(code, 0)
        self.assertIn('... and 1 more', output)

    def test_answers_str_precedence(self):
        """Prefer inline answers when an answers file is also supplied."""
        code, output = self.run_cli(
            '--answers-str', 'ghee', '--answers', str(self.answers),
        )
        self.assertEqual(code, 0)
        self.assertIn('Answers   : --answers-str', output)
        self.assertIn('Missing true in dict   : 0', output)


if __name__ == '__main__':
    unittest.main()
