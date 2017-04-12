from __future__ import unicode_literals, division

import collections
import curses
from curses.ascii import ctrl
import enum
from math import ceil
import os
import queue
import time
import sys

from atomicwrites import atomic_write
from wcwidth import wcwidth, wcswidth

from .app import Application

def main():
    app = Editor()

    if len(sys.argv) > 1:
        app.open(sys.argv[1])

    #app.add_timer(3.5, app.quit)
    app.run()

class Style(enum.IntEnum):
    """Styles for character cells."""
    WINDOW_BORDER = 1
    WINDOW_BACKGROUND = 2
    STATUS_BAR = 3
    STATUS_BAR_HL = 4
    SCROLL_BAR = 5
    WCHAR_RIGHT = 6

    HL_NORMAL = 10
    HL_DRAGONS = 11
    HL_WHITESPACE = 12

class TerminalPalette256(enum.IntEnum):
    """A terminal palette suitable for 256 colour displays."""

    BLACK = 16
    BLUE = 19
    GREEN = 34
    CYAN = 37
    RED = 124
    MAGENTA = 127
    BROWN = 130
    LIGHT_GREY = 248
    DARK_GREY = 240

    BRIGHT_BLUE = 63
    BRIGHT_GREEN = 83
    BRIGHT_CYAN = 87
    BRIGHT_RED = 203
    BRIGHT_MAGENTA = 207
    BRIGHT_YELLOW = 227
    BRIGHT_WHITE = 231

class FrameStyle(enum.Enum):
    SINGLE = 1
    DOUBLE = 2

# The location of a cell within a window or on-screen. A cell is located by the
# 0-based row and column indices.
CellLocation = collections.namedtuple('CellLocation', 'row col')

# A location within a text document. It is specified in terms of a 0-based line
# and character index.
DocumentLocation = collections.namedtuple('DocumentLocation', 'line char')

Cell = collections.namedtuple('Cell', 'char style')

# A special cell representing the right side of a two-column character cell
WCHAR_RIGHT = Cell('<', Style.WCHAR_RIGHT)

TAB_SIZE = 8

