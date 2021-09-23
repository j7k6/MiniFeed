#!/usr/bin/env python3

from PIL import Image
from flask import Flask, jsonify, request, send_from_directory
from io import BytesIO
from multiprocessing import Pool
from threading import Thread
from waitress import serve
import base64
import datetime
import favicon
import feedparser
import hashlib
import logging
import os
import re
import requests
import sys
import time
import yaml


NUM_PROCS = int(os.getenv("NUM_PROCS", os.cpu_count()-1))
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 60))
SERVER_PORT = int(os.getenv("SERVER_PORT", 5000))
DEBUG = bool(int(os.getenv("DEBUG", 0)))
ITEM_LIMIT = int(os.getenv("ITEM_LIMIT", 50))

loglevel = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=loglevel)

groups = []
feeds = []
items = []

app = Flask(__name__)


def fetch_favicon(feed_link):
    favicon_url = None
    favicon_base64 = None
    feed_link_stripped = "/".join(feed_link.split("/")[:3])
    fallback_url = f"{feed_link_stripped}/favicon.ico"

    for src in list(dict.fromkeys([feed_link, feed_link_stripped, fallback_url])):
        try:
            favicons = favicon.get(src)

            if len(favicons) > 0:
                favicon_url = list(filter(lambda icon: icon.width == icon.height, favicons))[0].url
                req = requests.get(favicon_url, allow_redirects=True)
                img = Image.open(BytesIO(req.content))

                with BytesIO() as output:
                    img.resize((16, 16), Image.ANTIALIAS).save(output, format="PNG")
                    favicon_base64 = base64.b64encode(output.getvalue()).decode()
                    break
        except:
            continue

    return favicon_base64


def fetch_feed_info(feed):
    try:
        feed_parsed = feedparser.parse(feed["url"])

        feed["title"] = feed_parsed.feed.title
        feed["favicon"] = fetch_favicon(feed_parsed.feed.link or feed["url"]) or ""
    except:
        logging.error(f"Error fetching '{feed['url']}'")
    
        feed = {}
    finally:
        return feed


def fetch_feed_items(feed):
    new_items = []

    try:
        feed_parsed = feedparser.parse(feed["url"])
        item_added = int(time.mktime((datetime.datetime.now()).timetuple()))

        for entry in feed_parsed.entries:
            try:
                item_title = entry.title
            except AttributeError:
                continue

            try:
                item_description = re.sub("<[^<]+?>", "", entry.description)
            except AttributeError:
                item_description = item_title

            try:
                item_published = int(time.strftime("%s", entry.published_parsed))
            except (TypeError, AttributeError):
                item_published = item_added

            new_items.append({
                "id": hashlib.md5(entry.link.encode()).hexdigest(),
                "feed": feed["id"],
                "group": feed["group"],
                "link": entry.link,
                "title": item_title,
                "description": item_description,
                "published": item_published,
                "added": item_added
            })
    except:
        logging.error(f"Error fetching '{feed['url']}'")
    finally:
        return new_items


def get_items(feed_id=None, group_id=None, after=None, since=0, limit=50):
    items_list = list(filter(lambda item: item["added"] > int(since), items))

    if feed_id is not None:
        items_list = list(filter(lambda item: item["feed"] == feed_id, items_list))

    if group_id is not None:
        items_list = list(filter(lambda item: item["group"] == group_id, items_list))

    items_list.sort(key=lambda k: k["added"], reverse=True)

    if after is not None:
        try:
            items_list = items_list[[x["id"] for x in items_list].index(after)+1:]
        except ValueError:
            items_list = []

    return items_list[:limit]


def update_task():
    while True:
        logging.info("Updating Feeds...")

        old_items_count = len(items)
        new_items = [new_item for new_items_list in Pool(processes=NUM_PROCS).map(fetch_feed_items, feeds) for new_item in new_items_list]

        for new_item in new_items:
            if not new_item["id"] in [item["id"] for item in items]:
                items.append(new_item)

        new_items_count = len(items) - old_items_count

        if new_items_count > 0:
            logging.info(f"[+{new_items_count}/{len(items)}]")

        time.sleep(UPDATE_INTERVAL)


if __name__ == "__main__":
    with open("feeds.yml") as stream:
        try:
            feeds_raw = yaml.safe_load(stream)["feeds"]
        except yaml.YAMLError as e:
            logging.fatal(e)

    for group_id in feeds_raw:
        groups.append(group_id)

        for feed_url in feeds_raw[group_id]:
            feeds.append({
                "id": hashlib.md5(feed_url.encode()).hexdigest(),
                "group": group_id,
                "url": feed_url
            })
        
    logging.info("Loading Feeds...")
    
    feeds = list(filter(lambda feed: feed != {}, Pool(processes=NUM_PROCS).map(fetch_feed_info, feeds)))

    logging.info(f"[{len(feeds)}]")

    Thread(target=update_task).start()

    while len(items) == 0:
        time.sleep(1)


    @app.route("/")
    def index():
        return app.send_static_file("index.html")


    @app.route("/assets/<path:path>")
    def serve_static(path):
        return send_from_directory("static/assets", path)


    @app.route("/api/getFeeds", methods=["GET"])
    def app_get_feeds():
        return jsonify(feeds)


    @app.route("/api/getGroups", methods=["GET"])
    def app_get_groups():
        return jsonify(groups)


    @app.route("/api/getItems", methods=["GET"])
    def api_get_items():
        feed_id = request.args.get("feed_id", default=None)
        group_id = request.args.get("group_id", default=None)
        after = request.args.get("after", default=None)
        since = request.args.get("since", default=0)

        return jsonify(get_items(feed_id=feed_id, group_id=group_id, after=after, since=since, limit=ITEM_LIMIT))


    logging.info("Ready!")

    serve(app, port=SERVER_PORT)
