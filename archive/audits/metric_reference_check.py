"""Check sktime forecasting metrics against textbook reference formulas.

Prints OK or DIFF per metric. A DIFF needs a manual look: MdASE, for example,
is documented as median over median, so it differs from the mean-scaled form.

Run inside an environment with the target library installed.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from sklearn import metrics as sk
from sktime.performance_metrics.forecasting import *
rng=np.random.default_rng(0)
yt=pd.Series(rng.normal(5,2,50)+10); yp=yt+rng.normal(0,1,50); ytr=pd.Series(rng.normal(5,2,60)+10)
checks={
 "MAE":(MeanAbsoluteError(),sk.mean_absolute_error(yt,yp)),
 "MSE":(MeanSquaredError(),sk.mean_squared_error(yt,yp)),
 "RMSE":(MeanSquaredError(square_root=True),np.sqrt(sk.mean_squared_error(yt,yp))),
 "MedAE":(MedianAbsoluteError(),sk.median_absolute_error(yt,yp)),
 "MAPE":(MeanAbsolutePercentageError(symmetric=False),sk.mean_absolute_percentage_error(yt,yp)),
 "sMAPE":(MeanAbsolutePercentageError(symmetric=True),np.mean(2*np.abs(yt-yp)/(np.abs(yt)+np.abs(yp)))),
 "MedAPE":(MedianAbsolutePercentageError(symmetric=False),np.median(np.abs((yt-yp)/yt))),
 "MaxErr":(MeanAbsoluteError(),None),
 "GMAE":(GeometricMeanAbsoluteError(),np.exp(np.mean(np.log(np.abs(yt-yp))))),
 "GMSE":(GeometricMeanSquaredError(),np.exp(np.mean(np.log((yt-yp)**2)))),
 "RMSPE":(MeanSquaredPercentageError(square_root=True),np.sqrt(np.mean(((yt-yp)/yt)**2))),
 "MSPE":(MeanSquaredPercentageError(),np.mean(((yt-yp)/yt)**2)),
 "RelMAE":(RelativeLoss(),None),
 "MASE":(MeanAbsoluteScaledError(),np.mean(np.abs(yt-yp))/np.mean(np.abs(np.diff(ytr)))),
 "MSSE":(MeanSquaredScaledError(),np.mean((yt-yp)**2)/np.mean(np.diff(ytr)**2)),
 "RMSSE":(MeanSquaredScaledError(square_root=True),np.sqrt(np.mean((yt-yp)**2)/np.mean(np.diff(ytr)**2))),
 "MdASE":(MedianAbsoluteScaledError(),np.median(np.abs(yt-yp))/np.mean(np.abs(np.diff(ytr)))),
 "MdSE":(MedianSquaredError(),np.median((yt-yp)**2)),
 "MAAPE":(MeanAsymmetricError(),None),
}
for k,(m,ref) in checks.items():
    if ref is None: continue
    try:
        v=m(yt,yp,y_train=ytr)
        ok=np.isclose(v,ref,rtol=1e-6)
        print(("OK  " if ok else "DIFF"),k,v,ref)
    except Exception as e: print("EXC ",k,type(e).__name__,str(e)[:80])
