#!/usr/bin/env python3

from PIL import Image
from flask import Flask, jsonify, request, send_from_directory
from io import BytesIO
from multiprocessing import Pool, Process
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
import yaml


db = sqlite3.connect("minifeed.db", check_same_thread=False, timeout=10)
db.row_factory = sqlite3.Row

api = Flask(__name__,  static_folder="public")


def get_items(feed_id=None, limit=100, offset=0, since=0):
    global db

    cur = db.cursor()

    if feed_id is None:
        cur.execute("SELECT * FROM items WHERE added > ? AND link NOT IN (SELECT link FROM items WHERE added > ? ORDER BY added DESC LIMIT ?) ORDER BY added DESC LIMIT ?", (since, since, offset, limit))
    else:
        cur.execute("SELECT * FROM items WHERE feed=? AND added > ? AND link NOT IN (SELECT link FROM items WHERE feed=? AND added > ? ORDER BY added DESC LIMIT ?) ORDER BY added DESC LIMIT ?", (feed_id, since, feed_id, since, offset, limit))

    rows = [dict(row) for row in cur.fetchall()]

    return rows


def get_feeds():
    global db

    cur = db.cursor()
    cur.execute("SELECT * FROM feeds ORDER BY title ASC")

    rows = [dict(row) for row in cur.fetchall()]

    return rows


def fetch_favicon(url):
    try:
        favicons = favicon.get(url)

        if len(favicons) > 0:
            for icon in favicons:
                if icon.width == icon.height:
                    favicon_url = icon.url
                    break
        else:
            favicon_url = f"{url}/favicon.ico"

        req = requests.get(favicon_url)
        img = Image.open(BytesIO(req.content))

        with BytesIO() as output:
            img = img.resize((16, 16), Image.ANTIALIAS)
            img.save(output, format='PNG')
            favicon_base64 = base64.b64encode(output.getvalue()).decode()
    except Exception as e:
        favicon_base64 = ""
        pass

    return favicon_base64


def fetch_feed_info(feed_url, feed_cat):
    global db

    feed_id = hashlib.md5(feed_url.encode()).hexdigest()

    try:
        feed_parsed = feedparser.parse(feed_url)
        feed_title = feed_parsed.feed.title
    except Exception as e:
        print(f"Error fetching '{feed_url}'")
        return False

    favicon_base64 = fetch_favicon(feed_parsed.feed.link)
    
    try:
        db.execute("INSERT INTO feeds (id, url, title, cat, favicon) VALUES (?, ?, ?, ?, ?)", (feed_id, feed_url, feed_title, feed_cat, favicon_base64))
        print(f"Added '{feed_title}'")
    except sqlite3.IntegrityError as e:
        db.execute("UPDATE feeds SET title=?, cat=?, favicon=? WHERE id=?", (feed_title, feed_cat, favicon_base64, feed_id))
        print(f"Updated '{feed_title}'")
    finally:
        db.commit()


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

    items_new = []

    for item in feed_parsed.entries:
        item_id = hashlib.md5(item.link.encode()).hexdigest()
        item_added = int(time.mktime((datetime.datetime.now()).timetuple()))
        
        try:
            item_published = time.strftime('%s', item.published_parsed)
        except TypeError as e:
            item_published = item_added

        try:
            item_description = re.sub("<[^<]+?>", "", item.description)
        except AttributeError as e:
            item_description = ""

        try:
            db.execute("INSERT INTO items (id, link, title, description, published, added, feed) VALUES (?, ?, ?, ?, ?, ?, ?)", (item_id, item.link, item.title, item_description, item_published, item_added, feed_id))
            items_new.append(item)
        except Exception as e:
            pass

    db.commit()
    
    print(f"Fetched '{feed_title}' ({len(items_new)})")


def cleanup_db(feeds, retention=7):
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
                db.commit()

                print(f"Deleted '{feed_title}'")
            except Exception as e:
                pass

    delete_before = int(time.mktime((datetime.datetime.now() - datetime.timedelta(days=retention)).timetuple()))

    cur.execute("DELETE FROM items WHERE added < ?", (delete_before,))

    db.commit()
    
    print(f"Deleted {cur.rowcount} Items")

    db.execute("INSERT OR REPLACE INTO maintenance (key, value) VALUES (?, ?)", ("ignore_before", delete_before))
    db.commit()


def update_task(feeds, update_interval):
    while True:
        print("Updating Feeds...")

        # Pool(processes=os.cpu_count()-1).map(fetch_feed_items, feeds)
        Pool(processes=len(feeds)).map(fetch_feed_items, feeds)

        time.sleep(update_interval)


def cleanup_task(feeds, cleanup_interval, retention):
    while True:
        print("Cleaning Up Database...")

        cleanup_db(feeds, retention)

        time.sleep(cleanup_interval)


if __name__ == "__main__":
    try:
        db.execute("CREATE TABLE maintenance (key TEXT UNIQUE PRIMARY KEY, value TEXT)")
        db.execute("CREATE TABLE feeds (id TEXT UNIQUE PRIMARY KEY, url TEXT, title TEXT, cat TEXT, favicon TEXT)")
        db.execute("CREATE TABLE items (id TEXT UNIQUE PRIMARY KEY, link TEXT, title TEXT, description TEXT, published INTEGER, added INTEGER, feed TEXT)")
        db.commit()
    except sqlite3.OperationalError as e:
        pass

    with open("feeds.yml") as stream:
        try:
            feeds = yaml.safe_load(stream)["feeds"]
        except yaml.YAMLError as e:
            print(e)

    categories = []
    feeds_queue = []
    feed_info_queue = []

    for cat in feeds:
        categories.append(cat)

        for feed in feeds[cat]:
            feed_info_queue.append((feed, cat))
            feeds_queue.append(feed)

    # Pool(processes=os.cpu_count()-1).starmap(fetch_feed_info, feed_info_queue)
    Pool(processes=len(feed_info_queue)).starmap(fetch_feed_info, feed_info_queue)

    Process(target=cleanup_task, args=(feeds_queue, 3600, 1)).start()
    Process(target=update_task, args=(feeds_queue, 60)).start()

    @api.route("/")
    def index():
        return api.send_static_file("index.html")

    @api.route("/api/getFeeds", methods=["GET"])
    def api_get_feeds():
        return jsonify(get_feeds())

    @api.route("/api/getItems", methods=["GET"])
    def api_get_items():
        feed_id = request.args.get("feed_id", default=None)
        limit = request.args.get("limit", default=100)
        offset = request.args.get("offset", default=0)
        since = request.args.get("since", default=0)

        return jsonify(get_items(feed_id, limit, offset, since))

    print("Ready!")
    serve(api, port=5000)

    db.close()
