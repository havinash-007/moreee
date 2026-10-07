"""Fuzz sktime window splitters for basic invariants.

Checks: no train/test overlap, test after train, no empty or out-of-bounds splits,
and that split, split_loc, split_series and get_n_splits agree on the count.

Run inside an environment with the target library installed.
"""
import warnings, itertools; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from sktime.split import *
bad=[]
def chk(name, cv, y):
    try:
        n=0
        for tr,te in cv.split(y):
            n+=1
            tr=np.asarray(tr); te=np.asarray(te)
            if len(set(tr)&set(te)): bad.append((name,"overlap")); return
            if len(te) and len(tr) and te.min()<=tr.max() and not isinstance(cv,(SingleWindowSplitter,)) and "Same" not in name: bad.append((name,"test before train end",tr.max(),te.min())); return
            if len(tr)==0 or len(te)==0: bad.append((name,"empty")); return
            if tr.max()>=len(y) or te.max()>=len(y) or tr.min()<0: bad.append((name,"oob")); return
        # compare split vs split_loc vs split_series count
        nl=sum(1 for _ in cv.split_loc(y)); ns=sum(1 for _ in cv.split_series(y))
        if not (n==nl==ns): bad.append((name,"count mismatch",n,nl,ns))
        if n!=cv.get_n_splits(y): bad.append((name,"get_n_splits",n,cv.get_n_splits(y)))
    except Exception as e: bad.append((name,"EXC",type(e).__name__,str(e)[:70]))
for N in [20,31]:
  y=pd.Series(np.arange(N,dtype=float),index=pd.date_range("2020",periods=N)) if N==20 else pd.Series(np.arange(N,dtype=float))
  for wl,fh,step in itertools.product([3,5,8],[1,2,[1,3],4],[1,2,3]):
    for cls in [SlidingWindowSplitter,ExpandingWindowSplitter]:
        for ip in [0,2]:
            try: cv=cls(fh=fh,window_length=wl,step_length=step,initial_window=wl+ip) if cls is ExpandingWindowSplitter else cls(fh=fh,window_length=wl,step_length=step,initial_window=wl+ip)
            except Exception as e: continue
            chk(f"{cls.__name__}(N={N},wl={wl},fh={fh},step={step},iw={wl+ip})",cv,y)
  for fh,wl in itertools.product([1,3,[1,2]],[None,4,6]):
    chk(f"SingleWindow(N={N},fh={fh},wl={wl})",SingleWindowSplitter(fh=fh,window_length=wl),y)
  for ts in [0.2,0.5,3]:
    chk(f"Temporal(N={N},ts={ts})",temporal_train_test_split and TemporalTrainTestSplitter(test_size=ts),y)
  for k in [2,3,4]:
    chk(f"CutoffSplitter(N={N},{k})",CutoffSplitter(cutoffs=np.array([8,12,15][:k]) if True else None,fh=2,window_length=5),y)
seen=set()
for b in bad:
    key=(b[0].split("(")[0],b[1]); 
    if key in seen: continue
    seen.add(key); print(b)
print(len(bad),"total issues")
