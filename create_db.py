#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import better_exceptions
import logging
from collections import Counter, OrderedDict
import sqlite3
import os
import sys

from star_realms import LeagueSheet, is_bye_player, PLAYER_ALIASES

def make_db(conn):
    c = conn.cursor()
    c.execute('''CREATE TABLE events
                 (id   TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  tier TEXT,
                  tier_rank INT,
                  division TEXT)''')
    c.execute('''CREATE TABLE players
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  bgg_name TEXT NOT NULL,
                  sr_name  TEXT NOT NULL)''')
    c.execute('''CREATE TABLE preferences
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  pref TEXT NOT NULL)''')
    c.execute('''CREATE TABLE playerinfo
                 (player_id    INT  NOT NULL,
                  event_id     INT  NOT NULL,
                  preference   INT  NOT NULL,
                  rating       REAL NOT NULL DEFAULT 0.0,
                  games_won    INT  NOT NULL DEFAULT 0,
                  games_played INT  NOT NULL DEFAULT 0,
                  tier_change  CHAR NOT NULL DEFAULT "=")''')
    c.execute('''CREATE TABLE matches
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id   INT NOT NULL,
                  round      INT,
                  game_no    INT,
                  player_a   INT,
                  player_b   INT,
                  winner_id  INT)''')
    c.execute('''CREATE INDEX players_id_idx on players (id)''')
    c.execute('''CREATE INDEX matches_player_a_idx on matches(player_a)''')
    c.execute('''CREATE INDEX matches_player_b_idx on matches(player_b)''')
    conn.commit()

TIER_RANKS = {
    'Iron': 1,
    'Bronze': 2,
    'Silver': 3,
    'Gold': 4,
    'Platinum': 5,
    'Legends': 6
}
def get_tier_rank(tier):
    return TIER_RANKS.get(tier, 0)

def make_master_playerlist(seasons, conn):
    c = conn.cursor()
    players, players_by_srname = {}, {}
    events, prefs, details = [], set(), []
    for season_no, season in seasons.items():
        event = "Season {}".format(season_no)
        for player_data in season.players.values():
            sr_name = player_data["SR Name"]
            if is_bye_player(sr_name, player_data["Division"]):
                continue
            bgg_name = player_data["BGG Name"]
            if bgg_name in players and players[bgg_name] != sr_name:
                logging.warn("[{}] BGG user '{}' changed SR name: {} -> {}".format(event, bgg_name, players[bgg_name], sr_name))
            players[bgg_name] = sr_name
            players_by_srname[sr_name] = bgg_name
            prefs.add(player_data["Preference"])
            details.append((bgg_name,
                            event,
                            player_data["Division"],
                            player_data["Preference"]))
        for tier, divisions in season.tiers.items():
            tier_rank = get_tier_rank(tier)
            for j, division in enumerate(sorted(divisions)):
                event_id = f"{season_no}-{tier}-{division}"
                events.append((event_id, event, tier, tier_rank, division))
    players = list(players.items())
    prefs = [(p,) for p in prefs]

    # sanity check: are SR names unique?
    sr_names = Counter(p[1] for p in players)
    if len(sr_names) != len(players):
        for (sr_name, count) in sr_names.items():
            if count == 1:
                continue
            for (player_name, player_sr_name) in players:
                if sr_name == player_sr_name:
                    logging.error("Duplicate name: {} / {}".format(player_name, sr_name))

    c.executemany('INSERT INTO players (bgg_name, sr_name) VALUES (?,?)', players)
    c.executemany('INSERT INTO events (id, name, tier, tier_rank, division) VALUES (?,?,?,?,?)', events)
    c.executemany('INSERT INTO preferences (pref) VALUES (?)', prefs)
    c.executemany('''INSERT INTO playerinfo (player_id, event_id, preference) VALUES
                     ((SELECT id FROM players WHERE bgg_name=?),
                      (SELECT id FROM events WHERE name=? AND division=?),
                      (SELECT id FROM preferences WHERE pref=?))''', details)
    conn.commit()

