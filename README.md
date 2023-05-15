# Scoreboard Controller and Overlay
Simple scoreboard web app geared towards volleyball. I tried numerous variants that produce an image which can be used as an overlay, but they were either costly or not very user friendly, so I decided to build my own. Controlling the scoreboard should be self-explanatory.

![TheControllerInterface](Controller.jpg)

# Installation

Copy the contents of the html directory to a web server with PHP enabled. Please note that no effort has gone into securing this yet, so upload.php could potentially be abused. Point your browser to where scoreboard.html is to use the controller interface. Point your streaming software to the url where you installed the files and it should pick up the overlay automatically through index.html.

![ExampleOverlay](PrismLive.png)
