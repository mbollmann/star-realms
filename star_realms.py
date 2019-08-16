from collections import defaultdict, Counter
import logging
import re
import os
import string
from utils import TableReader, parse_cell_string

CORESETS = 'VWR'
FORMATS = 'G1BEHF2CKUAM'
COLNAMES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

PLAYER_ALIASES = {
    'BarDown93': {'bgg_name': 'AJEddy', 'bgg_alias': 'AJEddy#'},
    'TeriP': {'bgg_name': 'sleemo', 'bgg_alias': 'sleemo#'},
    'Bagira': {'bgg_name': 'kbkuno', 'bgg_alias': 'kbkuno#'},
    'songofsongs': {'bgg_name': 'GodURmyall', 'bgg_alias': 'GodURmyall#'}
}

def parse_preference_string(pref):
    pref = pref.strip()
    if "-" in pref:
        pref = pref.split("-")
        core = pref[0].strip()
        expan = pref[1].strip()
    elif pref == "NP":
        core = "NP"
        expan = "NP"
    elif all(c in CORESETS + "()" for c in pref):
        core = pref
        expan = ""
    elif all(c in FORMATS + "()" for c in pref):
        core = "V"
        expan = pref
    else:
        raise Exception("Cannot parse preference: '{}'".format(pref))
    return (core, expan)

def get_expansion_set(format_):
    if format_ == "V" or not format_:
        return set(), set()
    elif format_ == "NP":
        return set(FORMATS), set()
    elif "(" in format_:
        fixed, optional = format_.split("(")
        optional = optional[:-1]
        return set(fixed), set(optional)
    else:
        return set(format_), set()

def lcd(a, b):
    if a == "NP" and b == "NP":
        return "NP"
    a_prefs = get_expansion_set(a)
    b_prefs = get_expansion_set(b)
    common = (a_prefs[0] & b_prefs[0]) | (a_prefs[0] & b_prefs[1]) | (a_prefs[1] & b_prefs[0])
    if not common:
        return ""
    common = ''.join(char for char in FORMATS if char in common)
    return common

def is_bye_player(name, division):
    if not name:
        return False
    is_bye = name.lower().startswith("bye") # or name.lower() == "(bye)"
    #and division.lower() in name.lower())
    return is_bye

def cell_to_str(cell):
    if cell is None or cell.string is None:
        return ''
    else:
        return cell.string.rstrip()

