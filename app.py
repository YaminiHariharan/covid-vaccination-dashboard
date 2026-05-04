import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import threading, time
warnings_import = __import__("warnings"); warnings_import.filterwarnings("ignore")

# ── Data ────────────────────────────────────────────────────────────────────
URL = ("https://docs.google.com/spreadsheets/d/e/"
       "2PACX-1vQ3tH-i9VBeECGw9yyyqroYrB7buCZvCCnXGaKtNUAz0F-tMDUWjamfOrOa5cUInIRnH2ZKYgR7htqR"
       "/pub?output=csv")

df_raw = pd.read_csv(URL)
print("Columns:", df_raw.columns.tolist())

# Parse date
for dc in ["month", "date", "week_date", "mmwr_week"]:
    if dc in df_raw.columns:
        df_raw["date"] = pd.to_datetime(df_raw[dc], errors="coerce")
        if df_raw["date"].notna().any():
            print(f"Dates from: {dc}")
            break

df = df_raw[
    (df_raw["age_group"] != "all_ages") &
    (df_raw["vaccine_product"] == "all_types")
].copy()
for col in df.columns:
    if col not in ["outcome","month","age_group","vaccine_product","date"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

print(f"Loaded {len(df):,} rows | outcomes={df['outcome'].unique()} | ages={df['age_group'].unique()}")
print("IR cols:", [c for c in df.columns if "_ir" in c.lower()])

# ── Auto-detect column names ─────────────────────────────────────────────────
ir_cols = [c for c in df.columns if "_ir" in c.lower()]

def _find(must, must_not=()):
    for c in ir_cols:
        cl = c.lower()
        if all(k in cl for k in must) and not any(k in cl for k in must_not):
            return c
    return None

unvax_c  = _find(["unvax","crude"], ["adj"]) or _find(["unvax"], ["adj"])
prim_c   = _find(["crude"], ["unvax","booster","adj"]) or _find(["vax","crude"], ["unvax","booster","adj"])
boost_c  = _find(["booster","crude"], ["adj"]) or _find(["booster"], ["adj"])
unvax_a  = _find(["unvax","adj"]) or _find(["unvax"], ["crude"])
prim_a   = _find(["adj"], ["unvax","booster"]) or _find(["vax","adj"], ["unvax","booster"])
boost_a  = _find(["booster","adj"]) or _find(["booster"], ["crude"])
irr_col  = _find(["irr","crude"], ["adj"]) or _find(["irr"])

CRUDE_COLS = {k:v for k,v in {"Unvaccinated":unvax_c,"Primary Series":prim_c,"Booster":boost_c}.items() if v}
ADJ_COLS   = {k:v for k,v in {"Unvaccinated":unvax_a,"Primary Series":prim_a,"Booster":boost_a}.items() if v}
print("CRUDE_COLS:", CRUDE_COLS)
print("ADJ_COLS:  ", ADJ_COLS)
print("IRR col:   ", irr_col)

AGE_ORDER = [a for a in ["5-11","12-17","18-49","50-64","65+"] if a in df["age_group"].values]
sorted_dates = sorted(df["date"].dropna().unique())
min_d, max_d = 0, len(sorted_dates)-1

PALETTE = {"Unvaccinated":"#D55E00","Primary Series":"#0072B2","Booster":"#009E73"}
DASHES  = {"Unvaccinated":"solid","Primary Series":"dot","Booster":"dash"}

def cols_for(rt): return CRUDE_COLS if rt=="crude" else ADJ_COLS

# ── Styles ───────────────────────────────────────────────────────────────────
SIDEBAR = {
    "background": "#1a2e45",
    "minHeight": "100vh",
    "padding": "24px 18px",
    "position": "sticky",
    "top": 0,
}
LBL  = {"color": "#a8c4d8", "fontSize": "0.78rem", "fontWeight": "700",
        "letterSpacing": "0.08em", "textTransform": "uppercase", "marginBottom": "6px"}
CTRL = {"marginBottom": "22px"}
STAT_CARD = {
    "backgroundColor": "#ffffff",
    "borderRadius": "10px",
    "padding": "14px 18px",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.08)",
    "textAlign": "center",
    "flex": "1",
}
RADIO_STYLE = {"color": "#e2edf5", "fontSize": "0.9rem"}

