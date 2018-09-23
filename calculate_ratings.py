#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import better_exceptions
import logging
import sqlite3
import math
import os
import sys

from collections import defaultdict
import elo
import trueskill

ELO_START = 1200
ELO_K = 32
TRUESKILL_MU = 100
TRUESKILL_SIGMA = 50 / 3 #TRUESKILL_MU / 3
TRUESKILL_BETA = 100 #TRUESKILL_SIGMA / 2
TRUESKILL_TAU = 0.41666666666666674 #TRUESKILL_SIGMA / 100

def calculate_elo(results):
    players = defaultdict(lambda: ELO_START)
    players_by_event = defaultdict(dict)
    outcome_by_event = defaultdict(lambda: defaultdict(list))
    accuracy_by_event = defaultdict(list)
    probability_by_event = defaultdict(list)
    match_rating_pairs = []

    for (event_name, round_no, player_a, player_b, winner) in results:
        if player_a is None or player_b is None:
            continue # This is a BYE match

        if winner is None:
            outcome_by_event[player_a][event_name].append(0)
            outcome_by_event[player_b][event_name].append(0)
            continue # This is a double loss

        loser = player_a if winner == player_b else player_b
        match_rating_pairs.append((players[winner], players[loser]))

        exp_a = elo.expected_score(players[player_a], players[player_b])
        exp_b = elo.expected_score(players[player_b], players[player_a])
        res_a = 1.0 if player_a == winner else 0.0
        res_b = 1.0 - res_a
        players[player_a] = elo.new_elo(players[player_a], exp_a, res_a, k=ELO_K)
        players[player_b] = elo.new_elo(players[player_b], exp_b, res_b, k=ELO_K)

        probability = (res_a * exp_a) + (res_b * exp_b)
        probability_by_event[event_name].append(probability)
        accuracy = 1.0 if probability > 0.5 else 0.0
        accuracy_by_event[event_name].append(accuracy)

        players_by_event[player_a][event_name] = round(players[player_a])
        players_by_event[player_b][event_name] = round(players[player_b])

        outcome_by_event[player_a][event_name].append(1 if player_a == winner else 0)
        outcome_by_event[player_b][event_name].append(1 if player_b == winner else 0)


    playerranks = {}
    for (player_name, rating) in players.items():
        playerranks[player_name] = round(rating)

    statistics = {
        'players_by_event': players_by_event,
        'accuracy_by_event': accuracy_by_event,
        'probability_by_event': probability_by_event,
        'outcome_by_event': outcome_by_event,
        'match_rating_pairs': match_rating_pairs}

    return (playerranks, statistics)

def trueskill_rank(rating):
    return rating.mu - 3 * rating.sigma

def trueskill_win_prob(player_rating, opponent_rating):
    BETA = trueskill.BETA
    delta_mu = player_rating.mu - opponent_rating.mu
    denom = math.sqrt(2 * (BETA * BETA) + pow(player_rating.sigma, 2) + pow(opponent_rating.sigma, 2))
    return trueskill.TrueSkill().cdf(delta_mu / denom)

