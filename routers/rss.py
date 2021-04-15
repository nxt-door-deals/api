import os
from datetime import datetime

import contentful
from fastapi import status

from . import router


@router.get("/rss", status_code=status.HTTP_200_OK)
def generate_rss_feed():
    item = ""
    new_item = ""

    client = contentful.Client(
        os.getenv("CONTENTFUL_SPACE_ID"), os.getenv("CONTENTFUL_ACCESS_TOKEN")
    )

    content_type = client.content_type("blog")
    last_updated_date = content_type.sys["updated_at"]

    entries = client.entries({"content_type": "blog"})

    for entry in entries:
        item = f"<item><title>{entry.title}</title><link>https://nxtdoordeals.com/blog/{entry.slug}</link><description>{entry.short_description}</description></item>"

        new_item += item

    title = "<title>The nxtdoordeals.com blog</title>"
    desctiption = "<description>A compendium of articles ranging from preloved's and pets to kids and all things DIY!</description>"
    link = "<link>https://nxtdoordeals.com/blog</link>"
    language = f"<language>{content_type.default_locale}</language>"
    copyright = f"<copyright>Copyright {datetime.today().year}</copyright>"
    last_build_date = f"<lastBuildDate>{last_updated_date}</lastBuildDate>"
    pub_date = f"<pubDate>{last_updated_date}</pubDate>"

    rss_start = (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
    )

    rss_end = "</channel></rss>"

    return (
        rss_start
        + title
        + desctiption
        + link
        + language
        + copyright
        + last_build_date
        + pub_date
        + new_item
        + rss_end
    )
