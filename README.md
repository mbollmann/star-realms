# Repository for the BGG Star Realms League

Scripts and website for the BGG Star Realms League

## General info

The scripts all use Python 3.  Install the dependencies in `requirements.txt`
and you should be good to go.  As a general rule, all scripts support the
`--help` option for more info.

League data is always read from HTML exports of the Google spreadsheets.  The
exports are part of this repo since I sometimes needed to fix things, and did so
in the HTML exports directly.

## Generating threads

```bash
$ ./generate_posts.py --season 42 [exported-season42-data]
```

## Building the website

The website is built using [webgen](https://webgen.gettalong.org/), which is a
static site generator built with Ruby.  If you have a Ruby installation, install
webgen via `gem install webgen`.

The website can then be built from the `website/` directory by simply calling
`webgen`.  The output will be in `website/html/`, but you need to setup a local
web server to view it properly.

## Building the database

League data for the website is stored in an SQLite database, which needs to be
built seperately like this:

```bash
$ ./create_db.py -d seasons.db
```

The ratings are added separately:

```bash
$ ./calculate_ratings.py --save seasons.db
```

The resulting `seasons.db` needs to be placed in the website directory.
