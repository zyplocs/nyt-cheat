"""Text-based User Interface (TUI) helper for NYT Wordle.

Runs in the terminal using Python's built-in ``curses`` module.  It
prompts for constraints and then prints matching candidate words.

Usage
-----
Run directly:
    python wordle_tui.py

Controls
--------
• Tab         cycle between the editable fields.
• Space       enter/exit text editing mode for the active field
• ↑ / k       scroll results up (when not in edit mode)
• ↓ / j       scroll results down (when not in edit mode)
• Enter       run the filter with current params
• Esc         exit text editing mode / quit program
• q           quit program (when not in edit mode)

Requires no third-party dependencies (only the ``wordle.py`` module in
this directory and the ``english-words/words_alpha.txt`` data file).
"""
from __future__ import annotations

import curses
from pathlib import Path
from typing import Dict, Set

import wordle  # local module with load_words / filter_words

DATASET_PATH = Path(__file__).resolve().parent / "english-words" / "words_alpha.txt"

# Default values
DEFAULT_LENGTH = 5
DEFAULT_PATTERN = ""
DEFAULT_INCLUDE = ""
DEFAULT_EXCLUDE = ""

HELP_BAR = (
    "[Tab] cycle  [Space] edit  [Enter] run  [q] quit"
)

# Color pair IDs
class PAIR:
    ERROR  = 1
    HELP   = 2
    FOCUS  = 3   # used for both focus and editing accent
    HEADER = 4

def init_colors() -> dict[str, int]:
    """Initialize color pairs and return a palette of attributes."""
    # Base attrs that work on monochrome terminals
    palette: dict[str, int] = {
        "normal":   curses.A_NORMAL,
        "bold":     curses.A_BOLD,
        "underline":curses.A_UNDERLINE,
        "reverse":  curses.A_REVERSE,

        # Semantic roles (color is added if available)
        "error":    curses.A_BOLD,
        "help":     curses.A_BOLD,
        "focus":    curses.A_UNDERLINE,
        "editing":  curses.A_REVERSE | curses.A_BOLD,
        "header":   curses.A_BOLD,
    }

    # No color support: return monochrome palette
    if not curses.has_colors():
        return palette

    try:
        curses.start_color()

        # Try default-bg; if that fails, use black
        bg = -1
        try:
            curses.use_default_colors()
        except curses.error:
            bg = curses.COLOR_BLACK

        # Only use a few pairs; works across low-color terminals
        curses.init_pair(PAIR.ERROR,  curses.COLOR_RED,    bg)
        curses.init_pair(PAIR.HELP,   curses.COLOR_CYAN,   bg)
        curses.init_pair(PAIR.FOCUS,  curses.COLOR_YELLOW, bg)
        curses.init_pair(PAIR.HEADER, curses.COLOR_GREEN,  bg)

        # Bind color to semantic roles
        palette["error"]   |= curses.color_pair(PAIR.ERROR)
        palette["help"]    |= curses.color_pair(PAIR.HELP)
        palette["focus"]   |= curses.color_pair(PAIR.FOCUS)
        palette["editing"] |= curses.color_pair(PAIR.FOCUS)   # same accent as focus
        palette["header"]  |= curses.color_pair(PAIR.HEADER)

    except curses.error:
        # Fall back to monochrome palette
        pass

    return palette

# Key codes grouped in a dotted namespace for pattern matching
class KEYS:
    Q = ord("q")
    K = ord("k")  
    J = ord("j")


