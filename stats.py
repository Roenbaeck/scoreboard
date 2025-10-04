#!/usr/bin/env python3
"""
Volleyball Player Statistics Analyzer

Analyzes player performance from Profixio match data JSON dumps.
Generates detailed statistics including points, scoring breakdowns, and performance metrics.

Usage: python3 stats.py completed.json
"""

import json
import sys
import argparse
import os
from collections import defaultdict, Counter
from datetime import datetime

# Event type mappings based on the JSON data
EVENT_TYPES = {
    468: "Attack",      # Anfall
    469: "Block",       # Block 
    470: "Service Ace", # Serveess
    480: "Serve",       # Serve (general)
    484: "Opponent Error", # Motståndarmisstag
    # Add more as discovered in the data
}

def parse_match_data(json_file):
    """Parse the JSON file and extract match data."""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: File '{json_file}' not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{json_file}': {e}")
        sys.exit(1)

def extract_team_info(data):
    """Extract team names and IDs from the match data."""
    teams = {}
    events = data.get('events', [])
    
    for event in events:
        team_id = event.get('teamId')
        team_name = event.get('teamName')
        if team_id and team_name and team_id not in teams:
            teams[team_id] = team_name
    
    return teams

def analyze_player_stats(data):
    """Analyze player statistics from match events."""
    events = data.get('events', [])
    teams = extract_team_info(data)
    
    # Player statistics storage
    player_stats = defaultdict(lambda: {
        'name': '',
        'number': '',
        'team_id': None,
        'team_name': '',
        'total_points': 0,
        'attacks': 0,
        'blocks': 0,
        'aces': 0,
        'serves': 0,
        'events': [],
        'points_by_type': defaultdict(int),
        'periods': set()
    })
    
    # Team statistics
    team_stats = defaultdict(lambda: {
        'name': '',
        'total_points': 0,
        'opponent_errors': 0,
        'events': []
    })
    
    # Process each event
    for event in events:
        team_id = event.get('teamId')
        team_name = event.get('teamName', '')
        event_type_id = event.get('eventTypeId')
        goals = event.get('goals') or 0
        period = event.get('period', 0)
        person = event.get('person')
        description = event.get('description', '')
        
        # Update team stats
        if team_id:
            team_stats[team_id]['name'] = team_name
            team_stats[team_id]['events'].append(event)
            
            if goals > 0:
                team_stats[team_id]['total_points'] += goals
                
                # Track opponent errors separately
                if event_type_id == 484:  # Opponent error
                    team_stats[team_id]['opponent_errors'] += goals
        
        # Process player events
        if person and goals > 0:
            person_id = person.get('personId')
            if not person_id:
                continue
                
            player = player_stats[person_id]
            player['name'] = person.get('name', '')
            player['number'] = person.get('number', '')
            player['team_id'] = team_id
            player['team_name'] = team_name
            player['total_points'] += goals
            player['periods'].add(period)
            player['events'].append(event)
            
            # Categorize by event type
            event_name = EVENT_TYPES.get(event_type_id, f"Unknown_{event_type_id}")
            player['points_by_type'][event_name] += goals
            
            # Individual counters
            if event_type_id == 468:  # Attack
                player['attacks'] += goals
            elif event_type_id == 469:  # Block
                player['blocks'] += goals
            elif event_type_id == 470:  # Service Ace
                player['aces'] += goals
            elif event_type_id == 480:  # Serve (general)
                player['serves'] += goals
    
    return dict(player_stats), dict(team_stats)

def calculate_advanced_stats(player_stats, team_stats):
    """Calculate advanced statistics and rankings."""
    for player_id, stats in player_stats.items():
        # Points per period played
        periods_played = len(stats['periods'])
        stats['periods_played'] = periods_played
        stats['points_per_period'] = stats['total_points'] / max(periods_played, 1)
        
        # Scoring efficiency (what percentage of team's points did this player contribute?)
        team_id = stats['team_id']
        if team_id and team_id in team_stats:
            team_total = team_stats[team_id]['total_points']
            stats['team_contribution_pct'] = (stats['total_points'] / max(team_total, 1)) * 100
        else:
            stats['team_contribution_pct'] = 0
    
    return player_stats

def print_team_summary(team_stats):
    """Print a summary of team performance."""
    print("=" * 80)
    print("TEAM SUMMARY")
    print("=" * 80)
    
    for team_id, stats in team_stats.items():
        print(f"\n{stats['name']} (ID: {team_id})")
        print(f"  Total Points: {stats['total_points']}")
        print(f"  Points from Opponent Errors: {stats['opponent_errors']}")
        print(f"  Points from Player Actions: {stats['total_points'] - stats['opponent_errors']}")