def calculate_trueskill(results):
    trueskill.setup(mu=TRUESKILL_MU, sigma=TRUESKILL_SIGMA,
                    beta=TRUESKILL_BETA, tau=TRUESKILL_TAU,
                    draw_probability=0.0)
    players = defaultdict(lambda: trueskill.Rating())
    players_by_event = defaultdict(dict)
    outcome_by_event = defaultdict(lambda: defaultdict(list))
    accuracy_by_event = defaultdict(list)
    probability_by_event = defaultdict(list)
    match_rating_pairs = []

    for (event_name, round_no, player_a, player_b, winner) in results:
        if player_a is None or player_b is None:
            continue # This is a BYE match

        if winner is None:
            outcome_by_event[player_a][event_name].append(0)
            outcome_by_event[player_b][event_name].append(0)
            continue # This is a double loss

        loser = player_a if winner == player_b else player_b
        rank_winner = trueskill_rank(players[winner])
        rank_loser  = trueskill_rank(players[loser])
        match_rating_pairs.append((rank_winner, rank_loser))

        probability = trueskill_win_prob(players[winner], players[loser])
        probability_by_event[event_name].append(probability)
        accuracy = 1.0 if probability > 0.5 else 0.0
        accuracy_by_event[event_name].append(accuracy)

        players[winner], players[loser] = trueskill.rate_1vs1(players[winner], players[loser])
        players_by_event[winner][event_name] = trueskill_rank(players[winner])
        players_by_event[loser][event_name] = trueskill_rank(players[loser])

        outcome_by_event[winner][event_name].append(1)
        outcome_by_event[loser][event_name].append(0)


    playerranks = {}
    for (player_name, rating) in players.items():
        playerranks[player_name] = round(trueskill_rank(rating), 2)

    statistics = {
        'players_by_event': players_by_event,
        'accuracy_by_event': accuracy_by_event,
        'probability_by_event': probability_by_event,
        'outcome_by_event': outcome_by_event,
        'match_rating_pairs': match_rating_pairs}

    return (playerranks, statistics)


def print_accuracy(players, statistics):
    total_entries = 0
    combined_accuracy = 0.0
    for numlist in statistics['accuracy_by_event'].values():
        combined_accuracy += sum(numlist)
        total_entries += len(numlist)
    combined_accuracy /= total_entries
    combined_probability = 0.0
    for numlist in statistics['probability_by_event'].values():
        combined_probability += sum(numlist)
    combined_probability /= total_entries

    print("mu={}, sigma={}, beta={}, tau={:.4f}".format(TRUESKILL_MU, TRUESKILL_SIGMA, TRUESKILL_BETA, TRUESKILL_TAU))
    print("   ACC: {:.4f}     PROB: {:.4f}".format(combined_accuracy, combined_probability))


def print_correlation(players, statistics, rating='trueskill'):
    rating_diffs = []
    rating_wins = []
    for (winner_rating, loser_rating) in statistics['match_rating_pairs']:
        rating_diff = winner_rating - loser_rating
        rating_diffs.append(abs(rating_diff))
        if rating_diff == 0:
            rating_wins.append(0.5)
        else:
            rating_wins.append(rating_diff >= 0)

    rating_range = range(0, 46) if rating == 'trueskill' else range(0, 305, 5)
    for r in rating_range:
        wins = [y for (x, y) in zip(rating_diffs, rating_wins) if x >= r]
        try:
            acc = sum(wins) / len(wins)
        except ZeroDivisionError:
            acc = 0.0
        print(">= {:2d}: {:5d}/{:5d} = {:.4f}".format(r, round(sum(wins)), len(wins), acc))

    import numpy as np
    r = np.corrcoef(rating_diffs, rating_wins)
    print()
    print("Pearson's r: {:.8f}".format(r[0][1]))

    if True:
        print()
        print('var rating_x = [' + ','.join(str(r) for r in rating_range) + '];')
        accs = []
        for r in rating_range:
            wins = [y for (x, y) in zip(rating_diffs, rating_wins) if math.ceil(x) == r] #x >= r]
            try:
                accs.append(sum(wins) / len(wins))
            except ZeroDivisionError:
                accs.append(0.0)
        print('var rating_y = [' + ','.join('{:.6f}'.format(a) for a in accs) + '];')


def print_stats(players, statistics):
    players_by_rating = sorted(players.items(), key=lambda x: x[1], reverse=True)
    print("Top 10 players:")
    print("========================")
    for (player_name, player_rating) in players_by_rating[:10]:
        print("{:15s}\t{}".format(player_name, (player_rating)))

    print()
    print("Bottom 10 players:")
    print("===========================")
    for (player_name, player_rating) in players_by_rating[-10:]:
        print("{:15s}\t{}".format(player_name, (player_rating)))

    print()
    print("Mean prediction accuracy and probability by event:")
    print("=================================================")
    for event_name in sorted(statistics['accuracy_by_event'].keys()):
        accuracy_list = statistics['accuracy_by_event'][event_name]
        accuracy = sum(accuracy_list) / len(accuracy_list)
        probability_list = statistics['probability_by_event'][event_name]
        probability = sum(probability_list) / len(probability_list)
        print("{:15s}\t{:.4f}\t{:.4f}".format(event_name, accuracy, probability))