def make_match_results(seasons, conn):
    c = conn.cursor()
    matches = []
    for season_no, season in seasons.items():
        logging.debug("Creating match results for Season {}".format(season_no))
        event = "Season {}".format(season_no)
        gamelog = season.get_game_log()
        for entry in gamelog:
            assert entry["Season"] == str(season_no)
            assert len(entry["Players"]) == 2
            player_a, player_b = entry["Players"]
            winner = entry["Winner"]
            if is_bye_player(player_a, entry["Division"]):
                player_a = None
            else:
                player_a = season.get_player(player_a)["BGG Name"]
            if is_bye_player(player_b, entry["Division"]):
                player_b = None
            else:
                player_b = season.get_player(player_b)["BGG Name"]
            if winner == "":
                winner = None
            if winner is not None:
                if is_bye_player(winner, entry["Division"]):
                    logging.error("{}/{}: BYE player won in Round {}, Game {}".format(season_no, entry["Division"], entry["Round"], entry["Game"]))
                    continue
                else:
                    winner = season.get_player(winner)["BGG Name"]
                    assert (winner == player_a) or (winner == player_b)
            if player_a is None and player_b is None:
                logging.error("{}/{}: No players participating in Round {}, Game {}".format(season_no, entry["Division"], entry["Round"], entry["Game"]))
                continue
            matches.append((
                event, entry["Division"],
                entry["Round"], entry["Game"],
                player_a, player_b, winner))

    logging.debug("Inserting {} matches".format(len(matches)))
    c.executemany('''INSERT INTO MATCHES
                     (event_id, round, game_no, player_a, player_b, winner_id)
                     VALUES
                     ((SELECT id FROM events WHERE name=? AND division=?),
                      ?, ?,
                      (SELECT id FROM players WHERE bgg_name=?),
                      (SELECT id FROM players WHERE bgg_name=?),
                      (SELECT id FROM players WHERE bgg_name=?))''',
                      matches)
    conn.commit()


def main(args):
    seasons = OrderedDict()
    for season_no in range(args.from_season, args.to_season + 1):
        do_load_tables = (season_no >= 13)
        do_always_fetch = (season_no >= 13) and not args.use_game_log

        logging.info("Fetching season {}...".format(season_no))
        seasons[season_no] = LeagueSheet("data/season{}".format(season_no), season_no)
        seasons[season_no].fetch_divisions(load_tables=do_load_tables)
        seasons[season_no].get_game_log(always_fetch=do_always_fetch)

    conn = sqlite3.connect(args.database)
    make_db(conn)
    make_master_playerlist(seasons, conn)
    make_match_results(seasons, conn)

    ##### TODO: get rid of this ugly hack #####
    c = conn.cursor()
    aliaslist = []
    for alias in PLAYER_ALIASES.values():
        aliaslist.append((alias['bgg_name'], alias['bgg_alias']))
    if aliaslist:
        c.executemany('''UPDATE players SET bgg_name=? WHERE bgg_name=?''', aliaslist)
        conn.commit()
    ###########################################

    conn.close()


if __name__ == "__main__":
    description = "Generates opening posts for each division in the BGG Star Realms League."
    epilog = ""
    parser = argparse.ArgumentParser(description=description, epilog=epilog)
    parser.add_argument('-d', '--database',
                        type=str,
                        default=':memory:',
                        help='Database to save to (default: %(default)s)')
    parser.add_argument('-f', '--from-season',
                        type=int,
                        default=11,
                        help='First season to process (default: %(default)d)')
    parser.add_argument('-t', '--to-season',
                        type=int,
                        default=32,
                        help='Last season to process (default: %(default)d)')
    parser.add_argument('--use-game-log',
                        action="store_true",
                        default=False,
                        help='Rely on the season game log for match results (broken)')
    parser.add_argument('-v', '--verbose',
                        action="store_true",
                        default=False,
                        help='Verbose status output')
    parser.add_argument('--debug',
                        action="store_true",
                        default=False,
                        help='Debug status output')

    args = parser.parse_args()
    loglevel = "DEBUG" if args.debug else ("INFO" if args.verbose else "WARN")
    logging.basicConfig(format="%(levelname)-8s %(message)s", level=loglevel)

    if os.path.exists(args.database):
        os.unlink(args.database)
    main(args)
