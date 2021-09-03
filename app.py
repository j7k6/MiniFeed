#!/usr/bin/env python3

from PIL import Image
from flask import Flask, jsonify, request, render_template
from io import BytesIO
from multiprocessing import Pool, Process
from urllib.parse import urlparse
from waitress import serve
import base64
import datetime
import favicon
import feedparser
import hashlib
import os
import pprint
import re
import requests
import sqlite3
import time
import tldextract
import yaml


num_procs = int(os.getenv("NUM_PROCS", os.cpu_count()-1))
update_interval = int(os.getenv("UPDATE_INTERVAL", 60))
cleanup_interval = int(os.getenv("CLEANUP_INTERVAL", 3600))
retention_days = int(os.getenv("RETENTION_DAYS", 7))
retention_items = int(os.getenv("RETENTION_ITEMS", None))
server_port = int(os.getenv("SERVER_PORT", 5000))


db = sqlite3.connect("minifeed.db", check_same_thread=False, timeout=10, isolation_level=None)
db.row_factory = sqlite3.Row

app = Flask(__name__)


def get_items(feed_id=None, limit=100, since=0, group_id=None):
    global db

    cur = db.cursor()

    rows = []

    try:
        if group_id is None:
            if feed_id is None:
                cur.execute("SELECT * FROM items WHERE added > ? ORDER BY added DESC LIMIT ?", (since, limit))
            else:
                cur.execute("SELECT * FROM items WHERE feed=? AND added > ? ORDER BY added DESC LIMIT ?", (feed_id, since, limit))
        else:
            cur.execute("SELECT * FROM items WHERE added > ? AND feed IN (SELECT id FROM feeds WHERE group_id=?) ORDER BY added DESC LIMIT ?", (since, group_id, limit))

        rows = [dict(row) for row in cur.fetchall()]
    except Exception as e:
        pass

    return rows


def get_feeds():
    global db

    rows = []

    try:
        cur = db.cursor()
        cur.execute("SELECT * FROM feeds ORDER BY title ASC")

        rows = [dict(row) for row in cur.fetchall()]
    except Exception as e:
        pass

    return rows


def fetch_favicon(url):
    favicon_url = None
    favicon_base64 = ""

    try:
        uri = urlparse(url)
        uri_extracted = tldextract.extract(url)

        favicons = favicon.get(url)

        if len(favicons) == 0:
            favicons = favicon.get(f"{uri.scheme}://{uri.netloc}")

        if len(favicons) == 0:
            favicons = favicon.get(f"{uri.scheme}://{uri_extracted.domain}.{uri_extracted.suffix}")

        if len(favicons) > 0:
            for icon in favicons:
                if icon.width == icon.height:
                    favicon_url = icon.url
                    break

        if favicon_url is None:
            fallback_urls = [f"{uri.scheme}://{uri.netloc}/favicon.ico", f"{uri.scheme}://{uri_extracted.domain}.{uri_extracted.suffix}/favicon.ico"]

            for f in fallback_urls:
                if requests.head(f, allow_redirects=True).status_code == 200:
                    favicon_url = f
                    break

        if favicon_url is not None:
            req = requests.get(favicon_url, allow_redirects=True)
            img = Image.open(BytesIO(req.content))

            with BytesIO() as output:
                img = img.resize((16, 16), Image.ANTIALIAS)
                img.save(output, format='PNG')
                favicon_base64 = base64.b64encode(output.getvalue()).decode()
    except Exception as e:
        pass

    return favicon_base64


def fetch_feed_info(feed_url, group_id):
    global db

    feed_id = hashlib.md5(feed_url.encode()).hexdigest()

    try:
        feed_parsed = feedparser.parse(feed_url)
        feed_title = feed_parsed.feed.title
    except Exception as e:
        print(f"Error fetching '{feed_url}'")
        return False

    url = feed_parsed.feed.link

    if url == "":
        url = feed_url

    favicon_base64 = fetch_favicon(url)

    try:
        db.execute("INSERT INTO feeds (id, url, title, group_id, favicon) VALUES (?, ?, ?, ?, ?)", (feed_id, feed_url, feed_title, group_id, favicon_base64))
        print(f"Added '{feed_title}'")
    except sqlite3.IntegrityError as e:
        db.execute("UPDATE feeds SET title=?, group_id=?, favicon=? WHERE id=?", (feed_title, group_id, favicon_base64, feed_id))
        print(f"Updated '{feed_title}'")


