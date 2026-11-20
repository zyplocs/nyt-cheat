import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spelling_bee
import wordle


class SpellingBeeTests(unittest.TestCase):
    def setUp(self):
        self.words = {'ghee', 'heel', 'hill', 'wheeling', 'glen', 'hen', 'zebra', 'hhhh'}
        self.allowed = set('eghilnw')

    def test_filter_words(self):
        for minimum, expected in [
            (4, ['ghee', 'heel', 'hhhh', 'hill', 'wheeling']),
            (3, ['ghee', 'heel', 'hen', 'hhhh', 'hill', 'wheeling']),
            (5, ['wheeling']),
            (9, []),
        ]:
            with self.subTest(minimum=minimum):
                self.assertEqual(
                    spelling_bee.filter_words(self.words, self.allowed, 'h', minimum),
                    expected,
                )

    def test_load_words(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'words.txt'
            path.write_text('Ghee\n  heel \n\nHILL\nghee\n')
            for module in (spelling_bee, wordle):
                with self.subTest(module=module.__name__):
                    self.assertEqual(module.load_words(path), {'ghee', 'heel', 'hill'})
                    with self.assertRaises(SystemExit):
                        module.load_words(Path(directory) / 'missing')

    def test_main_output_and_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'words.txt'
            output = Path(directory) / 'out.txt'
            path.write_text('Ghee\nheel\n\nHILL\nwheeling\nglen\nhen\nzebra\n')
            expected = '4 words found:\nghee\nheel\nhill\nwheeling\n'
            for extra in ([], ['-o', str(output)]):
                with self.subTest(extra=extra), patch.object(
                    spelling_bee.sys, 'argv',
                    ['spelling_bee.py', 'EGHILNW', 'H', '-d', str(path), *extra],
                ):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        spelling_bee.main()
                    self.assertEqual(stdout.getvalue(), expected)
            self.assertEqual(output.read_text(), 'ghee\nheel\nhill\nwheeling\n')

    def test_main_minimum_length(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'words.txt'
            path.write_text('Ghee\nheel\nHILL\nwheeling\nglen\nhen\nzebra\n')
            with patch.object(
                spelling_bee.sys, 'argv',
                ['spelling_bee.py', 'eghilnw', 'h', '-m', '3', '-d', str(path)],
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    spelling_bee.main()
            self.assertIn('5 words found:', stdout.getvalue())
            self.assertIn('\nhen\n', stdout.getvalue())

    def test_main_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'words.txt'
            path.write_text('ghee\n')
            cases = [
                ['eghilnw', 'z', '-d', str(path)],
                ['eghilnw', 'h', '-d', str(path), '-o', directory],
                ['eghilnw', 'h', '-d', str(Path(directory) / 'missing')],
            ]
            for args in cases:
                with self.subTest(args=args), patch.object(
                    spelling_bee.sys, 'argv', ['spelling_bee.py', *args],
                ), self.assertRaises(SystemExit) as raised:
                    spelling_bee.main()
                self.assertIsInstance(raised.exception.code, str)


class WordleTests(unittest.TestCase):
    def setUp(self):
        self.words = ['tacit', 'tarot', 'taunt', 'toast', 'treat', 'stats', 'cabin', 'tilt']

    def test_filter_words(self):
        cases = [
            ({'word_length': 5}, sorted(set(self.words) - {'tilt'})),
            ({}, sorted(self.words)),
            ({'word_length': 5, 'specific_positions': {0: 't', 4: 't'}},
             ['tacit', 'tarot', 'taunt', 'toast', 'treat']),
            ({'include_letters': 'ar'}, ['tarot', 'treat']),
            ({'exclude_letters': 's'}, sorted(set(self.words) - {'toast', 'stats'})),
            ({'word_length': 5, 'specific_positions': {0: 't'},
              'include_letters': 'a', 'exclude_letters': 'so'},
             ['tacit', 'taunt', 'treat']),
        ]
        for kwargs, expected in cases:
            with self.subTest(kwargs=kwargs):
                self.assertEqual(wordle.filter_words(self.words, **kwargs), expected)

    def test_positions_past_end_are_ignored(self):
        self.assertEqual(
            wordle.filter_words(['ab', 'abc'], specific_positions={2: 'c'}),
            ['ab', 'abc'],
        )

    def test_generator_and_empty_iterable(self):
        self.assertEqual(
            wordle.filter_words((word for word in self.words), word_length=4),
            ['tilt'],
        )
        self.assertEqual(wordle.filter_words([]), [])

    def test_main(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'words.txt'
            path.write_text('Tacit\ntarot\ntaunt\ntoast\ntreat\nstats\ncabin\ntilt\n')
            cases = [
                (['-d', str(path), '-p', '0:T', '-p', '4:t', '-i', 'A', '-x', 'S'],
                 'tacit\ntarot\ntaunt\ntreat\n'),
                (['-d', str(path), '-l', '4'], 'tilt\n'),
                (['-d', str(path), '-i', 'z'], 'No matching words found.\n'),
            ]
            for args, expected in cases:
                with self.subTest(args=args), patch.object(
                    wordle.sys, 'argv', ['wordle.py', *args],
                ):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        wordle.main()
                    self.assertEqual(stdout.getvalue(), expected)

    def test_main_invalid_positions_and_missing_dictionary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'words.txt'
            path.write_text('tacit\n')
            for spec in ('t', 'x:t', '0:t:x'):
                with self.subTest(spec=spec), patch.object(
                    wordle.sys, 'argv', ['wordle.py', '-d', str(path), '-p', spec],
                ), self.assertRaises(SystemExit) as raised:
                    wordle.main()
                self.assertIn('Invalid --position', str(raised.exception))
            with patch.object(
                wordle.sys, 'argv',
                ['wordle.py', '-d', str(Path(directory) / 'missing')],
            ), self.assertRaises(SystemExit):
                wordle.main()


if __name__ == '__main__':
    unittest.main()
