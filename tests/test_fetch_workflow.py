"""Tests for Spelling Bee extraction, fetching, and automated pruning."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from prune import auto, extractor, fetch_sb_answers, pruner


TODAY = {
    'displayWeekday': 'Saturday', 'displayDate': 'November 14, 2026',
    'printDate': '2026-11-14', 'centerLetter': 'h',
    'outerLetters': ['e', 'g', 'i', 'l', 'n', 'w'],
    'validLetters': ['h', 'e', 'g', 'i', 'l', 'n', 'w'],
    'pangrams': ['wheeling'],
    'answers': ['wheeling', 'ghee', 'heel', 'hill', 'hinge', 'when', 'while'],
    'id': 20001, 'freeExpiration': 0, 'editor': 'Sam "Ez}" Ezersky',
}
YESTERDAY = {
    'displayWeekday': 'Friday', 'displayDate': 'November 13, 2026',
    'printDate': '2026-11-13', 'centerLetter': 'p',
    'outerLetters': ['a', 'c', 'i', 'l', 'r', 't'],
    'validLetters': ['p', 'a', 'c', 'i', 'l', 'r', 't'],
    'pangrams': ['practical'],
    'answers': ['practical', 'capital', 'clap', 'pita', 'trap'],
    'id': 20000, 'freeExpiration': 0, 'editor': 'Sam Ezersky',
}
LAST_WEEK = {
    'displayWeekday': 'Friday', 'displayDate': 'November 6, 2026',
    'printDate': '2026-11-06', 'centerLetter': 'c',
    'outerLetters': ['d', 'e', 'i', 't', 'u', 'v'],
    'validLetters': ['c', 'd', 'e', 'i', 't', 'u', 'v'],
    'pangrams': ['deductive'],
    'answers': ['deductive', 'civic', 'cede', 'edict', 'vice'],
    'id': 19993, 'freeExpiration': 0, 'editor': 'Sam Ezersky',
}
GAME_DATA = {
    'today': TODAY,
    'yesterday': YESTERDAY,
    'pastPuzzles': {'thisWeek': [YESTERDAY, TODAY], 'lastWeek': [LAST_WEEK]},
}


def page_html(game_data=None):
    """Embed puzzle data in mock HTML alongside unrelated scripts."""
    return (
        '<html><head><script>window.other = {"x": {"y": 1}};</script></head><body>'
        f'<script type="text/javascript">window.gameData = '
        f'{json.dumps(game_data or GAME_DATA)}</script>'
        '<script>window.after = {"z": "}"};</script></body></html>'
    )


class ExtractorTests(unittest.TestCase):
    """Check puzzle extraction, selection, file writes, and HTTP retrieval."""

    def test_extract_game_data(self):
        """Extract gameData without confusing it with other scripts."""
        self.assertEqual(extractor.extract_game_data(page_html()), GAME_DATA)

    def test_extract_game_data_errors(self):
        """Report missing or malformed embedded puzzle data."""
        for html in [
            'no data here',
            '<script>window.gameData</script><script>x = {}</script>',
            '<script>window.gameData = null;</script> {}',
            'window.gameData = {"a": {"b": 1}',
            'window.gameData = {"a": "}',
            'window.gameData = {a: 1}</script>',
        ]:
            with self.subTest(html=html), self.assertRaises(extractor.SpellingBeeDataError):
                extractor.extract_game_data(html)

    def test_find_matching_json_object_end(self):
        """Ignore braces in JSON strings and reject non-object starts."""
        text = '{"a": "}", "b": {"c": "q\\"}"}} trailing }'
        end = extractor.find_matching_json_object_end(text, 0)
        expected = '{"a": "}", "b": {"c": "q\\"}"}}'
        self.assertEqual(text[:end + 1], expected)
        self.assertEqual(json.loads(text[:end + 1]), {'a': '}', 'b': {'c': 'q"}'}})
        with self.assertRaises(ValueError):
            extractor.find_matching_json_object_end(text, 1)

    def test_puzzle_from_dict(self):
        """Normalize case and optional metadata when building a puzzle."""
        data = {
            **TODAY, 'centerLetter': 'H',
            'outerLetters': [letter.upper() for letter in TODAY['outerLetters']],
            'validLetters': [letter.upper() for letter in TODAY['validLetters']],
            'answers': [word.upper() for word in TODAY['answers']],
            'pangrams': ['WHEELING'], 'id': '123',
        }
        puzzle = extractor.puzzle_from_dict(data)
        self.assertEqual(puzzle.center_letter, 'h')
        self.assertEqual(puzzle.outer_letters, TODAY['outerLetters'])
        self.assertEqual(puzzle.valid_letters, TODAY['validLetters'])
        self.assertEqual(puzzle.answers, TODAY['answers'])
        self.assertEqual(puzzle.pangrams, TODAY['pangrams'])
        self.assertEqual(puzzle.puzzle_id, 123)
        data = {key: value for key, value in TODAY.items() if key not in {'id', 'editor'}}
        puzzle = extractor.puzzle_from_dict(data)
        self.assertIsNone(puzzle.puzzle_id)
        self.assertIsNone(puzzle.editor)

    def test_puzzle_from_dict_errors(self):
        """Reject missing answer fields and answers of the wrong type."""
        data = {key: value for key, value in TODAY.items() if key not in {'answers', 'pangrams'}}
        with self.assertRaises(extractor.SpellingBeeDataError) as raised:
            extractor.puzzle_from_dict(data)
        self.assertIn('answers, pangrams', str(raised.exception))
        with self.assertRaises(extractor.SpellingBeeDataError):
            extractor.puzzle_from_dict({**TODAY, 'answers': 'ghee'})

    def test_puzzle_properties_and_lists(self):
        """Expose formatted puzzle details and deduplicate dated listings."""
        puzzle = extractor.puzzle_from_dict(TODAY)
        self.assertEqual(puzzle.date_token, '111426')
        self.assertEqual(puzzle.letters_string, 'hegilnw')
        self.assertEqual(len(extractor.iter_puzzle_dicts(GAME_DATA)), 5)
        self.assertEqual(
            [item.print_date for item in extractor.list_puzzles(GAME_DATA)],
            ['2026-11-06', '2026-11-13', '2026-11-14'],
        )

    def test_find_puzzle(self):
        """Resolve relative and explicit dates or report unavailable puzzles."""
        cases = [
            ('today', '2026-11-14'),
            (' Yesterday ', '2026-11-13'),
            ('111326', '2026-11-13'),
            ('2026-11-06', '2026-11-06'),
        ]
        for selector, expected in cases:
            with self.subTest(selector=selector):
                self.assertEqual(
                    extractor.find_puzzle(GAME_DATA, selector).print_date,
                    expected,
                )
        with self.assertRaises(extractor.SpellingBeeDataError) as raised:
            extractor.find_puzzle(GAME_DATA, '2026-01-01')
        self.assertIn('2026-11-06, 2026-11-13, 2026-11-14', str(raised.exception))
        for data, selector in [({}, 'today'), (GAME_DATA, 'tomorrow')]:
            with self.subTest(selector=selector), self.assertRaises(extractor.SpellingBeeDataError):
                extractor.find_puzzle(data, selector)

    def test_normalize_date_selector(self):
        """Accept six-digit and ISO dates but reject invalid selectors."""
        self.assertEqual(extractor.normalize_date_selector('111426'), '2026-11-14')
        self.assertEqual(extractor.normalize_date_selector('2026-11-14'), '2026-11-14')
        for selector in ('nope', '2026-13-01'):
            with self.subTest(selector=selector), self.assertRaises(extractor.SpellingBeeDataError):
                extractor.normalize_date_selector(selector)

    def test_normalize_invalid_six_digit_selector(self):
        """Reject an impossible six-digit date."""
        with self.assertRaises(extractor.SpellingBeeDataError):
            extractor.normalize_date_selector('999999')

    def test_write_word_file(self):
        """Normalize, order, and safely overwrite word files."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'a' / 'b' / 'w.txt'
            self.assertEqual(
                extractor.write_word_file(path, ['Hill', ' ghee ', '', 'hill', 'heel']),
                path,
            )
            self.assertEqual(path.read_text(), 'ghee\nheel\nhill\n')
            ordered = root / 'ordered.txt'
            extractor.write_word_file(
                ordered, ['Wheeling', 'ghee', 'wheeling', '', 'heel'],
                preserve_order=True,
            )
            self.assertEqual(ordered.read_text(), 'wheeling\nghee\nheel\n')
            empty = root / 'empty.txt'
            extractor.write_word_file(empty, [])
            self.assertEqual(empty.read_text(), '')
            self.assertEqual(
                extractor.write_word_file(path, ['ghee', 'heel', 'hill'], overwrite=False),
                path,
            )
            with self.assertRaises(FileExistsError):
                extractor.write_word_file(path, ['other'])
            self.assertEqual(path.read_text(), 'ghee\nheel\nhill\n')
            extractor.write_word_file(path, ['other'], overwrite=True)
            self.assertEqual(path.read_text(), 'other\n')

    def test_write_answers_file(self):
        """Name and populate a dated answers file."""
        with tempfile.TemporaryDirectory() as directory:
            path = extractor.write_answers_file(
                extractor.puzzle_from_dict(TODAY), Path(directory),
            )
            self.assertEqual(path.name, 'answers_111426.txt')
            self.assertEqual(path.read_text(), '\n'.join(TODAY['answers']) + '\n')

    def test_fetch_html(self):
        """Decode HTTP content using its declared charset or UTF-8."""
        class Response:
            """Mimic a context-managed HTTP response for fetch tests."""

            def __init__(self, data, charset):
                self.data = data
                self.headers = Mock()
                self.headers.get_content_charset.return_value = charset

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                """Return the encoded response content."""
                return self.data

        for data, charset, expected in [
            ('café'.encode('latin-1'), 'latin-1', 'café'),
            ('café'.encode(), None, 'café'),
        ]:
            with self.subTest(charset=charset), patch.object(
                extractor, 'urlopen', return_value=Response(data, charset),
            ) as urlopen:
                self.assertEqual(
                    extractor.fetch_html('https://example.test/x', timeout=7),
                    expected,
                )
                request = urlopen.call_args.args[0]
                self.assertEqual(request.full_url, 'https://example.test/x')
                self.assertTrue(request.get_header('User-agent'))
                self.assertEqual(urlopen.call_args.kwargs['timeout'], 7)

    def test_fetch_html_errors(self):
        """Translate HTTP, network, and timeout failures to fetch errors."""
        errors = [
            (HTTPError('https://example.test', 403, 'Forbidden', None, None), '403'),
            (URLError('dns'), 'dns'),
            (TimeoutError(), 'timed out'),
        ]
        for error, message in errors:
            with self.subTest(error=error), patch.object(
                extractor, 'urlopen', side_effect=error,
            ), self.assertRaises(extractor.SpellingBeeFetchError) as raised:
                extractor.fetch_html('https://example.test')
            self.assertIn(message, str(raised.exception))
            if isinstance(error, HTTPError):
                error.close()

    def test_load_game_data(self):
        """Prefer local HTML and fetch from the URL when no file is given."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'page.html'
            path.write_text(page_html())
            with patch.object(extractor, 'fetch_html') as fetch:
                self.assertEqual(extractor.load_game_data(html_path=path), GAME_DATA)
            fetch.assert_not_called()
        with patch.object(extractor, 'fetch_html', return_value=page_html()) as fetch:
            self.assertEqual(
                extractor.load_game_data(url='https://example.test/x'), GAME_DATA,
            )
        fetch.assert_called_once_with('https://example.test/x')


class FetchAnswersTests(unittest.TestCase):
    """Check answer-fetch CLI output, file writes, and errors."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.html = self.root / 'page.html'
        self.html.write_text(page_html())
        self.data = self.root / 'data'

    def run_main(self, *args):
        """Run the fetch command against temporary HTML and output paths."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = fetch_sb_answers.main([
                *args, '--html', str(self.html), '--data-dir', str(self.data),
            ])
        return code, stdout.getvalue()

    def test_list(self):
        """List available dates in order without creating files."""
        code, output = self.run_main('--list')
        self.assertEqual(code, 0)
        positions = [output.index(date) for date in (
            '2026-11-06', '2026-11-13', '2026-11-14',
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertFalse(self.data.exists())

    def test_stdout(self):
        """Print selected puzzle answers without writing to disk."""
        code, output = self.run_main('yesterday', '--stdout')
        self.assertEqual(code, 0)
        self.assertEqual(output, 'practical\ncapital\nclap\npita\ntrap\n')
        self.assertFalse(self.data.exists())

    def test_write_force_and_identical(self):
        """Reuse matching files and require force to replace stale answers."""
        code, output = self.run_main()
        self.assertEqual(code, 0)
        path = self.data / 'answers_111426.txt'
        expected = '\n'.join(TODAY['answers']) + '\n'
        self.assertEqual(path.read_text(), expected)
        self.assertIn('Token    : 111426', output)
        self.assertIn('Answers  : 7', output)
        self.assertEqual(self.run_main()[0], 0)
        path.write_text('junk\n')
        with self.assertRaises(FileExistsError):
            self.run_main()
        self.assertEqual(path.read_text(), 'junk\n')
        self.assertEqual(self.run_main('--force')[0], 0)
        self.assertEqual(path.read_text(), expected)

    def test_cli_errors(self):
        """Render selection and fetch errors to stderr with a failing code."""
        stderr = io.StringIO()
        argv = [
            'fetch', 'tomorrow', '--html', str(self.html),
            '--data-dir', str(self.data),
        ]
        with patch.object(fetch_sb_answers.sys, 'argv', argv), contextlib.redirect_stderr(stderr):
            self.assertEqual(fetch_sb_answers.cli(), 1)
        self.assertTrue(stderr.getvalue().startswith('Error:'))
        stderr = io.StringIO()
        argv = [
            'fetch', '--html', str(self.html), '--data-dir', str(self.data),
        ]
        with patch.object(fetch_sb_answers.sys, 'argv', argv), patch.object(
            fetch_sb_answers, 'load_game_data',
            side_effect=extractor.SpellingBeeFetchError('boom'),
        ), contextlib.redirect_stderr(stderr):
            self.assertEqual(fetch_sb_answers.cli(), 1)
        self.assertIn('boom', stderr.getvalue())


class AutoTests(unittest.TestCase):
    """Check the automated workflow and its pruner integration."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.html = self.root / 'page.html'
        self.html.write_text(page_html())
        self.data = self.root / 'data'
        self.dictionary = self.root / 'words.txt'
        self.original_words = {
            'ghee', 'heel', 'hill', 'hinge', 'when', 'while', 'hhhh',
            'heeling', 'zebra', 'glen', 'gel',
        }
        self.dictionary.write_text('\n'.join(sorted(self.original_words)) + '\n')
        self.original = self.dictionary.read_bytes()
        self.common = [
            'today', '--html', str(self.html), '--data-dir', str(self.data),
            '--dict', str(self.dictionary),
        ]

    def run_main(self, *args):
        """Run the auto command against the temporary puzzle and dictionary."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = auto.main([*self.common, *args])
        return code, stdout.getvalue()

    def test_generate_candidates(self):
        """Select dictionary words compatible with the puzzle letters."""
        self.assertEqual(
            auto.generate_candidates(extractor.puzzle_from_dict(TODAY), self.dictionary),
            ['ghee', 'heel', 'heeling', 'hhhh', 'hill', 'hinge', 'when', 'while'],
        )

    def test_no_pruner(self):
        """Write dated answers, candidates, and fakes without pruning."""
        code, output = self.run_main('--no-pruner')
        self.assertEqual(code, 0)
        self.assertEqual(
            (self.data / 'answers_111426.txt').read_text(),
            '\n'.join(TODAY['answers']) + '\n',
        )
        self.assertEqual(
            (self.data / 'output_111426.txt').read_text(),
            'ghee\nheel\nheeling\nhhhh\nhill\nhinge\nwhen\nwhile\n',
        )
        self.assertEqual((self.data / 'fakes_111426.txt').read_text(), 'heeling\nhhhh\n')
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertIn('Fake words : 2', output)
        self.assertIn('Missing    : 1', output)
        self.assertIn('Next dry-run command', output)

    def test_pruner_dry_run(self):
        """Preview pruning by default without changing the dictionary."""
        code, output = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn('Dry-run mode', output)
        self.assertEqual(self.dictionary.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob('words.txt.bak-*')), [])

    def test_apply_with_and_without_backup(self):
        """Apply dictionary changes with a backup unless disabled."""
        expected = {
            'ghee', 'heel', 'hill', 'hinge', 'when', 'while', 'wheeling',
            'zebra', 'glen', 'gel',
        }
        code, _ = self.run_main('--apply', '--yes')
        self.assertEqual(code, 0)
        self.assertEqual(pruner.read_words(self.dictionary), expected)
        backups = list(self.root.glob('words.txt.bak-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.original)
        self.dictionary.write_bytes(self.original)
        for path in backups:
            path.unlink()
        self.data.mkdir(exist_ok=True)
        code, _ = self.run_main('--apply', '--yes', '--no-backup')
        self.assertEqual(code, 0)
        self.assertEqual(pruner.read_words(self.dictionary), expected)
        self.assertEqual(list(self.root.glob('words.txt.bak-*')), [])

    def test_no_remove_and_no_add(self):
        """Honor flags that separately disable removals and additions."""
        cases = [
            (['--apply', '--yes', '--no-remove'], self.original_words | {'wheeling'}),
            (['--apply', '--yes', '--no-add'], self.original_words - {'hhhh', 'heeling'}),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.dictionary.write_bytes(self.original)
                for path in self.root.glob('words.txt.bak-*'):
                    path.unlink()
                code, _ = self.run_main(*args, '--no-backup')
                self.assertEqual(code, 0)
                self.assertEqual(pruner.read_words(self.dictionary), expected)

    def test_apply_requires_pruner_before_writes(self):
        """Reject applying with pruning disabled before writing files."""
        with self.assertRaises(ValueError):
            self.run_main('--apply', '--no-pruner')
        self.assertFalse(self.data.exists())

    def test_existing_fakes_requires_force(self):
        """Refuse to overwrite stale fake-word output without force."""
        self.data.mkdir()
        path = self.data / 'fakes_111426.txt'
        path.write_text('stale\n')
        with self.assertRaises(FileExistsError):
            self.run_main('--no-pruner')
        self.assertEqual(path.read_text(), 'stale\n')
        self.assertEqual(self.run_main('--no-pruner', '--force')[0], 0)
        self.assertEqual(path.read_text(), 'heeling\nhhhh\n')

    def test_show_limit(self):
        """Limit the fake-word preview to the requested count."""
        code, output = self.run_main('--no-pruner', '--show', '1')
        self.assertEqual(code, 0)
        self.assertIn('... and 1 more', output)

    def test_run_pruner_argv(self):
        """Forward only the selected command flags to the pruner."""
        puzzle = extractor.puzzle_from_dict(TODAY)
        cases = [
            (
                dict(apply=False, yes=True, backup=True, conservative=False,
                     no_add=False, no_remove=False),
                {'--date', '111426', '--data-dir', str(self.data), '--dict',
                 str(self.dictionary), '--show', '3'},
                {'--apply', '--yes', '--backup'},
            ),
            (
                dict(apply=True, yes=True, backup=True, conservative=True,
                     no_add=True, no_remove=True),
                {'--apply', '--yes', '--backup', '--conservative', '--no-add', '--no-remove'},
                set(),
            ),
            (
                dict(apply=True, yes=False, backup=False, conservative=False,
                     no_add=False, no_remove=False),
                {'--apply'},
                {'--yes', '--backup'},
            ),
        ]
        for kwargs, present, absent in cases:
            with self.subTest(kwargs=kwargs), patch.object(
                auto.pruner, 'main', return_value=7,
            ) as main:
                self.assertEqual(auto.run_pruner(
                    puzzle=puzzle, data_dir=self.data, dictionary=self.dictionary,
                    show=3, **kwargs,
                ), 7)
                argv = main.call_args.args[0]
                for item in present:
                    self.assertIn(item, argv)
                for item in absent:
                    self.assertNotIn(item, argv)

    def test_cli_error(self):
        """Report conflicting auto flags on stderr."""
        stderr = io.StringIO()
        argv = [
            'auto', '--apply', '--no-pruner', '--html', str(self.html),
            '--data-dir', str(self.data), '--dict', str(self.dictionary),
        ]
        with patch.object(auto.sys, 'argv', argv), contextlib.redirect_stderr(stderr):
            self.assertEqual(auto.cli(), 1)
        self.assertIn('Error:', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
