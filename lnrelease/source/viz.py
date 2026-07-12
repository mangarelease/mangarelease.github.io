import datetime
import os
import re
import warnings
from pathlib import Path
from random import random
from time import monotonic
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from session import Session
from utils import Info, Key, Series, Table

NAME = 'VIZ Media'

PAGES = Path('viz.csv')
ISBN = re.compile(r'e?ISBN-13')

# --- historical backfill via the release calendar ---------------------------
# viz.com/calendar/YYYY/MM renders a whole month's releases (and, unlike
# /search, is allowed by robots.txt). Two tiers keep request volume bounded:
#   1. calendar-tier -- the month table alone gives title, product URL, format
#      and day-precision date; ingest those rows immediately, ISBN left blank.
#   2. product-tier  -- the ISBN lives on the product page (30-60s/request), so
#      fetch those incrementally through the viz.csv skip-cache, oldest backfill
#      month first, within a per-run time budget. Each weekly run chips away at
#      the backlog and never re-fetches a cached product.
# The calendar-tier Info key (link, format) and series key (volume-stripped
# title) match what parse() produces, so a later product fetch upgrades the row
# in place rather than creating a duplicate.
BACKFILL_MONTHS = int(os.getenv('VIZ_BACKFILL_MONTHS', '0'))    # calendar months back per run; 0 disables
BACKFILL_SECONDS = int(os.getenv('VIZ_BACKFILL_SECONDS', '0'))  # product-fetch budget; 0 = calendar-tier only
BACKFILL_FLOOR = datetime.date(2015, 1, 1)  # a decade of trend data; going deeper is config, not code
BACKFILL_EMPTY_STOP = 3  # consecutive empty calendar months => site predates the calendar; stop
# trailing /format segment of a product URL (…/product/6246/paperback)
PRODUCT_FMT = re.compile(r'/product/\d+/([a-z][a-z-]*)')


def parse(session: Session, link: str) -> tuple[Series, set[Info], datetime.date] | None:
    info = set()
    page = session.get(link, cf =True, ia=True)
    soup = BeautifulSoup(page.content, 'lxml')
    product = soup.find(id='product_row')
    if not product:
        return None

    series_title = product.find('strong', string='Series').find_next_sibling(class_='color-red').text
    title = product.select_one('div#purchase_links_block h2').text
    index = 0
    isbn = product.find('strong', string=ISBN).next_sibling.strip()
    date = product.find('strong', string='Release').next_sibling.strip()
    date = datetime.datetime.strptime(date, '%B %d, %Y').date()

    series = Series(None, series_title)
    for a in product.find(role='tablist').find_all('a'):
        format = a.text
        url = f'{link}/{format.lower()}'
        i = isbn if a.get('data-tab-state') == 'on' else ''
        info.add(Info(series.key, url, NAME, NAME, title, index, format, i, date))
    return series, info, date


HOME = 'https://www.viz.com/'
SEARCH = 'https://www.viz.com/search/{}?search=Manga&category=Manga'
CALENDAR = 'https://www.viz.com/calendar/{}/{:02d}'
# normalize any product URL (search or calendar, with/without a trailing format
# segment) to its base product page, which parse() expands per format
PRODUCT = re.compile(r'(/manga-books/[^/]+/[^/]+/product/\d+)')


def product_link(href: str) -> str | None:
    if match := PRODUCT.search(href):
        return urljoin(HOME, match.group(1))
    return None


def month_window(today: datetime.date, back: int = 2, ahead: int = 13) -> list[tuple[int, int]]:
    # recent past through announced future; VIZ lists ~6 months ahead
    start = today.year * 12 + today.month - 1 - back
    return [divmod(start + k, 12) for k in range(back + ahead + 1)]  # (year, month-1)


def handle(session: Session, link: str, series: set[Series], info: set[Info],
           pages: Table) -> None:
    try:
        res = parse(session, link)
        if res:
            series.add(res[0])
            info -= res[1]
            info |= res[1]
            date = res[2]
        else:
            date = None
        pages.discard(Key(link, date))
        pages.add(Key(link, date))
    except Exception as e:
        warnings.warn(f'({link}): {e}', RuntimeWarning)


def calendar_products(session: Session, today: datetime.date) -> list[str]:
    links: list[str] = []
    seen = set()
    for year, month0 in month_window(today):
        page = session.get(CALENDAR.format(year, month0 + 1))
        if page is None:
            continue
        soup = BeautifulSoup(page.content, 'lxml')
        for a in soup.find_all('a', href=True):
            if (link := product_link(a['href'])) and link not in seen:
                seen.add(link)
                links.append(link)
    return links