class Editor(Application):
    def __init__(self):
        super(Editor, self).__init__()
        self._redraw_scheduled = False

        self._document = TextDocument()
        self._filename = None

        # A simple dictionary mapping key-presses to callables.
        self.key_bindings = {
            ctrl('q'): self.quit,
            ctrl('s'): self.save,

            '\n': self.insert_newline,
            curses.KEY_ENTER: self.insert_newline,

            ctrl('h'): self.backspace,
            curses.KEY_BACKSPACE: self.backspace,

            curses.KEY_DOWN: self.move_down,
            curses.KEY_NPAGE: self.move_page_down,
            curses.KEY_UP: self.move_up,
            curses.KEY_PPAGE: self.move_page_up,

            curses.KEY_LEFT: self.move_left,
            curses.KEY_RIGHT: self.move_right,
            curses.KEY_HOME: self.move_home,
            curses.KEY_END: self.move_end,
        }

        # The scroll position within the document is represented as the cell
        # location of the upper-left corner
        self.scroll = CellLocation(0, 0)

        # Desired cell cursor position after motion
        self.desired_x = 0

        # Flag indicating desired x should be updated
        self._update_desired_x = True

    ### Properties

    @property
    def document(self):
        return self._document

    @document.setter
    def document(self, value):
        self._document = value
        self.redraw()

    ### Motion commands

    def move_home(self):
        self.document.move_home()

    def move_end(self):
        self.document.move_end()

    def move_left(self):
        self.document.move_backward()

    def move_right(self):
        self.document.move_forward()

    def move_down(self):
        cy, cx = self.document.cursor
        self.document.move_cursor(DocumentLocation(cy+1, cx))
        self._update_desired_x = False

    def move_page_down(self):
        for _ in range(max(1, self.n_lines-3)):
            self.move_down()

        _, sc = self.scroll
        sr, _ = self.document.cursor_cell
        self.scroll = CellLocation(sr, sc)

    def move_up(self):
        cy, cx = self.document.cursor
        self.document.move_cursor(DocumentLocation(cy-1, cx))
        self._update_desired_x = False

    def move_page_up(self):
        for _ in range(max(1, self.n_lines-3)):
            self.move_up()

        _, sc = self.scroll
        sr = self.document.max_row
        self.scroll = CellLocation(sr, sc)

    ### Editing

    def insert_character(self, ch):
        self.document.insert_character(ch)
        self.document.move_forward()

    def insert_newline(self):
        self.document.insert_newline()
        self.document.move_forward()

    def backspace(self):
        self.document.move_backward()
        self.document.delete_character()

    ### File I/O

    def open(self, filename):
        with open(filename) as f:
            self.document.read_from_file(f)
            self._filename = filename

    def save(self):
        with atomic_write(self._filename, overwrite=True) as f:
            self.document.write_to_file(f)

    ### Event handlers

    def start(self):
        setup_curses_colour_pairs()

    def resize(self):
        self.redraw()

    def key_press(self, ch):
        self._update_desired_x = True

        handler = self.key_bindings.get(ch)
        if handler is not None:
            handler()
        elif not isinstance(ch, int) and not curses.ascii.iscntrl(ch):
            self.insert_character(ch)

        if self._update_desired_x:
            _, self.desired_x = self.document.cursor_cell
        else:
            cr, _ = self.document.cursor_cell
            self.document.move_cursor(self.document.cell_to_cursor(
                CellLocation(cr, self.desired_x)))

        self.redraw()

    def redraw(self):
        if not self._redraw_scheduled:
            self._redraw_scheduled = True
            self.add_timer(0, self._redraw)

    def _redraw(self):
        """Redraw the screen."""
        # Reset redraw schedule flag
        self._redraw_scheduled = False

        # Move cursor to be within text document bounds
        curses.curs_set(0)
        self.screen.leaveok(1)

        self.screen.bkgdset(' ', style_attr(Style.WINDOW_BACKGROUND))
        self.screen.erase()

        # Draw frame for text view
        title = self._filename if self._filename is not None else 'Untitled'
        draw_window_frame(
            self.screen, 0, 0, self.n_lines - 1, self.n_cols,
            title=title, frame_style=FrameStyle.DOUBLE)

        # Draw text content
        n_vis_rows = self.n_lines - 3
        n_vis_cols = self.n_cols - 2

        # Update scroll position
        self._update_scroll(self.document.cursor_cell, n_vis_rows, n_vis_cols)
        ccy, ccx = self.document.cursor_cell

        if self.n_cols > 2:
            for doc_y in range(n_vis_rows):
                win_y = 1 + doc_y
                line_cells = self.document.get_cells_for_row(self.scroll.row + doc_y)

                if line_cells is None:
                    s_line = [('\u2591' * n_vis_cols, Style.HL_DRAGONS)]
                else:
                    s_line = []
                    sx = self.scroll.col
                    for cell in line_cells[sx:sx + n_vis_cols]:
                        if cell is WCHAR_RIGHT and len(s_line) > 0:
                            continue
                        s_line.append((cell.char, cell.style))
                    s_line = normalise_styled_text(s_line)

                draw_regions(self.screen, s_line, win_y, 1, self.n_cols-2)

        # Draw scroll bars
        if self.n_lines > 3 and n_vis_rows < self.document.max_row:
            draw_v_scroll(
                self.screen, self.n_cols-1, 1, self.n_lines-3,
                self.scroll.row, n_vis_rows, self.document.max_row)

        if self.n_cols > 3 and n_vis_cols < self.document.max_col:
            draw_h_scroll(
                self.screen, 1, self.n_lines-2, self.n_cols-2,
                self.scroll.col, n_vis_cols, self.document.max_col)

        self._draw_status()

        # Calculate on-screen cursor pos
        scy = ccy - self.scroll.row + 1
        scx = ccx - self.scroll.col + 1
        if scx >= 1 and scx < self.n_cols - 1 and scy >= 1 and scy < self.n_lines - 1:
            self.screen.leaveok(0)
            self.screen.move(scy, scx)
            curses.curs_set(1)

    ### Internal

    def _update_scroll(self, cursor_cell, win_rows, win_cols):
        """Update the current scroll position so that the cursor at the
        CellLocation cursor_cell is visible assuming the window is win_rows tall
        and win_cols wide.

        """
        # current scroll position
        sr, sc = self.scroll

        # update row
        if win_rows < 1:
            sr = 0
        elif cursor_cell.row < sr:
            sr = cursor_cell.row
        elif cursor_cell.row >= sr + win_rows:
            sr = max(0, cursor_cell.row - win_rows + 1)
        sr = min(sr, max(0, self.document.max_row - win_rows + 1))

        # update col
        if win_cols < 1:
            sc = 0
        elif cursor_cell.col < sc:
            sc = cursor_cell.col
        elif cursor_cell.col >= sc + win_cols:
            sc = max(0, cursor_cell.col - win_cols + 1)
        sc = min(sc, max(0, self.document.max_col - win_cols + 1))

        # set new scroll position
        self.scroll = CellLocation(sr, sc)

    def _draw_status(self):
        if self.n_lines < 1:
            return

        # Clear status bar
        self.screen.move(self.n_lines-1, 0)
        self.screen.bkgdset(' ', style_attr(Style.STATUS_BAR))
        self.screen.clrtoeol()

        # Draw status bar line
        draw_regions(self.screen, [
            (' ', Style.STATUS_BAR),
            ('Ctrl-Q', Style.STATUS_BAR_HL),
            (' Quit', Style.STATUS_BAR),
        ], y=self.n_lines-1, x=0)

