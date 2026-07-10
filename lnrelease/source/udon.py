import datetime
import re
import warnings

from session import Session
from utils import Info, Series

NAME = 'Udon Entertainment'

# udonentertainment.com 302s to store.udonentertainment.com;
# request the apex so the configured rate limits apply
SITE = 'https://udonentertainment.com'
PRODUCTS = f'{SITE}/products.json?limit=250&page={{}}'
PRODUCT = f'{SITE}/products/{{}}.js'

VOLUME = re.compile(r'(?P<title>.+?)[,.:]?\s+Vol(?:ume|\.)\s*(?P<volume>\d+(?:\.\d+)?|[IVX]+)\b', re.IGNORECASE)
EDITION = re.compile(r'\s*[-–—(]*\s*(?:UDON STORE\s+)?'
                     r'(?:Exclusive|Standard|Deluxe|Hardcover|Softcover|Paperback|HC|SC|Edition)'
                     r'(?:\s+(?:Exclusive|Standard|Deluxe|Hardcover|Softcover|Paperback|HC|SC|Edition))*'
                     r'\)?\s*$', re.IGNORECASE)
MONTH = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
         'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')
DATE = re.compile(r'SHIP(?:PING|S)[:\s]+(?:IN\s+)?(?:EARLY\s+|MID[-\s]?|LATE\s+)?'
                  r'(?P<month>JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUNE?'
                  r'|JULY?|AUG(?:UST)?|SEPT?(?:EMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)'
                  r'\.?,?\s+(?P<year>20\d\d)', re.IGNORECASE)
ROMAN = {'I': 1, 'V': 5, 'X': 10}


def roman(numeral: str) -> int:
    total = 0
    prev = 0
    for c in reversed(numeral.upper()):
        value = ROMAN[c]
        total += value if value >= prev else -value
        prev = value
    return total


def get_format(product: dict) -> str:
    text = f'{product["title"]} {product["body_html"]}'.lower()
    if 'hardcover' in text:
        return 'Hardcover'
    elif 'paperback' in text or 'softcover' in text:
        return 'Paperback'
    return 'Physical'


def get_date(product: dict) -> datetime.date | None:
    if match := DATE.search(product['body_html']):
        month = MONTH.index(match.group('month')[:3].upper()) + 1
        return datetime.date(int(match.group('year')), month, 1)
    return None


def get_isbn(session: Session, product: dict) -> str:
    page = session.get(PRODUCT.format(product['handle']))
    if page is None:
        return ''
    barcode = re.sub(r'\D', '', page.json()['variants'][0].get('barcode') or '')
    if len(barcode) == 13 and barcode.startswith(('978', '979')):
        return barcode
    return ''


def parse(session: Session, product: dict) -> tuple[Series, set[Info]]:
    title = product['title']
    tags = set(product['tags'])
    if {'Catalog_Art Books', 'Catalog_Artist Editions'} & tags:
        category = 'artbook'
    elif 'Catalog_Manga' in tags:
        category = 'manga'
    else:
        category = ''

    if match := VOLUME.match(title):
        volume = match.group('volume')
        index = roman(volume) if volume.upper().strip('IVX') == '' and not volume.isdigit() else int(float(volume))
        series = Series(None, match.group('title').strip(' ,.:-–'), '', category)
    else:
        index = 1
        stripped = title
        while match := EDITION.search(stripped):
            stripped = stripped[:match.start()]
        series = Series(None, stripped or title, '', category)

    link = f'{SITE}/products/{product["handle"]}'
    format = get_format(product)
    isbn = get_isbn(session, product)
    date = get_date(product)
    return series, {Info(series.key, link, NAME, NAME, title, index, format, isbn, date)}


def scrape_full(series: set[Series], info: set[Info], limit: int = 10000) -> tuple[set[Series], set[Info]]:
    kept = 0
    filtered = 0
    with Session() as session:
        for page in range(1, 100):
            res = session.get(PRODUCTS.format(page))
            products = res.json()['products']
            if not products:
                break
            for product in products:
                if product['product_type'] != 'Book':
                    filtered += 1
                    continue
                if kept >= limit:
                    continue
                kept += 1
                try:
                    serie, inf = parse(session, product)
                    series.add(serie)
                    info -= inf
                    info |= inf
                except Exception as e:
                    warnings.warn(f'{product["handle"]}: {e}', RuntimeWarning)
            if kept >= limit:
                break
    print(f'{NAME}: {kept} kept, {filtered} filtered', flush=True)

    return series, info


def scrape(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    return scrape_full(series, info)
