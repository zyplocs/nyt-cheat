import curses
import tempfile
import unittest
from pathlib import Path
from unittest.mock import DEFAULT, Mock, patch

import spelling_bee

with patch.object(spelling_bee, 'load_words', return_value=set()):
    import tui_spelling_bee
import tui_wordle


class FakeScreen:
    def __init__(self, keys=(), lines=(), size=(24, 80)):
        self.keys, self.lines, self.size, self.writes = iter(keys), iter(lines), size, []

    def _next(self, source):
        item = next(source)
        if isinstance(item, BaseException):
            raise item
        return item

    def getch(self):
        key = self._next(self.keys)
        return ord(key) if isinstance(key, str) else key

    def getstr(self):
        return self._next(self.lines)

    def getmaxyx(self):
        return self.size

    def addstr(self, y, x, text, attr=0):
        rows, cols = self.size
        if not (0 <= y < rows and 0 <= x < cols):
            raise curses.error('addstr out of bounds')
        self.writes.append((y, x, text[:cols - x], attr))

    def erase(self):
        self.writes.clear()

    clear = erase

    def refresh(self):
        pass

    def keypad(self, flag):
        pass

    def nodelay(self, flag):
        pass

    def clrtoeol(self):
        pass

    def row(self, y):
        cells = {}
        for wy, x, text, _ in self.writes:
            if wy == y:
                cells.update({x + i: char for i, char in enumerate(text)})
        return ''.join(cells.get(i, ' ') for i in range(max(cells, default=-1) + 1))

    def attr_of(self, text):
        return next(attr for _, _, written, attr in self.writes if written == text)


def run_tui(module, screen):
    with patch.multiple(
        curses, curs_set=DEFAULT, mousemask=DEFAULT, echo=DEFAULT, noecho=DEFAULT,
    ), patch.object(curses, 'has_colors', return_value=False):
        module.main(screen)


class FieldTests(unittest.TestCase):
    def test_wordle_field_validation(self):
        field = tui_wordle.Field('x', 0, 5, '', 'length')
        self.assertTrue(field.add_char('2'))
        self.assertFalse(field.add_char('a'))
        self.assertFalse(field.add_char('1'))
        self.assertTrue(field.add_char('0'))
        self.assertEqual(field.value, '20')
        field = tui_wordle.Field('x', 0, 5, '', 'pattern')
        self.assertTrue(field.add_char('T'))
        self.assertTrue(field.add_char('_'))
        self.assertFalse(field.add_char('5'))
        self.assertFalse(field.add_char('-'))
        self.assertEqual(field.value, 't_')
        for field_type in ('include', 'exclude'):
            with self.subTest(field_type=field_type):
                field = tui_wordle.Field('x', 0, 5, '', field_type)
                self.assertTrue(field.add_char('a'))
                self.assertFalse(field.add_char('A'))
                self.assertTrue(field.add_char('b'))
                self.assertFalse(field.add_char('1'))
                self.assertEqual(field.value, 'ab')
        field = tui_wordle.Field('x', 0, 5)
        self.assertTrue(field.add_char('!'))
        field = tui_wordle.Field('x', 0, 3, '', 'pattern')
        self.assertTrue(field.add_char('a'))
        self.assertTrue(field.add_char('b'))
        self.assertFalse(field.add_char('c'))
        field.backspace()
        self.assertEqual(field.value, 'a')
        field.clear()
        field.backspace()
        self.assertEqual(field.value, '')
        field.add_char('a')
        field.clear()
        self.assertEqual(field.value, '')

    def test_spelling_bee_field_validation(self):
        field = tui_spelling_bee.Field('x', 0, 5, '', 'letters')
        self.assertTrue(field.add_char('a'))
        self.assertFalse(field.add_char('A'))
        self.assertFalse(field.add_char('1'))
        self.assertTrue(field.add_char('B'))
        self.assertEqual(field.value, 'ab')
        field = tui_spelling_bee.Field('x', 0, 2, '', 'required')
        for char in ('a', 'B', '1'):
            field.add_char(char)
        self.assertEqual(len(field.value), 1)
        self.assertTrue(field.value.islower())
        field = tui_spelling_bee.Field('x', 0, 3, '', 'minlen')
        self.assertTrue(field.add_char('1'))
        self.assertFalse(field.add_char('x'))
        self.assertTrue(field.add_char('2'))
        self.assertFalse(field.add_char('3'))
        self.assertEqual(field.value, '12')

    def test_is_pangram(self):
        allowed = set('eghilnw')
        self.assertTrue(tui_spelling_bee.is_pangram('wheeling', allowed))
        self.assertFalse(tui_spelling_bee.is_pangram('heel', allowed))
        self.assertFalse(tui_spelling_bee.is_pangram('wheelings', allowed))

    def test_field_render(self):
        palette = {'normal': 1, 'focus': 2, 'editing': 4}
        for module in (tui_wordle, tui_spelling_bee):
            with self.subTest(module=module.__name__):
                screen = FakeScreen(size=(5, 40))
                field = module.Field('Pat:', 3, 6, 'ab', 'text', palette)
                field.render(screen, 2, focused=False)
                self.assertEqual(
                    screen.writes,
                    [(2, 3, 'Pat:', 0), (2, 8, 'ab   ', 1)],
                )
                screen.writes.clear()
                field.render(screen, 2, focused=True)
                self.assertEqual(screen.writes[1][3], 2)
                screen.writes.clear()
                field.render(screen, 2, focused=True, editing=True)
                self.assertEqual(screen.writes[1], (2, 8, 'ab    ', 4))
                screen.writes.clear()
                field.render(screen, 9, focused=False)
                self.assertEqual(screen.writes, [])
                field = module.Field('Pat:', 38, 6, 'ab', 'text', palette)
                field.render(screen, 2, focused=False)
                self.assertEqual(screen.writes, [(2, 38, 'P', 0)])
                broken = Mock()
                broken.getmaxyx.return_value = (5, 40)
                broken.addstr.side_effect = curses.error('x')
                field.render(broken, 2, focused=False)


