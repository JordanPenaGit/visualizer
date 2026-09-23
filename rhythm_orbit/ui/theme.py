STYLE = """
QWidget { background: #0d141b; color: #dce5eb; font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 12px; }
QMainWindow { background: #0d141b; }
QFrame#panel { background: #131d26; border: 1px solid #263440; border-radius: 12px; }
QLabel { background: transparent; }
QLabel#brand { color: #d7f4e9; font-size: 23px; font-weight: 700; letter-spacing: 3px; }
QLabel#title { font-size: 21px; font-weight: 600; }
QLabel#muted { color: #8a9ca9; }
QLabel#eyebrow { color: #70dcc8; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QPushButton { border: 1px solid #344551; background: #1b2a35; border-radius: 7px; padding: 9px 12px; }
QPushButton:hover { background: #293d48; border-color: #70dcc8; }
QPushButton:checked { background: #2e4c4a; border-color: #70dcc8; }
QPushButton:disabled { color: #51616c; border-color: #22303b; }
QPushButton#primary { background: #70dcc8; color: #0d2324; font-weight: 700; border: 0; }
QComboBox, QSpinBox, QLineEdit { background: #14222c; border: 1px solid #344551; border-radius: 6px; padding: 7px; }
QComboBox::drop-down { border: 0; width: 20px; }
QListWidget { background: #131d26; border: 0; outline: none; }
QListWidget::item { padding: 9px 4px; border-bottom: 1px solid #22313d; }
QListWidget::item:selected { background: #243b43; color: #d7f4e9; }
QCheckBox { background: transparent; spacing: 8px; padding: 3px; }
QCheckBox::indicator { width: 13px; height: 13px; border-radius: 3px; border: 1px solid #526773; background: #0d141b; }
QCheckBox::indicator:checked { background: #70dcc8; border-color: #70dcc8; }
QSlider::groove:horizontal { height: 4px; border-radius: 2px; background: #2a3a46; }
QSlider::sub-page:horizontal { background: #70dcc8; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -4px 0; background: #dcf9ef; border-radius: 6px; }
QProgressBar { border: 0; background: #1c2b36; border-radius: 3px; height: 5px; text-align: center; }
QProgressBar::chunk { background: #70dcc8; border-radius: 3px; }
QToolTip { background: #233642; color: #edf6f3; border: 1px solid #70dcc8; padding: 8px; }
QScrollArea { border: 0; }
QScrollBar:vertical { width: 8px; background: #131d26; }
QScrollBar::handle:vertical { background: #344551; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
