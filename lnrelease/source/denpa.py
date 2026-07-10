import datetime
import json
import re
import warnings
from collections.abc import Iterator

from bs4 import BeautifulSoup
from session import Session
from utils import Info, Series

NAME = 'Denpa'

SITE = 'https://denpa.pub'
PAYLOAD = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', flags=re.DOTALL)
ISBN = re.compile(r'\d{13}')
INDEX = re.compile(r'(?:,? (?:Volume|Vol\.?|Part) |, )(?P<index>\d+)$', flags=re.IGNORECASE)
ARTBOOK = re.compile(r'\bart ?book\b|\bart of\b|\bartworks?\b|\bscrapbook\b', flags=re.IGNORECASE)

# root category for series (authors is pcat_01HSE5E465Y3CYDA8R136V8G41)
SERIES_CAT = 'pcat_01HSE5EWJY06F57E9T0C6C8Q4M'
# site sells digital directly; paperbacks are stocked or sold through retailers
FORMATS = ('Digital', 'Paperback', 'Hardcover')


def decode(chunk: str) -> str:
    try:
        return json.loads(f'"{chunk}"')
    except json.JSONDecodeError:
        return chunk.encode().decode('unicode_escape')


def products(text: str) -> Iterator[dict]:
    # product objects are embedded in the Next.js RSC payload
    data = ''.join(decode(chunk) for chunk in PAYLOAD.findall(text))
    decoder = json.JSONDecoder()
    start = 0
    while (start := data.find('{"id":"prod_', start)) != -1:
        try:
            jsn, end = decoder.raw_decode(data, start)
            yield jsn
            start = end
        except json.JSONDecodeError:
            start += 1


def parse(session: Session, handle: str) -> tuple[Series, set[Info]] | None:
    link = f'{SITE}/book/{handle}'
    page = session.get(link)
    if page is None or page.status_code != 200:
        page = session.get(link, cf=True, ia=True)
    if page is None:
        return None
    prods = list(products(page.text))
    jsn = next((p for p in prods if p.get('handle') == handle), None)
    if jsn is None:
        return None

    title = jsn['title']
    metadata = jsn.get('metadata') or {}
    tags = {t['value'].lower() for t in jsn.get('tags') or []}
    match = INDEX.search(title)
    index = int(match.group('index')) if match else 0

    if 'art book' in tags or ARTBOOK.search(title):
        series = Series(None, title, category='artbook')
    else:
        names = [c['name'] for c in jsn.get('categories') or []
                 if c.get('parent_category_id') == SERIES_CAT]
        name = names[0] if len(names) == 1 else title[:match.start()] if match else title
        series = Series(None, name)

    date = None
    if d := metadata.get('Release Date'):
        try:
            date = datetime.date.fromisoformat(d)
        except ValueError:
            warnings.warn(f'Bad date {d}: {link}', RuntimeWarning)

    isbn = re.sub(r'\D', '', metadata.get('ISBN') or '')
    if isbn and not ISBN.fullmatch(isbn):
        warnings.warn(f'Bad ISBN {isbn}: {link}', RuntimeWarning)
        isbn = ''

    info = set()
    if isbn:  # metadata ISBN identifies the print edition
        info.add(Info(series.key, link, NAME, NAME, title, index, 'Paperback', isbn, date))
    for variant in jsn.get('variants') or []:
        format = variant.get('title')
        if format not in FORMATS:
            warnings.warn(f'Unknown format {format}: {link}', RuntimeWarning)
            continue
        i = '' if format == 'Digital' else isbn
        info.add(Info(series.key, link, NAME, NAME, title, index, format, i, date))
    return series, info


def keep(handle: str) -> bool:
    # everything except prose novels and digital chapters
    slug = handle.lower()
    return not ('-light-novel' in slug or '-novel' in slug or '-chapter-' in slug)


def scrape_full(series: set[Series], info: set[Info], limit: int = 1000) -> tuple[set[Series], set[Info]]:
    kept = 0
    filtered = 0
    with Session() as session:
        page = session.get(f'{SITE}/book')
        if page is None or page.status_code != 200:
            page = session.get(f'{SITE}/book', cf=True, ia=True)
        soup = BeautifulSoup(page.content, 'lxml')
        handles = sorted({a.get('href').removeprefix('/product/')
                          for a in soup.select('a[href^="/product/"]')})
        for handle in handles:
            if not keep(handle):
                filtered += 1
                continue
            if kept >= limit:
                break
            try:
                if res := parse(session, handle):
                    kept += 1
                    series.add(res[0])
                    info -= res[1]
                    info |= res[1]
                else:
                    filtered += 1
                    warnings.warn(f'No product data: {handle}', RuntimeWarning)
            except Exception as e:
                warnings.warn(f'({handle}): {e}', RuntimeWarning)
        print(f'{NAME}: {kept} kept, {filtered} filtered', flush=True)

    return series, info


def scrape(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    return scrape_full(series, info)
