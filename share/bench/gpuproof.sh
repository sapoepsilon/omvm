#!/bin/bash
# usage: gpuproof.sh CLIP(.mov in ~/Movies/gputest) -> proof PNG source | before | after at frame 150, and patch colours
export PATH=/opt/homebrew/bin:$PATH
D=~/Movies/gputest; cd $D; c=$1; b=${c%.*}
fr() { ffmpeg -v error -y -i "$1" -vf "select=eq(n\,150),scale=960:540" -frames:v 1 "$2"; }
fr $c /tmp/p-src.png "source $c"
fr out/before-$b.mp4 /tmp/p-before.png "before (dispatch skipped)"
fr out/after-$b.mp4 /tmp/p-after.png "after (4\:2\:2 surface twin)"
ffmpeg -v error -y -i /tmp/p-src.png -i /tmp/p-before.png -i /tmp/p-after.png -filter_complex hstack=inputs=3 $D/out/proof-$b.png
# mean RGB of a 4x3 grid of patches, frame 150
for f in $c out/before-$b.mp4 out/after-$b.mp4; do
  printf "PATCH %s " $f
  ffmpeg -v error -i $f -vf "select=eq(n\,150),scale=4:3:flags=area,format=rgb24" -frames:v 1 -f rawvideo - | xxd -p | tr -d '\n'; echo
done
ls -la $D/out/proof-$b.png
