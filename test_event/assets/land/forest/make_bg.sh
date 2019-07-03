#!/bin/bash

x=land_bg.jpg

composite -geometry +39+65 food_locked.png $x temp.png
mv temp.png prev.png
x=prev.png

composite -geometry +226+36 coaster_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +746+164 cars_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +819+41 show_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +48+179 track_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +398+214 pavillion_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +568+251 dolphin_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +712+283 balloon_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +845+250 tent_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +27+314 carousel_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +82+410 building_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +200+291 fountain_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +490+338 ferris_locked.png $x temp.png
mv temp.png prev.png

composite -geometry +757+456 shed_locked.png $x temp.png

mv temp.png land_base.png