class ColorTests(unittest.TestCase):
    def test_no_colors(self):
        for module in (tui_wordle, tui_spelling_bee):
            with self.subTest(module=module.__name__), patch.object(
                curses, 'has_colors', return_value=False,
            ), patch.object(curses, 'start_color') as start:
                palette = module.init_colors()
                self.assertEqual(palette['error'], curses.A_BOLD)
                start.assert_not_called()

    def test_colors(self):
        for module in (tui_wordle, tui_spelling_bee):
            with self.subTest(module=module.__name__), patch.object(
                curses, 'has_colors', return_value=True,
            ), patch.object(curses, 'start_color'), patch.object(
                curses, 'use_default_colors',
            ), patch.object(curses, 'init_pair') as init_pair, patch.object(
                curses, 'color_pair', side_effect=lambda number: number << 8,
            ):
                palette = module.init_colors()
                self.assertEqual(
                    palette['error'],
                    curses.A_BOLD | (module.PAIR.ERROR << 8),
                )
                self.assertEqual(
                    palette['editing'],
                    curses.A_REVERSE | curses.A_BOLD | (module.PAIR.FOCUS << 8),
                )
                self.assertEqual(init_pair.call_count, 4)
                self.assertTrue(all(call.args[2] == -1 for call in init_pair.call_args_list))

    def test_default_color_failure(self):
        for module in (tui_wordle, tui_spelling_bee):
            with self.subTest(module=module.__name__), patch.object(
                curses, 'has_colors', return_value=True,
            ), patch.object(curses, 'start_color'), patch.object(
                curses, 'use_default_colors', side_effect=curses.error('x'),
            ), patch.object(curses, 'init_pair') as init_pair, patch.object(
                curses, 'color_pair', return_value=0,
            ):
                module.init_colors()
                self.assertTrue(
                    all(call.args[2] == curses.COLOR_BLACK for call in init_pair.call_args_list),
                )

    def test_start_color_failure(self):
        for module in (tui_wordle, tui_spelling_bee):
            with self.subTest(module=module.__name__), patch.object(
                curses, 'has_colors', return_value=True,
            ), patch.object(
                curses, 'start_color', side_effect=curses.error('x'),
            ):
                self.assertEqual(module.init_colors()['help'], curses.A_BOLD)


