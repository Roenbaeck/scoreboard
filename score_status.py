"""Derive API data from the same saved scoreboard used by the overlay.

Both the manual controller and scraper write scoreboard.xml. Reading that one
source avoids stale JSON sidecars when the operator switches between them.
"""
from pathlib import Path
import re
from string import punctuation
import unicodedata

from bs4 import BeautifulSoup

MAX_XML_BYTES = 256 * 1024


def read_score(path):
    with Path(path).open('rb') as source:
        data = source.read(MAX_XML_BYTES + 1)
    if len(data) > MAX_XML_BYTES:
        raise ValueError('Scoreboard too large')
    # Existing overlays are XHTML fragments, sometimes with unescaped '&'.
    # html.parser tolerates those and never resolves external XML entities.
    soup = BeautifulSoup(data.decode('utf-8'), 'html.parser')
    board = soup.find(id='scoreboard')
    if board is None:
        raise ValueError('Missing scoreboard')

    def field(identifier, optional=False):
        elements = board.find_all(id=identifier)
        if not elements and optional:
            return None
        if len(elements) != 1:
            raise ValueError('Missing or ambiguous score field')
        return elements[0].get_text().strip()

    def counter(value):
        if not re.fullmatch(r'[0-9]{1,6}', value):
            raise ValueError('Invalid score')
        return int(value)

    home_points, away_points = field('home_score', True), field('away_score', True)
    if (home_points is None) != (away_points is None):
        raise ValueError('Incomplete points')
    ended = home_points is None  # The scraper removes both points at match end.
    score = {'matchEnded': ended}
    for side, points in (('home', home_points), ('away', away_points)):
        name = field(f'{side}_team')
        if not name:
            raise ValueError('Missing team name')
        score[side] = {'name': name, 'sets': counter(field(f'{side}_set')),
                       'points': 0 if ended else counter(points)}
    return score


def _display_name(value):
    # One bounded line, preserving normal Unicode, RTL scripts, and emoji.
    value = ''.join(' ' if unicodedata.category(char) == 'Cc'
                    or ord(char) in range(0x202A, 0x202F)
                    or ord(char) in range(0x2066, 0x206A) else char for char in value)
    value = ' '.join(value.split())
    value = value[:79] + '…' if len(value) > 80 else value
    # Names are data, not Markdown. Escape punctuation after bounding the name
    # so backslashes, emphasis, links, HTML, and entities stay literal.
    return ''.join('\\' + char if char in punctuation else char for char in value)


def format_status(score):
    """All sport-specific vocabulary and layout stay on the server."""
    home, away = score['home'], score['away']
    title = f"**{_display_name(home['name'])} – {_display_name(away['name'])}**"
    if score['matchEnded']:
        return f"{title}\n**Final: {home['sets']}–{away['sets']}**"
    return (f"{title}\nSets: {home['sets']}–{away['sets']}"
            f"\n**Points: {home['points']}–{away['points']}**")
