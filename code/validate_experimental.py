# validate_experimental.py  -> Aspen Gibbs vs Song & Pan (2004) Table 2
# Benchmark feed CH4:CO2:H2O:O2 = 1:0.475:0.475:0.1, 1 atm, T = 700-850 C
from pathlib import Path
import time
import numpy as np
import pandas as pd
import win32com.client

CLEAN_APW = Path(r"C:\Users\KaraPardazesh\Desktop\Review\simulation\TRM_automation_no_S1.apw")
FEED_T_C, FEED_P_BAR, FEED_CH4 = 500.0, 1.0, 1.0
TIMEOUT_S = 120.0

# Song & Pan feed (per mol CH4) + their reported equilibrium values (Table 2)
FEED = dict(Fw=0.475, Fc=0.475, Fo=0.1, P=1.0)
LIT = {  # T : (CH4 conv %, CO2 conv %, H2/CO)
    700: (86.0, 55.6, 2.14),
    750: (90.7, 73.3, 1.77),
    800: (96.0, 81.1, 1.72),
    850: (97.9, 87.0, 1.67),
}

IN = {
    "feed_T": r"\Data\Streams\1\Input\TEMP\MIXED",
    "feed_P": r"\Data\Streams\1\Input\PRES\MIXED",
    "CH4":    r"\Data\Streams\1\Input\FLOW\MIXED\CH4",
    "WATER":  r"\Data\Streams\1\Input\FLOW\MIXED\WATER",
    "CO2":    r"\Data\Streams\1\Input\FLOW\MIXED\CO2",
    "O2":     r"\Data\Streams\1\Input\FLOW\MIXED\O2",
    "H2":     r"\Data\Streams\1\Input\FLOW\MIXED\H2",
    "CO":     r"\Data\Streams\1\Input\FLOW\MIXED\CO",
    "CARBON": r"\Data\Streams\1\Input\FLOW\MIXED\CARBON",
    "block_T":r"\Data\Blocks\B1\Input\TEMP",
    "block_P":r"\Data\Blocks\B1\Input\PRES",
}
OUT = {
    "FCH4": r"\Data\Streams\2\Output\MOLEFLOW\MIXED\CH4",
    "FCO2": r"\Data\Streams\2\Output\MOLEFLOW\MIXED\CO2",
    "FCO":  r"\Data\Streams\2\Output\MOLEFLOW\MIXED\CO",
    "FH2":  r"\Data\Streams\2\Output\MOLEFLOW\MIXED\H2",
}

def w(a,p,v): a.Tree.FindNode(p).Value = float(v)
def r(a,p):   return float(a.Tree.FindNode(p).Value)

def run_case(a, T):
    w(a, IN["feed_T"], FEED_T_C); w(a, IN["feed_P"], FEED_P_BAR)
    w(a, IN["CH4"], FEED_CH4)
    for z in ("H2","CO","CARBON"): w(a, IN[z], 0.0)
    w(a, IN["WATER"], FEED["Fw"]); w(a, IN["CO2"], FEED["Fc"]); w(a, IN["O2"], FEED["Fo"])
    w(a, IN["block_T"], T); w(a, IN["block_P"], FEED["P"])
    a.Reinit(); a.Engine.Run2()
    t0=time.perf_counter()
    while bool(a.Engine.IsRunning):
        if time.perf_counter()-t0 > TIMEOUT_S: raise TimeoutError()
        time.sleep(0.02)
    FCH4=r(a,OUT["FCH4"]); FCO2=r(a,OUT["FCO2"]); FCO=r(a,OUT["FCO"]); FH2=r(a,OUT["FH2"])
    X_CH4 = (FEED_CH4 - FCH4)/FEED_CH4 * 100
    X_CO2 = (FEED["Fc"] - FCO2)/FEED["Fc"] * 100
    H2CO  = FH2/FCO if FCO>1e-9 else np.nan
    return X_CH4, X_CO2, H2CO

a = win32com.client.Dispatch("Apwn.Document")
a.InitFromArchive2(str(CLEAN_APW.resolve())); a.Visible=0; a.SuppressDialogs=1

rows=[]
for T,(xch4_l,xco2_l,hc_l) in LIT.items():
    xch4,xco2,hc = run_case(a, T)
    rows.append((T, xch4, xch4_l, xco2, xco2_l, hc, hc_l))
    print(f"T={T}  CH4 model={xch4:.1f}% lit={xch4_l}%  "
          f"CO2 model={xco2:.1f}% lit={xco2_l}%  H2/CO model={hc:.2f} lit={hc_l}")

df=pd.DataFrame(rows, columns=["T","CH4_model","CH4_lit","CO2_model","CO2_lit","H2CO_model","H2CO_lit"])
df.to_csv("validation_songpan.csv", index=False)
print("\nsaved validation_songpan.csv")