def fetch_feed_items(feed_url):
    global db

    cur = db.cursor()

    feed_id = hashlib.md5(feed_url.encode()).hexdigest()

    try:
        feed_parsed = feedparser.parse(feed_url)
        feed_title = feed_parsed.feed.title
    except Exception as e:
        print(f"Error fetching '{feed_url}'")
        return False

    ignore_before = 0

    try:
        cur.execute("SELECT value FROM maintenance WHERE key='ignore_before'")

        if cur.rowcount > 0:
            ignore_before = int(cur.fetchone()[0])
    except Exception as e:
        pass

    new_items = 0

    for item in feed_parsed.entries:
        item_id = hashlib.md5(item.link.encode()).hexdigest()
        item_added = int(time.mktime((datetime.datetime.now()).timetuple()))

        try:
            item_published = int(time.strftime('%s', item.published_parsed))
        except Exception as e:
            item_published = item_added

        if item_published > ignore_before:
            try:
                item_description = re.sub("<[^<]+?>", "", item.description)
            except AttributeError as e:
                try:
                    item_description = item.title
                except AttributeError as e:
                    item_description = ""

            try:
                db.execute("INSERT INTO items (id, link, title, description, published, added, feed) VALUES (?, ?, ?, ?, ?, ?, ?)", (item_id, item.link, item.title, item_description, item_published, item_added, feed_id))

                new_items += 1
            except Exception as e:
                pass

    if new_items > 0:
        print(f"Fetched '{feed_title}' ({new_items})")


def cleanup_db(feeds, retention_days, retention_items):
    global db

    cur = db.cursor()

    feeds_in_db = get_feeds()

    for feed in feeds_in_db:
        if not any(feed["url"] in sublist for sublist in feeds):
            try:
                cur.execute("SELECT title FROM feeds WHERE id=?", (feed["id"],))
                feed_title = cur.fetchone()[0]

                db.execute("DELETE FROM feeds WHERE id=? LIMIT 1", (feed["id"],))
                db.execute("DELETE FROM items WHERE feed=?", (feed["id"],))

                print(f"Deleted '{feed_title}'")
            except Exception as e:
                pass

    ignore_before = 0

    if retention_items is not None:
        try:
            cur.execute("SELECT published FROM items WHERE id NOT IN (SELECT id FROM items ORDER BY added DESC LIMIT ?) ORDER BY published ASC LIMIT 1", (retention_items,))

            if cur.rowcount == 1:
                ignore_before = int(cur.fetchone()[0])

            cur.execute("DELETE FROM items WHERE id NOT IN (SELECT id FROM items ORDER BY added DESC LIMIT ?)", (retention_items,))

            if cur.rowcount > 0:
                print(f"Deleted {cur.rowcount} Item(s)")
        except Exception as e:
            pass

    delete_before = int(time.mktime((datetime.datetime.now() - datetime.timedelta(days=retention_days)).timetuple()))

    cur.execute("DELETE FROM items WHERE added < ?", (delete_before,))

    if cur.rowcount > 0:
        print(f"Deleted {cur.rowcount} Item(s)")

    if ignore_before > delete_before:
        ignore_before = delete_before

    db.execute("INSERT OR REPLACE INTO maintenance (key, value) VALUES (?, ?)", ("ignore_before", ignore_before))


def update_task(feeds, update_interval):
    while True:
        print("Updating Feeds...")

        Pool(processes=num_procs).map(fetch_feed_items, feeds)

        time.sleep(update_interval)


def cleanup_task(feeds, cleanup_interval, retention_days, retention_items):
    while True:
        print("Cleaning Up Database...")

        cleanup_db(feeds, retention_days, retention_items)

        time.sleep(cleanup_interval)


if __name__ == "__main__":
    try:
        db.execute("CREATE TABLE maintenance (key TEXT UNIQUE PRIMARY KEY, value TEXT)")
        db.execute("CREATE TABLE feeds (id TEXT UNIQUE PRIMARY KEY, url TEXT, title TEXT, group_id TEXT, favicon TEXT)")
        db.execute("CREATE TABLE items (id TEXT UNIQUE PRIMARY KEY, link TEXT, title TEXT, description TEXT, published INTEGER, added INTEGER, feed TEXT)")
    except sqlite3.OperationalError as e:
        pass

    with open("feeds.yml") as stream:
        try:
            feeds = yaml.safe_load(stream)["feeds"]
        except yaml.YAMLError as e:
            print(e)

    feeds_queue = []
    feed_info_queue = []
    groups = []

    for group_id in feeds:
        groups.append(group_id)

        for feed in feeds[group_id]:
            feed_info_queue.append((feed, group_id))
            feeds_queue.append(feed)

    Pool(processes=num_procs).starmap(fetch_feed_info, feed_info_queue)

    Process(target=cleanup_task, args=(feeds_queue, cleanup_interval, retention_days, retention_items)).start()
    Process(target=update_task, args=(feeds_queue, update_interval)).start()

    @app.route("/")
    def index():
        return render_template("index.html", groups=groups, feeds=get_feeds())

    @app.route("/group/<group_id>")
    def index_by_group(group_id):
        return render_template("index.html", group_id=group_id, groups=groups, items=get_items(group_id=group_id), feeds=get_feeds())

    @app.route("/feed/<feed_id>")
    def index_by_feed(feed_id):
        return render_template("index.html", feed_id=feed_id, groups=groups, items=get_items(feed_id=feed_id), feeds=get_feeds())

    @app.route("/api/getItems", methods=["GET"])
    def api_get_items():
        feed_id = request.args.get("feed_id", default=None)
        limit = request.args.get("limit", default=100)
        since = request.args.get("since", default=0)
        group_id = request.args.get("group_id", default=None)

        return jsonify(get_items(feed_id, limit, since, group_id))

    print("Ready!")
    serve(app, port=server_port)

    db.close()
