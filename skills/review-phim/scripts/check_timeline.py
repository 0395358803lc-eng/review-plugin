#!/usr/bin/env python3
"""Validate a single-source hard-cut timeline. Not semantic QC."""
import argparse,json,math
from fractions import Fraction
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('timeline',type=Path);p.add_argument('--source-duration',type=float);p.add_argument('--audio-duration',type=float);p.add_argument('--report',type=Path);a=p.parse_args()
    t=json.loads(a.timeline.read_text(encoding='utf-8-sig'));fps=Fraction(str(t['fps']));dur=float(t['duration']);sd=a.source_duration if a.source_duration is not None else float(t['source_duration']);rows=t['clips'];errors=[];flags=[];seen=set();used=[];cursor=0
    if fps<=0 or not math.isfinite(dur) or dur<=0 or not math.isfinite(sd) or sd<=0 or not rows:raise ValueError('invalid timeline header')
    tol=float(1/fps)+.001
    for r in rows:
        i=r['clip_id'];x=r['review_start_frame'];y=r['review_end_frame'];s=float(r['source_start']);e=float(r['source_end']);v=float(r.get('speed',1))
        if i in seen:errors.append([i,'duplicate ID'])
        seen.add(i)
        if type(x)!=int or type(y)!=int or x!=cursor or y<=x:errors.append([i,'frame gap, overlap, or invalid interval'])
        if r.get('transition','cut')!='cut':errors.append([i,'unsupported transition'])
        if not all(map(math.isfinite,[s,e,v])) or not 0<=s<e<=sd+.001 or v<=0:errors.append([i,'invalid source bounds/speed'])
        elif abs((e-s)/v-float(Fraction(y-x)/fps))>tol:errors.append([i,'source/review duration mismatch'])
        if any(min(e,b)-max(s,c)>.4 for c,b in used):flags.append([i,'source reuse > 0.4s'])
        used.append((s,e));cursor=y
        if not str(r.get('narration','')).strip():errors.append([i,'missing narration'])
        if not str(r.get('visual_observation','')).strip():flags.append([i,'missing visual observation'])
    actual=float(Fraction(cursor)/fps)
    if abs(actual-dur)>tol:errors.append(['total','timeline duration mismatch'])
    if a.audio_duration is not None and (not math.isfinite(a.audio_duration) or abs(actual-a.audio_duration)>tol):errors.append(['total','audio duration mismatch'])
    report={'status':'pass' if not errors else 'fail','clips':len(rows),'frames':cursor,'duration':actual,'fps':str(fps),'errors':errors,'flags':flags,'scope':'numeric timeline validation only; semantic and rendered-frame QC still required'}
    text=json.dumps(report,ensure_ascii=False,indent=2);print(text)
    if a.report:a.report.write_text(text+'\n',encoding='utf-8')
    raise SystemExit(bool(errors))
if __name__=='__main__':main()
