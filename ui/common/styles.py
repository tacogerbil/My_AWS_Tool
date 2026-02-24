
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
