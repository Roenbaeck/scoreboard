import requests
import re
import json
import argparse
import time
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from html import unescape

# Common browser User-Agent to avoid detection
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_api_url(url):
    """Fetch HTML for the page and extract the Profixio match API URL plus raw HTML.

    Returns:
        (api_url_or_none, html_content_or_empty)
    """
    html_content = ''
    try:
        print(f"Attempting to fetch content from: {url}")
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        html_content = response.text
        print("Successfully fetched HTML content.")

        print("Searching for all 'wire:effects' attributes...")
        matches = re.findall(r'wire:effects="([^"]+)"', html_content)

        if not matches:
            print("Could not find any 'wire:effects' attributes.")
            return None, html_content

        print(f"Found {len(matches)} 'wire:effects' attribute(s). Checking each one...")

        for i, effects_str_raw in enumerate(matches):
            try:
                effects_str = unescape(effects_str_raw)
                effects_data = json.loads(effects_str)

                if 'scripts' in effects_data and isinstance(effects_data['scripts'], dict):
                    for script_content in effects_data['scripts'].values():
                        api_url_match = re.search(r"apiurl:\s*'([^']*)'", script_content)
                        if api_url_match:
                            dirty_url = api_url_match.group(1)
                            print(f"Found 'apiurl' in effects attribute #{i + 1}.")
                            clean_url = dirty_url.replace('\\/', '/').replace('\\u0026', '&')
                            return clean_url, html_content
            except json.JSONDecodeError:
                continue
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page URL: {e}")
    return None, html_content


