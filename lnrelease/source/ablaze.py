import datetime
import re
import warnings

from session import Session
from utils import Info, Series, clean_str

NAME = 'Ablaze'

# www.ablaze.net redirects to the ablazecomics.myshopify.com storefront,
# but only the homepage: all deep paths 404, so link straight to the store
API = 'https://ablazecomics.myshopify.com/collections/graphic-novels/products.json?limit=250&page={}'
LINK = 'https://ablazecomics.myshopify.com/products/{}'

MONTH = re.compile(r'(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4}')
VOLUME = re.compile(r'\b(?P<omnibus>OMNIBUS )?VOL(?:\.|UME)? ?(?P<volume>\d+)\b')
SET = re.compile(r'\b(?:BUNDLE|BOX SET|(?:BINGE |COLLECTED )?COLLECTION|COLLECTED SET|SLIPCASE)\b')
KEYWORD = re.compile(r'\b(?P<category>manga|manhwa|manhua|webtoon)\b', flags=re.IGNORECASE)
HTML = re.compile(r'<[^>]+>')

FORMATS = {'TP': 'Paperback', 'TPB': 'Paperback', 'SC': 'Paperback', 'HC': 'Hardcover'}
ORIGINS = {'manga': '', 'manhwa': 'KR', 'manhua': 'CN', 'webtoon': 'KR'}

# known manga/manhwa series: not every volume's blurb mentions the category
KNOWN = {clean_str(name): (name, origin, category) for name, origin, category in (
    ('Blitz', '', 'manga'),
    ('Cagaster', 'JP', 'manga'),
    ('Crueler Than Dead', 'JP', 'manga'),
    ('Fight Class 3', 'KR', 'manhwa'),
    ('Gannibal', 'JP', 'manga'),
    ('Get Schooled', 'KR', 'webtoon'),
    ('Heavenly Demon Reborn!', 'KR', 'manhwa'),
    ('Immortal Regis', 'KR', 'manhwa'),
    ('Neo Faust', 'JP', 'manga'),
    ('One Hundred Tales', 'JP', 'manga'),
    ('Savage Garden', 'KR', 'manhwa'),
    ('Shakespeare Manga Theater', 'JP', 'manga'),
    ('Terror Man', 'KR', 'webtoon'),
    ('The Awl', 'KR', 'manhwa'),
    ('The Breaker', 'KR', 'manhwa'),
    ('The Breaker: New Waves', 'KR', 'manhwa'),
    ('Tomorrow The Birds', 'JP', 'manga'),
    ('Versus Fighting Story', '', 'manga'),
    ('WAKFU', '', 'manga'),
    ('Witch of Mine', 'KR', 'manhwa'),
)}
# keyword matches that are not manga/manhwa/manhua lines
EXCLUDE = {clean_str(k) for k in (
    'Action Panels',                    # how-to journal, blurb mentions "manga story"
    'GG: Life is a Video Game',         # "pop manga" art style only
    'Zombie Makeout Club',              # western webtoon
    'The Art of Zombie Makeout Club',
)}


def isbn13(isbn: str) -> str:
    if len(isbn) != 10:
        return isbn
    isbn = f'978{isbn[:9]}'
    check = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(isbn))
    return f'{isbn}{-check % 10}'


def match_key(key: str, table) -> str | None:
    return max((k for k in table if key.startswith(k)), key=len, default=None)


def parse(product: dict) -> tuple[Series, Info] | None:
    title: str = product['title']
    upper = title.upper()
    if SET.search(upper):
        return None

    words = upper.split()
    format = FORMATS.get(words[-1].strip('.'))
    base = ' '.join(words[:-1] if format else words)
    key = clean_str(base)
    if match_key(key, EXCLUDE):
        return None

    match = VOLUME.search(base)
    tags: list[str] = product['tags']
    if k := match_key(key, KNOWN):
        name, origin, category = KNOWN[k]
    else:
        body = HTML.sub(' ', product['body_html'] or '')
        if m := KEYWORD.search(f'{title} {body}'):
            category = m.group('category').lower()
            origin = ORIGINS[category]
        else:
            return None
        prefix = (base[:match.start()] if match else base).rstrip(' -–:,')
        prefix = prefix.removesuffix(' MANGA')
        pkey = clean_str(prefix)
        name = (next((t for t in tags if clean_str(t) == pkey), '')
                or max((t for t in tags
                        if t != 'Graphic Novel' and not MONTH.fullmatch(t)
                        and pkey.startswith(clean_str(t))),
                       key=len, default='')
                or prefix.title())

    if match:
        volume = match.group('volume').lstrip('0')
        if match.group('omnibus'):
            index = 0
            volume_title = f'{name} Omnibus Vol. {volume}'
        else:
            index = int(volume)
            volume_title = f'{name} Vol. {volume}'
    else:
        index = 1
        volume_title = name

    isbn = isbn13(product['variants'][0]['sku'].removeprefix('G'))
    # site only exposes the release month; day defaults to the 1st
    date = next((datetime.datetime.strptime(t, '%B %Y').date()
                 for t in tags if MONTH.fullmatch(t)), None)
    link = LINK.format(product['handle'])

    serie = Series(None, name, origin, category)
    return serie, Info(serie.key, link, NAME, NAME, volume_title, index,
                       format or 'Paperback', isbn, date)


def scrape_full(series: set[Series], info: set[Info], limit: int = 10000) -> tuple[set[Series], set[Info]]:
    kept = 0
    filtered = 0
    with Session() as session:
        count = 0
        page = 1
        while count < limit:
            resp = session.get(API.format(page))
            products = resp.json()['products']
            if not products:
                break
            for product in products:
                if count >= limit:
                    break
                count += 1
                try:
                    if res := parse(product):
                        kept += 1
                        series.add(res[0])
                        info.discard(res[1])
                        info.add(res[1])
                    else:
                        filtered += 1
                except Exception as e:
                    warnings.warn(f'{product.get("handle")}: {e}', RuntimeWarning)
            page += 1
        print(f'{NAME}: {kept} kept, {filtered} filtered', flush=True)

    return series, info
