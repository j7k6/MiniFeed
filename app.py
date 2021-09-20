#!/usr/bin/env python3

from PIL import Image
from flask import Flask, jsonify, request, send_from_directory
from io import BytesIO
from multiprocessing import Pool
from threading import Thread
from urllib.parse import urlparse
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
import tldextract
import yaml


if sys.stdout.isatty():
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.DEBUG)
else:
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

app = Flask(__name__)

num_procs = int(os.getenv("NUM_PROCS", os.cpu_count()-1))
update_interval = int(os.getenv("UPDATE_INTERVAL", 60))
server_port = int(os.getenv("SERVER_PORT", 5000))

groups = []
feeds = []
items = []


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
                img.resize((16, 16), Image.ANTIALIAS).save(output, format="PNG")
                favicon_base64 = base64.b64encode(output.getvalue()).decode()
    except:
        pass

    return favicon_base64


def fetch_feed_info(feed):
    try:
        feed_parsed = feedparser.parse(feed["url"])

        feed["title"] = feed_parsed.feed.title
        feed["favicon"] = fetch_favicon(feed_parsed.feed.link or feed["url"])

        return feed
    except:
        logging.error(f"Error fetching '{feed['url']}'")

        return {}


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
        loggin.error(f"Error fetching '{feed['url']}'")
         
    return new_items


def update_task():
    while True:
        logging.info("Updating Feeds...")

        old_items_count = len(items)
        new_items = [new_item for new_items_list in Pool(processes=num_procs).map(fetch_feed_items, feeds) for new_item in new_items_list]

        for new_item in new_items:
            if not new_item["id"] in [item["id"] for item in items]:
                items.append(new_item)

        new_items_count = len(items) - old_items_count

        if new_items_count > 0:
            logging.info(f"[+{new_items_count}/{len(items)}]")

        time.sleep(update_interval)


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

    feeds = list(filter(lambda feed: feed != {}, Pool(processes=num_procs).map(fetch_feed_info, feeds)))

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
        since = request.args.get("since", default=0)
        after = request.args.get("after", default=None)
        
        get_items = list(filter(lambda item: item["added"] > int(since), items))

        if feed_id is not None:
            get_items = list(filter(lambda item: item["feed"] == feed_id, get_items))

        if group_id is not None:
            get_items = list(filter(lambda item: item["group"] == group_id, get_items))

        get_items.sort(key=lambda k: k["added"], reverse=True)

        if after is not None:
            try:
                get_items = get_items[[x["id"] for x in get_items].index(after)+1:]
            except ValueError as e:
                get_items = []

        return jsonify(get_items[:50])


    logging.info("Ready!")

    serve(app, port=server_port)