class Division:
    def __init__(self, table):
        self._table = table
        self.round_offsets = {
            1: 'A22:C30',
            2: 'A32:C40',
            3: 'A42:C50',
            4: 'A52:C60',
            5: 'A62:C70',
            6: 'A72:C80',
            7: '<22:>30',
            8: '<32:>40',
            9: '<42:>50',
            10: '<52:>60',
            11: '<62:>70'
        }
        self.col_offset = 0
        self.row_offset = 0
        self._find_offsets()
        self._find_round_offsets()

    def _find_offsets(self):
        for row in range(25):
            for col_offset, col in enumerate(COLNAMES):
                try:
                    assert self._table.cell((col, row+1)).strip() == "Tier:"
                    assert self._table.cell((col, row+2)).strip() == "Division:"
                    assert self._table.cell((col, row+22)) == "[b]Round:"
                    # if all checks passed, we found our offset
                    self.col_offset = col_offset
                    self.row_offset = row
                    if col_offset != 0 or row != 0:
                        logging.debug("Table offset is {},{}".format(col_offset, row))
                    return
                except Exception as e:
                    continue
        raise Exception("Sheet format not recognized: couldn't find offsets")

    def _find_round_offsets(self):
        cell = self.cell
        known_ranges = 'FGHIJKLMNOPQRSTUVWXYZ'
        for i, col in enumerate(known_ranges[:-3]):
            try:
                cell22 = cell_to_str(cell(col + '22'))
            except KeyError:
                continue
            if cell22 == "[b]Round:":
                col_l = col
                col_r = known_ranges[i+2]
                break
        else:
            logging.error("Could not parse round layout!")
            return
        for i in range(7, 12):
            offset = self.round_offsets[i]
            offset = offset.replace('<', col_l).replace('>', col_r)
            self.round_offsets[i] = offset

    @property
    def commissioner(self):
        assert self.cell('C2').strip() == "DC:"
        return self.cell('D2')

    @property
    def members(self):
        cell = self.cell
        if cell('B4').strip() != "[c]Name" \
            or cell('C4').strip() != "BGG Name" \
            or cell('D4').strip() != "Card Pref" \
            or cell('B17').strip() != "[/c]":
            raise Exception("Sheet format not recognized")
        return self._table.region('B4', 'D17')

    @property
    def bye_player(self):
        for r in range(5, 17):
            name = self.cell('B{}'.format(r)).strip()
            if is_bye_player(name, self.name):
                return name
        return None

    @property
    def coreset(self):
        return "V"

    @property
    def preferences(self):
        prefs = Counter()
        set_pref = self.cell('C18')
        if set_pref is not None and "type" in set_pref.lower():
            m = re.search("Type ([^ ]+) ", set_pref)
            if m:
                logging.info("Found set division format; overriding player preferences")
                prefs[m.group(1)] = 12
                return prefs
        for r in range(5, 17):
            name = self.cell('B{}'.format(r)).strip()
            if is_bye_player(name, self.name):
                continue
            pref = self.cell('D{}'.format(r)).strip()
            prefs[pref] += 1
        return prefs

    @property
    def standings(self):
        return self._table.region('R2', 'V17')

    @property
    def name(self):
        assert self.cell('A2').strip() == "Division:"
        return self.cell('B2')

    @property
    def tier(self):
        assert self.cell('A1').strip() == "Tier:"
        return self.cell('B1')

    def cell(self, name):
        col, row = parse_cell_string(name)
        if self.col_offset and COLNAMES.find(col) >= 0:
            col = COLNAMES[COLNAMES.find(col) + self.col_offset]
        if self.row_offset:
            row = str(int(row) + self.row_offset)
        return self._table.cell((col, row))

    def get_round(self, num):
        if num not in self.round_offsets:
            raise ValueError("Invalid round number: {}".format(num))
        return self._table.region(self.round_offsets[num])

    def get_match(self, round_no, match_no):
        offset = self.round_offsets[int(round_no)]
        col_a = offset[0]
        col_b = string.ascii_uppercase[string.ascii_uppercase.find(col_a) + 2]
        col_c = string.ascii_uppercase[string.ascii_uppercase.find(col_a) + 3]
        row = int(offset[1:offset.find(":")]) + int(match_no) + 1
        row = str(row)
        #logging.debug("[{}] Getting match results from {}, {}, {}"\
        #              .format(self.name, col_a + row, col_b + row, col_c + row))
        # return player_a, player_b, winner
        return (cell_to_str(self.cell(col_a + row)),
                cell_to_str(self.cell(col_b + row)),
                cell_to_str(self.cell(col_c + row)))


