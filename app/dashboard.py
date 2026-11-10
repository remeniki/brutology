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
PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b",
           "#e377c2"]

# jednotka podľa konca názvu veličiny (katalóg názvov je v sources.py)
UNITS = {"rpm": "ot/min", "_pct": "%", "_c": "°C", "_v": "V", "_kpa": "kPa",
         "_gs": "g/s", "_deg": "°", "_s": "s"}


def unit(name: str) -> str:
    for suffix, u in UNITS.items():
        if name == suffix or name.endswith(suffix):
            return u
    return ""


def label(name: str) -> str:
    u = unit(name)
    return f"{name} [{u}]" if u else name

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
view = st.sidebar.segmented_control(
    "Zobrazenie", ["Pod sebou", "Cez seba (vlastné osi)", "Cez seba (0–100 %)"],
    default="Pod sebou", required=True, key="view",
    help="Cez seba: veličiny v jednom grafe. Vlastné osi = každá má svoju stupnicu; "
         "0–100 % = všetky roztiahnuté na rovnakú výšku, aby bolo vidno, čo sa deje naraz.")
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

def series(name: str) -> pd.Series:
    return df[name].rolling(smooth, min_periods=1).mean() if smooth > 1 else df[name]


def add_bands(fig, names, **where):
    """Vyznačí nálezy farebným pásom (len pre zobrazené veličiny)."""
    for f in findings:
        if f.signal in names:
            fig.add_vrect(x0=f.t_start, x1=max(f.t_end, f.t_start + 0.5),
                          fillcolor=SEVERITY_COLOR.get(f.severity, "gray"),
                          opacity=0.12, line_width=0, **where)


X_TITLE = "čas od začiatku nahrávania [s]"

if not signals:
    st.info("Vyber aspoň jednu veličinu v ľavom paneli.")
elif view == "Pod sebou":
    fig = make_subplots(rows=len(signals), cols=1, shared_xaxes=True,
                        subplot_titles=[label(s) for s in signals], vertical_spacing=0.06)
    for i, name in enumerate(signals, start=1):
        fig.add_trace(go.Scatter(x=df.index, y=series(name), name=name, mode="lines"),
                      row=i, col=1)
        add_bands(fig, [name], row=i, col=1)
    fig.update_xaxes(title_text=X_TITLE, row=len(signals), col=1)
    fig.update_layout(height=260 * len(signals), showlegend=False,
                      margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, width="stretch")
else:
    fig = go.Figure()
    normalized = view == "Cez seba (0–100 %)"
    if not normalized and len(signals) > 4:
        st.warning("Viac ako 4 osi sú neprehľadné – zváž režim 0–100 %.")
    layout = {}
    for i, name in enumerate(signals):
        color = PALETTE[i % len(PALETTE)]
        y = series(name)
        hover = f"<b>{name}</b><br>%{{customdata:.2f}} {unit(name)}<br>t = %{{x:.1f}} s<extra></extra>"
        if normalized:
            lo, hi = y.min(), y.max()
            y_plot = (y - lo) / (hi - lo) * 100 if hi > lo else y * 0 + 50
            fig.add_trace(go.Scatter(x=df.index, y=y_plot, customdata=y, name=label(name),
                                     mode="lines", line=dict(color=color),
                                     hovertemplate=hover))
        else:
            axis = "y" if i == 0 else f"y{i + 1}"
            fig.add_trace(go.Scatter(x=df.index, y=y, customdata=y, name=label(name),
                                     mode="lines", line=dict(color=color), yaxis=axis,
                                     hovertemplate=hover))
            spec = dict(title=dict(text=label(name), font=dict(color=color)),
                        tickfont=dict(color=color), showgrid=i == 0)
            if i > 0:
                spec.update(overlaying="y", side="right" if i % 2 else "left",
                            anchor="free", autoshift=True)
            layout["yaxis" if i == 0 else f"yaxis{i + 1}"] = spec
    if normalized:
        layout["yaxis"] = dict(title="0 % = minimum, 100 % = maximum veličiny",
                               range=[-5, 105])
    add_bands(fig, signals)
    fig.update_layout(**layout, height=520, hovermode="x unified",
                      xaxis=dict(title=X_TITLE),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0),
                      margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, width="stretch")
    if normalized:
        st.caption("Každá veličina je roztiahnutá na celú výšku grafu, aby bolo vidno, "
                   "kedy sa čo deje naraz. Skutočné hodnoty uvidíš, keď prejdeš myšou nad graf.")

with st.expander("Surové dáta"):
    st.dataframe(df)