def extract_team_colors(html_content):
    """Parse the original match page HTML to map team IDs to jersey colors and names.

    Returns dict: { team_id: { 'color': '#RRGGBB' or 'transparent', 'name': 'Team Name' } }
    """
    team_map = {}
    if not html_content:
        return team_map

    # Limit search to the first big container to reduce noise (optional optimization)
    # Still safe if it fails to find; fallback to full html.
    container_match = re.search(r'<div class="w-full flex justify-around[\s\S]*?</div>\s*</div>?', html_content)
    search_block = container_match.group(0) if container_match else html_content

    anchor_pattern = re.compile(r'<a[^>]+href="([^"]*/teams/(\d+))"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
    for m in anchor_pattern.finditer(search_block):
        team_id = m.group(2)
        inner = m.group(3)
        # Find background color inside the anchor contents
        color_match = re.search(r'background-color:\s*([^;"\s]+)', inner, re.IGNORECASE)
        color = color_match.group(1).upper() if color_match else 'transparent'
        # Derive a name by stripping tags & comments
        cleaned = re.sub(r'<!--.*?-->', ' ', inner, flags=re.DOTALL)
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        # Remove the hex color token if it appears at start
        if color and cleaned.startswith(color):
            cleaned = cleaned[len(color):].strip()
        # Heuristic: keep last 5 words if it's very long
        parts = cleaned.split()
        if len(parts) > 8:
            cleaned = ' '.join(parts[-8:])
        team_map[team_id] = { 'color': color, 'name': cleaned }
    if team_map:
        print(f"Extracted {len(team_map)} team entries: " + ", ".join(f"{tid}:{info['color']}" for tid, info in team_map.items()))
    else:
        print("No team information could be extracted.")
    return team_map

def parse_volleyball_data(api_data, team_color_name_map=None):
    """
    Parses the JSON response from the volleyball API to extract match details.

    Args:
        api_data: A dictionary loaded from the JSON response.

    Returns:
        A formatted string with the summary of the match.
    """
    try:
        gamestate = api_data['gamestate']
        events = api_data['events']
        
        home_team_name = "Home"
        away_team_name = "Away"
        home_team_id = None
        away_team_id = None
        # Build a lookup by team id -> color (from HTML) if provided
        id_to_color = {}
        if team_color_name_map:
            for tid, entry in team_color_name_map.items():
                color = entry.get('color')
                if color:
                    id_to_color[str(tid)] = color
        
        # Prefer ordering from HTML anchors: first = home, second = away
        if team_color_name_map and len(team_color_name_map) == 2:
            ordered = list(team_color_name_map.items())  # preserves insertion order (Py3.7+)
            h_id_str, h_info = ordered[0]
            a_id_str, a_info = ordered[1]
            home_team_id = int(h_id_str) if isinstance(h_id_str, str) and h_id_str.isdigit() else h_id_str
            away_team_id = int(a_id_str) if isinstance(a_id_str, str) and a_id_str.isdigit() else a_id_str
            if h_info.get('name'):
                home_team_name = h_info['name']
            if a_info.get('name'):
                away_team_name = a_info['name']
        else:
            # Derive team names & IDs using scoring events as fallback
            for event in reversed(events):
                if event.get('goals') == 1 and event.get('teamName') and event.get('teamId') is not None:
                    score = event.get('currentScore', {})
                    scorer_team_name = event['teamName']
                    scorer_team_id = event['teamId']
                    if score.get('home') == 1 and score.get('away') == 0:
                        home_team_name = scorer_team_name
                        home_team_id = scorer_team_id
                        # Find the other team
                        for e in events:
                            if e.get('teamName') and e.get('teamId') != home_team_id:
                                away_team_name = e['teamName']
                                away_team_id = e.get('teamId')
                                break
                        break
                    elif score.get('away') == 1 and score.get('home') == 0:
                        away_team_name = scorer_team_name
                        away_team_id = scorer_team_id
                        for e in events:
                            if e.get('teamName') and e.get('teamId') != away_team_id:
                                home_team_name = e['teamName']
                                home_team_id = e.get('teamId')
                                break
                        break
                if home_team_id and away_team_id:
                    break

        # Fallback: if IDs still missing, attempt to infer from first two distinct teamIds encountered
        if not (home_team_id and away_team_id):
            seen = {}
            for e in events:
                tid = e.get('teamId')
                tn = e.get('teamName')
                if tid is not None and tn and tid not in seen:
                    seen[tid] = tn
                if len(seen) == 2:
                    break
            if len(seen) == 2:
                tids = list(seen.keys())
                if not home_team_id:
                    home_team_id, away_team_id = tids[0], tids[1]
                    home_team_name, away_team_name = seen[home_team_id], seen[away_team_id]

        home_sets_won = gamestate['currentScore']['homeGoals']
        away_sets_won = gamestate['currentScore']['awayGoals']

        # Order events chronologically using created_at (oldest -> newest)
        def parse_ts(ev):
            ts = ev.get('created_at') or ev.get('createdAt')
            if not ts:
                return None
            # Normalize Z -> +00:00 for datetime.fromisoformat
            if ts.endswith('Z'):
                ts = ts[:-1] + '+00:00'
            try:
                return datetime.fromisoformat(ts)
            except ValueError:
                return None
        # Annotate with timestamp; keep original order for stable sort among missing timestamps
        indexed = []
        for idx, ev in enumerate(events):
            indexed.append((parse_ts(ev), idx, ev))
        indexed.sort(key=lambda t: (t[0] is None, t[0] or datetime.min, t[1]))
        chronological = [e for _, _, e in indexed]
        latest_event = chronological[-1] if chronological else {}
        current_set_score_home = latest_event.get('currentScore', {}).get('home', 0)
        current_set_score_away = latest_event.get('currentScore', {}).get('away', 0)

        set_scores = gamestate['currentSetScores']
        
        home_color = id_to_color.get(str(home_team_id)) if home_team_id else None
        away_color = id_to_color.get(str(away_team_id)) if away_team_id else None
        color_summary = ''
        if home_color or away_color:
            color_summary = (
                " (Colors: "
                f"{home_team_name}#{home_team_id if home_team_id is not None else ''}:{home_color or 'N/A'}, "
                f"{away_team_name}#{away_team_id if away_team_id is not None else ''}:{away_color or 'N/A'})"
            )

        output = [
            "\n--- Volleyball Match Summary ---",
            f"\nTeams: {home_team_name} vs. {away_team_name}{color_summary}",
            f"\nFinal Score (Sets):",
            f"  - {home_team_name}: {home_sets_won}",
            f"  - {away_team_name}: {away_sets_won}",
            f"\nScore in Final Set:",
            f"  - {home_team_name}: {current_set_score_home}",
            f"  - {away_team_name}: {current_set_score_away}",
            "\nSet-by-Set Breakdown:"
        ]
        for i, scores in enumerate(set_scores):
            output.append(f"  - Set {i+1}: {scores['homeGoals']} - {scores['awayGoals']}")
            
        return "\n".join(output)

    except (KeyError, IndexError) as e:
        return f"An error occurred while parsing the data: {e}. Please check the JSON structure."


def extract_match_state(api_data, team_color_name_map=None, force_lineup=False):
    """Return structured match state for scoreboard rendering.

    Returns dict with keys: home, away each containing id, name, color, sets, points.
    """
    try:
        gamestate = api_data['gamestate']
        events = api_data['events']
    except (KeyError, TypeError):
        return None

    # Reuse logic from parse_volleyball_data (simplified & corrected ordering for current points)
    home_team_name = "Home"
    away_team_name = "Away"
    home_team_id = None
    away_team_id = None

    # Build id->color from HTML map
    id_to_color = {}
    if team_color_name_map:
        for tid, entry in team_color_name_map.items():
            col = entry.get('color')
            if col:
                id_to_color[str(tid)] = col

    # Preferred: ordering from HTML anchors if available
    if team_color_name_map and len(team_color_name_map) == 2:
        ordered = list(team_color_name_map.items())
        h_id_str, h_info = ordered[0]
        a_id_str, a_info = ordered[1]
        home_team_id = int(h_id_str) if isinstance(h_id_str, str) and h_id_str.isdigit() else h_id_str
        away_team_id = int(a_id_str) if isinstance(a_id_str, str) and a_id_str.isdigit() else a_id_str
        if h_info.get('name'):
            home_team_name = h_info['name']
        if a_info.get('name'):
            away_team_name = a_info['name']
    else:
        # Fallback heuristic using scoring events
        for event in reversed(events):
            if event.get('goals') == 1 and event.get('teamName') and event.get('teamId') is not None:
                score = event.get('currentScore', {})
                scorer_team_name = event['teamName']
                scorer_team_id = event['teamId']
                if score.get('home') == 1 and score.get('away') == 0:
                    home_team_name = scorer_team_name
                    home_team_id = scorer_team_id
                    for e in events:
                        if e.get('teamName') and e.get('teamId') != home_team_id:
                            away_team_name = e['teamName']
                            away_team_id = e.get('teamId')
                            break
                    break
                elif score.get('away') == 1 and score.get('home') == 0:
                    away_team_name = scorer_team_name
                    away_team_id = scorer_team_id
                    for e in events:
                        if e.get('teamName') and e.get('teamId') != away_team_id:
                            home_team_name = e['teamName']
                            home_team_id = e.get('teamId')
                            break
                    break
            if home_team_id and away_team_id:
                break

        if not (home_team_id and away_team_id):
            seen = {}
            for e in events:
                tid = e.get('teamId')
                tn = e.get('teamName')
                if tid is not None and tn and tid not in seen:
                    seen[tid] = tn
                if len(seen) == 2:
                    break
            if len(seen) == 2 and not (home_team_id and away_team_id):
                tids = list(seen.keys())
                home_team_id, away_team_id = tids[0], tids[1]
                home_team_name, away_team_name = seen[home_team_id], seen[away_team_id]

    # Check if match has started by looking at the first chronological event
    match_started = False
    in_set = False
    if events:
        indexed = []
        for idx, ev in enumerate(events):
            ts = ev.get('created_at') or ev.get('createdAt')
            if ts:
                if ts.endswith('Z'):
                    ts = ts[:-1] + '+00:00'
                try:
                    parsed_ts = datetime.fromisoformat(ts)
                    indexed.append((parsed_ts, idx, ev))
                except ValueError:
                    indexed.append((None, idx, ev))
            else:
                indexed.append((None, idx, ev))
        indexed.sort(key=lambda t: (t[0] is None, t[0] or datetime.min, t[1]))
        first_event = indexed[0][2] if indexed else None
        if first_event and first_event.get('startsMatch'):
            match_started = True

        # Check if currently in a set
        for _, _, ev in reversed(indexed):
            if ev.get('startsPeriod'):
                in_set = True
                break
            elif ev.get('stopsPeriod'):
                in_set = False
                break

        # Find the most recent highlight event 
        # 468 - Attack
        # 469 - Block
        # 470 - Service Ace
        highlight = None
        last_event = indexed[-1][2] if indexed else None
        if last_event and last_event.get('eventTypeId') in [468, 469, 470] and last_event.get('person'):
            highlight = {
                'description': last_event.get('description', ''),
                'player_name': last_event['person'].get('name', ''),
                'player_number': last_event['person'].get('number', '')
            }
    # Fallback: if scores are present, assume match has started
    if not match_started:
        current_score = gamestate.get('currentScore', {})
        if current_score.get('homeGoals', 0) > 0 or current_score.get('awayGoals', 0) > 0:
            match_started = True

    # Parse lineup if match not started or not in a set
    lineup_data = None
    if (force_lineup or not match_started or not in_set) and 'lineup' in api_data:
        lineup = api_data['lineup']
        home_lineup_dict = {}  # Track unique players by personId
        away_lineup_dict = {}
        
        for player in lineup:
            web_team_id = player.get('webTeamId')
            person_id = player.get('personId')
            
            if player.get('type') == 'player' and person_id:
                player_info = {
                    'number': player.get('number', ''),
                    'name': player.get('name', ''),
                    'libero': player.get('libero', False)
                }
                
                # Only process if we have at least a name
                if player_info['name']:
                    if web_team_id == home_team_id:
                        target_dict = home_lineup_dict
                    elif web_team_id == away_team_id:
                        target_dict = away_lineup_dict
                    else:
                        continue
                    
                    # If we haven't seen this personId before, add them
                    if person_id not in target_dict:
                        target_dict[person_id] = player_info
                    else:
                        # Update existing player info, preferring entries with jersey numbers
                        existing = target_dict[person_id]
                        # If current entry has a number but existing doesn't, update
                        if player_info['number'] and not existing['number']:
                            existing['number'] = player_info['number']
                        # Always update libero status (in case it changed)
                        existing['libero'] = player_info['libero']
        
        # Convert dictionaries back to lists
        home_lineup = list(home_lineup_dict.values())
        away_lineup = list(away_lineup_dict.values())
        
        # Sort lineups by jersey number
        def sort_key(p):
            try:
                num = int(p['number'])
                return num
            except:
                return 999
        home_lineup.sort(key=sort_key)
        away_lineup.sort(key=sort_key)
        lineup_data = {'home': home_lineup, 'away': away_lineup}

    # Detect if match has a terminating event
    match_ended = any((e.get('stopsMatch') is True) for e in events) if isinstance(events, list) else False
    print (f"Match ended status: {'Yes' if match_ended else 'No'}")

    # Sets won
    try:
        home_sets_won = gamestate['currentScore']['homeGoals']
        away_sets_won = gamestate['currentScore']['awayGoals']
    except (KeyError, TypeError):
        home_sets_won = away_sets_won = 0

    # Current set points: order events chronologically by created_at
    def parse_ts(ev):
        ts = ev.get('created_at') or ev.get('createdAt')
        if not ts:
            return None
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return None
    current_home_points = 0
    current_away_points = 0
    if events:
        indexed = []
        for idx, ev in enumerate(events):
            indexed.append((parse_ts(ev), idx, ev))
        indexed.sort(key=lambda t: (t[0] is None, t[0] or datetime.min, t[1]))
        latest = indexed[-1][2]
        cs = latest.get('currentScore', {})
        current_home_points = cs.get('home', 0)
        current_away_points = cs.get('away', 0)

    # Determine serving team: prefer correct key 'teamIdServing' (observed in API), fallback to legacy 'servingTeamId'
    serving_team_id = None
    if isinstance(gamestate, dict):
        serving_team_id = gamestate.get('teamIdServing')
        if serving_team_id is None:
            serving_team_id = gamestate.get('servingTeamId')
    if serving_team_id is None:
        # Fallback: last scoring event's team
        for ev in reversed(events):
            if ev.get('goals') == 1 and ev.get('teamId') is not None:
                serving_team_id = ev['teamId']
                break

    state = {
        'home': {
            'id': home_team_id,
            'name': home_team_name,
            'color': id_to_color.get(str(home_team_id)),
            'sets': home_sets_won,
            'points': current_home_points,
            'serving': serving_team_id == home_team_id
        },
        'away': {
            'id': away_team_id,
            'name': away_team_name,
            'color': id_to_color.get(str(away_team_id)),
            'sets': away_sets_won,
            'points': current_away_points,
            'serving': serving_team_id == away_team_id
        }
    }
    if match_ended:
        state['matchEnded'] = True
    if lineup_data:
        state['lineup'] = lineup_data
    state['matchStarted'] = match_started
    state['forceLineup'] = force_lineup
    state['inSet'] = in_set
    if highlight:
        state['highlight'] = highlight
    # Attach completed set scores for overlay (list of dicts with homeGoals/awayGoals)
    try:
        state['setScores'] = list(gamestate.get('currentSetScores') or [])
    except Exception:
        state['setScores'] = []
    return state


def hex_to_rgb_tuple(hex_color):
    if not hex_color:
        return (128, 128, 128)
    hc = hex_color.strip().lstrip('#')
    if len(hc) == 3:
        hc = ''.join(ch * 2 for ch in hc)
    if len(hc) != 6:
        return (128, 128, 128)
    try:
        return tuple(int(hc[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return (128, 128, 128)


def write_scoreboard_xml(state, output_path):
    """Write (atomically) the scoreboard XML overlay file based on match state."""
    if not state:
        return False
    home = state['home']
    away = state['away']
    hr, hg, hb = hex_to_rgb_tuple(home.get('color'))
    ar, ag, ab = hex_to_rgb_tuple(away.get('color'))
    home_serve_class = 'serve serving' if home.get('serving') else 'serve'
    away_serve_class = 'serve serving' if away.get('serving') else 'serve'
    nbsp = '\u00A0'
    set_scores = state.get('setScores') or []
    # Build ended set score spans (completed sets). We assume provided order is chronological.
    # We'll render each completed set's score for home & away respectively.
    home_ended_fragments = []
    away_ended_fragments = []
    for idx, s in enumerate(set_scores, start=1):
        hgs = s.get('homeGoals')
        ags = s.get('awayGoals')
        # Skip if values missing
        if hgs is None or ags is None:
            continue
        home_ended_fragments.append(f'<div id="home_ended_{idx}" class="ended" data-set="{idx}">{hgs}</div>')
        away_ended_fragments.append(f'<div id="away_ended_{idx}" class="ended" data-set="{idx}">{ags}</div>')

    home_ended_html = '\n        '.join(home_ended_fragments)
    away_ended_html = '\n        '.join(away_ended_fragments)

    # Wrap ended fragments in a container so CSS :last-child can target the final ended cell
    if home_ended_html:
        home_ended_html = '<div class="ended-sets">\n        ' + home_ended_html + '\n        </div>'
    if away_ended_html:
        away_ended_html = '<div class="ended-sets">\n        ' + away_ended_html + '\n        </div>'

    # Conditionally include style for color divs if not transparent
    home_color_style = f' style="background: rgb({hr}, {hg}, {hb});"' if home.get('color') != 'transparent' else ''
    away_color_style = f' style="background: rgb({ar}, {ag}, {ab});"' if away.get('color') != 'transparent' else ''

    # New order: set, color, team, serve, (ended sets), score
    xml_parts = [
        '<div xmlns="http://www.w3.org/1999/xhtml">',
        '    <div id="scoreboard" class="scoreboard">',
        '        <div class="home">',
        f'            <div id="home_set" class="set">{home.get("sets", 0)}</div>',
        f'            <div id="home_color" class="color"{home_color_style}>{nbsp}</div>',
        f'            <div id="home_team" class="team" contenteditable="true">{home.get("name","Home")}</div>',
        f'            <div id="home_serve" class="{home_serve_class}">{nbsp}</div>'
    ]
    if home_ended_html:
        for line in home_ended_html.split('\n'):
            if line.strip():
                xml_parts.append('        ' + line.strip())
    match_ended_flag = state.get('matchEnded')
    if not match_ended_flag:
        xml_parts.append(f'        <div id="home_score" class="score">{home.get("points",0)}</div>')
    xml_parts.append('    </div>')  # close home div
    xml_parts.append('    <div class="away">')
    xml_parts.append(f'        <div id="away_set" class="set">{away.get("sets", 0)}</div>')
    xml_parts.append(f'        <div id="away_color" class="color"{away_color_style}>{nbsp}</div>')
    xml_parts.append(f'        <div id="away_team" class="team" contenteditable="true">{away.get("name","Away")}</div>')
    xml_parts.append(f'        <div id="away_serve" class="{away_serve_class}">{nbsp}</div>')
    if away_ended_html:
        for line in away_ended_html.split('\n'):
            if line.strip():
                xml_parts.append('        ' + line.strip())
    if not match_ended_flag:
        xml_parts.append(f'        <div id="away_score" class="score">{away.get("points",0)}</div>')
    xml_parts.append('    </div>')  # close away div
    xml_parts.append('    </div>')  # close scoreboard div
    if 'lineup' in state and (state.get('forceLineup', False) or not state.get('matchStarted', True) or not state.get('inSet', False)):
        xml_parts.append('    <div id="lineup" class="lineup">')
        xml_parts.append('        <div class="home_team">')
        xml_parts.append(f'            <div id="home_team_name" class="team_name">{home.get("name","Home")}</div>')
        xml_parts.append('            <div id="home_lineup" class="home_lineup">')
        for player in state['lineup']['home']:
            libero_class = ' libero' if player.get('libero') else ''
            xml_parts.append(f'                <div class="player{libero_class}">')
            xml_parts.append(f'                    <div class="number">{player["number"]}</div>')
            xml_parts.append(f'                    <div class="name">{player["name"]}</div>')
            xml_parts.append('                </div>')
        xml_parts.append('            </div>')
        xml_parts.append('        </div>')
        xml_parts.append('        <div class="away_team">')
        xml_parts.append(f'            <div id="away_team_name" class="team_name">{away.get("name","Away")}</div>')
        xml_parts.append('            <div id="away_lineup" class="away_lineup">')
        for player in state['lineup']['away']:
            libero_class = ' libero' if player.get('libero') else ''
            xml_parts.append(f'                <div class="player{libero_class}">')
            xml_parts.append(f'                    <div class="number">{player["number"]}</div>')
            xml_parts.append(f'                    <div class="name">{player["name"]}</div>')
            xml_parts.append('                </div>')
        xml_parts.append('            </div>')
        xml_parts.append('        </div>')
        xml_parts.append('    </div>')
    if 'highlight' in state:
        xml_parts.append('<div id="highlight" class="highlight">')
        xml_parts.append(f'    <div class="highlight_desc">{state["highlight"]["description"]}</div>')
        xml_parts.append(f'    <div class="highlight_player">{state["highlight"]["player_number"]} {state["highlight"]["player_name"]}</div>')
        xml_parts.append('</div>')
    xml_parts.append('</div>')
    xml_content = '\n'.join(xml_parts)
    tmp_path = output_path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        os.replace(tmp_path, output_path)
        return True
    except OSError as e:
        print(f"Failed writing scoreboard XML: {e}")
        return False

def main(argv=None):
    """Entry point for command-line execution.

    The script now requires an explicit full Profixio competition page URL.

    Example:
      python scraper.py https://www.profixio.com/app/lx/competition/leagueid17734?expandmatch=32334711
    """
    parser = argparse.ArgumentParser(description="Fetch / follow a volleyball match from a Profixio competition page URL.")
    parser.add_argument("page_url", help="Full Profixio page URL containing ?expandmatch=<matchId>.")
    parser.add_argument("--daemon", action="store_true", help="Run continuously: refresh page every minute & poll API every second.")
    parser.add_argument("--page-refresh-interval", type=int, default=60, help="Seconds between refreshing original page (default: 60)")
    parser.add_argument("--api-interval", type=float, default=1.0, help="Seconds between API polls (default: 1.0)")
    parser.add_argument("--output", default=os.path.join('html', 'scoreboard.xml'), help="Path to write scoreboard XML (default: html/scoreboard.xml)")
    parser.add_argument("--no-summary", action="store_true", help="Suppress textual summary output (useful in daemon mode)")
    parser.add_argument("--dump-json", help="If set, write the latest raw API JSON to this file for debugging home/away mapping.")
    parser.add_argument("--force-lineup", action="store_true", help="Force display of lineups even if match has started.")
    args = parser.parse_args(argv)

    page_url = args.page_url.strip()

    # Validate presence of expandmatch regardless of its position in query string
    parsed = urlparse(page_url)
    query_params = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
    if 'expandmatch' not in query_params or not query_params['expandmatch']:
        parser.error("Provided URL must include an 'expandmatch' query parameter (e.g. ?expandmatch=123 or &expandmatch=123).")

    match_id = query_params['expandmatch'][0]
    print(f"Using page URL: {page_url} (match id: {match_id})")

    def single_cycle():
        api_url_local, html_content_local = get_api_url(page_url)
        tcm = extract_team_colors(html_content_local)
        return api_url_local, tcm

    api_url, team_color_map = single_cycle()
    if not api_url:
        print("Could not locate API URL on initial fetch. Exiting.")
        return 1

    print(f"\nSuccessfully Found API URL: {api_url}")

    last_page_refresh = time.time()

    if not args.daemon:
        try:
            api_response = requests.get(api_url, headers=HEADERS)
            api_response.raise_for_status()
            api_data = api_response.json()
            if args.dump_json:
                try:
                    with open(args.dump_json, 'w', encoding='utf-8') as jf:
                        json.dump(api_data, jf, ensure_ascii=False, indent=2)
                    print(f"Raw API JSON written to {args.dump_json}")
                except OSError as e:
                    print(f"Failed to write dump JSON: {e}")
            if not args.no_summary:
                match_summary = parse_volleyball_data(api_data, team_color_map)
                print(match_summary)
            state = extract_match_state(api_data, team_color_map, force_lineup=args.force_lineup)
            if state:
                write_scoreboard_xml(state, args.output)
                print(f"Scoreboard written to {args.output}")
        except requests.exceptions.RequestException as e:
            print(f"Error fetching API data: {e}")
            return 2
        except json.JSONDecodeError:
            print("Error: Could not decode the response from the API as JSON.")
            return 3
        return 0

    # Daemon mode
    print("Entering daemon mode. Press Ctrl+C to stop.")
    cycles = 0
    while True:
        now = time.time()
        # Refresh page (API URL & team colors) if interval passed or API expired errors encountered
        if now - last_page_refresh >= args.page_refresh_interval:
            print("[Daemon] Refreshing original page for updated API URL & team colors...")
            new_api_url, new_team_map = single_cycle()
            if new_api_url:
                api_url = new_api_url
            if new_team_map:
                team_color_map = new_team_map
            last_page_refresh = now

        try:
            api_response = requests.get(api_url, timeout=10, headers=HEADERS)
            if api_response.status_code == 403:
                # Possibly expired signature; force refresh next loop
                print("[Daemon] API returned 403; forcing page refresh next cycle.")
                last_page_refresh = 0
                time.sleep(args.api_interval)
                continue
            api_response.raise_for_status()
            api_data = api_response.json()
            if args.dump_json:
                try:
                    with open(args.dump_json, 'w', encoding='utf-8') as jf:
                        json.dump(api_data, jf, ensure_ascii=False, indent=2)
                except OSError:
                    pass
            state = extract_match_state(api_data, team_color_map, force_lineup=args.force_lineup)
            if state:
                if write_scoreboard_xml(state, args.output):
                    if cycles % 10 == 0:  # reduce chatter
                        print(f"[Daemon] Updated scoreboard (home {state['home']['points']} - away {state['away']['points']})")
                if state.get('matchEnded'):
                    print("[Daemon] Match has ended. Stopping daemon.")
                    break
            else:
                print("[Daemon] Could not extract match state from API data.")
        except requests.exceptions.RequestException as e:
            print(f"[Daemon] Error polling API: {e}")
        except json.JSONDecodeError:
            print("[Daemon] JSON decode error from API response.")
        except KeyboardInterrupt:
            print("\nDaemon stopped by user.")
            break
        cycles += 1
        try:
            time.sleep(args.api_interval)
        except KeyboardInterrupt:
            print("\nDaemon stopped by user.")
            break
    return 0


if __name__ == "__main__":
    exit_code = main()
    raise SystemExit(exit_code)
