#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, subprocess, tempfile
from pathlib import Path

def video_duration(path):
 p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],text=True,capture_output=True,check=True)
 return float(p.stdout.strip())

def main():
 ap=argparse.ArgumentParser();ap.add_argument('edits',type=Path);ap.add_argument('--out',type=Path,default=Path('highlights.mp4'));a=ap.parse_args();d=json.loads(a.edits.read_text(encoding='utf-8'))
 if not d.get('confirmed'): raise SystemExit('edits.json is not confirmed; export it from review.html first')
 src=Path(d['source']); src=src if src.is_absolute() else (a.edits.parent / src).resolve(); clips=[c for c in d['clips'] if c.get('keep')]
 if not src.is_file(): raise SystemExit(f'Source video not found: {src}')
 if not clips: raise SystemExit('No clips selected')
 source_duration=video_duration(src)
 validated=[]
 for c in clips:
  try: start, end = float(c['start']), float(c['end'])
  except (KeyError, TypeError, ValueError): raise SystemExit(f"Invalid timestamps for clip {c.get('id', '<unknown>')}")
  if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= source_duration): raise SystemExit(f"Invalid timestamp range for clip {c.get('id', '<unknown>')}")
  validated.append((start,end,c))
 validated.sort(key=lambda item:item[0])
 previous_end = -1.0
 for start,end,c in validated:
  if start < previous_end: raise SystemExit('Selected clips overlap')
  previous_end = end
 a.out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='rain-cut-') as td:
  parts=[]
  for i,(_,_,c) in enumerate(validated):
   part=Path(td)/f'part-{i:03d}.mp4'; subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss',str(float(c['start'])),'-to',str(float(c['end'])),'-i',str(src),'-c','copy',str(part)],check=True);parts.append(part)
  listing=Path(td)/'concat.txt';listing.write_text(''.join(f"file '{p.as_posix().replace("'","'\\''")}'\n" for p in parts))
  subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(a.out)],check=True)
 print(f'Wrote {a.out}')
if __name__=='__main__':main()
