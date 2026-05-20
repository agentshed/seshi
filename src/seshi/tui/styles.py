from seshi.themes import Palette


def theme_css(palette: Palette) -> str:
    return f"""
Screen {{
    background: #1a1a2e;
}}

#header {{
    height: 5;
    border: solid {palette.border};
    padding: 0 2;
    color: {palette.fg};
    background: #1a1a2e;
}}

#header .logo {{
    color: {palette.accent};
}}

#tab-bar {{
    height: 1;
    padding: 0 1;
    color: {palette.fg_muted};
}}

#tab-bar .active {{
    color: {palette.accent};
    text-style: bold;
}}

#search-bar {{
    height: 1;
    padding: 0 1;
    color: {palette.fg};
    background: #1a1a2e;
}}

#session-list {{
    min-height: 10;
    border: solid {palette.border_dim};
    color: {palette.fg};
    background: #1a1a2e;
}}

.session-row {{
    height: 1;
    color: {palette.fg};
}}

.session-row.--highlight {{
    background: {palette.bg_selected};
    color: {palette.fg_selected};
}}

.session-row .favorite {{
    color: {palette.accent};
}}

.session-row .tag {{
    color: {palette.accent_soft};
}}

.session-row .time {{
    color: {palette.fg_dim};
}}

.session-row .cwd {{
    color: {palette.fg_muted};
}}

.group-header {{
    height: 1;
    color: {palette.fg_dim};
    padding: 0 1;
}}

#preview {{
    height: 8;
    border: solid {palette.border_dim};
    padding: 0 1;
    color: {palette.fg_muted};
    background: #1a1a2e;
}}

#preview .role-user {{
    color: {palette.user};
}}

#preview .role-assistant {{
    color: {palette.assistant};
}}

#footer {{
    height: 1;
    dock: bottom;
    color: {palette.fg_dim};
    padding: 0 1;
    background: #1a1a2e;
}}

#footer .key {{
    color: {palette.accent};
    text-style: bold;
}}

#overview, #projects-view, #help-view {{
    padding: 1 2;
    color: {palette.fg};
    background: #1a1a2e;
}}

.sparkline {{
    color: {palette.accent};
}}

.stat-label {{
    color: {palette.fg_muted};
}}

.stat-value {{
    color: {palette.fg};
    text-style: bold;
}}
"""
