import contextlib
import io
import json
import unittest
from unittest.mock import Mock, patch

from prune import transform_text


class TransformTextTests(unittest.TestCase):
    def test_get_input_text(self):
        with patch.object(transform_text.sys, 'stdin', io.StringIO('  GHEE 4\n')):
            self.assertEqual(transform_text.get_input_text(), 'GHEE 4')
        with patch.object(transform_text.sys, 'stdin', io.StringIO('')), patch.object(
            transform_text, 'PASTED_TEXT', '\nHILL 4\n',
        ):
            self.assertEqual(transform_text.get_input_text(), 'HILL 4')
        stdin = Mock()
        stdin.isatty.return_value = True
        stdin.read.return_value = 'IGNORED 7'
        with patch.object(transform_text.sys, 'stdin', stdin), patch.object(
            transform_text, 'PASTED_TEXT', 'HILL 4',
        ):
            self.assertEqual(transform_text.get_input_text(), 'HILL 4')
        stdin.read.assert_not_called()
        with patch.object(transform_text.sys, 'stdin', io.StringIO('')), patch.object(
            transform_text, 'PASTED_TEXT', '\n',
        ), self.assertRaises(SystemExit):
            transform_text.get_input_text()

    def test_main(self):
        stdout = io.StringIO()
        with patch.object(
            transform_text.sys, 'stdin',
            io.StringIO('GHEE 4\nWHEELING 8 pangram\nhill\n'),
        ), contextlib.redirect_stdout(stdout):
            transform_text.main()
        self.assertEqual(json.loads(stdout.getvalue()), ['wheeling', 'ghee', 'hill'])
        with patch.object(
            transform_text.sys, 'stdin', io.StringIO('GHEE 5'),
        ), self.assertRaises(SystemExit) as raised:
            transform_text.main()
        self.assertTrue(str(raised.exception).startswith('Error:'))

    def test_parse_answer_table_extras(self):
        table = transform_text.parse_answer_table(
            "'ghee\n\n  Hill 4  \nWHEELING pangram'",
        )
        self.assertEqual(table.words, ('ghee', 'hill', 'wheeling'))
        self.assertEqual(table.pangrams, frozenset({'wheeling'}))


if __name__ == '__main__':
    unittest.main()
