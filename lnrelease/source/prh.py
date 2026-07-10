import datetime
import warnings
from urllib.parse import urljoin

from session import Session
from utils import FORMATS, Info, Series, find_series

NAME = 'Penguin Random House'
NON_FORMATS = ('Boxed Set', 'Non-traditional book')
CATEGORIES = ('Manga', 'Manhwa', 'Manhua', 'Webtoon', 'Graphic Novel')
CATEGORY_TAGS = {
    'Manhwa': ('KR', 'manhwa'),
    'Manhua': ('CN', 'manhua'),
    'Webtoon': ('', 'webtoon'),
}
# PRH-distributed imprints (code, publisher attribution)
IMPRINTS = (
    ('VT', 'Kodansha'),            # Vertical
    ('V4', 'Kodansha'),            # Vertical Comics
    ('KM', 'Kodansha'),            # Kodansha Comics
    ('209', 'TOKYOPOP'),
    ('204', 'TOKYOPOP'),           # Disney Manga
    ('210', 'TOKYOPOP'),           # TOKYOPOP Classics
    ('344', 'TOKYOPOP'),           # TOKYOPOP Kids
    ('205', 'TOKYOPOP'),           # International Women of Manga
    ('KN', 'Dark Horse'),          # Dark Horse Manga
    ('334', 'Dark Horse'),         # Dark Horse Manhwa
    ('DH', 'Dark Horse'),          # Dark Horse Books
    ('HO', 'Dark Horse'),          # Dark Horse Originals
    ('140', 'Titan Comics'),       # Titan Manga
    ('181', 'Inklore'),
    ('198', 'WEBTOON Unscrolled'),
    ('41', 'Square Enix'),         # Square Enix Manga
    ('182', 'Square Enix'),        # Manga UP!
)


def scrape_imprint(session: Session, series: set[Series], info: set[Info],
                   imprint: str, publisher: str, limit: int) -> None:
    params = {'sort': 'onsale',
              'dir': 'desc',
              'rows': limit,
              'zoom': 'https://api.penguinrandomhouse.com/title/titles/definition',
              'imprintCode': imprint}
    page = session.get('https://www.penguinrandomhouse.ca/api/enhanced/works', params=params)

    jsn = page.json()
    for book in jsn['data']:
        title = book['title'].replace(' (paperback)', '')
        serie = find_series(title, series) or Series(None, title)

        for variant in book['_embeds'][0]['titles']:
            if variant['graphicCategory'] not in CATEGORIES:
                continue
            if signal := CATEGORY_TAGS.get(variant['graphicCategory']):
                serie.origin = serie.origin or signal[0]
                serie.category = serie.category or signal[1]
            isbn = variant['isbn']
            date = datetime.date.fromisoformat(variant['onsale'])
            url = urljoin('https://www.penguinrandomhouse.com/', variant['seoFriendlyUrl'])
            format = variant['format']['description']
            if format in NON_FORMATS:
                continue
            elif format not in FORMATS:
                for f in FORMATS:
                    if f in format:
                        format = f
                        break
                else:
                    warnings.warn(f'Unknown PRH format: {format}', RuntimeWarning)
                    continue
            if language := variant['language'] != 'E':
                warnings.warn(f'Non-E PRH language: {language}', RuntimeWarning)
                continue

            inf = Info(serie.key, url, NAME, publisher, title, 0, format, isbn, date)
            info.discard(inf)
            info.add(inf)
            series.add(serie)


def scrape_full(series: set[Series], info: set[Info], limit: int = 1000) -> tuple[set[Series], set[Info]]:
    with Session() as session:
        for imprint, publisher in IMPRINTS:
            try:
                scrape_imprint(session, series, info, imprint, publisher, limit)
            except Exception as e:
                warnings.warn(f'PRH imprint {imprint} ({publisher}): {e}', RuntimeWarning)
    return series, info


def scrape(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    return scrape_full(series, info, 100)
