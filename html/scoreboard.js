const rgba2hex = (rgba) => `#${rgba.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*(\d+\.{0,1}\d*))?\)$/).slice(1).map((n, i) => (i === 3 ? Math.round(parseFloat(n) * 255) : parseFloat(n)).toString(16).padStart(2, '0').replace('NaN', '')).join('')}`
const undoable_scoreboards = []; 
const redoable_scoreboards = []; 
const DOM_PARSER = new DOMParser();
const XML_SERIALIZER = new XMLSerializer();
function save_state(clear) {
    if(clear == true) undoable_scoreboards.length = 0;
    undoable_scoreboards.push(XML_SERIALIZER.serializeToString(document.getElementById('scoreboard')));
    document.getElementById('undo').classList.add('undo');
    redoable_scoreboards.length = 0;
    document.getElementById('redo').classList.remove('redo');
}
function undo(evt) {
    if (undoable_scoreboards.length > 0) {
        var last_scoreboard = undoable_scoreboards.pop();
        redoable_scoreboards.push(XML_SERIALIZER.serializeToString(document.getElementById('scoreboard')));
        document.getElementById('redo').classList.add('redo');
        var doc = DOM_PARSER.parseFromString(last_scoreboard, 'text/xml');
        document.getElementById('scoreboard').replaceWith(doc.getElementById('scoreboard'));        
        if (undoable_scoreboards.length == 0) document.getElementById('undo').classList.remove('undo');
        upload();
    }
}
function redo(evt) {
    if (redoable_scoreboards.length > 0) {
        var last_scoreboard = redoable_scoreboards.pop();
        undoable_scoreboards.push(XML_SERIALIZER.serializeToString(document.getElementById('scoreboard')));
        document.getElementById('undo').classList.add('undo');
        var doc = DOM_PARSER.parseFromString(last_scoreboard, 'text/xml');
        document.getElementById('scoreboard').replaceWith(doc.getElementById('scoreboard'));        
        if (redoable_scoreboards.length == 0) document.getElementById('redo').classList.remove('redo');
        upload();            
    }
}
function upload() {
    var scoreboard = XML_SERIALIZER.serializeToString(document.getElementById('scoreboard'));
    window.localStorage.setItem('scoreboard', scoreboard);
    var data = new FormData();
    data.append('filedata', scoreboard);
    data.append('filename', 'scoreboard.xml');
    fetch('upload.php', {
        method: 'POST',
        body: data
    });
}
function score(evt) {
    save_state(false);
    var counter = evt.currentTarget.counter;
    var action = evt.currentTarget.action;
    var score = parseInt(document.getElementById(counter).textContent);
    switch (action) {
        case 'plus': score = score + 1; break;
        case 'minus': score = score -1; break;
    } 
    score = score < 0 ? score = 0 : score;    
    if (counter.endsWith('set') && action == 'plus') {
        if(confirm('Start next set at 0-0?') == true) {
            document.getElementById('home_score').textContent = 0;
            document.getElementById('away_score').textContent = 0;
        }
    }  
    if (evt.currentTarget.id == 'home_score_plus') {
        document.getElementById('home_serve').classList.add('serving');
        document.getElementById('away_serve').classList.remove('serving');
    }
    else if (evt.currentTarget.id == 'away_score_plus') {
        document.getElementById('home_serve').classList.remove('serving');
        document.getElementById('away_serve').classList.add('serving');
    }
    document.getElementById(counter).textContent = score;
    upload();
}
function toggle_serve(evt) {
    save_state(false);
    if(document.getElementById('home_serve').classList.contains('serving')) {
        document.getElementById('home_serve').classList.remove('serving');
        document.getElementById('away_serve').classList.add('serving');
    }
    else {
        document.getElementById('home_serve').classList.add('serving');
        document.getElementById('away_serve').classList.remove('serving');
    }
    upload();
}
function pick_color(evt) {
    var picker = evt.currentTarget.id.replace('set', 'color') + '_picker';
    var color = window.getComputedStyle(evt.currentTarget, null).getPropertyValue('background-color');
    document.getElementById(picker).focus();
    document.getElementById(picker).value = rgba2hex(color); 
    document.getElementById(picker).click();
}
function set_color(evt) {
    save_state(false);
    var team_color = evt.currentTarget.id.replace('_picker', '');
    document.getElementById(team_color).style.background = evt.currentTarget.value;
    upload();
}
function save_team(evt) {
    save_state(false);
}
function update_team(evt) {
    upload();
}
function reset(evt) {
    if(confirm("Would you to reset the game?") == true) {
        save_state(true);
        document.getElementById('home_set').textContent = 0;
        document.getElementById('away_set').textContent = 0;
        document.getElementById('home_score').textContent = 0;
        document.getElementById('away_score').textContent = 0;
        upload();
        window.localStorage.clear();
    }
}     
window.addEventListener('load', function() {
    var scoreboard = window.localStorage.getItem('scoreboard');
    if(scoreboard) {
        var doc = DOM_PARSER.parseFromString(scoreboard, 'text/xml');
        document.getElementById('scoreboard').replaceWith(doc.getElementById('scoreboard'));
    }
    var home_color = window.getComputedStyle(document.getElementById('home_color'), null).getPropertyValue('background-color');
    document.getElementById('home_color_picker').value = rgba2hex(home_color);
    var away_color = window.getComputedStyle(document.getElementById('away_color'), null).getPropertyValue('background-color');
    document.getElementById('away_color_picker').value = rgba2hex(away_color);

    document.getElementById('home_set_plus').counter = 'home_set';
    document.getElementById('home_set_plus').action = 'plus';
    document.getElementById('home_set_plus').addEventListener('pointerup', score);
    document.getElementById('home_set_minus').counter = 'home_set';
    document.getElementById('home_set_minus').action = 'minus';
    document.getElementById('home_set_minus').addEventListener('pointerup', score);
    document.getElementById('away_set_plus').counter = 'away_set';
    document.getElementById('away_set_plus').action = 'plus';
    document.getElementById('away_set_plus').addEventListener('pointerup', score);
    document.getElementById('away_set_minus').counter = 'away_set';
    document.getElementById('away_set_minus').action = 'minus';
    document.getElementById('away_set_minus').addEventListener('pointerup', score);
    document.getElementById('home_score_plus').counter = 'home_score';
    document.getElementById('home_score_plus').action = 'plus';
    document.getElementById('home_score_plus').addEventListener('pointerup', score);
    document.getElementById('home_score_minus').counter = 'home_score';
    document.getElementById('home_score_minus').action = 'minus';
    document.getElementById('home_score_minus').addEventListener('pointerup', score);
    document.getElementById('away_score_plus').counter = 'away_score';
    document.getElementById('away_score_plus').action = 'plus';
    document.getElementById('away_score_plus').addEventListener('pointerup', score);
    document.getElementById('away_score_minus').counter = 'away_score';
    document.getElementById('away_score_minus').action = 'minus';
    document.getElementById('away_score_minus').addEventListener('pointerup', score);
    document.getElementById('home_serve').addEventListener('pointerup', toggle_serve);
    document.getElementById('away_serve').addEventListener('pointerup', toggle_serve);            
    document.getElementById('home_color').addEventListener('pointerup', pick_color);
    document.getElementById('away_color').addEventListener('pointerup', pick_color);
    document.getElementById('home_set').addEventListener('pointerup', pick_color);
    document.getElementById('away_set').addEventListener('pointerup', pick_color);
    document.getElementById('home_color_picker').addEventListener('change', set_color);
    document.getElementById('away_color_picker').addEventListener('change', set_color);
    document.getElementById('home_team').addEventListener('focus', save_team);
    document.getElementById('home_team').addEventListener('blur', update_team);
    document.getElementById('away_team').addEventListener('focus', save_team);
    document.getElementById('away_team').addEventListener('blur', update_team);
    document.getElementById('undo').addEventListener('pointerup', undo);
    document.getElementById('reset').addEventListener('pointerup', reset);
    document.getElementById('redo').addEventListener('pointerup', redo);
});      