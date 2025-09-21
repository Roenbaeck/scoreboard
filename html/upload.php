<?php 
// Configuration
$TOKEN = 'your_secure_token_here';  // Change this to your secure token

// Security checks
if (!isset($_POST['token']) || $_POST['token'] !== $TOKEN) {
    http_response_code(403);
    echo 'Forbidden: Invalid token';
    exit;
}

if (!isset($_POST['filename']) || $_POST['filename'] !== 'scoreboard.xml') {
    http_response_code(403);
    echo 'Forbidden: Only scoreboard.xml can be updated';
    exit;
}

if (!isset($_POST['filedata'])) {
    http_response_code(400);
    echo 'Bad Request: Missing filedata';
    exit;
}

file_put_contents($_POST['filename'], $_POST['filedata']);
echo 'OK';
?>