def calendar_entries(session: Session, year: int, month: int
                     ) -> list[tuple[str, str, str, datetime.date]] | None:
    """Parse one month's manga release table into calendar-tier records.

    Returns (base_product_link, format, title, date) per row. None means the
    page could not be fetched (robots-disallowed or network); an empty list
    means the page rendered but listed no manga releases.
    """
    page = session.get(CALENDAR.format(year, month))
    if page is None:
        return None
    soup = BeautifulSoup(page.content, 'lxml')
    section = soup.find('section', id='manga-books')  # skip dvd-bluray etc.
    if section is None:
        return []
    table = section.find('table', class_='product-table')
    if table is None:
        return []

    entries: list[tuple[str, str, str, datetime.date]] = []
    for tr in table.find_all('tr'):
        # the title anchor carries text; the thumbnail anchor (same href) is
        # image-only -- require non-empty text so the title isn't lost
        a = next((x for x in tr.find_all('a', href=True)
                  if product_link(x['href']) and x.get_text(strip=True)), None)
        if a is None:
            continue
        base = product_link(a['href'])
        fmt = PRODUCT_FMT.search(a['href'])
        if not fmt:
            continue
        # 'paperback' -> 'Paperback' to match the product-page tab labels parse()
        # reads, so Format.from_str downstream maps it the same way
        format = fmt.group(1).replace('-', ' ').title()
        title = a.get_text(strip=True)
        cells = tr.find_all('td', class_='product-table--primary')
        text = cells[-1].get_text(strip=True) if cells else ''
        try:  # "May 05" -> that day in the calendar year
            md = datetime.datetime.strptime(text, '%b %d')
            date = datetime.date(year, md.month, md.day)
        except ValueError:
            continue
        entries.append((base, format, title, date))
    return entries


def ingest_calendar(series: set[Series], info: set[Info], base: str,
                    format: str, title: str, date: datetime.date) -> None:
    """Add one calendar-tier row (no ISBN). A later product fetch upgrades it in
    place: the Info key is (link, format) and the series key is the
    volume-stripped title, both matching parse(). Never overwrite a row that
    already carries an ISBN from a product fetch."""
    s = Series(None, title)
    series.add(s)  # idempotent; keeps any existing origin/category tags
    row = Info(s.key, f'{base}/{format.lower()}', NAME, NAME, title, 0, format, '', date)
    if row not in info:  # equality is (link, format): don't clobber an ISBN row
        info.add(row)


def backfill(session: Session, series: set[Series], info: set[Info],
             pages: Table, today: datetime.date) -> None:
    """Walk the calendar backwards from the oldest cached month, ingesting
    calendar-tier rows, then fetch product pages for missing ISBNs within a
    bounded time budget. Runs after the recent+upcoming window so a truncated
    run always lands current data first."""
    if BACKFILL_MONTHS <= 0:
        return

    fetched = {row.key for row in pages}  # product pages already fetched (any date)
    dated = [row.date for row in pages if row.date]
    oldest = min(dated) if dated else today
    year, month = oldest.year, oldest.month

    backlog: list[str] = []
    seen: set[str] = set()
    empty = 0
    for _ in range(BACKFILL_MONTHS):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        if datetime.date(year, month, 1) < BACKFILL_FLOOR:
            break

        entries = calendar_entries(session, year, month)
        if entries is None:
            continue  # transient/robots; bounded by BACKFILL_MONTHS, so no loop
        if not entries:
            empty += 1
            if empty >= BACKFILL_EMPTY_STOP:
                warnings.warn(f'VIZ backfill: {empty} empty calendar months near '
                              f'{year}-{month:02d}; stopping', RuntimeWarning)
                break
            continue
        empty = 0

        for base, format, title, date in entries:
            ingest_calendar(series, info, base, format, title, date)
            if base not in fetched and base not in seen:
                seen.add(base)
                backlog.append(base)  # oldest-first: walk order is newest backfill month down

    # product-tier: fetch missing ISBNs within budget; handle() records each in
    # `pages` so it is never re-fetched, and upgrades the calendar-tier row
    if BACKFILL_SECONDS > 0 and backlog:
        deadline = monotonic() + BACKFILL_SECONDS
        done = 0
        for base in backlog:
            if monotonic() >= deadline:
                break
            handle(session, base, series, info, pages)
            done += 1
        warnings.warn(f'VIZ backfill: fetched {done}/{len(backlog)} backlog product '
                      f'pages this run', RuntimeWarning)


def scrape_full(series: set[Series], info: set[Info], limit: int = 1000) -> tuple[set[Series], set[Info]]:
    pages = Table(PAGES, Key)
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=365)
    # no date = not manga
    skip = {row.key for row in pages if random() > 0.2 and (not row.date or row.date < cutoff)}

    with Session() as session:
        # recent + upcoming releases first: the release calendar lists a whole
        # month per page, so a handful of requests covers what matters most and
        # lands even if the deep search crawl below is cut short by a timeout
        for link in calendar_products(session, today):
            if link not in skip:
                handle(session, link, series, info, pages)

        # historical backfill: walk the calendar backwards from the oldest
        # cached month (see BACKFILL_* above). Runs after the recent+upcoming
        # window so a time-bounded run always commits current data first.
        backfill(session, series, info, pages, today)

        # deep backfill: page through the full manga catalogue. NB viz.com's
        # robots.txt disallows /search, so session.get returns None and this
        # loop stops immediately -- the calendar seeding above is the real
        # source; the crawl only runs where a host permits it.
        for i in range(1, limit + 1):
            page = session.get(SEARCH.format(i))
            if page is None:
                break
            soup = BeautifulSoup(page.content, 'lxml')
            results = soup.select('div#results > article > div > a')
            for a in results:
                link = product_link(a.get('href', ''))
                if link and link not in skip:
                    handle(session, link, series, info, pages)
            if not results:
                break
    pages.save()
    return series, info


def scrape(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    # incremental: recent + upcoming calendar only (fast), skip the deep crawl
    return scrape_full(series, info, 0)
