const rgba2hex = (rgba) => `#${rgba.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*(\d+\.{0,1}\d*))?\)$/).slice(1).map((n, i) => (i === 3 ? Math.round(parseFloat(n) * 255) : parseFloat(n)).toString(16).padStart(2, '0').replace('NaN', '')).join('')}`
const undoable_scoreboards = [];
const redoable_scoreboards = [];
const SIDES = ['home', 'away'];
const DOM_PARSER = new DOMParser();
const XML_SERIALIZER = new XMLSerializer();

// Configuration - extract username from URL path
const USERNAME = window.location.pathname.split('/')[1] || 'default';
const TOKEN = 'SET_BY_SERVER';  // This will be set dynamically
const SCOREBOARD_STORAGE_KEY = `scoreboard_${USERNAME}`;

// Inject token from server (will be set via script tag in HTML)
window.SCOREBOARD_TOKEN = window.SCOREBOARD_TOKEN || TOKEN;

// The hidden #scoreboard element is the model that is uploaded to the overlay.
// The controls on the page only read it in render() and change it through the handlers below.
function save_state(clear) {
    if(clear == true) undoable_scoreboards.length = 0;
    undoable_scoreboards.push(XML_SERIALIZER.serializeToString(document.getElementById('scoreboard')));
    redoable_scoreboards.length = 0;
    update_history_buttons();
}
function update_history_buttons() {
    document.getElementById('undo').disabled = undoable_scoreboards.length == 0;
    document.getElementById('redo').disabled = redoable_scoreboards.length == 0;
}
function replace_scoreboard(serialized_scoreboard) {
    var doc = DOM_PARSER.parseFromString(serialized_scoreboard, 'text/xml');
    var scoreboard = doc.getElementById('scoreboard');
    if (!scoreboard) return false;
    document.getElementById('scoreboard').replaceWith(document.importNode(scoreboard, true));
    // Scraped scoreboards drop the scores once a match has ended; manual scoring needs them back.
    for (const side of SIDES) {
        if (!document.getElementById(side + '_score')) {
            var score = document.createElement('div');
            score.id = side + '_score';
            score.className = 'score';
            score.textContent = 0;
            document.querySelector('#scoreboard .' + side).append(score);
        }
    }
    return true;
}
function undo(evt) {
    if (undoable_scoreboards.length > 0) {
        var last_scoreboard = undoable_scoreboards.pop();
        redoable_scoreboards.push(XML_SERIALIZER.serializeToString(document.getElementById('scoreboard')));
        replace_scoreboard(last_scoreboard);
        update_history_buttons();
        render();
        upload();
    }
}
function redo(evt) {
    if (redoable_scoreboards.length > 0) {
        var last_scoreboard = redoable_scoreboards.pop();
        undoable_scoreboards.push(XML_SERIALIZER.serializeToString(document.getElementById('scoreboard')));
        replace_scoreboard(last_scoreboard);
        update_history_buttons();
        render();
        upload();
    }
}
function upload() {
    var scoreboard = XML_SERIALIZER.serializeToString(document.getElementById('scoreboard'));
    window.localStorage.setItem(SCOREBOARD_STORAGE_KEY, scoreboard);
    var data = new FormData();
    data.append('filedata', scoreboard);
    data.append('filename', 'scoreboard.xml');
    data.append('token', window.SCOREBOARD_TOKEN || TOKEN);  // Use dynamic token
    fetch(`/${USERNAME}/upload.php`, {
        method: 'POST',
        body: data
    });
}
function set_serving(side) {
    for (const s of SIDES) {
        document.getElementById(s + '_serve').classList.toggle('serving', s == side);
    }
}
function score(evt) {
    var counter = evt.currentTarget.dataset.counter;
    var action = evt.currentTarget.dataset.action;
    var score = parseInt(document.getElementById(counter).textContent) || 0;
    switch (action) {
        case 'plus': score = score + 1; break;
        case 'minus': score = score - 1; break;
    }
    if (score < 0) return;
    save_state(false);
    if (counter.endsWith('set') && action == 'plus') {
        if(confirm('Start next set at 0-0?') == true) {
            document.getElementById('home_score').textContent = 0;
            document.getElementById('away_score').textContent = 0;
        }
    }
    // Rally scoring: the team that wins the point serves next.
    if (counter.endsWith('score') && action == 'plus') {
        set_serving(counter.replace('_score', ''));
    }
    document.getElementById(counter).textContent = score;
    render();
    flash(counter + '_value');
    upload();
}
function give_serve(evt) {
    var side = evt.currentTarget.dataset.side;
    if (document.getElementById(side + '_serve').classList.contains('serving')) return;
    save_state(false);
    set_serving(side);
    render();
    upload();
}
function set_color(evt) {
    save_state(false);
    document.getElementById(evt.currentTarget.dataset.side + '_color').style.background = evt.currentTarget.value;
    render();
    upload();
}
function set_team(evt) {
    var team = document.getElementById(evt.currentTarget.dataset.side + '_team');
    var name = evt.currentTarget.value.trim();
    if (!name || name == team.textContent) {
        evt.currentTarget.value = team.textContent.trim();
        return;
    }
    save_state(false);
    team.textContent = name;
    render();
    upload();
}
function finish_team(evt) {
    if (evt.key == 'Enter') evt.currentTarget.blur();
}
function reset(evt) {
    if(confirm("Would you like to reset the game?") == true) {
        save_state(true);
        document.getElementById('home_set').textContent = 0;
        document.getElementById('away_set').textContent = 0;
        document.getElementById('home_score').textContent = 0;
        document.getElementById('away_score').textContent = 0;
        render();
        upload();
        window.localStorage.removeItem(SCOREBOARD_STORAGE_KEY);
    }
}
function render() {
    for (const side of SIDES) {
        document.getElementById(side + '_score_value').textContent = document.getElementById(side + '_score').textContent;
        document.getElementById(side + '_set_value').textContent = document.getElementById(side + '_set').textContent;
        var team_input = document.getElementById(side + '_team_input');
        if (document.activeElement !== team_input) team_input.value = document.getElementById(side + '_team').textContent.trim();
        var serving = document.getElementById(side + '_serve').classList.contains('serving');
        var serve_button = document.getElementById(side + '_serve_button');
        serve_button.setAttribute('aria-pressed', serving);
        // Only an inline color is uploaded; without one the overlay theme decides.
        var team_color = document.getElementById(side + '_color');
        var color = team_color.style.backgroundColor && window.getComputedStyle(team_color).backgroundColor;
        var picker = document.getElementById(side + '_color_picker');
        picker.parentElement.classList.toggle('unset', !color);
        picker.parentElement.style.setProperty('--swatch', color || 'transparent');
        if (color) picker.value = rgba2hex(color).slice(0, 7);
    }
}
function flash(id) {
    var element = document.getElementById(id);
    element.classList.remove('flash');
    void element.offsetWidth;
    element.classList.add('flash');
}

