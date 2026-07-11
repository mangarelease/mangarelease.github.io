import datetime
import re
import warnings
from pathlib import Path
from random import random
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from session import Session
from utils import Info, Key, Series, Table

NAME = 'VIZ Media'

PAGES = Path('viz.csv')
ISBN = re.compile(r'e?ISBN-13')


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

        # deep backfill: page through the full manga catalogue
        for i in range(1, limit + 1):
            page = session.get(SEARCH.format(i))
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