def prompt_initial_params(stdscr: "curses._CursesWindow") -> tuple[int, str, str, str]:
    """Interactive startup form asking the user for initial parameters.
    
    Hitting *Enter* on an empty line keeps the default value.
    Returns `(length, pattern, include_letters, exclude_letters)`.
    """
    curses.echo()
    stdscr.clear()
    stdscr.addstr(0, 0, "NYT Wordle Solver Setup – press Enter to accept default values", curses.A_BOLD)

    stdscr.addstr(2, 0, f"Word length (default {DEFAULT_LENGTH}): ")
    length_in = stdscr.getstr().decode().strip()

    stdscr.addstr(3, 0, f"Pattern with _ for unknown (e.g. t_a_t): ")
    pattern_in = stdscr.getstr().decode().strip().lower()

    stdscr.addstr(4, 0, f"Letters that must appear (e.g. ar): ")
    include_in = stdscr.getstr().decode().strip().lower()

    stdscr.addstr(5, 0, f"Letters that must NOT appear (e.g. seb): ")
    exclude_in = stdscr.getstr().decode().strip().lower()

    curses.noecho()
    stdscr.clear()

    # Parse and validate inputs with proper error handling
    try:
        length = int(length_in) if length_in else DEFAULT_LENGTH
        length = max(1, min(20, length))  # Reasonable bounds
    except ValueError:
        length = DEFAULT_LENGTH

    pattern = pattern_in or DEFAULT_PATTERN
    include = include_in or DEFAULT_INCLUDE
    exclude = exclude_in or DEFAULT_EXCLUDE

    return length, pattern, include, exclude


class Field:
    """Robust text-input field with validation and display logic."""

    def __init__(self, label: str, x: int, width: int, value: str = "", field_type: str = "text", palette: dict[str, int] | None = None) -> None:
        self.label = label
        self.x = x  # column position on the screen
        self.width = width  # max chars displayed (incl. space for cursor)
        self.value = value
        self.field_type = field_type  # "length", "pattern", "include", "exclude"
        self.palette = palette or {"normal": curses.A_NORMAL, "focus": curses.A_UNDERLINE, "editing": curses.A_REVERSE | curses.A_BOLD}

    def render(self, win: "curses._CursesWindow", y: int, focused: bool, editing: bool = False) -> None:
        """Render the field with appropriate highlighting."""
        try:
            # Different highlighting for focused vs editing states
            if editing:
                attr = self.palette["editing"]
            elif focused:
                attr = self.palette["focus"]
            else:
                attr = self.palette["normal"]
                
            # Safely add label
            max_y, max_x = win.getmaxyx()
            if y < max_y and self.x < max_x:
                win.addstr(y, min(self.x, max_x - 1), self.label[:max_x - self.x - 1])
            
            # Display value with cursor if editing
            # Ensure cursor fits within width allocation
            max_value_len = self.width - 2 if editing else self.width - 1
            display_value = self.value[:max_value_len].ljust(max_value_len)
            if editing:
                display_value += "█"  # Show cursor when editing
            
            field_x = self.x + len(self.label) + 1
            if y < max_y and field_x < max_x:
                # Ensure we don't overflow the field bounds
                safe_display = display_value[:min(len(display_value), max_x - field_x)]
                win.addstr(
                    y,
                    field_x,
                    safe_display,
                    attr,
                )
        except curses.error:
            # Gracefully handle window size issues
            pass

    def add_char(self, char: str) -> bool:
        """Add character to field value with validation. Returns True if added successfully."""
        # Reserve space for cursor when editing
        if len(self.value) >= self.width - 2:
            return False
            
        # Validation based on field type
        if self.field_type == "length":
            if not char.isdigit():
                return False
            # Only allow reasonable word lengths
            potential_value = self.value + char
            try:
                if int(potential_value) > 20:
                    return False
            except ValueError:
                return False
            self.value += char
            return True
        elif self.field_type == "pattern":
            if not (char.isalpha() or char == '_'):
                return False
            self.value += char.lower()
            return True
        elif self.field_type in ("include", "exclude"):
            if not char.isalpha():
                return False
            char_lower = char.lower()
            if char_lower in self.value:
                return False  # No duplicates
            self.value += char_lower
            return True
        else:
            # Default: allow any printable character
            self.value += char
            return True

    def backspace(self) -> None:
        """Remove last character from field value."""
        self.value = self.value[:-1]

    def clear(self) -> None:
        """Clear the field value."""
        self.value = ""


def safe_load_words() -> set[str]:
    """Safely load words with error handling."""
    try:
        return wordle.load_words(DATASET_PATH)
    except FileNotFoundError:
        return set()
    except Exception:
        return set()


