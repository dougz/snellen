#!/bin/bash

djpeg land_bg.jpg | pnmcut 17 304 119 125 | pnmtopng > carousel_solved_thumb.png
composite -geometry +10+10 carousel_unlocked.png carousel_solved_thumb.png carousel_unlocked_thumb.png

djpeg land_bg.jpg | pnmcut 190 281 163 133 | pnmtopng > fountain_solved_thumb.png
composite -geometry +10+10 fountain_unlocked.png fountain_solved_thumb.png fountain_unlocked_thumb.png

djpeg land_bg.jpg | pnmcut 216 26 247 224 | pnmtopng > coaster_solved_thumb.png
composite -geometry +10+10 coaster_unlocked.png coaster_solved_thumb.png coaster_unlocked_thumb.png

djpeg land_bg.jpg | pnmcut 473 20 313 218 | pnmtopng > ship_solved_thumb.png
composite -geometry +10+10 ship_unlocked.png ship_solved_thumb.png ship_unlocked_thumb.png



