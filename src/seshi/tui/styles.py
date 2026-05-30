from seshi.themes import Palette


def theme_css(palette: Palette) -> str:
    return f"""
Screen {{
    background: {palette.bg};
}}

#header {{
    border: solid {palette.border};
    color: {palette.fg};
    background: {palette.bg};
}}

#header .logo {{
    color: {palette.accent};
}}

#tab-bar {{
    color: {palette.fg_muted};
}}

#tab-bar .active {{
    color: {palette.accent};
    text-style: bold;
}}

#search-bar {{
    color: {palette.fg};
    background: {palette.bg};
}}

#session-list {{
    border: solid {palette.border_dim};
    color: {palette.fg};
    background: {palette.bg};
}}

.session-row {{
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
    color: {palette.fg_dim};
}}

#preview {{
    border: solid {palette.border_dim};
    color: {palette.fg_muted};
    background: {palette.bg};
}}

#preview .role-user {{
    color: {palette.user};
}}

#preview .role-assistant {{
    color: {palette.assistant};
}}

#footer {{
    color: {palette.fg_dim};
    background: {palette.bg};
}}

#footer .key {{
    color: {palette.accent};
    text-style: bold;
}}

#overview, #projects-view, #help-view {{
    color: {palette.fg};
    background: {palette.bg};
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