# ── Sidebar ──────────────────────────────────────────────────────────────────
sidebar = html.Div([
    html.Div([
        html.H5("COVID-19", style={"color":"white","margin":0,"fontWeight":"800","fontSize":"1.1rem"}),
        html.H6("Vaccination Explorer", style={"color":"#7fb3cf","margin":"2px 0 4px","fontWeight":"600"}),
        html.Small("CDC  2021 – 2022", style={"color":"#4d7a96","fontSize":"0.75rem"}),
    ], style={"marginBottom":"30px","paddingBottom":"18px","borderBottom":"1px solid #2d4a62"}),

    # Outcome
    html.Div([
        html.P("Outcome", style=LBL),
        dcc.RadioItems(id="s-outcome",
            options=[{"label":"  Cases","value":"case"},
                     {"label":"  Deaths","value":"death"}],
            value="death",
            labelStyle={"display":"block","marginBottom":"6px","cursor":"pointer"},
            inputStyle={"marginRight":"7px"},
            style=RADIO_STYLE),
    ], style=CTRL),

    # Age Group
    html.Div([
        html.P("Age Group", style=LBL),
        dcc.Dropdown(id="s-age",
            options=[{"label":a,"value":a} for a in AGE_ORDER],
            value="65+", clearable=False,
            style={"fontSize":"0.88rem"}),
    ], style=CTRL),

    # Rate Type (fixed to Crude — age-adjusted not needed)
    dcc.Store(id="s-rate", data="crude"),

    # Time Range
    html.Div([
        html.P("Time Range", style=LBL),
        html.Div(id="range-label", style={"color":"#7fb3cf","fontSize":"0.8rem","marginBottom":"8px"}),
        dcc.RangeSlider(id="s-range",
            min=min_d, max=max_d, step=1,
            value=[min_d, max_d],
            marks={0: pd.Timestamp(sorted_dates[0]).strftime("%b %y"),
                   max_d: pd.Timestamp(sorted_dates[-1]).strftime("%b %y")},
            allowCross=False,
            tooltip={"placement":"bottom","always_visible":False}),
    ], style=CTRL),

    html.Hr(style={"borderColor":"#2d4a62","margin":"10px 0 20px"}),
    html.Small([
        "Colors: Okabe-Ito palette",html.Br(),
        "Colorblind-safe · Munzner Ch. 5/6/10"
    ], style={"color":"#4d7a96","fontSize":"0.72rem","lineHeight":"1.7"}),
], style=SIDEBAR)

# ── KPI row ──────────────────────────────────────────────────────────────────
kpi_row = html.Div([
    html.Div([
        html.P("Unvax Rate", style={"margin":0,"color":"#888","fontSize":"0.75rem","fontWeight":"600"}),
        html.H4(id="kpi-unvax", style={"margin":"4px 0 0","color":"#D55E00","fontWeight":"800"}),
        html.Small("per 100,000", style={"color":"#aaa","fontSize":"0.72rem"}),
    ], style=STAT_CARD),
    html.Div([
        html.P("Vaccinated Rate", style={"margin":0,"color":"#888","fontSize":"0.75rem","fontWeight":"600"}),
        html.H4(id="kpi-vax", style={"margin":"4px 0 0","color":"#0072B2","fontWeight":"800"}),
        html.Small("per 100,000", style={"color":"#aaa","fontSize":"0.72rem"}),
    ], style=STAT_CARD),
    html.Div([
        html.P("Avg IRR", style={"margin":0,"color":"#888","fontSize":"0.75rem","fontWeight":"600"}),
        html.H4(id="kpi-irr", style={"margin":"4px 0 0","color":"#009E73","fontWeight":"800"}),
        html.Small("unvax ÷ vax rate", style={"color":"#aaa","fontSize":"0.72rem"}),
    ], style=STAT_CARD),
], style={"display":"flex","gap":"14px","marginBottom":"16px"})

