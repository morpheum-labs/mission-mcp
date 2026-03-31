from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

import spider_rs

from omnimission.chroma_store import ChromaStore
from omnimission.config import get_settings
from omnimission.ingest import chunk_markdown_skill_like, ingest_records

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("omnimission.crawler")


def _host_publisher(url: str) -> str:
    try:
        return urlparse(url).netloc or "unknown"
    except Exception:
        return "unknown"


async def crawl_and_ingest_once() -> int:
    settings = get_settings()
    store = ChromaStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        collection_name=settings.collection_name,
    )
    total = 0
    for seed in settings.seed_urls:
        try:
            site = await spider_rs.crawl(seed)
        except Exception as e:
            log.warning("crawl failed for %s: %s", seed, e)
            continue
        publisher = _host_publisher(seed)
        for page in site.pages:
            url = page.url or seed
            content = page.content or ""
            records = chunk_markdown_skill_like(url, content, publisher=publisher)
            n = ingest_records(store, settings.embed_model, records)
            total += n
            log.info("ingested %s chunks from %s", n, url)
    return total


def _run_loop() -> None:
    settings = get_settings()
    from apscheduler.schedulers.blocking import BlockingScheduler

    def job() -> None:
        n = asyncio.run(crawl_and_ingest_once())
        log.info("crawl cycle finished, total chunks upserted: %s", n)

    job()
    sched = BlockingScheduler()
    sched.add_job(
        job,
        "interval",
        minutes=max(1, settings.crawler_interval_minutes),
        id="omnimission_crawl",
        replace_existing=True,
    )
    log.info(
        "scheduler running every %s minutes",
        settings.crawler_interval_minutes,
    )
    sched.start()


def main() -> None:
    _run_loop()


if __name__ == "__main__":
    main()
