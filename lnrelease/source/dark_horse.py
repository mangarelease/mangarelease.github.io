import datetime
import re
import warnings
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from session import Session
from utils import Info, Series

NAME = 'Dark Horse'

SITE = 'https://www.darkhorse.com/'
BROWSE = 'https://www.darkhorse.com/books/browse/'
GENRES = ('19', '20')  # manga, manhwa
ORIGINS = {'Manhwa': ('KR', 'manhwa')}
FORMATS = {'TPB': 'Paperback', 'SC': 'Paperback', 'HC': 'Hardcover'}
PAGES = re.compile(r'Page (?P<cur>\d+) of (?P<last>\d+)')
FORMAT = re.compile(r' (?P<format>TPB|HC|SC)(?= |$)')
VOLUME = re.compile(r'volume (?P<volume>\d+)', flags=re.IGNORECASE)
ISBN = re.compile(r'\d{13}')
DATES = (r'%B %d, %Y', r'%b %d, %Y')


def strpdate(s: str) -> datetime.date:
    # AP style months: 'Jan.', 'Sept.', 'March', ...
    s = s.replace('.', '').replace('Sept ', 'Sep ')
    for d in DATES:
        try:
            return datetime.datetime.strptime(s, d).date()
        except ValueError:
            pass
    raise ValueError(f"Invalid time data '{s}'")


def links(soup: BeautifulSoup) -> list[str]:
    return [urljoin(SITE, product.a['href'])
            for product in soup.find_all(class_='product-result') if product.a]


def parse(session: Session, link: str) -> tuple[Series, Info] | None:
    page = session.get(link, cf=True, ia=True)
    soup = BeautifulSoup(page.content, 'lxml')
    body = soup.find(class_='product-detail-body')
    meta = body.find(class_='product-meta') if body else None
    if not meta:
        return None

    isbn = meta.find('strong', string='ISBN-13:')
    isbn = isbn.next_sibling.strip() if isbn else ''
    date = meta.find('strong', string='Publication date:')
    if not ISBN.fullmatch(isbn) or not date:
        return None
    date = strpdate(date.next_sibling.strip())

    title = body.h2.text.strip()
    format = FORMATS.get(m.group('format')) if (m := FORMAT.search(title)) else None
    title = FORMAT.sub('', title)
    if f := meta.find('strong', string='Format:'):
        for part in f.next_sibling.split(';'):
            if part.strip() in FORMATS:
                format = FORMATS[part.strip()]
                break
    format = format or 'Physical'
    index = int(m.group('volume')) if (m := VOLUME.search(title)) else 0

    origin = category = ''
    for a in body.select('a[href^="/search/genre:"]'):
        if o := ORIGINS.get(a.text.strip()):
            origin, category = o
            break
    series = Series(None, title, origin, category)
    return series, Info(series.key, link, NAME, NAME, title, index, format, isbn, date)


def scrape_full(series: set[Series], info: set[Info], limit: int = 1000) -> tuple[set[Series], set[Info]]:
    kept = 0
    filtered = 0
    seen = set()
    with Session() as session:
        for genre in GENRES:
            params = {
                'filter_type': 'genre',
                'genre_filter': genre,
                'sort': '-on_sale_date',
            }
            last = limit
            for p in range(1, limit + 1):
                if p > last:
                    break
                page = session.get(BROWSE, params={**params, 'p': p}, cf=True, ia=True)
                soup = BeautifulSoup(page.content, 'lxml')
                if not soup.select_one(f'option[value="{genre}"][selected]'):
                    # invalid form silently falls back to unfiltered results
                    warnings.warn(f'Genre filter {genre} not applied', RuntimeWarning)
                    break
                if match := PAGES.search(soup.text):
                    last = int(match.group('last'))
                else:
                    last = p
                results = links(soup)
                for link in results:
                    if link in seen or '/books/' not in link:
                        filtered += 1
                        continue
                    seen.add(link)
                    try:
                        if res := parse(session, link):
                            series.add(res[0])
                            info.discard(res[1])
                            info.add(res[1])
                            kept += 1
                        else:
                            filtered += 1
                    except Exception as e:
                        warnings.warn(f'({link}): {e}', RuntimeWarning)
                if not results:
                    break
    print(f'{NAME}: {kept} kept, {filtered} filtered', flush=True)
    return series, info


def scrape(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    return scrape_full(series, info, 2)