# ── Chart cards ──────────────────────────────────────────────────────────────
def card(title, child_id, insight=None, extra_ctrl=None):
    inner = []
    if insight:
        inner.append(html.P(insight,
            style={"fontSize":"0.78rem","color":"#555","backgroundColor":"#f7f9fc",
                   "borderLeft":"3px solid #0072B2","padding":"7px 10px",
                   "borderRadius":"4px","margin":"0 0 10px"}))
    if extra_ctrl:
        inner.append(extra_ctrl)
    inner.append(dcc.Graph(id=child_id, config={"displayModeBar":False}))
    return dbc.Card([
        dbc.CardHeader(title,
            style={"fontWeight":"700","fontSize":"0.88rem",
                   "backgroundColor":"#f0f4f8","borderBottom":"2px solid #d0dce8"}),
        dbc.CardBody(inner, style={"padding":"12px"}),
    ], className="shadow-sm", style={"borderRadius":"10px","border":"none"})

chart_a = card(
    "Chart A — Rates Over Time",
    "fig-a",
    insight="Line style (solid/dot/dash) redundantly encodes group alongside color — readable in greyscale and for colorblind viewers.",
)

chart_bar = card(
    "Bar Chart — Rates by Age Group",
    "fig-b",
    insight="Compare magnitude across age groups at the selected time point.",
)

chart_irr = card(
    "IRR Heatmap — When Did Vaccines Work Hardest?",
    "fig-c",
    insight="Higher IRR = stronger protection. Dark red = vaccines were most effective.",
)

chart_d = card(
    "Chart D — Cases vs. Deaths IRR",
    "fig-d",
    insight="Death-IRR >> Case-IRR means vaccines prevented severity far better than infection.",
    extra_ctrl=html.Div([
        html.Label("Age Group for Viz D:", style={"fontWeight":"600","fontSize":"0.8rem","marginRight":"8px"}),
        dcc.Dropdown(id="d-age",
            options=[{"label":a,"value":a} for a in AGE_ORDER],
            value="65+", clearable=False,
            style={"display":"inline-block","width":"100px","fontSize":"0.85rem","verticalAlign":"middle"}),
    ], style={"marginBottom":"8px"}),
)

main_area = html.Div([
    kpi_row,
    html.Div(chart_a, style={"marginBottom":"16px"}),
    dbc.Row([
        dbc.Col(chart_bar, md=6),
        dbc.Col(chart_irr, md=6),
    ], className="g-3 mb-3"),
    html.Div(chart_d, style={"marginBottom":"16px"}),
    html.Footer(
        html.Small("Data: CDC Open Data · Palette: Okabe-Ito · Design: Munzner Ch.5/6/10",
                   style={"color":"#bbb","fontSize":"0.72rem"}),
        style={"textAlign":"center","padding":"20px 0 8px"}),
], style={"padding":"20px 24px","backgroundColor":"#eef2f7","minHeight":"100vh"})

# ── App ──────────────────────────────────────────────────────────────────────
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP],
                title="COVID-19 Vaccination Explorer")
app.layout = dbc.Container(
    dbc.Row([
        dbc.Col(sidebar, md=2, style={"padding":0}),
        dbc.Col(main_area, md=10, style={"padding":0}),
    ], className="g-0"),
    fluid=True, style={"fontFamily":"'Segoe UI',Arial,sans-serif"}
)

# ── Callbacks ────────────────────────────────────────────────────────────────
def filtered(outcome, rate, date_range):
    d0, d1 = sorted_dates[date_range[0]], sorted_dates[date_range[1]]
    return df[(df["outcome"]==outcome) &
              (df["date"]>=d0) & (df["date"]<=d1)].copy()