class TextRow:
    # pylint: disable=too-few-public-methods
    def __init__(self, s=''):
        self._text = s
        self._rendered_widths = []
        self._render()

    @property
    def cells(self):
        return self._cells

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value
        self._render()

    def char_to_cell(self, idx):
        """Convert an index into text into a column co-ordinate."""
        return sum(self._rendered_widths[:idx])

    def cell_to_char(self, x):
        """Convert a column co-ordinate to an index into text."""
        w_sum = 0
        for idx, w in enumerate(self._rendered_widths):
            if w_sum + w > x:
                return idx
            w_sum += w
        return len(self.text)

    def insert_character_at(self, idx, ch):
        self._text = self._text[:idx] + ch + self._text[idx:]
        self._render()

    def _render(self):
        self._cells = []
        self._rendered_widths = []
        x = 0
        text_is_ws = self._text.isspace()
        for ch in self._text:
            ch_w = wcwidth(ch)
            if ch == '\t':
                tab_size = TAB_SIZE - (x % TAB_SIZE)
                tab_chars = '\u203a' + (TAB_SIZE-1) * ' '
                self._cells.extend(
                    Cell(c, Style.HL_WHITESPACE) for c in tab_chars[:tab_size])
                self._rendered_widths.append(tab_size)
            elif text_is_ws and ch_w > 0:
                self._cells.extend([Cell('\u00b7', Style.HL_WHITESPACE)] * ch_w)
                self._rendered_widths.append(ch_w)
                x += ch_w
            elif ch_w > 0:
                self._cells.append(Cell(ch, Style.HL_NORMAL))
                if ch_w == 2:
                    self._cells.append(WCHAR_RIGHT)
                self._rendered_widths.append(ch_w)
                x += ch_w

class TextDocument:
    def __init__(self):
        self.lines = []
        self._cursor = DocumentLocation(0, 0)
        self._max_col = 0

    def read_from_file(self, file_object):
        self.clear()
        for line in file_object:
            line = line.rstrip('\n\r')
            self.append_line(line)

    def write_to_file(self, file_object):
        for line in self.lines:
            file_object.write(line.text)
            file_object.write('\n')

    def get_cells_for_row(self, row_idx):
        if row_idx < 0 or row_idx >= self.max_row:
            return None
        return self.lines[row_idx].cells

    @property
    def max_row(self):
        return len(self.lines)

    @property
    def max_col(self):
        return self._max_col

    @property
    def cursor(self):
        """A DocumentLocation giving the location of the cursor."""
        return self._cursor

    @property
    def cursor_cell(self):
        """A CellLocation giving the row and column index of the cell
        corresponding to the cursor.

        """
        if self._cursor.line == self.max_row:
            return CellLocation(self._cursor.line, 0)
        row = self.lines[self._cursor.line]
        return CellLocation(self._cursor.line, row.char_to_cell(self._cursor.char))

    def move_home(self):
        cr, _ = self.cursor
        self.move_cursor(DocumentLocation(cr, 0))

    def move_end(self):
        cr, _ = self.cursor
        if cr == self.max_row:
            return
        row = self.lines[cr]
        self.move_cursor(DocumentLocation(cr, len(row.text)))

    def move_forward(self):
        """Advance the cursor one position."""
        cr, ci = self.cursor
        if cr == self.max_row:
            return
        row = self.lines[cr]

        ci += 1
        if ci > len(row.text):
            ci, cr = 0, cr + 1

        self.move_cursor(DocumentLocation(cr, ci))

    def move_backward(self):
        """Advance the cursor one position."""
        cr, ci = self.cursor
        if cr == 0 and ci == 0 or cr - 1 >= len(self.lines):
            return

        row = self.lines[cr-1]
        ci -= 1
        if ci < 0 and cr > 0:
            ci, cr = len(row.text), cr - 1

        self.move_cursor(DocumentLocation(cr, ci))

    def move_cursor(self, doc_location):
        """Move the cursor to a specific row and index within that row. The
        cursor is constrained to the valid set of input points for the document.

        """
        row, index = doc_location

        # constrain row
        row = max(0, min(row, self.max_row))

        # constrain index
        if row == self.max_row:
            index = 0
        else:
            index = max(0, min(index, len(self.lines[row].text)))

        self._cursor = DocumentLocation(row, index)

    def delete_character(self):
        if self.cursor.line == len(self.lines):
            return
        line = self.lines[self.cursor.line]
        if self.cursor.char == len(line.text):
            if self.cursor.line + 1 < len(self.lines):
                # join lines
                new_line = TextRow(
                    line.text + self.lines[self.cursor.line+1].text)
                self.lines[self.cursor.line:self.cursor.line+2] = [new_line]
        else:
            new_line = TextRow(
                line.text[:self.cursor.char] + line.text[self.cursor.char+1:])
            self.lines[self.cursor.line] = new_line

    def insert_character(self, ch):
        if ch in '\r\n':
            self.insert_newline()
        elif self.cursor.line == len(self.lines):
            self.append_line(ch)
        else:
            line = self.lines[self.cursor.line]
            line.insert_character_at(self.cursor.char, ch)
            self._max_col = max(self._max_col, len(line.cells))

    def insert_newline(self):
        if self.cursor.line == len(self.lines):
            self.append_line('')
            return

        # Split current line at cursor
        line = self.lines[self.cursor.line]
        new_lines = [
            TextRow(line.text[:self.cursor.char]),
            TextRow(line.text[self.cursor.char:]),
        ]
        self.lines[self.cursor.line:self.cursor.line+1] = new_lines

    def append_line(self, s):
        row = TextRow(s)
        self._max_col = max(self._max_col, len(row.cells))
        self.lines.append(row)

    def clear(self):
        self.lines = []

    def cell_to_cursor(self, cell_location):
        """Convert a CellLocation to the nearest DocumentLocation."""

        y, x = cell_location

        if y < 0:
            return 0, 0
        if y >= self.max_row:
            return self.max_row, 0
        if x < 0:
            return y, 0

        row = self.lines[y]
        return DocumentLocation(y, row.cell_to_char(x))