class Division2(Division):
    def __init__(self, table):
        self._table = table
        self.round_offsets = {
            1: 'A22:E30',
            2: 'A32:E40',
            3: 'A42:E50',
            4: 'A52:E60',
            5: 'A62:E70',
            6: 'A72:E80',
            7: 'H22:L30',
            8: 'H32:L40',
            9: 'H42:L50',
            10: 'H52:L60',
            11: 'H62:L70'
        }
        self.col_offset = 0
        self.row_offset = 0
        self._find_offsets()
        #self._find_round_offsets()

    @property
    def commissioner(self):
        assert self.cell('D1').strip() == "DC:"
        return self.cell('E1')

    @property
    def members(self):
        cell = self.cell
        if cell('J3').strip() != "[c]Name" \
            or cell('K3').strip() != "BGG Name" \
            or cell('L3').strip() != "Card Pref" \
            or cell('J16').strip() != "[/c]":
            raise Exception("Sheet format not recognized")
        return self._table.region('J3', 'L16')

    @property
    def bye_player(self):
        for r in range(4, 16):
            name = self.cell('J{}'.format(r)).strip()
            if is_bye_player(name, self.name):
                return name
        return None

    @property
    def coreset(self):
        assert self.cell('K18').strip() == "Fixed Core:"
        if self.cell('K19'):
            return self.cell('K19').strip()
        else:
            logging.warn("No coreset(s) given -- going with V")
            return 'V'

    @property
    def expansions(self):
        prefs = Counter()
        assert self.cell('L18').strip() == "Fixed Expan:"
        fixed_pref = self.cell('L19')
        if fixed_pref is not None:
            logging.info("Found set division format; overriding player preferences")
            prefs[fixed_pref] = 12
        else:
            for r in range(4, 16):
                name = self.cell('J{}'.format(r)).strip()
                if not is_bye_player(name, self.name):
                    pref = self.cell('L{}'.format(r)).strip()
                    _, pref = parse_preference_string(pref)
                    prefs[pref] += 1
        return prefs

    @property
    def preferences(self):
        raise NotImplementedError("Not implemented for new-style spreadsheets")

    @property
    def standings(self):
        return self._table.region('B4', 'F20')

    def get_match(self, round_no, match_no):
        offset = self.round_offsets[int(round_no)]
        col_a = offset[0]
        col_b = string.ascii_uppercase[string.ascii_uppercase.find(col_a) + 2]
        col_c = string.ascii_uppercase[string.ascii_uppercase.find(col_a) + 4]
        row = int(offset[1:offset.find(":")]) + int(match_no) + 1
        row = str(row)
        #logging.debug("[{}] Getting match results from {}, {}, {}"\
        #              .format(self.name, col_a + row, col_b + row, col_c + row))
        # return player_a, player_b, winner
        return (cell_to_str(self.cell(col_a + row)),
                cell_to_str(self.cell(col_b + row)),
                cell_to_str(self.cell(col_c + row)))


