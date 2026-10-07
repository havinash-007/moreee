"""Sample-based consistency audit for skpro distributions.

Compares mean, var, cdf at the median, energy and energy(x) against Monte Carlo
estimates for every distribution in skpro. Heavy-tailed families are exempt from
variance checks. Found nothing alone; it is a screening tool, so confirm hits by hand.

Run inside an environment with the target library installed.
"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from skbase.lookup import all_objects
from skpro.distributions.base import BaseDistribution
np.random.seed(1)
V=lambda a: np.asarray(getattr(a,"values",a),dtype=float)
SKIP_VAR={"TDistribution","Cauchy","LogLaplace","Pareto","Levy","Fisk","BurrIII","BurrXII","GenPareto","InverseGamma","HalfCauchy"}
for name, cls in all_objects(object_types=BaseDistribution, package_name="skpro", return_names=True):
    try: params = cls.get_test_params()
    except Exception: continue
    for i,p in enumerate(params):
        msgs=[]
        try:
            d=cls(**p); N=20000
            s=d.sample(N); sv=V(s)
            m=V(d.mean()); v=V(d.var())
            shp=np.broadcast_to(m,m.shape).shape
            sv=sv.reshape(N,*(m.shape if m.shape else ()))
            sm=sv.mean(0); ssd=sv.std(0)
            if name not in SKIP_VAR:
                if not np.allclose(m,sm,atol=5*np.sqrt(np.maximum(v,1e-12)/N)+1e-3): msgs.append(f"mean {np.ravel(m)[:3]} vs {np.ravel(sm)[:3]}")
                if np.all(np.isfinite(v)) and not np.allclose(v,sv.var(0),rtol=0.15,atol=0.02): msgs.append(f"var {np.ravel(v)[:3]} vs {np.ravel(sv.var(0))[:3]}")
            # cdf at sample points vs empirical
            x0=V(d.ppf(0.5*np.ones(d.shape))) if d.shape else V(d.ppf(0.5))
            emp=(sv<=x0).mean(0); c=V(d.cdf(x0 if not d.shape else pd.DataFrame(x0,index=d.index,columns=d.columns)))
            if "discrete" not in str(d.get_tag("distr:measuretype","")) and not np.allclose(c,emp,atol=0.03): msgs.append(f"cdf@median {np.ravel(c)[:3]} vs emp {np.ravel(emp)[:3]}")
            if not np.allclose(c,0.5,atol=1e-3) and "discrete" not in str(d.get_tag("distr:measuretype","")): msgs.append(f"cdf(ppf(.5)) {np.ravel(c)[:3]}")
            e=V(d.energy()); s2=V(d.sample(N)).reshape(N,*(m.shape if m.shape else ()))
            me=np.abs(sv-s2).mean(0)
            if name not in SKIP_VAR and not np.allclose(e,me,rtol=0.1,atol=0.03): msgs.append(f"energy {np.ravel(e)[:3]} vs {np.ravel(me)[:3]}")
            # energy with x
            x=V(d.ppf(0.3*np.ones(d.shape))) if d.shape else V(d.ppf(0.3))
            xdf=x if not d.shape else pd.DataFrame(x,index=d.index,columns=d.columns)
            ex=V(d.energy(xdf)); mex=np.abs(sv-x).mean(0)
            if name not in SKIP_VAR and not np.allclose(ex,mex,rtol=0.1,atol=0.03): msgs.append(f"energy(x) {np.ravel(ex)[:3]} vs {np.ravel(mex)[:3]}")
        except Exception as ex:
            msgs=[f"EXC {type(ex).__name__}: {str(ex)[:90]}"]
        if msgs: print(name,i,msgs)