def print_csv(players, statistics):
    events = sorted(statistics['accuracy_by_event'].keys())
    print("{}\t{}".format("Player", "\t".join(events)))
    for player in sorted(statistics['players_by_event'].keys(), key=lambda x: x.lower()):
        ratings_by_event = statistics['players_by_event'][player]
        ratings = [str(statistics['players_by_event'].get(e, '')) for e in events]
        print("{}\t{}".format(player, "\t".join(ratings)))


def save_ratings(c, players, statistics):
    print("Fetching player and event IDs...")
    player_id, event_id = {}, defaultdict(dict)
    c.execute('''SELECT id, sr_name FROM players''')
    for (id_, name) in c.fetchall():
        player_id[name] = id_
    c.execute('''SELECT players.sr_name, events.id, events.name FROM playerinfo
                   LEFT JOIN players ON players.id=playerinfo.player_id
                   LEFT JOIN events  ON events.id=playerinfo.event_id''')
    for (player, id_, name) in c.fetchall():
        event_id[player][name] = id_

    records = []
    for player, ratings_by_event in statistics['players_by_event'].items():
        for event, rating in ratings_by_event.items():
            games_won = statistics['outcome_by_event'][player][event].count(1)
            games_played = len(statistics['outcome_by_event'][player][event])
            data = (rating, games_won, games_played, player_id[player], event_id[player][event])
            print("{} ({}) in {} ({}): {}".format(player, player_id[player], event, event_id[player][event], rating))
            records.append(data)

    print("Saving to database...")
    c.executemany('''UPDATE playerinfo SET rating=?, games_won=?, games_played=? WHERE player_id=? AND event_id=?''', records)
    print("Saved.")


def main(args):
    conn = sqlite3.connect(args.database)
    c = conn.cursor()

    c.execute('''SELECT events.name, matches.round,
                        players_a.sr_name AS player_a_name,
                        players_b.sr_name AS player_b_name,
                        players_w.sr_name AS winner_name
                 FROM matches
                 LEFT JOIN events ON events.id=matches.event_id
                 LEFT JOIN players AS players_a ON players_a.id=matches.player_a
                 LEFT JOIN players AS players_b ON players_b.id=matches.player_b
                 LEFT JOIN players AS players_w ON players_w.id=matches.winner_id
                 ORDER BY matches.event_id ASC, matches.round ASC''')
    results = c.fetchall()

    if args.rating == "elo":
        stats = calculate_elo(results)
    elif args.rating == "trueskill":
        stats = calculate_trueskill(results)

    if args.print is not None:
        if 'stats' in args.print:
            print_stats(*stats)
        if 'acc' in args.print:
            print_accuracy(*stats)
        if 'csv' in args.print:
            print_csv(*stats)
        if 'corr' in args.print:
            print_correlation(*stats, rating=args.rating)

    if args.save:
        save_ratings(c, *stats)
        conn.commit()

    conn.close()


if __name__ == "__main__":
    description = "Calculates ratings based on a database of league matches."
    epilog = ""
    parser = argparse.ArgumentParser(description=description, epilog=epilog)
    parser.add_argument('database',
                        type=str,
                        help='Database with match results')
    parser.add_argument('-r', '--rating',
                        choices=("elo", "trueskill"),
                        default="trueskill",
                        help='Rating system to use (default: %(default)s)')
    parser.add_argument('-v', '--verbose',
                        action="store_true",
                        default=False,
                        help='Verbose status output')
    parser.add_argument('-p', '--print',
                        nargs='+',
                        choices=('stats','acc','csv','corr'),
                        help='Print statistics')
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