class LeagueSheet:
    def __init__(self, directory, season_no):
        self.players = {}
        self._dir = directory
        self._table = {}
        self._fetch_playerlist()
        self.gamelog = None
        self.season_no = season_no

    def fetch_table(self, name):
        if name not in self._table:
            filename = "{}/{}.html".format(self._dir, name)
            if not os.path.exists(filename):
                raise ValueError("No HTML file found for table '{}'".format(name))
            with open(filename, 'r') as f:
                self._table[name] = TableReader(f.read())
        return self._table[name]

    def _fetch_playerlist(self):
        self.players = {}
        logging.debug("Loading Master Player List...")
        playerlist = self.fetch_table("Master Player List")
        attribs = ("SR Name", "BGG Name", "Preference", "Tier", "Division")
        assert playerlist.region("A1", "E1") == "\t".join(attribs)
        for row in playerlist.rows[1:]:
            if not row[0].string or not row[1].string:
                continue
            player = row[0].string.lower().strip()
            player_data = {
                'SR Name': row[0].string.strip(),
                'BGG Name': row[1].string.strip(),
                'Preference': row[2].string, # TODO parse this
                'Tier': row[3].string,
                'Division': row[4].string}
            if player_data['SR Name'] in PLAYER_ALIASES:
                alias = PLAYER_ALIASES[player_data['SR Name']]
                if alias['bgg_name'].lower() == player_data['BGG Name'].lower():
                    player_data['BGG Name'] = alias['bgg_alias']
            if player_data['Tier'] is None or player_data['Division'] is None:
                logging.warn('No tier and/or division for player {}; skipping'.format(player))
                continue
            if is_bye_player(player_data['SR Name'], player_data['Division']):
                continue
            if player_data['Preference'] is None:
                logging.warn('Preference for player {} is empty; changing to NP'.format(player))
                player_data['Preference'] = "NP"
            self.players[player] = player_data
        logging.debug("Found {} players.".format(len(self.players)))

    def fetch_divisions(self, load_tables=True):
        self.tiers, self.divisions = defaultdict(set), {}
        DivClass = Division if self.season_no < 26 else Division2
        for player in self.players.values():
            tier, division = player['Tier'], player['Division']
            if tier is None or division is None:
                continue
            self.tiers[tier].add(division)
            if load_tables and tier != "Legends":
                if division not in self.divisions:
                    logging.debug("Loading table for {}/{}...".format(tier, division))
                    table = self.fetch_table(division)
                    self.divisions[str(division)] = DivClass(table)
            else:
                self.divisions[str(division)] = False
        logging.debug("Found {} divisions ({} loaded) in {} tiers.".format(
            sum(len(t) for t in self.tiers.values()),
            len(self.divisions), len(self.tiers)
            ))

    def get_game_log(self, always_fetch=False):
        # always_fetch=True ignores the "Season Game Log" sheet for match results

        if self.gamelog:
            return self.gamelog

        logs = []
        has_legends = False
        debug_skipped = set()
        if always_fetch:
            for (tier, divisions) in self.tiers.items():
                if tier == "Legends":
                    has_legends = True
                    continue
                for division in divisions:
                    before_div = len(logs)
                    for round_no in range(1, 12):
                        for game_no in range(1, 7):
                            player_a, player_b, winner = self.divisions[division].get_match(round_no, game_no)
                            loser = player_a if winner == player_b else player_b
                            if not winner or winner == "v." or not player_a or not player_b:
                                if not winner == "v.":
                                    logging.warn("Missing match result: {}/{} Round {}, Game {}".format(
                                        tier, division, round_no, game_no))
                                winner, loser = None, None
                            win_with_bye = is_bye_player(loser, division)
                            logs.append({
                                #"UniqueID": cell_to_str(row[0]), # isn't so unique ...
                                "Season": str(self.season_no),
                                "Tier": tier,
                                "Division": division,
                                "Round": round_no,
                                "Game": game_no,
                                "Players": [player_a, player_b],
                                "Winner": winner,
                                "Win With Bye": win_with_bye
                                })
                    logging.debug("Stored {} match results for {}/{}".format(len(logs) - before_div, tier, division))

        if not always_fetch or has_legends:
            logging.debug("Loading Season Game Log...")
            games = self.fetch_table("Season Game Log")
            headers = ("UniqueID", "Season", "Tier", "Division",
                       "Round", "Game", "Winner", "Loser", "Win With Bye")
            assert games.region("A1", "I1") == "\t".join(headers)
            for row in games.rows:
                if not row[0].string or row[0].string == "UniqueID":
                    continue
                tier, division = cell_to_str(row[2]), cell_to_str(row[3])
                if has_legends and tier != "Legends":
                    continue
                if division not in self.divisions:
                    if division not in debug_skipped:
                        logging.warn("Unknown division, skipping: {}".format(division))
                        debug_skipped.add(division)
                    continue
                player_a, player_b = cell_to_str(row[6]), cell_to_str(row[7])
                winner, loser = player_a, player_b  # on the game log sheet, winner is always in the first column
                round_no, game_no = cell_to_str(row[4]), cell_to_str(row[5])
                if not winner or winner == "v." or not player_a or not player_b:
                    logging.warn("Missing match result: {}/{} Round {}, Game {}".format(
                        tier, division, round_no, game_no))
                    player_a, player_b, winner = self.divisions[division].get_match(round_no, game_no)
                    loser = player_a if winner == player_b else player_b
                    if winner and winner != "v.":
                        logging.error("  -- Game has a winner ({}) on the division sheet; I'm confused".format(winner))
                        continue
                    winner, loser = None, None
                win_with_bye = True if cell_to_str(row[8]) == "TRUE" else False
                if win_with_bye != is_bye_player(loser, division):
                    logging.debug("Inconsistent knowledge about BYE win: {} def. {} (win_with_bye = {})"\
                                  .format(winner, loser, win_with_bye))
                    win_with_bye = is_bye_player(loser, division)
                logs.append({
                    #"UniqueID": cell_to_str(row[0]), # isn't so unique ...
                    "Season": str(self.season_no),
                    "Tier": tier,
                    "Division": division,
                    "Round": round_no,
                    "Game": game_no,
                    "Players": [player_a, player_b],
                    "Winner": winner,
                    "Win With Bye": win_with_bye
                    })

        self.gamelog = logs
        return logs

    def get_player(self, name):
        try:
            return self.players[name.lower()]
        except KeyError:
            print(sorted(self.players.keys()))
            raise