def normalise_styled_text(regions):
    norm = []
    for txt, style in regions:
        if len(norm) == 0 or norm[-1][1] is not style:
            norm.append((txt, style))
        else:
            norm[-1] = (norm[-1][0] + txt, norm[-1][1])
    return norm

def wctrim(s, max_w):
    """Return pair s, w which is a string and the cell width of that string. The
    string is trimmed so that w <= max_w. Characters which wcwidth() reports as
    having negative width are removed.

    """
    assert max_w >= 0

    # Common case: string needs no trimming
    w = wcswidth(s)
    if w >= 0 and w <= max_w:
        return s, w

    # Otherwise, walk character by character
    w, chs = 0, []
    for ch in s:
        ch_w = wcwidth(ch)
        if ch_w < 0:
            continue

        if w + ch_w > max_w:
            return ''.join(chs), w

        chs.append(ch)
        w += ch_w
    return ''.join(chs), w

def draw_regions(win, regions, y=None, x=None, max_w=None, starting_at=None):
    # pylint: disable=too-many-locals,too-many-branches,too-many-arguments
    # Get cursor position and window size
    cy, cx = win.getyx()
    nl, nc = win.getmaxyx()

    # Set default values
    if y is None:
        y = cy
    if x is None:
        x = cx
    if starting_at is None:
        starting_at = 0
    if max_w is None:
        max_w = max(0, nc - x)

    # Use max_w to set nc
    nc = min(nc, x + max_w)

    # Abort if x or y outside of window
    if x < 0 or x >= nc or y < 0 or y >= nl:
        return

    # Otherwise, let's go
    for region in regions:
        text, style = region
        attr = style_attr(style)

        # Get width of region in cells and remaining space
        region_w = wcswidth(text)
        w_remaining = nc - x
        assert w_remaining >= 0

        if region_w != -1 and w_remaining >= region_w:
            # If this text fits in the remaining space, just use addstr. Note
            # that we need to silently ignore any errors from addstr as per
            # https://bugs.python.org/issue8243
            try:
                win.addstr(y, x, text, attr)
            except curses.error:
                pass
            x += region_w
        else:
            # The remaining space is too small, add character-by-character
            for c in text:
                c_w = wcwidth(c)
                if c_w == -1:
                    continue
                if w_remaining >= c_w:
                    try:
                        win.addstr(y, x, c, attr)
                    except curses.error:
                        pass
                x += c_w
                w_remaining -= c_w

        # We're done if we're past the end of the line
        if x >= nc:
            break

