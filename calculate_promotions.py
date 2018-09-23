#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import better_exceptions
import itertools as it
import logging
import sqlite3
import math
import os
import sys

from collections import defaultdict

PLAYER_DEMOTED = "D"
PLAYER_PROMOTED = "P"
PLAYER_NOCHANGE = "="
PLAYER_UNKNOWN = "?"

RANK_LEGENDS = 6
NUM_PROMOTIONS_BY_RANK = {
    1: 2,
    2: 2,
    3: 2,
    4: 2,
    5: 0,
    6: 0
}
NUM_DEMOTIONS_BY_RANK = {
    1: 0,  # Iron
    2: 3,  # Bronze
    3: 3,  # Silver
    4: 4,  # Gold
    5: 4,  # Platinum
    6: 0
}
MAX_PLAYERS_IN_DIVISION = 12

class Ranker:
    def __init__(self, args):
        self._conn = sqlite3.connect(args.database)
        self._c = self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def save_stats(self, stats):
        records = []
        for ((player, event), result) in stats.items():
            records.append((result, player, event))

        logging.info("Saving to database...")
        self._c.executemany('''UPDATE playerinfo SET tier_change=? WHERE player_id=? AND event_id=?''', records)
        logging.info("Saved.")

    def get_results(self):
        self._c.execute('''SELECT players.id,
                           playerinfo.games_won, playerinfo.games_played,
                           events.id, events.name, events.tier, events.tier_rank, events.division
                      FROM playerinfo
                      LEFT JOIN players ON players.id=playerinfo.player_id
                      LEFT JOIN events ON events.id=playerinfo.event_id
                      ORDER BY playerinfo.event_id ASC''')
        return self._c.fetchall()

    def get_all_standings(self, results):
        standings = defaultdict(list)
        self.division_ranks = {}
        self.season_to_event = defaultdict(set)
        for (player, games_won, games_played, event, season, tier, tier_rank, division) in results:
            try:
                standings[event].append((player, int(100 * games_won / games_played)))
            except ZeroDivisionError:
                print(player, games_won, games_played, season, tier, division)
                continue
            self.division_ranks[event] = tier_rank
            self.season_to_event[season].add(event)
        return standings

    def find_promotions_by_roster(self, standings):
        seasons = sorted(list(self.season_to_event.keys()))
        stats = defaultdict(lambda: PLAYER_UNKNOWN)
        prev_event, prev_season, this_event, this_season = {}, {}, {}, {}
        for season in seasons:
            for event in self.season_to_event[season]:
                div_rank = self.division_ranks[event]
                for (player, _) in standings[event]:
                    stat = PLAYER_NOCHANGE
                    if player in prev_season:
                        if prev_season[player] == RANK_LEGENDS:
                            stat = PLAYER_NOCHANGE
                        elif prev_season[player] > div_rank:
                            stat = PLAYER_DEMOTED
                        elif prev_season[player] < div_rank:
                            stat = PLAYER_PROMOTED
                        stats[(player, prev_event[player])] = stat
                    this_season[player] = div_rank
                    this_event[player] = event
            prev_season, this_season = this_season, {}
            prev_event, this_event = this_event, {}
        return stats

    def fetch_winner(self, player_a, player_b):
        params = (player_a, player_b, player_b, player_a, self._current_event)
        self._c.execute('''SELECT winner_id FROM matches
                            WHERE ((player_a=? AND player_b=?)
                                   OR (player_a=? AND player_b=?))
                              AND event_id=?''', params)
        return self._c.fetchone()[0]

    def fetch_wins(self, playerlist):
        wins = defaultdict(int)
        for (player_a, player_b) in it.combinations(list(playerlist), r=2):
            winner = self.fetch_winner(player_a, player_b)
            wins[winner] += 1
        return wins

    def fetch_wins_against(self, playerlist, opponentlist):
        wins = defaultdict(int)
        for player_a in playerlist:
            for player_b in opponentlist:
                winner = self.fetch_winner(player_a, player_b)
                if winner == player_a:
                    wins[winner] += 1
        return wins

    def break_tie(self, ranked_players, rank, number, direction):
        cmp_rank = -1
        tied_players = set(ranked_players[rank])
        logging.debug(f"Event {self._current_event}: Need {number} {direction}s from: " + \
                      ', '.join(str(x) for x in tied_players))

        def apply_reductions(plrs, win_count, num):
            sorted_plrs = sorted(list(plrs), key=lambda x: win_count[x],
                                 reverse=(direction == 'promotion'))
            # Take the #number top players, plus all remaining ones with the
            # same win count
            red_plrs = sorted_plrs[:num]
            tied_count = None
            for j in range(num, len(sorted_plrs)):
                if win_count[sorted_plrs[j]] == win_count[sorted_plrs[num-1]]:
                    red_plrs.append(sorted_plrs[j])
                    tied_count = win_count[sorted_plrs[num-1]]
                else:
                    break
            if tied_count is None:
                return red_plrs, []
            else:
                return [p for p in red_plrs if win_count[p] != tied_count], \
                       [p for p in red_plrs if win_count[p] == tied_count]

        chosen_players = []
        while number < len(tied_players):
            chosen = []
            if len(tied_players) == 2:
                winner = self.fetch_winner(*list(tied_players))
                if not winner:
                    # undecidable!
                    logging.warn(f"Event {self._current_event}: Tie cannot be broken; no winner in 2-player match")
                    break
                else:
                    wins = self.fetch_wins(tied_players)
                    chosen, tied_players = apply_reductions(tied_players, wins, number)
            else:
                if cmp_rank == -1:
                    # compare tied players amongst themselves
                    wins = self.fetch_wins(tied_players)
                    chosen, tied_players = apply_reductions(tied_players, wins, number)
                elif cmp_rank == rank:
                    pass
                elif cmp_rank > MAX_PLAYERS_IN_DIVISION:
                    # undecidable!
                    logging.warn(f"Event {self._current_event}: Tie cannot be broken; all players remain tied")
                    break
                elif ranked_players[cmp_rank]:
                    # compare tied players with another rank
                    wins = self.fetch_wins_against(tied_players, ranked_players[cmp_rank])
                    chosen, tied_players = apply_reductions(tied_players, wins, number)
                cmp_rank += 1

            if chosen:
                number -= len(chosen)
                chosen_players += chosen
                logging.debug("Rank {:2d}: applied reductions -- chose {}; remaining tied: {}".format(
                    cmp_rank, ', '.join(str(x) for x in chosen), ', '.join(str(x) for x in tied_players)))
            elif cmp_rank != rank and ranked_players[cmp_rank]:
                logging.debug("Rank {:2d}: no reductions".format(cmp_rank))

        logging.debug("Resolved tie: " + ', '.join([str(x) for x in chosen_players]))
        return list(chosen_players), list(tied_players)

    def get_promotions(self, players, div_rank):
        prev_perc, rank = 10001, 0
        ranked_players = defaultdict(list)
        promoted, tied, spots = [], [], NUM_PROMOTIONS_BY_RANK[div_rank]
        if spots == 0:
            return [], []
        for i, (player, win_perc) in enumerate(sorted(players, key=lambda x: x[1], reverse=True)):
            if win_perc < prev_perc:
                rank = i
                prev_perc = win_perc
            ranked_players[rank].append(player)
        for i in range(len(players)):
            if len(ranked_players[i]) == 0:
                continue
            if len(ranked_players[i]) <= spots:
                spots -= len(ranked_players[i])
                promoted.extend(list(ranked_players[i]))
            else:
                chosen, tied = self.break_tie(ranked_players, i, spots, 'promotion')
                promoted.extend(chosen)
                spots = 0
            if spots <= 0:
                break
        return promoted, tied

    def get_demotions(self, players, div_rank):
        prev_perc, rank = -1, 0
        ranked_players = defaultdict(list)
        demoted, tied, spots = [], [], NUM_DEMOTIONS_BY_RANK[div_rank]
        if spots == 0:
            return [], []
        for i, (player, win_perc) in enumerate(sorted(players, key=lambda x: x[1])):
            if win_perc > prev_perc:
                rank = i
                prev_perc = win_perc
            ranked_players[rank].append(player)
        for i in range(len(players)):
            if len(ranked_players[i]) == 0:
                continue
            if len(ranked_players[i]) <= spots:
                spots -= len(ranked_players[i])
                demoted.extend(list(ranked_players[i]))
            else:
                chosen, tied = self.break_tie(ranked_players, i, spots, 'demotion')
                demoted.extend(chosen)
                spots = 0
            if spots <= 0:
                break
        return demoted, tied

    def calculate_promotions(self, standings):
        stats = defaultdict(lambda: PLAYER_NOCHANGE)
        for event, players in standings.items():
            self._current_event = event
            div_rank = self.division_ranks[event]
            promoted, tied_p = self.get_promotions(players, div_rank)
            demoted, tied_d = self.get_demotions(players, div_rank)
            for player in promoted:
                stats[(player, event)] = PLAYER_PROMOTED
            for player in demoted:
                stats[(player, event)] = PLAYER_DEMOTED
            for player in tied_p + tied_d:
                stats[(player, event)] = PLAYER_UNKNOWN
        return stats