async function load_initial_scoreboard() {
    const cacheBuster = Date.now();
    try {
        const response = await fetch(`/${USERNAME}/scoreboard.xml?ts=${cacheBuster}`, { cache: 'no-store' });
        if (response.ok) {
            const text = await response.text();
            if (text && replace_scoreboard(text)) {
                window.localStorage.setItem(SCOREBOARD_STORAGE_KEY, text);
                return;
            }
        }
    } catch (err) {
        // Ignore fetch errors; fallback to local storage
    }

    const stored = window.localStorage.getItem(SCOREBOARD_STORAGE_KEY);
    if (stored) {
        replace_scoreboard(stored);
    }
}
function add_listeners() {
    for (const button of document.querySelectorAll('[data-counter]')) {
        button.addEventListener('click', score);
    }
    for (const side of SIDES) {
        document.getElementById(side + '_serve_button').addEventListener('click', give_serve);
        document.getElementById(side + '_color_picker').addEventListener('change', set_color);
        document.getElementById(side + '_team_input').addEventListener('change', set_team);
        document.getElementById(side + '_team_input').addEventListener('keydown', finish_team);
    }
    document.getElementById('undo').addEventListener('click', undo);
    document.getElementById('reset').addEventListener('click', reset);
    document.getElementById('redo').addEventListener('click', redo);
    // iOS Safari only shows :active styles when a touch listener exists.
    document.addEventListener('touchstart', function() {}, { passive: true });
}
window.addEventListener('scroll', function(evt) {
    if (!document.activeElement || document.activeElement === document.body) {
        evt.preventDefault();
        document.body.scrollIntoView(true);
    }
});
window.addEventListener('load', function() {
    add_listeners();
    render();
    load_initial_scoreboard().finally(function() {
        render();
        document.addEventListener('dblclick', function(event) {
            event.preventDefault();
        }, { passive: false });
    });
});