def setup_curses_colour_pairs():
    """Associate sensible colour pairs for the values in Style."""
    if curses.COLORS == 256:
        p = TerminalPalette256
    else:
        raise RuntimeError('Only 256 colour terminals supported')

    curses.init_pair(Style.WINDOW_BORDER, p.BRIGHT_WHITE, p.BLUE)
    curses.init_pair(Style.WINDOW_BACKGROUND, p.LIGHT_GREY, p.BLUE)
    curses.init_pair(Style.STATUS_BAR, p.BLACK, p.LIGHT_GREY)
    curses.init_pair(Style.STATUS_BAR_HL, p.RED, p.LIGHT_GREY)
    curses.init_pair(Style.SCROLL_BAR, p.BLUE, p.CYAN)
    curses.init_pair(Style.WCHAR_RIGHT, p.CYAN, p.BLUE)

    curses.init_pair(Style.HL_NORMAL, p.LIGHT_GREY, p.BLUE)
    curses.init_pair(Style.HL_DRAGONS, p.DARK_GREY, p.BLUE)
    curses.init_pair(Style.HL_WHITESPACE, p.CYAN, p.BLUE)

def style_attr(style):
    """Convert a style to a curses attribute value."""
    return curses.color_pair(style)

def draw_window_frame(
        win, top, left, height, width,
        title=None, frame_style=FrameStyle.SINGLE):
    # pylint: disable=too-many-arguments

    draw_frame(win, top, left, height, width, Style.WINDOW_BORDER, frame_style)

    # Compute region left for window title
    title_x, title_w = left + 2, width - 4

    if title_w > 2:
        title_text, title_text_w = wctrim(title, title_w-2)
        title_right_pad = (title_w - title_text_w - 2) >> 1
        title_left_pad = title_w - title_text_w - 2 - title_right_pad
        draw_regions(win, [
            (' ', Style.WINDOW_BORDER),
            (title_text, Style.WINDOW_BORDER),
            (' ', Style.WINDOW_BORDER),
        ], y=top, x=title_x+title_left_pad, max_w=title_w)


def draw_frame(win, y, x, h, w, style, frame_style=FrameStyle.SINGLE):
    # pylint: disable=too-many-arguments
    if frame_style is FrameStyle.SINGLE:
        tlc, trc, blc, brc, hc, vc = '\u250c\u2510\u2514\u2518\u2500\u2502'
    elif frame_style is FrameStyle.DOUBLE:
        tlc, trc, blc, brc, hc, vc = '\u2554\u2557\u255a\u255d\u2550\u2551'
    else:
        raise TypeError('style is invalid')

    # Cannot draw < 2x3 frames
    if h < 2 or w < 3:
        return

    draw_regions(win, [
        (tlc, style), (hc * max(0, w-2), style), (trc, style)
    ], y=y, x=x)
    draw_regions(win, [
        (blc, style), (hc * max(0, w-2), style), (brc, style)
    ], y=y+h-1, x=x)

    for side_y in range(y+1, y+h-1):
        draw_regions(win, [(vc, style)], y=side_y, x=x)
        draw_regions(win, [(vc, style)], y=side_y, x=x+w-1)

class ScrollDirection(enum.Enum):
    HORIZONTAL = 1
    VERTICAL = 2

def draw_h_scroll(win, x, y, width, value, page_size, total):
    # pylint:disable=too-many-arguments
    draw_scroll(
        win, x, y, width, value, page_size, total, ScrollDirection.HORIZONTAL)

def draw_v_scroll(win, x, y, height, value, page_size, total):
    # pylint:disable=too-many-arguments
    draw_scroll(
        win, x, y, height, value, page_size, total, ScrollDirection.VERTICAL)

def draw_scroll(win, x, y, extent, value, page_size, total, direction):
    # pylint:disable=too-many-arguments
    value = max(0, min(value, total))
    page_size = max(0, min(page_size, total))
    if extent < 1:
        return

    # Convert value and page_size rescaling s.t. total -> extent
    page_size = ceil(max(1, page_size * (extent / total)))
    value = min(value * (extent / total), extent - page_size)

    # Draw bar itself
    for bar_idx in range(extent):
        ch, style = '\u2591', Style.SCROLL_BAR
        if bar_idx >= value and bar_idx < value + page_size:
            ch = ' '
        if direction is ScrollDirection.VERTICAL:
            draw_regions(win, [(ch, style)], y=bar_idx + y, x=x)
        elif direction is ScrollDirection.HORIZONTAL:
            draw_regions(win, [(ch, style)], x=bar_idx + x, y=y)
        else:
            assert False # should never happen
