import re
from bs4 import BeautifulSoup

NUM_A = {
    2: 'twenty', 3: 'thirty',  4: 'forty',  5: 'fifty',
    6: 'sixty',  7: 'seventy', 8: 'eighty', 9: 'ninety'
}
NUM_B = {
    1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth',
    6: 'sixth', 7: 'seventh', 8: 'eighth', 9: 'ninth'
}


def num_to_adj(num):
    adj = NUM_A[num // 10]
    if num % 10 == 0:
        adj = adj[:-1] + "ieth"
    else:
        adj = '-'.join((adj, NUM_B[num % 10]))
    return adj

def parse_cell_string(s):
    i = re.search("\d", s)
    if not i:
        raise ValueError("Invalid cell name: {}".format(s))
    i = i.start()
    return s[:i], s[i:]

class TableReader:
    """Parse and access a table exported to HTML by Google Docs."""

    def __init__(self, data):
        self.col_idx = {}
        self.row_idx = {}
        self._soup = BeautifulSoup(data, "lxml")
        self._parse()

    def _parse(self):
        # normalize colspan/rowspan -- this is so we can actually find
        # individual cells by counting <tr>/<td> elements
        rowspan = {}
        for i, tr in enumerate(self._soup.find("tbody").find_all("tr")):
            j0 = 0
            for j, td in enumerate(tr.find_all("td")):
                if j0 in rowspan:
                    new_td = self._soup.new_tag("td", class_="{}-{}".format(i, j))
                    td.insert_before(new_td)
                    if rowspan[j0] == 1:
                        del rowspan[j0]
                    else:
                        rowspan[j0] -= 1
                    j0 += 1
                if 'colspan' in td.attrs:
                    span = int(td['colspan'])
                    for _ in range(span - 1):
                        td.insert_after(self._soup.new_tag("td", class_="{}-{}".format(i, j)))
                    del td['colspan']
                    j0 += span - 1
                if 'rowspan' in td.attrs:
                    span = int(td['rowspan'])
                    rowspan[j0] = span - 1
                    del td['rowspan']
                j0 += 1

        # make table matrix
        self._table = [e.find_all("td") for e in \
                       self._soup.find("tbody").find_all("tr")]

        # make dictionaries that map names to indices
        col_headers = self._soup.find("thead").find_all("th")
        for n, th in enumerate(col_headers[1:]):
            self.col_idx[th.string] = n

        row_headers = [e.find("th") for e in \
                       self._soup.find("tbody").find_all("tr")]
        for n, th in enumerate(row_headers):
            self.row_idx[th.string] = n

    def _get_cell_indices(self, cell):
        if not isinstance(cell, (tuple, list)):
            cell = parse_cell_string(cell)
        column, row = cell
        try:
            c = self.col_idx[column.upper()]
            r = self.row_idx[str(row)]
        except KeyError:
            raise KeyError("Cell {}{} doesn't exist".format(column, row))
        return (c, r)

    def cell(self, cell):
        """Return the value of a given cell."""
        (c, r) = self._get_cell_indices(cell)
        return self._table[r][c].string

    def region(self, start_cell, end_cell=None):
        """Return the value of a cell region as a single string."""
        if end_cell is None:
            start_cell, end_cell = start_cell.split(":")
        (c0, r0) = self._get_cell_indices(start_cell)
        (c1, r1) = self._get_cell_indices(end_cell)
        if c0 > c1 or r0 > r1:
            raise ValueError("start_cell can't be farther right or down than end_cell")
        lines = []
        for row in self._table[r0:r1+1]:
            cells = [c.string if c.string else '' for c in row[c0:c1+1]]
            lines.append('\t'.join(cells))
        return '\n'.join(lines)

    @property
    def rows(self):
        return self._table