class WordleTuiTests(unittest.TestCase):
    WORDS = 'cabin\nHELLO\nquiet\nstats\ntacit\ntarot\ntaunt\ntilt\ntoast\nTREAT\n'
    EMPTY = [b'', b'', b'', b'']

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'words.txt'
        self.path.write_text(self.WORDS)

    def run_case(self, keys, lines=None, size=(24, 80), path=None):
        screen = FakeScreen(
            keys=keys, lines=self.EMPTY if lines is None else lines, size=size,
        )
        with patch.object(tui_wordle, 'DATASET_PATH', path or self.path):
            run_tui(tui_wordle, screen)
        return screen

    def test_initial_results(self):
        screen = self.run_case(['q'])
        self.assertEqual(screen.row(3), '9 candidates found')
        self.assertEqual(screen.row(4).strip(), 'cabin')
        self.assertEqual(screen.row(12).strip(), 'treat')
        self.assertTrue(screen.row(0).startswith(tui_wordle.HELP_BAR))

    def test_initial_filters(self):
        screen = self.run_case(
            ['q'], [b'5', b'T___T', b'A', b'S'],
        )
        self.assertEqual(screen.row(3), '4 candidates found')
        self.assertEqual(
            [screen.row(row).strip() for row in range(4, 8)],
            ['tacit', 'tarot', 'taunt', 'treat'],
        )
        self.assertIn('Pattern: t___t', screen.row(2))

    def test_initial_errors(self):
        cases = [
            (
                [b'5', b't_t', b'', b''],
                "Error: Pattern length (3) doesn't match word length (5)",
            ),
            (
                [b'', b'', b'at', b'ta'],
                "Error: Letters can't be both included and excluded: a, t",
            ),
        ]
        for lines, expected in cases:
            with self.subTest(lines=lines):
                screen = self.run_case(['q'], lines)
                self.assertEqual(screen.row(3), expected)
                self.assertFalse(any('candidates found' in screen.row(row) for row in range(24)))

    def test_prompt_initial_params(self):
        cases = [
            ([b'99', b'', b'', b''], (20, '', '', '')),
            ([b'0', b'', b'', b''], (1, '', '', '')),
            ([b'abc', b'', b'', b''], (5, '', '', '')),
            ([b' 7 ', b' Ab_ ', b' XY ', b' Q '], (7, 'ab_', 'xy', 'q')),
        ]
        for lines, expected in cases:
            with self.subTest(lines=lines), patch.object(curses, 'echo'), patch.object(
                curses, 'noecho',
            ):
                self.assertEqual(
                    tui_wordle.prompt_initial_params(FakeScreen(lines=lines)),
                    expected,
                )

    def test_typing_pattern(self):
        screen = self.run_case([9, ' ', 't', '_', '_', '5', '_', 't', 10, 10, 'q'])
        self.assertIn('Pattern: t___t', screen.row(2))
        self.assertEqual(screen.row(3), '5 candidates found')

    def test_q_is_text_while_editing(self):
        screen = self.run_case([9, 9, ' ', 'q', 27, 10, 'q'])
        self.assertEqual(screen.row(3), '1 candidates found')
        self.assertEqual(screen.row(4).strip(), 'quiet')

    def test_enter_while_editing_only_exits_edit_mode(self):
        cases = [
            ([' ', 127, '4', 10, 'q'], '9 candidates found', None),
            ([' ', 127, '4', 10, 10, 'q'], '1 candidates found', 'tilt'),
        ]
        for keys, header, word in cases:
            with self.subTest(keys=keys):
                screen = self.run_case(keys)
                self.assertIn('Length: 4', screen.row(2))
                self.assertEqual(screen.row(3), header)
                if word:
                    self.assertEqual(screen.row(4).strip(), word)

    def test_delete_clears(self):
        screen = self.run_case([9, ' ', 'x', 'y', curses.KEY_DC, 10, 10, 'q'])
        self.assertEqual(screen.row(3), '9 candidates found')

    def test_editing_badge_and_interrupt(self):
        screen = self.run_case([' ', KeyboardInterrupt()])
        self.assertIn('[EDITING - Esc to exit]', screen.row(0))

    def test_quitting_and_transient_curses_error(self):
        for keys in ([27], [curses.error('x'), 'q']):
            with self.subTest(keys=keys):
                self.run_case(keys)

    def test_scrolling(self):
        cases = [
            (['q'], ['cabin', None, None], False, True),
            (['j', 'j', 'q'], ['quiet', 'stats', 'tacit'], True, True),
            (['j'] * 20 + ['q'], ['taunt', 'toast', 'treat'], True, False),
            (['j'] * 20 + ['k'] * 20 + ['q'], ['cabin', None, None], False, True),
            ([curses.KEY_NPAGE, 'q'], ['stats', None, None], True, True),
            ([curses.KEY_NPAGE, curses.KEY_PPAGE, 'q'], ['cabin', None, None], False, True),
            ([curses.KEY_DOWN, 'q'], ['hello', None, None], True, True),
            ([curses.KEY_DOWN, curses.KEY_UP, 'q'], ['cabin', None, None], False, True),
        ]
        for keys, words, up, down in cases:
            with self.subTest(keys=keys):
                screen = self.run_case(keys, size=(8, 80))
                for row, word in zip(range(4, 7), words):
                    if word:
                        self.assertIn(word, screen.row(row))
                self.assertEqual('↑' in screen.row(4), up)
                self.assertEqual('↓' in screen.row(6), down)

    def test_tiny_terminal(self):
        self.run_case(['q'], lines=[], size=(2, 10))

    def test_unusable_dictionary(self):
        empty = Path(self.temp.name) / 'empty.txt'
        empty.write_text('')
        screen = self.run_case(['x'], lines=[], path=empty)
        self.assertTrue(screen.row(0).startswith('Error: Could not load word list'))
        self.assertIsNone(next(screen.keys, None))

    def test_missing_dictionary_shows_error(self):
        screen = self.run_case(
            ['x'], lines=[], path=Path(self.temp.name) / 'missing',
        )
        self.assertTrue(screen.row(0).startswith('Error: Could not load word list'))

    def test_safe_load_words_missing_file(self):
        with patch.object(tui_wordle, 'DATASET_PATH', Path(self.temp.name) / 'missing'):
            self.assertEqual(tui_wordle.safe_load_words(), set())


