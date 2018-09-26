#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import better_exceptions
import itertools as it
import logging
from string import Template
import sys
import yaml

from star_realms import LeagueSheet, lcd
from utils import num_to_adj

#BGG_URL="https://boardgamegeek.com/article/create/thing/147020/194"

DC_OVERRIDES = {
    'horowits': {'BGG Name': 'horowits'}
}

def baseset_reminder(core):
    sets = {
        'V': 'Core Set',
        'W': 'Colony Wars'
        }
    reminder = [sets[c] for c in core]
    return ' + '.join(reminder)

class PostGenerator:
    def __init__(self, args):
        self.browser = False
        #self.browser = args.browser
        self.template = yaml.load(args.template)
        self.season = args.season
        self.sheet = LeagueSheet(args.indir, args.season)
        self.sheet.fetch_divisions()
        self.post_template = Template(self.template['post_template'])

    def determine_format_string(self, division):
        core = division.coreset
        prefs = division.expansions
        coretext = Template(self.template['format']['coreset_reminder'])
        coretext = coretext.substitute(core=core,
                                       basesets="base set" if len(core) == 1 else "base sets",
                                       basesetreminder=baseset_reminder(core))
        # single_format, dual_format, or no_format?
        if len(prefs) == 1 and prefs['NP'] > 0:
            format_ = coretext + self.template['format']['no_format']
        else:
            if len(prefs) == 1:
                lowest_common = set(prefs.keys())
            else:
                lowest_common = set(lcd(*c) for c in it.combinations(prefs.elements(), 2))
            if len(lowest_common) == 1:
                format_ = Template(self.template['format']['single_format'])
                exp = lowest_common.pop()
                fmt = '-'.join((core, exp)) if exp else core
                format_ = format_.substitute(format=fmt)
            elif len(lowest_common) == 2 and 'NP' in lowest_common:
                lowest_common.remove('NP')
                exp = lowest_common.pop()
                if exp:
                    exptext = Template(self.template['format']['dual_format']).substitute(format=exp)
                else:
                    exptext = self.template['format']['dual_format_empty']
                format_ = coretext + exptext
            else:
                #expl = Template(self.template['format']['lcd_explanation'])
                #prefset = set(prefs.keys()) - set(('NP',))
                #a, b = prefset.pop(), prefset.pop()
                #c = lcd(a, b)
                #c = "expansions {}".format(c) if c else "no expansions"
                format_ = coretext
                format_ += self.template['format']['no_format']
                format_ += " " + self.template['format']['lcd_explanation'] #expl.substitute(a=a, b=b, c=c)
        # more than one NP player?
        if prefs['NP'] > 1:
            format_ += " " + self.template['format']['no_pref']
        return format_

    def generate_title(self, tier, divname):
        if tier == divname:
            title = "BGG Star Realms League -- Season {}, {} Tier"
            return title.format(self.season, tier)
        else:
            title = "BGG Star Realms League -- Season {}, {} Tier, {} Division"
            return title.format(self.season, tier, divname)

    def generate_post(self, divname):
        division = self.sheet.divisions[divname]
        if division.bye_player is not None:
            bye_notice = Template(self.template['bye_notice'])
            bye_notice = bye_notice.substitute(bye_player=division.bye_player)
        else:
            bye_notice = ''
        try:
            dc = self.sheet.get_player(division.commissioner)
        except KeyError:
            dc = DC_OVERRIDES[division.commissioner]
        opts = {
            'season': num_to_adj(self.season),
            'format': self.determine_format_string(division),
            'dc_ign': division.commissioner,
            'dc': dc["BGG Name"],
            'members': division.members,
            'pairings': division.get_round(1),
            'bye_notice': bye_notice
            }
        return self.post_template.safe_substitute(opts).rstrip()

    def main(self):
        if self.browser:
            from selenium import webdriver
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import time

        posts = []
        for tier in ('Platinum', 'Gold', 'Silver', 'Bronze', 'Iron'):
            divnames = sorted(list(self.sheet.tiers[tier]))
            for name in divnames:
                logging.info("Generating post for {}/{}...".format(tier, name))
                title, post = self.generate_title(tier, name), self.generate_post(name)
                posts.append((title, post))

        if self.browser:
            logging.error("Web-browser automation is currently unfinished")
            return
            driver = webdriver.Chrome()
            driver.get("https://boardgamegeek.com/")
            elem = driver.find_element_by_xpath('//input[@id="login_username"]')
            elem.send_keys(BGG_USER)
            elem = driver.find_element_by_xpath('//input[@id="login_password"]')
            elem.send_keys(BGG_PASSWORD)
            elem = driver.find_element_by_xpath('//input[@value="Sign in"]')
            elem.click()
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//a[@href="/user/{}"]'.format(BGG_USER)))
                )
            for (title, post) in posts:
                ActionChains(driver).key_down(Keys.CONTROL).send_keys('t').key_up(Keys.CONTROL).perform()
                time.sleep(1)
                driver.get(BGG_URL)
                elem = driver.find_element_by_xpath('//input[@name="subject"]')
                elem.send_keys(title)
                elem = driver.find_element_by_xpath('//textarea[@name="body"]')
                elem.send_keys(post)
                break
        else:
            for (title, post) in posts:
                print("### Subject:")
                print(title)
                print()
                print("### Message:")
                print(post)
                print()


if __name__ == "__main__":
    description = "Generates opening posts for each division in the BGG Star Realms League."
    epilog = ""
    parser = argparse.ArgumentParser(description=description, epilog=epilog)
    parser.add_argument('indir',
                        metavar='DIR',
                        type=str,
                        help='Directory with league spreadsheet as HTML export')
    #parser.add_argument('-b', '--browser',
    #                    action="store_true",
    #                    default=False,
    #                    help='Open Chromium browser tabs for posts (default: output to STDOUT)')
    parser.add_argument('-s', '--season',
                        required=True,
                        type=int,
                        help='Number of season (required)')
    parser.add_argument('-t', '--template',
                        metavar='YAML',
                        type=argparse.FileType('r'),
                        default="./template_thread.yaml",
                        help='Post template (default: %(default)s)')
    parser.add_argument('-v', '--verbose',
                        action="store_true",
                        default=False,
                        help='Verbose status output')

    args = parser.parse_args()

    loglevel = "INFO" if args.verbose else "WARN"
    logging.basicConfig(format="%(levelname)-8s %(message)s", level=loglevel)
    PostGenerator(args).main()
