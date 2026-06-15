"""
core/styles.py
==============
Design tokens + premium dark glassmorphism CSS, plus small HTML helpers for KPI
cards, badges and alert banners. Injected once per page via inject_global_css().

Palette: deep slate backgrounds, neon accents — emerald (ok), amber (warn),
coral (alert), electric blue (actions/AI).
"""

import streamlit as st

PALETTE = {
    "bg_deep": "#0b0f1a", "bg_panel": "#121826",
    "glass": "rgba(255,255,255,0.04)", "glass_border": "rgba(255,255,255,0.08)",
    "text": "#e8edf6", "muted": "#8b97ad",
    "emerald": "#10e0a0", "blue": "#3da9fc", "coral": "#ff5d6c",
    "amber": "#ffb454", "violet": "#a78bfa",
}


def inject_global_css() -> None:
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    :root {{
        --bg-deep:{PALETTE['bg_deep']}; --glass:{PALETTE['glass']};
        --glass-border:{PALETTE['glass_border']}; --text:{PALETTE['text']};
        --muted:{PALETTE['muted']}; --emerald:{PALETTE['emerald']};
        --blue:{PALETTE['blue']}; --coral:{PALETTE['coral']};
        --amber:{PALETTE['amber']}; --violet:{PALETTE['violet']};
    }}
    .stApp {{
        background:
          radial-gradient(1200px 700px at 15% -10%, rgba(61,169,252,0.10), transparent 55%),
          radial-gradient(1000px 600px at 95% 0%, rgba(167,139,250,0.10), transparent 50%),
          var(--bg-deep);
        color: var(--text); font-family:'Inter',sans-serif;
    }}
    .block-container {{ padding-top:2.0rem; padding-bottom:3rem; max-width:1320px; }}
    h1,h2,h3,h4 {{ color:var(--text); letter-spacing:-0.02em; }}
    h1 {{ font-weight:800; }}
    #MainMenu, footer {{ visibility:hidden; }}
    /* Keep the header present (transparent) so the sidebar expand arrow still works. */
    header[data-testid="stHeader"] {{ background:transparent; }}
    /* Force the collapsed-sidebar expand control to always be visible & clickable. */
    [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{
        visibility:visible !important; opacity:1 !important; display:flex !important;
        z-index:999999 !important; }}
    [data-testid="stSidebarCollapsedControl"] svg, [data-testid="collapsedControl"] svg {{
        color:var(--text) !important; fill:var(--text) !important; }}

    section[data-testid="stSidebar"] {{
        background:linear-gradient(180deg,#0e1422,#0b0f1a);
        border-right:1px solid var(--glass-border);
    }}
    section[data-testid="stSidebar"] * {{ color:var(--text); }}

    .glass-card {{
        background:var(--glass); border:1px solid var(--glass-border);
        border-radius:16px; padding:20px 22px; backdrop-filter:blur(14px);
        box-shadow:0 8px 30px rgba(0,0,0,0.35); transition:transform .18s ease;
    }}
    .glass-card:hover {{ transform:translateY(-3px); border-color:rgba(255,255,255,0.18); }}

    .kpi {{ background:var(--glass); border:1px solid var(--glass-border);
        border-radius:16px; padding:18px 20px; backdrop-filter:blur(14px);
        box-shadow:0 8px 26px rgba(0,0,0,0.30); position:relative; overflow:hidden; }}
    .kpi::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:4px;
        background:var(--accent,var(--blue)); box-shadow:0 0 18px 1px var(--accent,var(--blue)); }}
    .kpi .kpi-label {{ font-size:.78rem; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-weight:600; }}
    .kpi .kpi-value {{ font-size:2.0rem; font-weight:800; margin:6px 0 2px; line-height:1.05; }}
    .kpi .kpi-sub {{ font-size:.78rem; color:var(--muted); }}

    .glow-block {{ text-align:center; border-radius:18px; padding:26px;
        background:radial-gradient(120% 120% at 50% 0%, rgba(16,224,160,0.18), rgba(16,224,160,0.02));
        border:1px solid rgba(16,224,160,0.35);
        box-shadow:0 0 40px rgba(16,224,160,0.18), inset 0 0 24px rgba(16,224,160,0.06); }}
    .glow-block .gb-value {{ font-size:3rem; font-weight:800; color:var(--emerald); text-shadow:0 0 22px rgba(16,224,160,0.55); }}
    .glow-block .gb-label {{ color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-size:.8rem; font-weight:600; }}

    .badge {{ display:inline-block; padding:3px 11px; border-radius:999px; font-size:.74rem; font-weight:700; }}
    .badge-green  {{ background:rgba(16,224,160,0.14); color:var(--emerald); border:1px solid rgba(16,224,160,0.4); }}
    .badge-blue   {{ background:rgba(61,169,252,0.14); color:var(--blue);    border:1px solid rgba(61,169,252,0.4); }}
    .badge-amber  {{ background:rgba(255,180,84,0.14); color:var(--amber);   border:1px solid rgba(255,180,84,0.4); }}
    .badge-coral  {{ background:rgba(255,93,108,0.14); color:var(--coral);   border:1px solid rgba(255,93,108,0.4); }}
    .badge-violet {{ background:rgba(167,139,250,0.14);color:var(--violet);  border:1px solid rgba(167,139,250,0.4); }}

    .alert {{ border-radius:14px; padding:14px 18px; margin:6px 0; font-weight:600;
        display:flex; align-items:center; gap:12px; border:1px solid; }}
    .alert-coral {{ background:rgba(255,93,108,0.10); border-color:rgba(255,93,108,0.45); color:#ffd2d7; }}
    .alert-amber {{ background:rgba(255,180,84,0.10); border-color:rgba(255,180,84,0.45); color:#ffe7c4; }}
    .alert-green {{ background:rgba(16,224,160,0.10); border-color:rgba(16,224,160,0.45); color:#c4ffec; }}
    .alert-blue  {{ background:rgba(61,169,252,0.10); border-color:rgba(61,169,252,0.45); color:#cfe7ff; }}
    @keyframes pulseRed {{ 0%{{box-shadow:0 0 0 0 rgba(255,93,108,0.45);}} 70%{{box-shadow:0 0 0 14px rgba(255,93,108,0);}} 100%{{box-shadow:0 0 0 0 rgba(255,93,108,0);}} }}
    .alert-flash {{ animation:pulseRed 1.8s infinite; }}

    .headline {{ display:flex; align-items:center; gap:14px; background:var(--glass);
        border:1px solid var(--glass-border); border-left:4px solid var(--accent,var(--blue));
        border-radius:12px; padding:13px 16px; margin-bottom:10px; }}
    .headline .h-title {{ font-weight:700; font-size:.95rem; }}
    .headline .h-sub {{ color:var(--muted); font-size:.82rem; }}

    .stButton > button {{ background:linear-gradient(135deg,var(--blue),#2b6fd6); color:#fff;
        border:none; border-radius:11px; padding:.5rem 1.1rem; font-weight:700;
        box-shadow:0 6px 18px rgba(61,169,252,0.35); transition:transform .15s ease; }}
    .stButton > button:hover {{ transform:translateY(-2px); box-shadow:0 10px 26px rgba(61,169,252,0.5); }}
    .stDownloadButton > button {{ background:linear-gradient(135deg,var(--emerald),#07b07e);
        color:#04221a; border:none; border-radius:11px; font-weight:700; }}

    .stTextInput input, .stNumberInput input, .stTextArea textarea,
    .stSelectbox div[data-baseweb="select"] {{
        background:rgba(255,255,255,0.03)!important; border:1px solid var(--glass-border)!important;
        border-radius:10px!important; color:var(--text)!important; }}

    .pretty-table {{ width:100%; border-collapse:separate; border-spacing:0; font-size:.85rem;
        border-radius:12px; overflow:hidden; }}
    .pretty-table thead th {{ background:rgba(255,255,255,0.05); color:var(--muted);
        text-transform:uppercase; font-size:.70rem; letter-spacing:.06em; text-align:left;
        padding:11px 14px; font-weight:700; border-bottom:1px solid var(--glass-border); }}
    .pretty-table tbody td {{ padding:10px 14px; border-bottom:1px solid rgba(255,255,255,0.04); }}
    .pretty-table tbody tr:nth-child(even) {{ background:rgba(255,255,255,0.018); }}
    .pretty-table tbody tr:hover {{ background:rgba(61,169,252,0.06); }}
    .row-danger {{ background:rgba(255,93,108,0.09)!important; }}
    .row-warn   {{ background:rgba(255,180,84,0.08)!important; }}
    .row-good   {{ background:rgba(16,224,160,0.07)!important; }}

    .stTabs [data-baseweb="tab"] {{ background:var(--glass); border:1px solid var(--glass-border);
        border-radius:10px 10px 0 0; padding:8px 16px; color:var(--muted); }}
    .stTabs [aria-selected="true"] {{ background:rgba(61,169,252,0.14); color:var(--blue); border-color:rgba(61,169,252,0.4); }}

    .section-label {{ font-size:.76rem; text-transform:uppercase; letter-spacing:.12em;
        color:var(--muted); font-weight:700; margin:4px 0 10px; }}

    .login-hero {{ text-align:center; margin-bottom:8px; }}
    .login-hero .lh-logo {{ font-size:2.6rem; }}
    .login-hero .lh-title {{ font-size:1.7rem; font-weight:800; margin-top:6px; }}
    .login-hero .lh-sub {{ color:var(--muted); font-size:.9rem; }}
    </style>
    """, unsafe_allow_html=True)


# --------------------------- HTML helpers ----------------------------------
def kpi_card(label, value, sub="", accent="blue") -> str:
    hexc = PALETTE.get(accent, PALETTE["blue"])
    sub_html = f"<div class='kpi-sub'>{sub}</div>" if sub else ""
    return (f"<div class='kpi' style='--accent:{hexc}'>"
            f"<div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value' style='color:{hexc}'>{value}</div>{sub_html}</div>")


def badge(text, kind="green") -> str:
    return f"<span class='badge badge-{kind}'>{text}</span>"


def alert(text, kind="coral", icon="⚠️", flash=False) -> str:
    fl = " alert-flash" if flash else ""
    return f"<div class='alert alert-{kind}{fl}'><span style='font-size:1.3rem'>{icon}</span><span>{text}</span></div>"


def headline(title, sub="", accent="blue", icon="•") -> str:
    hexc = PALETTE.get(accent, PALETTE["blue"])
    sub_html = f"<div class='h-sub'>{sub}</div>" if sub else ""
    return (f"<div class='headline' style='--accent:{hexc}'>"
            f"<span style='font-size:1.3rem'>{icon}</span>"
            f"<div><div class='h-title'>{title}</div>{sub_html}</div></div>")


def section_label(text) -> str:
    return f"<div class='section-label'>{text}</div>"


def glow_block(value, label) -> str:
    return f"<div class='glow-block'><div class='gb-label'>{label}</div><div class='gb-value'>{value}</div></div>"