def print_player_stats_table(player_stats):
    """Print a formatted table of player statistics."""
    if not player_stats:
        print("No player statistics found.")
        return
    
    # Sort players by total points (descending)
    sorted_players = sorted(
        player_stats.items(), 
        key=lambda x: x[1]['total_points'], 
        reverse=True
    )
    
    print("\n" + "=" * 120)
    print("PLAYER PERFORMANCE STATISTICS")
    print("=" * 120)
    
    # Header
    print(f"{'Rank':<4} {'#':<3} {'Player Name':<20} {'Team':<15} {'Pts':<4} {'Att':<4} {'Blk':<4} {'Ace':<4} {'Srv':<4} {'PPP':<5} {'Team%':<6} {'Periods'}")
    print("-" * 120)
    
    # Player rows
    for rank, (player_id, stats) in enumerate(sorted_players, 1):
        if stats['total_points'] == 0:
            continue  # Skip players with no points
            
        print(f"{rank:<4} "
              f"{stats['number']:<3} "
              f"{stats['name']:<20} "
              f"{stats['team_name'][:14]:<15} "
              f"{stats['total_points']:<4} "
              f"{stats['attacks']:<4} "
              f"{stats['blocks']:<4} "
              f"{stats['aces']:<4} "
              f"{stats['serves']:<4} "
              f"{stats['points_per_period']:<5.1f} "
              f"{stats['team_contribution_pct']:<5.1f}% "
              f"{stats['periods_played']}")

def print_detailed_breakdown(player_stats, top_n=10):
    """Print detailed scoring breakdown for top players."""
    sorted_players = sorted(
        player_stats.items(), 
        key=lambda x: x[1]['total_points'], 
        reverse=True
    )
    
    print(f"\n" + "=" * 80)
    print(f"DETAILED SCORING BREAKDOWN (Top {top_n})")
    print("=" * 80)
    
    for i, (player_id, stats) in enumerate(sorted_players[:top_n]):
        if stats['total_points'] == 0:
            continue
            
        print(f"\n#{i+1} {stats['name']} (#{stats['number']}) - {stats['team_name']}")
        print(f"Total Points: {stats['total_points']} | Efficiency: {stats['points_per_period']:.1f} pts/period | Team Contribution: {stats['team_contribution_pct']:.1f}%")
        
        # Breakdown by scoring type
        for score_type, count in stats['points_by_type'].items():
            if count > 0:
                percentage = (count / stats['total_points']) * 100
                print(f"  {score_type}: {count} ({percentage:.1f}%)")
        
        print(f"Active in periods: {sorted(stats['periods'])}")

def print_team_rankings(player_stats):
    """Print rankings by team."""
    teams = {}
    for player_id, stats in player_stats.items():
        if stats['total_points'] > 0:
            team_name = stats['team_name']
            if team_name not in teams:
                teams[team_name] = []
            teams[team_name].append(stats)
    
    print(f"\n" + "=" * 80)
    print("TOP SCORERS BY TEAM")
    print("=" * 80)
    
    for team_name, players in teams.items():
        players.sort(key=lambda x: x['total_points'], reverse=True)
        print(f"\n{team_name}:")
        for i, player in enumerate(players[:5]):  # Top 5 per team
            print(f"  {i+1}. {player['name']} (#{player['number']}): {player['total_points']} pts")