def main(stdscr: "curses._CursesWindow") -> None:
    """Main TUI application with robust error handling."""
    # Configure curses settings safely
    try:
        curses.curs_set(1)
        stdscr.keypad(True)       # interpret arrow & function keys correctly
        stdscr.nodelay(False)     # blocking I/O is fine for this simple UI
        curses.mousemask(0)       # ignore mouse/track-pad scroll events
        stdscr.clear()
    except curses.error:
        pass  # Continue even if some curses features aren't available

    # Load words once at startup with error handling
    words = safe_load_words()
    if not words:
        stdscr.addstr(0, 0, "Error: Could not load word list. Check that english-words/words_alpha.txt exists.", curses.A_BOLD)
        stdscr.addstr(1, 0, "Press any key to exit.")
        stdscr.getch()
        return

    # Initialize colors (safe no-op on monochrome terminals)
    palette = init_colors()

    # Get initial parameters
    try:
        length_default, pattern_default, include_default, exclude_default = prompt_initial_params(stdscr)
    except Exception:
        # Use defaults if prompting fails
        length_default = DEFAULT_LENGTH
        pattern_default = DEFAULT_PATTERN
        include_default = DEFAULT_INCLUDE
        exclude_default = DEFAULT_EXCLUDE

    # Build the editable fields with proper spacing
    fields: list[Field] = [
        Field("Length:", 0, 5, str(length_default), "length", palette),
        Field("Pattern:", 13, 12, pattern_default, "pattern", palette),
        Field("Include:", 31, 10, include_default, "include", palette),
        Field("Exclude:", 47, 15, exclude_default, "exclude", palette),
    ]

    active = 0  # index of the currently-focused field
    editing = False  # whether we're in text editing mode
    results: list[str] = []
    offset = 0  # vertical scroll offset for results list
    error_msg = ""  # error message to display

    def draw() -> None:
        """Safely draw the UI with error handling."""
        try:
            stdscr.erase()
            max_y, max_x = stdscr.getmaxyx()

            # Help bar
            help_text = HELP_BAR
            if max_x > 0:
                stdscr.addstr(0, 0, help_text[:max_x], palette["help"])

                if editing:
                    badge = "  [EDITING - Esc to exit]"
                    if len(help_text) + len(badge) < max_x:
                        stdscr.addstr(0, len(help_text), badge, palette["editing"])

            # Input fields
            if max_y > 2:
                for idx, f in enumerate(fields):
                    f.render(stdscr, 2, focused=(idx == active), editing=(idx == active and editing))

            # Error message if present
            if error_msg and max_y > 3:
                stdscr.addstr(3, 0, f"Error: {error_msg}", palette["error"])

            # Results with scrolling
            start_row = 5 if error_msg else 4
            available_rows = max(0, max_y - start_row - 1)

            if results and available_rows > 0:
                # Results header
                header = f"{len(results)} candidates found"
                if max_y > start_row - 1:
                    stdscr.addstr(start_row - 1, 0, header, palette["header"])

                # Display results with scrolling
                for i in range(min(available_rows, len(results) - offset)):
                    if start_row + i < max_y and offset + i < len(results):
                        word = results[offset + i][:max_x - 3]  # Truncate if needed
                        stdscr.addstr(start_row + i, 2, word)

                # Scroll indicators
                if offset > 0 and max_y > start_row:
                    stdscr.addstr(start_row, max_x - 5, "↑", palette["bold"])
                if offset + available_rows < len(results) and max_y > start_row + available_rows - 1:
                    stdscr.addstr(start_row + available_rows - 1, max_x - 5, "↓", palette["bold"])

            stdscr.refresh()
        except curses.error:
            # Handle drawing errors gracefully
            pass

    def run_filter() -> None:
        """Run the word filter with comprehensive error handling."""
        nonlocal results, offset, error_msg
        error_msg = ""
        
        try:
            # Parse field values with validation
            try:
                word_length = int(fields[0].value) if fields[0].value else DEFAULT_LENGTH
                word_length = max(1, min(20, word_length))
            except ValueError:
                word_length = DEFAULT_LENGTH

            pattern = fields[1].value.lower() if fields[1].value else ""
            include_str = fields[2].value.lower() if fields[2].value else ""
            exclude_str = fields[3].value.lower() if fields[3].value else ""

            # Validate pattern length matches word length if both specified
            if pattern and word_length and len(pattern) != word_length:
                error_msg = f"Pattern length ({len(pattern)}) doesn't match word length ({word_length})"
                results = []
                offset = 0
                return

            # Parse pattern into specific positions
            specific_positions: Dict[int, str] = {}
            if pattern:
                specific_positions = {
                    idx: ch for idx, ch in enumerate(pattern) if ch != "_"
                }

            include_letters: Set[str] = set(include_str)
            exclude_letters: Set[str] = set(exclude_str)

            # Check for conflicting constraints
            conflict = include_letters & exclude_letters
            if conflict:
                error_msg = f"Letters can't be both included and excluded: {', '.join(sorted(conflict))}"
                results = []
                offset = 0
                return

            # Run the filter
            results = wordle.filter_words(
                words,
                word_length=word_length,
                specific_positions=specific_positions or None,
                include_letters=include_letters,
                exclude_letters=exclude_letters,
            )
            offset = 0

        except Exception as e:
            error_msg = f"Filter error: {str(e)}"
            results = []
            offset = 0

    # Initial run & draw
    run_filter()
    draw()

    # Main event loop with comprehensive key handling
    while True:
        try:
            key = stdscr.getch()
        except KeyboardInterrupt:
            break
        except curses.error:
            continue

        # Key-dispatch loop using structural pattern matching
        try:
            match key:
                case KEYS.Q if not editing:  # q only quits when not editing
                    break
                case 27:  # Esc
                    if editing:
                        editing = False
                    else:
                        break  # Quit if not editing
                case 9 if not editing:  # Tab - only works when not editing
                    active = (active + 1) % len(fields)
                case 32 if not editing:  # Space - enter/exit edit mode
                    editing = True
                case curses.KEY_UP | KEYS.K if not editing:  # Navigation only when not editing
                    if results:
                        offset = max(0, offset - 1)
                case curses.KEY_DOWN | KEYS.J if not editing:
                    if results:
                        max_y, _ = stdscr.getmaxyx()
                        available_rows = max(0, max_y - (5 if error_msg else 4) - 1)
                        max_offset = max(0, len(results) - available_rows)
                        offset = min(max_offset, offset + 1)
                # PageUp / PageDown
                case curses.KEY_PPAGE if not editing:  # PageUp
                    if results:
                        max_y, _ = stdscr.getmaxyx()
                        page_size = max(1, max_y - (5 if error_msg else 4) - 1)
                        offset = max(0, offset - page_size)
                case curses.KEY_NPAGE if not editing:  # PageDown
                    if results:
                        max_y, _ = stdscr.getmaxyx()
                        page_size = max(1, max_y - (5 if error_msg else 4) - 1)
                        available_rows = max(0, max_y - (5 if error_msg else 4) - 1)
                        max_offset = max(0, len(results) - available_rows)
                        offset = min(max_offset, offset + page_size)
                case curses.KEY_ENTER | 10 | 13:
                    if editing:
                        editing = False  # Exit edit mode on Enter
                    else:
                        run_filter()  # Run filter when not editing
                case key_print if 32 <= key_print < 127 and editing:  # printable ASCII - only when editing
                    fields[active].add_char(chr(key_print))
                case curses.KEY_BACKSPACE | 127 | 8 if editing:  # Backspace - only when editing
                    fields[active].backspace()
                case curses.KEY_DC if editing:  # Delete key - clear field
                    fields[active].clear()
                case _:
                    # Ignore all other keys
                    pass
        except Exception:
            # Continue even if key handling fails
            pass

        draw()  # Redraw after every key to show state changes


if __name__ == "__main__":
    curses.wrapper(main)