def unify_stats(by_roster, by_calc):
    all_keys = set(by_roster.keys()) | set(by_calc.keys())
    counts = defaultdict(int)
    unified = {}
    for (player, event) in all_keys:
        r = by_roster[(player, event)]
        c = by_calc[(player, event)]
        if r != c:
            counts[(r, c)] += 1
            if r == PLAYER_UNKNOWN:
                unified[(player, event)] = c if c != PLAYER_UNKNOWN else PLAYER_NOCHANGE
            else:
                unified[(player, event)] = r
        else:
            unified[(player, event)] = r
    print(counts)
    return unified



def main(args):
    ranker = Ranker(args)

    results = ranker.get_results()
    standings = ranker.get_all_standings(results)
    by_roster = ranker.find_promotions_by_roster(standings)
    by_calc   = ranker.calculate_promotions(standings)
    unified   = unify_stats(by_roster, by_calc)

    if args.save:
        ranker.save_stats(unified)
        ranker.commit()

    ranker.close()


if __name__ == "__main__":
    description = "Calculates ratings based on a database of league matches."
    epilog = ""
    parser = argparse.ArgumentParser(description=description, epilog=epilog)
    parser.add_argument('database',
                        type=str,
                        help='Database with match results')
    parser.add_argument('-v', '--verbose',
                        action="store_true",
                        default=False,
                        help='Verbose status output')
    parser.add_argument('--save',
                        action="store_true",
                        default=False,
                        help='Store rating histories in DB')
    parser.add_argument('--debug',
                        action="store_true",
                        default=False,
                        help='Debug status output')

    args = parser.parse_args()
    loglevel = "DEBUG" if args.debug else ("INFO" if args.verbose else "WARN")
    logging.basicConfig(format="%(levelname)-8s %(message)s", level=loglevel)
    main(args)