class SpellingBeeTuiTests(unittest.TestCase):
    START = list('eghilnw') + [10, 'h', 10, 10]
    WORDS = {'ghee', 'heel', 'hill', 'wheeling', 'glen', 'hen', 'zebra', 'hinge'}

    def run_case(self, keys, words=None, size=(24, 80)):
        screen = FakeScreen(keys=keys, size=size)
        with patch.object(
            tui_spelling_bee, 'WORDS', self.WORDS if words is None else words,
        ):
            run_tui(tui_spelling_bee, screen)
        return screen

    def test_initial_results(self):
        screen = self.run_case(self.START + ['q'])
        self.assertEqual(screen.row(3), '5 candidates found')
        expected = ['ghee', 'heel', 'hill', 'hinge', 'wheeling']
        self.assertEqual(
            [screen.row(row).strip() for row in range(4, 9)],
            expected,
        )
        self.assertIn('Letters (7)  Required (h)  MinLen (4)', screen.row(0))
        self.assertEqual(
            screen.attr_of('wheeling'),
            getattr(curses, 'A_ITALIC', curses.A_UNDERLINE),
        )
        self.assertEqual(screen.attr_of('ghee'), curses.A_NORMAL)

    def test_defaults(self):
        words = {'tilt', 'dial', 'mint', 'lid'}
        screen = self.run_case([10, 10, 10, 'q'], words)
        self.assertEqual(screen.row(3), '2 candidates found')
        self.assertEqual(
            [screen.row(row).strip() for row in (4, 5)],
            ['dial', 'tilt'],
        )
        self.assertIn('Letters (7)  Required (l)  MinLen (4)', screen.row(0))

    def test_prompt_initial_params(self):
        cases = [
            (
                ['a', 'A', '1', 'b', 127, 'c', 10, 'Z', 10, '7', 10],
                ('ac', 'z', 7),
            ),
            (['x', 'y', 10, 10, 10], ('xy', 'x', 4)),
        ]
        for keys, expected in cases:
            with self.subTest(keys=keys), patch.object(curses, 'noecho'):
                self.assertEqual(
                    tui_spelling_bee.prompt_initial_params(FakeScreen(keys=keys)),
                    expected,
                )

    def test_edit_minimum_length(self):
        screen = self.run_case(self.START + [9, 9, ' ', 127, '6', 10, 10, 'q'])
        self.assertEqual(screen.row(3), '1 candidates found')
        self.assertEqual(screen.row(4).strip(), 'wheeling')

    def test_empty_minimum_length(self):
        screen = self.run_case(self.START + [9, 9, ' ', 127, 10, 10, 'q'])
        self.assertEqual(screen.row(3), '6 candidates found')
        self.assertIn('MinLen (-)', screen.row(0))

    def test_q_is_text_while_editing(self):
        screen = self.run_case(self.START + [' ', 'q', 27, 'q'])
        self.assertIn('Letters (8)', screen.row(0))

    def test_tab_wraps(self):
        screen = self.run_case(self.START + [9, 9, 9, ' ', 'z', 27, 'q'])
        self.assertIn('Letters (8)', screen.row(0))

    def test_scrolling(self):
        cases = [
            (['q'], 'ghee', None, True),
            (['j', 'j', 'q'], 'hill', True, None),
            (['j'] * 20 + ['q'], 'wheeling', None, None),
            (['j'] * 20 + ['k'] * 20 + ['q'], 'ghee', None, None),
            ([curses.KEY_NPAGE, 'q'], 'hinge', None, None),
            ([curses.KEY_NPAGE, curses.KEY_PPAGE, 'q'], 'ghee', None, None),
        ]
        for keys, word, up, down in cases:
            with self.subTest(keys=keys):
                screen = self.run_case(self.START + keys, size=(8, 80))
                self.assertIn(word, screen.row(4))
                if up is not None:
                    self.assertEqual('↑' in screen.row(4), up)
                if down is not None:
                    self.assertEqual('↓' in screen.row(6), down)


if __name__ == '__main__':
    unittest.main()