def analyze_scoring_patterns(player_stats):
    """Analyze overall scoring patterns."""
    all_events = []
    scoring_types = defaultdict(int)
    
    for player_id, stats in player_stats.items():
        for event in stats['events']:
            all_events.append(event)
            event_type = EVENT_TYPES.get(event.get('eventTypeId'), 'Unknown')
            scoring_types[event_type] += event.get('goals', 0)
    
    print(f"\n" + "=" * 80)
    print("MATCH SCORING ANALYSIS")
    print("=" * 80)
    
    total_player_points = sum(scoring_types.values())
    print(f"Total points from player actions: {total_player_points}")
    
    for score_type, count in sorted(scoring_types.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            percentage = (count / total_player_points) * 100 if total_player_points > 0 else 0
            print(f"  {score_type}: {count} ({percentage:.1f}%)")
    
    return scoring_types

def generate_html_report(player_stats, team_stats, match_data, output_file="volleyball_stats.html"):
    """Generate an HTML report with all statistics."""
    
    # Extract match result information
    gamestate = match_data.get('gamestate', {})
    current_score = gamestate.get('currentScore', {})
    set_scores = gamestate.get('currentSetScores', [])
    
    # Determine team names and final set score
    team_names = list(team_stats.keys())
    if len(team_names) >= 2:
        home_team_name = list(team_stats.values())[0]['name']
        away_team_name = list(team_stats.values())[1]['name']
    else:
        home_team_name = "Team 1"
        away_team_name = "Team 2"
    
    final_home_sets = current_score.get('homeGoals', 0)
    final_away_sets = current_score.get('awayGoals', 0)
    
    # Sort players by total points
    sorted_players = sorted(
        player_stats.items(), 
        key=lambda x: x[1]['total_points'], 
        reverse=True
    )
    
    # Get team rankings
    teams = {}
    for player_id, stats in player_stats.items():
        if stats['total_points'] > 0:
            team_name = stats['team_name']
            if team_name not in teams:
                teams[team_name] = []
            teams[team_name].append(stats)
    
    for team_name, players in teams.items():
        players.sort(key=lambda x: x['total_points'], reverse=True)
    
    # Calculate scoring patterns
    scoring_types = defaultdict(int)
    for player_id, stats in player_stats.items():
        for score_type, count in stats['points_by_type'].items():
            scoring_types[score_type] += count
    
    total_player_points = sum(scoring_types.values())
    
    # Generate HTML
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Volleyball Match Statistics</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #2c3e50;
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 3px solid #3498db;
            padding-bottom: 15px;
        }}
        
        h2 {{
            color: #34495e;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 10px;
            margin-top: 40px;
        }}
        
        .team-summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        
        .team-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 5px solid #3498db;
        }}
        
        .team-name {{
            font-size: 1.2em;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
        }}
        
        .stat-row {{
            display: flex;
            justify-content: space-between;
            margin: 5px 0;
        }}
        
        .stats-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
        }}
        
        .stats-table th,
        .stats-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        
        .stats-table th {{
            background-color: #3498db;
            color: white;
            font-weight: bold;
            position: sticky;
            top: 0;
        }}
        
        .stats-table tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        
        .stats-table tr:hover {{
            background-color: #e8f4f8;
        }}
        
        .rank-1 {{ background-color: #f1c40f !important; color: #2c3e50; }}
        .rank-2 {{ background-color: #95a5a6 !important; color: white; }}
        .rank-3 {{ background-color: #e67e22 !important; color: white; }}
        
        .player-detail {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            border-left: 4px solid #3498db;
        }}
        
        .player-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        
        .player-name {{
            font-size: 1.3em;
            font-weight: bold;
            color: #2c3e50;
        }}
        
        .player-stats {{
            font-size: 0.9em;
            color: #7f8c8d;
        }}
        
        .scoring-breakdown {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin: 10px 0;
        }}
        
        .score-type {{
            background: #3498db;
            color: white;
            padding: 8px 12px;
            border-radius: 20px;
            font-size: 0.9em;
        }}
        
        .chart-container {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        
        .chart-bar {{
            display: flex;
            align-items: center;
            margin: 10px 0;
        }}
        
        .chart-label {{
            width: 140px;
            min-width: 140px;
            font-weight: bold;
            flex-shrink: 0;
        }}
        
        .chart-progress {{
            flex: 1;
            height: 20px;
            background: #ecf0f1;
            border-radius: 10px;
            margin: 0 15px;
            position: relative;
        }}
        
        .chart-fill {{
            height: 100%;
            background: linear-gradient(90deg, #3498db, #2ecc71);
            border-radius: 10px;
        }}
        
        .chart-value {{
            width: 120px;
            min-width: 120px;
            text-align: right;
            font-weight: bold;
            flex-shrink: 0;
        }}
        
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        
        .summary-card {{
            text-align: center;
            background: #3498db;
            color: white;
            padding: 20px;
            border-radius: 8px;
        }}
        
        .summary-number {{
            font-size: 2em;
            font-weight: bold;
            display: block;
        }}
        
        .summary-label {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        
        @media (max-width: 768px) {{
            .container {{ padding: 15px; }}
            .stats-table {{ font-size: 0.9em; }}
            .player-header {{ flex-direction: column; align-items: flex-start; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏐 Volleyball Match Statistics</h1>
        
        <div style="text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; border-radius: 10px; margin: 20px 0;">
            <h2 style="margin: 0 0 15px 0; font-size: 1.8em; color: white; border: none; padding: 0;">Match Result</h2>
            <div style="font-size: 2.2em; font-weight: bold; margin: 10px 0;">
                {home_team_name} {final_home_sets} - {final_away_sets} {away_team_name}
            </div>"""
    
    # Add individual set scores if available (filter out unplayed sets)
    played_sets = [score for score in set_scores if score.get('homeGoals', 0) > 0 or score.get('awayGoals', 0) > 0]
    
    if played_sets:
        html_content += """
            <div style="font-size: 1.2em; margin-top: 20px; opacity: 0.95;">
                <strong>Set Scores:</strong>
            </div>
            <div style="display: flex; justify-content: center; gap: 20px; margin-top: 10px; flex-wrap: wrap;">"""
        
        for i, score in enumerate(played_sets, 1):
            home_score = score.get('homeGoals', 0)
            away_score = score.get('awayGoals', 0)
            
            # Determine set winner for styling
            winner_style = ""
            if home_score > away_score:
                winner_style = "border-bottom: 3px solid #f39c12;"
            elif away_score > home_score:
                winner_style = "border-bottom: 3px solid #f39c12;"
            
            html_content += f"""
                <div style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 8px; {winner_style}">
                    <div style="font-size: 0.9em; opacity: 0.8;">Set {i}</div>
                    <div style="font-size: 1.1em; font-weight: bold;">{home_score} - {away_score}</div>
                </div>"""
        
        html_content += """
            </div>"""
    
    html_content += """
        </div>
        
        <h2>Team Performance Summary</h2>
        <div class="team-summary">
"""
    
    # Add team cards
    for team_id, stats in team_stats.items():
        player_points = stats['total_points'] - stats['opponent_errors']
        html_content += f"""
            <div class="team-card">
                <div class="team-name">{stats['name']}</div>
                <div class="stat-row">
                    <span>Total Points:</span>
                    <strong>{stats['total_points']}</strong>
                </div>
                <div class="stat-row">
                    <span>Player Actions:</span>
                    <span>{player_points}</span>
                </div>
                <div class="stat-row">
                    <span>Opponent Errors:</span>
                    <span>{stats['opponent_errors']}</span>
                </div>
            </div>
"""
    
    # Player performance table
    html_content += """
        </div>
        
        <h2>Player Performance Rankings</h2>
        <table class="stats-table">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>#</th>
                    <th>Player Name</th>
                    <th>Team</th>
                    <th>Total Pts</th>
                    <th>Attacks</th>
                    <th>Blocks</th>
                    <th>Aces</th>
                    <th>PPP</th>
                    <th>Team %</th>
                    <th>Periods</th>
                </tr>
            </thead>
            <tbody>
"""
    
    # Add player rows
    for rank, (player_id, stats) in enumerate(sorted_players, 1):
        if stats['total_points'] == 0:
            continue
            
        rank_class = ""
        if rank == 1:
            rank_class = "rank-1"
        elif rank == 2:
            rank_class = "rank-2"
        elif rank == 3:
            rank_class = "rank-3"
            
        html_content += f"""
                <tr class="{rank_class}">
                    <td><strong>{rank}</strong></td>
                    <td>{stats['number']}</td>
                    <td><strong>{stats['name']}</strong></td>
                    <td>{stats['team_name']}</td>
                    <td><strong>{stats['total_points']}</strong></td>
                    <td>{stats['attacks']}</td>
                    <td>{stats['blocks']}</td>
                    <td>{stats['aces']}</td>
                    <td>{stats['points_per_period']:.1f}</td>
                    <td>{stats['team_contribution_pct']:.1f}%</td>
                    <td>{stats['periods_played']}</td>
                </tr>
"""
    
    # Top players detailed breakdown
    html_content += """
            </tbody>
        </table>
        
        <h2>Top 5 Players - Detailed Breakdown</h2>
"""
    
    for i, (player_id, stats) in enumerate(sorted_players[:5]):
        if stats['total_points'] == 0:
            continue
            
        html_content += f"""
        <div class="player-detail">
            <div class="player-header">
                <div class="player-name">#{i+1} {stats['name']} (#{stats['number']})</div>
                <div class="player-stats">
                    {stats['total_points']} pts | {stats['points_per_period']:.1f} pts/period | {stats['team_contribution_pct']:.1f}% team contribution
                </div>
            </div>
            <div><strong>Team:</strong> {stats['team_name']}</div>
            <div><strong>Active Periods:</strong> {', '.join(map(str, sorted(stats['periods'])))}</div>
            <div class="scoring-breakdown">
"""
        
        for score_type, count in stats['points_by_type'].items():
            if count > 0:
                percentage = (count / stats['total_points']) * 100
                html_content += f"""
                <div class="score-type">{score_type}: {count} ({percentage:.1f}%)</div>
"""
        
        html_content += """
            </div>
        </div>
"""
    
    # Team rankings
    html_content += """
        <h2>Top Scorers by Team</h2>
"""
    
    for team_name, players in teams.items():
        html_content += f"""
        <div class="team-card">
            <div class="team-name">{team_name}</div>
"""
        for i, player in enumerate(players[:5]):
            html_content += f"""
            <div class="stat-row">
                <span>{i+1}. {player['name']} (#{player['number']})</span>
                <strong>{player['total_points']} pts</strong>
            </div>
"""
        html_content += """
        </div>
"""
    
    # Scoring analysis by team
    html_content += """
        <h2>Match Scoring Analysis</h2>
"""
    
    # Calculate team-specific scoring patterns
    team_scoring = {}
    for team_id, team_info in team_stats.items():
        team_name = team_info['name']
        team_scoring[team_name] = {
            'player_actions': defaultdict(int),
            'opponent_errors': team_info['opponent_errors'],
            'total_points': team_info['total_points']
        }
    
    # Collect player scoring by team
    for player_id, stats in player_stats.items():
        if stats['total_points'] > 0:
            team_name = stats['team_name']
            if team_name in team_scoring:
                for score_type, count in stats['points_by_type'].items():
                    team_scoring[team_name]['player_actions'][score_type] += count
    
    # Overall scoring summary
    total_all_points = sum(team_info['total_points'] for team_info in team_stats.values())
    total_opponent_errors = sum(team_info['opponent_errors'] for team_info in team_stats.values())
    
    html_content += f"""
        <div class="chart-container">
            <h3>Overall Match Scoring</h3>
            <div class="chart-bar">
                <div class="chart-label">Player Actions</div>
                <div class="chart-progress">
                    <div class="chart-fill" style="width: {(total_player_points/total_all_points)*100 if total_all_points > 0 else 0}%"></div>
                </div>
                <div class="chart-value">{total_player_points} ({(total_player_points/total_all_points)*100 if total_all_points > 0 else 0:.1f}%)</div>
            </div>
            <div class="chart-bar">
                <div class="chart-label">Opponent Errors</div>
                <div class="chart-progress">
                    <div class="chart-fill" style="width: {(total_opponent_errors/total_all_points)*100 if total_all_points > 0 else 0}%; background: linear-gradient(90deg, #e74c3c, #c0392b);"></div>
                </div>
                <div class="chart-value">{total_opponent_errors} ({(total_opponent_errors/total_all_points)*100 if total_all_points > 0 else 0:.1f}%)</div>
            </div>
        </div>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 30px; margin: 30px 0;">
"""
    
    # Team-specific scoring analysis
    for team_name, scoring_data in team_scoring.items():
        team_total = scoring_data['total_points']
        player_total = sum(scoring_data['player_actions'].values())
        opponent_errors = scoring_data['opponent_errors']
        
        html_content += f"""
            <div class="chart-container">
                <h3>{team_name} - Scoring Breakdown</h3>
                <div style="margin-bottom: 15px; font-weight: bold; color: #2c3e50;">
                    Total Points: {team_total}
                </div>
"""
        
        # Show opponent errors first
        if opponent_errors > 0:
            error_pct = (opponent_errors / team_total) * 100 if team_total > 0 else 0
            html_content += f"""
                <div class="chart-bar">
                    <div class="chart-label">Opponent Errors</div>
                    <div class="chart-progress">
                        <div class="chart-fill" style="width: {error_pct}%; background: linear-gradient(90deg, #e74c3c, #c0392b);"></div>
                    </div>
                    <div class="chart-value">{opponent_errors} ({error_pct:.1f}%)</div>
                </div>
"""
        
        # Show player actions
        for score_type, count in sorted(scoring_data['player_actions'].items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                percentage = (count / team_total) * 100 if team_total > 0 else 0
                html_content += f"""
                <div class="chart-bar">
                    <div class="chart-label">{score_type}</div>
                    <div class="chart-progress">
                        <div class="chart-fill" style="width: {percentage}%"></div>
                    </div>
                    <div class="chart-value">{count} ({percentage:.1f}%)</div>
                </div>
"""
        
        html_content += """
            </div>
"""
    
    html_content += """
        </div>
"""
    
    # Summary statistics
    total_players = len([p for p in player_stats.values() if p['total_points'] > 0])
    total_points = sum(stats['total_points'] for stats in player_stats.values())
    avg_points = total_points / max(total_players, 1)
    
    # Most efficient players
    efficient_players = [
        (stats['name'], stats['points_per_period']) 
        for stats in player_stats.values() 
        if stats['total_points'] >= 3
    ]
    efficient_players.sort(key=lambda x: x[1], reverse=True)
    
    html_content += f"""
        </div>
        
        <h2>Match Summary</h2>
        <div class="summary-grid">
            <div class="summary-card">
                <span class="summary-number">{total_players}</span>
                <div class="summary-label">Players with Points</div>
            </div>
            <div class="summary-card">
                <span class="summary-number">{total_points}</span>
                <div class="summary-label">Total Player Points</div>
            </div>
            <div class="summary-card">
                <span class="summary-number">{avg_points:.1f}</span>
                <div class="summary-label">Average Points/Player</div>
            </div>
        </div>
"""
    
    if efficient_players:
        html_content += """
        <h3>Most Efficient Players (≥3 points)</h3>
        <div class="team-card">
"""
        for i, (name, eff) in enumerate(efficient_players[:3]):
            html_content += f"""
            <div class="stat-row">
                <span>{i+1}. {name}</span>
                <strong>{eff:.1f} pts/period</strong>
            </div>
"""
        html_content += """
        </div>
"""
    
    html_content += f"""
        <div style="text-align: center; margin-top: 40px; color: #7f8c8d; font-size: 0.9em;">
            Generated on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""
    
    # Write HTML file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return True
    except Exception as e:
        print(f"Error writing HTML file: {e}")
        return False

def print_usage():
    """Print usage information."""
    print("Usage: python3 stats.py <json_file>")
    print("Example: python3 stats.py completed.json")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Analyze volleyball player statistics from Profixio JSON data')
    parser.add_argument('json_file', help='Path to the JSON file containing match data')
    parser.add_argument('--top', type=int, default=10, help='Number of top players to show in detailed breakdown (default: 10)')
    parser.add_argument('--min-points', type=int, default=0, help='Minimum points required to show player (default: 0)')
    parser.add_argument('--html', type=str, help='Generate HTML report and save to specified file (e.g., --html stats.html)')
    parser.add_argument('--html-only', action='store_true', help='Generate only HTML output (no text output)')
    
    args = parser.parse_args()
    
    # Parse match data
    print(f"Analyzing match data from: {args.json_file}")
    data = parse_match_data(args.json_file)
    
    # Analyze statistics
    player_stats, team_stats = analyze_player_stats(data)
    player_stats = calculate_advanced_stats(player_stats, team_stats)
    
    # Filter by minimum points if specified
    if args.min_points > 0:
        player_stats = {
            pid: stats for pid, stats in player_stats.items() 
            if stats['total_points'] >= args.min_points
        }
    
    # Generate HTML report if requested
    if args.html:
        print(f"Generating HTML report: {args.html}")
        if generate_html_report(player_stats, team_stats, data, args.html):
            print(f"✅ HTML report saved to: {args.html}")
        else:
            print("❌ Failed to generate HTML report")
    
    # Skip text output if HTML-only mode
    if args.html_only and args.html:
        return 0
    
    # Print text results
    print_team_summary(team_stats)
    print_player_stats_table(player_stats)
    print_detailed_breakdown(player_stats, args.top)
    print_team_rankings(player_stats)
    scoring_patterns = analyze_scoring_patterns(player_stats)
    
    # Summary statistics
    total_players = len([p for p in player_stats.values() if p['total_points'] > 0])
    total_points = sum(stats['total_points'] for stats in player_stats.values())
    
    print(f"\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total players with points: {total_players}")
    print(f"Total points by players: {total_points}")
    print(f"Average points per player: {total_points / max(total_players, 1):.1f}")
    
    # Most efficient players (min 3 points)
    efficient_players = [
        (stats['name'], stats['points_per_period']) 
        for stats in player_stats.values() 
        if stats['total_points'] >= 3
    ]
    efficient_players.sort(key=lambda x: x[1], reverse=True)
    
    if efficient_players:
        print(f"\nMost efficient players (≥3 pts):")
        for i, (name, eff) in enumerate(efficient_players[:3]):
            print(f"  {i+1}. {name}: {eff:.1f} pts/period")

if __name__ == "__main__":
    main()