@app.callback(
    Output("range-label","children"),
    Input("s-range","value"),
)
def update_label(dr):
    d0 = pd.Timestamp(sorted_dates[dr[0]]).strftime("%b %Y")
    d1 = pd.Timestamp(sorted_dates[dr[1]]).strftime("%b %Y")
    return f"{d0} → {d1}"

@app.callback(
    Output("kpi-unvax","children"),
    Output("kpi-vax","children"),
    Output("kpi-irr","children"),
    Input("s-outcome","value"),
    Input("s-rate","value"),
    Input("s-range","value"),
    Input("s-age","value"),
)
def update_kpis(outcome, rate, dr, age):
    sub = filtered(outcome, rate, dr)
    sub = sub[sub["age_group"]==age]
    cols = cols_for(rate)
    uv = sub[cols.get("Unvaccinated","")].mean() if cols.get("Unvaccinated","") in sub.columns else None
    vx = sub[cols.get("Primary Series","")].mean() if cols.get("Primary Series","") in sub.columns else None
    irr = (uv/vx) if (uv and vx and vx!=0) else None
    fmt = lambda v: f"{v:,.1f}" if v is not None else "—"
    return fmt(uv), fmt(vx), (f"{irr:.1f}×" if irr else "—")

@app.callback(
    Output("fig-a","figure"),
    Input("s-outcome","value"),
    Input("s-rate","value"),
    Input("s-range","value"),
    Input("s-age","value"),
)
def update_a(outcome, rate, dr, age):
    cols = cols_for(rate)
    sub = filtered(outcome, rate, dr)
    sub = sub[sub["age_group"]==age].sort_values("date")
    fig = go.Figure()
    for label, col in cols.items():
        if col not in sub.columns: continue
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub[col], name=label, mode="lines",
            line=dict(color=PALETTE[label], dash=DASHES[label], width=2.8),
            hovertemplate=f"<b>{label}</b><br>%{{x|%b %Y}}<br>Rate: %{{y:.1f}}<extra></extra>",
        ))
    # surge annotation
    if unvax_c and unvax_c in sub.columns:
        peak = sub.groupby("date")[unvax_c].mean()
        if not peak.empty:
            pd_ts = peak.idxmax()
            fig.add_vline(x=pd_ts.timestamp()*1000,
                line=dict(color="rgba(150,150,150,0.4)", dash="dot", width=1.5),
                annotation_text="▲ Peak", annotation_position="top",
                annotation_font=dict(size=9, color="#999"))
    rl = "Crude" if rate=="crude" else "Age-Adjusted"
    fig.update_layout(
        xaxis=dict(title="Date", tickformat="%b %Y", showgrid=True, gridcolor="#ebebeb", zeroline=False),
        yaxis=dict(title=f"{rl} Rate per 100,000", showgrid=True, gridcolor="#ebebeb", zeroline=False),
        legend=dict(orientation="h", y=1.08, x=1, xanchor="right",
                    bgcolor="rgba(255,255,255,0.85)", bordercolor="#ddd", borderwidth=1),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", height=310,
        margin=dict(t=30, b=45, l=65, r=20),
    )
    return fig

