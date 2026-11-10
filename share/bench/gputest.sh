#!/bin/bash
# usage: gputest.sh LABEL  -> exports each test clip to H.264 with AVFoundation and compares to the source
export PATH=/opt/homebrew/bin:$PATH
D=~/Movies/gputest; mkdir -p $D/out; cd $D
gen() { [ -f "$1" ] || ffmpeg -v error -y -f lavfi -i "testsrc2=size=1920x1080:rate=30" -f lavfi -i "mandelbrot=size=1920x1080:rate=30" -filter_complex "[0][1]blend=all_expr='if(lt(X,W/2),A,B)'" -t 10 "${@:2}" "$1"; }
gen prores422_10.mov -c:v prores_ks -profile:v 2 -pix_fmt yuv422p10le
gen prores422hq_10.mov -c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le
gen prores4444_10.mov -c:v prores_ks -profile:v 4 -pix_fmt yuv444p10le
gen hevc420_10.mov -c:v libx265 -x265-params log-level=error -preset fast -crf 14 -pix_fmt yuv420p10le -tag:v hvc1
gen hevc422_10.mov -c:v libx265 -x265-params log-level=error -preset fast -crf 14 -pix_fmt yuv422p10le -tag:v hvc1
gen h264_420_8.mp4 -c:v libx264 -preset fast -crf 14 -pix_fmt yuv420p
L=${1:-run}
for f in prores422_10.mov prores422hq_10.mov prores4444_10.mov hevc420_10.mov hevc422_10.mov h264_420_8.mp4; do
  o=out/$L-${f%.*}.mp4
  r=$(~/bin/pipe $f $o AVAssetExportPreset1920x1080 2>&1 | tr '\n' ' ')
  n=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 $o 2>/dev/null)
  p=$(ffmpeg -v info -i $o -i $f -lavfi "[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]psnr" -f null - 2>&1 | grep -o "average:[0-9a-z.]*" | tail -1)
  s=$(ffmpeg -v info -i $o -i $f -lavfi "[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim" -f null - 2>&1 | grep -o "All:[0-9.]*" | tail -1)
  echo "RESULT $L $f frames=${n:-0} psnr_${p:-none} ssim_${s:-none} :: $r"
done
