"""Grafy nahraných relácií.  Spustenie:  streamlit run app/dashboard.py"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from brutology.analysis import NO_FINDINGS_HINT, analyze, rank_causes
from brutology.storage import DEFAULT_DB, Storage

SEVERITY_ICON = {"vysoká": "🔴", "stredná": "🟠", "nízka": "🟡"}
SEVERITY_COLOR = {"vysoká": "red", "stredná": "orange", "nízka": "gold"}

st.set_page_config(page_title="Brutology", layout="wide")
st.title("Brutology - Brutus E46 330i")


@st.cache_data
def load(session_id: int, _mtime: float) -> pd.DataFrame:
    """Nacita relaciu ako tabulku: riadok = cas, stlpec = velicina."""
    storage = Storage()
    rows = storage.db.execute(
        "SELECT t, name, value FROM samples WHERE session_id=?", (session_id,)
    ).fetchall()
    storage.close()
    df = pd.DataFrame(rows, columns=["t", "name", "value"])
    return df.pivot_table(index="t", columns="name", values="value").sort_index()


storage = Storage()
sessions = storage.sessions()
storage.close()

if not sessions:
    st.info("Zatiaľ nie je nahraná žiadna relácia. Spusti:  python scripts/simulate.py")
    st.stop()

labels = {
    s[0]: f"#{s[0]} - {datetime.fromtimestamp(s[1]):%d.%m.%Y %H:%M} - {s[2] or 'bez poznámky'}"
    for s in sessions
}
sid = st.sidebar.selectbox("Relácia", list(labels), format_func=labels.get,
                           index=len(labels) - 1)
mtime = DEFAULT_DB.stat().st_mtime
df = load(sid, mtime)

signals = st.sidebar.multiselect(
    "Veličiny", list(df.columns),
    default=[c for c in ("rpm", "coolant_temp_c", "stft_pct") if c in df.columns],
)
smooth = st.sidebar.slider("Vyhladenie (počet vzoriek)", 1, 50, 1)

c1, c2, c3 = st.columns(3)
c1.metric("Trvanie", f"{df.index.max():.0f} s")
c2.metric("Vzoriek na veličinu", len(df))
misfire_cols = [c for c in df.columns if c.startswith("misfire_cyl")]
if misfire_cols:
    c3.metric("Výpadky zapaľovania (všetky valce)", int(df[misfire_cols].sum().sum()))

findings = analyze(df)
suspects = rank_causes(findings)
if suspects:
    st.subheader("Najpravdepodobnejšie príčiny")
    for i, s in enumerate(suspects[:5], 1):
        with st.expander(f"{i}. {s.name}  ·  skóre {s.score:.1f}", expanded=i == 1):
            st.markdown(f"**Prečo:** {', '.join(s.evidence)}  \n**Čo urobiť:** {s.tip}")

st.subheader("Nálezy")
if findings:
    for f in findings:
        icon = SEVERITY_ICON.get(f.severity, "⚪")
        st.markdown(f"{icon} **{f.title}** · {f.when()}  \n{f.detail}")
    st.caption("Nálezy sú v grafoch vyznačené farebným pásom. Prahy sú zatiaľ "
               "odhady – doladíme ich na reálnych dátach z auta.")
else:
    st.success("Žiadne anomálie nenájdené.")
    st.caption(NO_FINDINGS_HINT)

if signals:
    fig = make_subplots(rows=len(signals), cols=1, shared_xaxes=True,
                        subplot_titles=signals, vertical_spacing=0.06)
    for i, name in enumerate(signals, start=1):
        y = df[name].rolling(smooth, min_periods=1).mean() if smooth > 1 else df[name]
        fig.add_trace(go.Scatter(x=df.index, y=y, name=name, mode="lines"), row=i, col=1)
        for f in findings:
            if f.signal == name:
                fig.add_vrect(x0=f.t_start, x1=max(f.t_end, f.t_start + 0.5),
                              fillcolor=SEVERITY_COLOR.get(f.severity, "gray"),
                              opacity=0.15, line_width=0, row=i, col=1)
    fig.update_xaxes(title_text="čas od začiatku nahrávania [s]", row=len(signals), col=1)
    fig.update_layout(height=260 * len(signals), showlegend=False,
                      margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, width="stretch")
else:
    st.write("Vyber aspoň jednu veličinu v ľavom paneli.")

with st.expander("Surové dáta"):
    st.dataframe(df)