@app.callback(
    Output("fig-b","figure"),
    Input("s-outcome","value"),
    Input("s-rate","value"),
    Input("s-range","value"),
)
def update_b(outcome, rate, dr):
    cols = cols_for(rate)
    sub = filtered(outcome, rate, dr)
    present = [c for c in cols.values() if c in sub.columns]
    agg = (sub.groupby("age_group")[present].mean().reset_index()
             .set_index("age_group").reindex(AGE_ORDER).reset_index())
    fig = go.Figure()
    for label, col in cols.items():
        if col not in agg.columns: continue
        fig.add_trace(go.Bar(
            name=label, x=agg["age_group"], y=agg[col],
            marker_color=PALETTE[label],
            hovertemplate=f"<b>{label}</b><br>Age: %{{x}}<br>Rate: %{{y:.1f}}<extra></extra>",
        ))
    fig.update_layout(
        barmode="group",
        xaxis=dict(title="Age Group", categoryorder="array", categoryarray=AGE_ORDER),
        yaxis=dict(title="Rate per 100,000", showgrid=True, gridcolor="#ebebeb", zeroline=False),
        legend=dict(orientation="h", y=1.08, x=1, xanchor="right",
                    bgcolor="rgba(255,255,255,0.85)", bordercolor="#ddd", borderwidth=1),
        plot_bgcolor="white", paper_bgcolor="white",
        height=310, margin=dict(t=30, b=50, l=65, r=10),
    )
    return fig

@app.callback(
    Output("fig-c","figure"),
    Input("s-outcome","value"),
    Input("s-range","value"),
)
def update_c(outcome, dr):
    if not irr_col:
        return go.Figure().add_annotation(text="IRR column not found", showarrow=False)
    sub = filtered(outcome, "crude", dr)
    sub2 = sub[["date","age_group",irr_col]].rename(columns={irr_col:"irr"})
    pivot = (sub2.pivot_table(index="age_group", columns="date", values="irr", aggfunc="mean")
               .reindex(AGE_ORDER))
    xlbls = [pd.Timestamp(d).strftime("%b %y") for d in pivot.columns]
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=xlbls, y=pivot.index.tolist(),
        colorscale="YlOrRd",
        colorbar=dict(title=dict(text="IRR", side="right", font=dict(size=10)), thickness=12),
        hovertemplate="Age: %{y}<br>Period: %{x}<br>IRR: %{z:.2f}<extra></extra>",
        zmin=1, zmax=12,
    ))
    fig.update_layout(
        xaxis=dict(title="", tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(title="Age Group", tickfont=dict(size=10)),
        height=310, margin=dict(t=10, b=65, l=70, r=20),
        paper_bgcolor="white",
    )
    return fig

@app.callback(
    Output("fig-d","figure"),
    Input("s-range","value"),
    Input("d-age","value"),
)
def update_d(dr, age):
    if not irr_col:
        return go.Figure().add_annotation(text="IRR column not found", showarrow=False)
    d_colors = {"case":"#0072B2", "death":"#D55E00"}
    d_dashes  = {"case":"dot",     "death":"solid"}
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=1, fillcolor="rgba(200,50,50,0.06)", line_width=0)
    fig.add_hline(y=1, line=dict(color="#bbb", dash="dot", width=1.2),
                  annotation_text="IRR=1 (no difference)",
                  annotation_position="bottom right",
                  annotation_font=dict(size=9, color="#aaa"))
    for outcome in ["case", "death"]:
        sub = filtered(outcome, "crude", dr)
        sub = sub[sub["age_group"]==age].sort_values("date")
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub[irr_col],
            name=outcome.title() + " IRR",
            mode="lines",
            line=dict(color=d_colors[outcome], dash=d_dashes[outcome], width=2.8),
            hovertemplate=f"%{{x|%b %Y}}<br>{outcome.title()} IRR: %{{y:.2f}}<extra></extra>",
        ))
    fig.update_layout(
        legend=dict(orientation="h", y=1.08, x=1, xanchor="right",
                    bgcolor="rgba(255,255,255,0.85)", bordercolor="#ddd", borderwidth=1),
        xaxis=dict(title="Date", tickformat="%b %y", tickangle=-30,
                   showgrid=True, gridcolor="#ebebeb", zeroline=False),
        yaxis=dict(title="IRR (higher = more protection)",
                   showgrid=True, gridcolor="#ebebeb", zeroline=False),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified",
        height=310, margin=dict(t=30, b=50, l=65, r=10),
    )
    return fig
# ── Expose server for Render/gunicorn ────────────────────────────────────────
server = app.server  # needed by gunicorn

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
