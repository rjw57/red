import collections
import enum

from wcwidth import wcwidth, wcswidth

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
    HL_TAB = 13

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
                new_line = TextLine(
                    line.text + self.lines[self.cursor.line+1].text)
                self.lines[self.cursor.line:self.cursor.line+2] = [new_line]
        else:
            new_line = TextLine(
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
            TextLine(line.text[:self.cursor.char]),
            TextLine(line.text[self.cursor.char:]),
        ]
        self.lines[self.cursor.line:self.cursor.line+1] = new_lines

    def append_line(self, s):
        row = TextLine(s)
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

class TextLine:
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

        # What character do we use to represent whitespace?
        ws_char = '\u00b7' if self._text.isspace() else ' '

        idx, x = 0, 0
        while idx < len(self._text):
            if self._text[idx] == '\t':
                # Handle tab
                tab_size = TAB_SIZE - (x % TAB_SIZE)
                tab_chars = '\u203a' + (TAB_SIZE-1) * ws_char
                self._cells.extend(
                    Cell(c, Style.HL_TAB) for c in tab_chars[:tab_size])
                self._rendered_widths.append(tab_size)
                idx += 1
            elif self._text[idx].isspace():
                w = wcwidth(self._text[idx])
                if w > 0:
                    self._cells.extend([Cell(ws_char, Style.HL_WHITESPACE)] * w)
                    self._rendered_widths.append(w)
                    x += w
                idx += len(self._text[idx])
            else:
                # Handle normal text
                end_idx = idx + 1
                while end_idx < len(self._text) and wcwidth(self._text[end_idx]) == 0:
                    end_idx += 1
                cell_text = self._text[idx:end_idx]
                w = wcswidth(cell_text)
                if w > 0:
                    self._cells.append(Cell(cell_text, Style.HL_NORMAL))
                    if w == 2:
                        self._cells.append(WCHAR_RIGHT)
                    self._rendered_widths.append(w)
                    x += w
                idx = end_idx
