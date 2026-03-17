import os as _os

_ICONS_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "icons")


def get_checkbox_style() -> str:
    """Return QSS for clearly visible, blue-checked QCheckBox indicators.

    Uses an absolute path to the bundled SVG so the stylesheet works
    regardless of the process working directory.
    """
    icon = _os.path.join(_ICONS_DIR, "check_white.svg").replace("\\", "/")
    return f"""
    QCheckBox {{
        spacing: 8px;
        color: #34495e;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid #adb5bd;
        border-radius: 3px;
        background: white;
    }}
    QCheckBox::indicator:hover {{
        border-color: #3498db;
        background: #f0f8ff;
    }}
    QCheckBox::indicator:checked {{
        background-color: #2980b9;
        border-color: #1a6ea3;
        image: url({icon});
    }}
    QCheckBox::indicator:checked:hover {{
        background-color: #3498db;
        border-color: #2980b9;
    }}
    QCheckBox::indicator:disabled {{
        background: #ecf0f1;
        border-color: #ced4da;
    }}
    """


def interpolate_color(val, min_val, max_val, start_color, end_color):
    """Interpolates between two RGB tuples."""
    ratio = (val - min_val) / (max_val - min_val)
    r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
    g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
    b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
    return f"#{r:02x}{g:02x}{b:02x}"

def get_progress_bar_style(percent: int) -> str:
    """
    Returns a QSS stylesheet with smooth color transition.
    Red (0%) -> Yellow (50%) -> Green (100%).
    """
    # RGB Constants
    c_red = (231, 76, 60)    # #e74c3c
    c_yellow = (241, 196, 15) # #f1c40f
    c_green = (46, 204, 113)  # #2ecc71
    
    if percent <= 50:
        # Red to Yellow
        color_hex = interpolate_color(percent, 0, 50, c_red, c_yellow)
    else:
        # Yellow to Green
        color_hex = interpolate_color(percent, 50, 100, c_yellow, c_green)
        
    return f"""
        QProgressBar {{
            border: 1px solid #bdc3c7;
            border-radius: 5px;
            text-align: center;
            min-height: 25px;
            font-weight: bold;
            font-size: 14px;
            background-color: #ecf0f1;
            color: #2c3e50;
        }}
        QProgressBar::chunk {{
            background-color: {color_hex};
            border-radius: 4px;
        }}
    """
