#!/bin/bash

convert -size 962x635 canvas:white prev.png
x=prev.png

composite -geometry +558+270 bigtop_unlocked.png $x temp.png
mv temp.png prev.png

composite -geometry +0+251 forest_unlocked.png $x temp.png
mv temp.png prev.png

composite -geometry +206+187 mainstreet_unlocked.png $x temp.png
mv temp.png prev.png

composite -geometry +27+54 space_unlocked.png $x temp.png
mv temp.png prev.png

composite -geometry +540+22 wizard_unlocked.png $x temp.png
mv temp.png prev.png

composite -geometry +270+0 yesterday_unlocked.png $x temp.png
mv temp.png prev.png

zopflipng prev.png all_open.png
rm prev.png




