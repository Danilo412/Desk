"""Native Qt theme based on the Astryx 0.7.16 semantic token roles."""
from pathlib import Path
from string import Template

ASSETS = Path(__file__).resolve().parents[2] / "assets"
COLORS = {
    "body": "#111112",
    "surface": "#1f1f22",
    "popover": "#28292c",
    "hover": "#303136",
    "pressed": "#383940",
    "line": "#3b3d43",
    "control": "#696b76",
    "text": "#dfe2e5",
    "muted": "#aaafb5",
    "disabled": "#818791",
    "accent": "#ff998e",
    "accent_hover": "#ffb4ab",
    "accent_pressed": "#ee857b",
    "accent_muted": "#3a2729",
    "on_accent": "#241315",
    "focus": "#8db9ff",
    "success": "#8addab",
    "success_muted": "#18382b",
    "danger": "#ffa7ad",
    "danger_muted": "#42292c",
    "info": "#aad0ff",
    "info_muted": "#203047",
    "warning": "#edc375",
}
ELEMENT_RADIUS = 8
CONTAINER_RADIUS = 12
MOTION_FAST = 175
MOTION_REVEAL = 310

STYLE = Template("""
QWidget { font-family: 'Segoe UI'; font-size: 14px; color: $text; }
QMainWindow, QWidget#deskWorkspace, QWidget#scrollContent, QScrollArea, QWidget#connectionOverlay {
    background: $body;
}
QLabel, QCheckBox, QRadioButton { background: transparent; }
QLabel#brand { font-size: 19px; font-weight: 700; }
QLabel#headline, QLabel#connectionHeading, QLabel#settingsHeading {
    font-size: 24px; font-weight: 600;
}
QLabel#sectionTitle, QLabel#connectorName, QLabel#sessionDevice {
    font-size: 17px; font-weight: 600;
}
QLabel#muted, QLabel#deviceLabel, QLabel#tileDescription, QLabel#imageHint {
    color: $muted;
}
QLabel#status, QLabel#sessionBadge, QLabel#recordingBadge {
    font-size: 12px; font-weight: 600; border-radius: ${element}px; padding: 4px 10px;
}
QLabel#status, QLabel#sessionBadge { background: $popover; color: $text; }
QLabel#sessionBadge[connected="true"] { background: $success_muted; color: $success; }
QLabel#recordingBadge { background: $danger_muted; color: $danger; }
QLabel#onlineDot { color: $success; }
QLabel#deviceLabel { font-weight: 600; }
QFrame#titleStrip, QFrame#addressBar, QFrame#acceptHeader {
    background: $surface; border-bottom: 1px solid $line;
}
QFrame#acceptFooter { background: $surface; border-top: 1px solid $line; }
QFrame#identityHero, QFrame#permissionsPanel, QFrame#connectionCard,
QFrame#connectorCard, QFrame#sessionToolbar, QFrame#fullscreenBar, QFrame#deskNotification {
    background: $surface; border: 1px solid $line; border-radius: ${container}px;
}
QFrame#identityHero {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 $surface,stop:1 $accent_muted);
}
QFrame#incomingNotice {
    background: $info_muted; border: 1px solid $info; border-radius: ${element}px;
}
QFrame#incomingNotice QLabel { color: $info; }
QFrame#deskNotification { border-left: 3px solid $accent; }
QFrame#fileDropArea {
    background: $surface; border: 1px dashed $control; border-radius: ${container}px;
}
QFrame#fileDropArea QLabel { color: $muted; }
QPushButton, QToolButton {
    background: $popover; border: 1px solid $line; border-radius: ${element}px;
    padding: 6px 12px; min-height: 18px; font-weight: 600;
}
QToolButton { background: transparent; border-color: transparent; padding: 5px 8px; }
QPushButton:hover, QToolButton:hover { background: $hover; border-color: $control; }
QPushButton:pressed, QToolButton:pressed { background: $pressed; }
QPushButton:checked, QToolButton:checked { background: $accent_muted; color: $accent; }
QPushButton:disabled, QToolButton:disabled { color: $disabled; border-color: transparent; }
QPushButton#primary, QPushButton#acceptConnection {
    background: $accent; color: $on_accent; border-color: $accent;
}
QPushButton#primary:hover, QPushButton#acceptConnection:hover { background: $accent_hover; }
QPushButton#primary:pressed, QPushButton#acceptConnection:pressed { background: $accent_pressed; }
QPushButton#primary:disabled, QPushButton#acceptConnection:disabled {
    background: $popover; color: $disabled; border-color: $line;
}
QPushButton#dangerOutline { background: $danger_muted; color: $danger; border-color: $line; }
QPushButton#dangerOutline:hover { border-color: $danger; }
QPushButton#dangerOutline:focus { border-color: $focus; }
QPushButton#dangerOutline:disabled { background: $surface; color: $disabled; }
QPushButton#outlineAccent, QToolButton#outlineAccent { background: $accent_muted; color: $accent; }
QPushButton#outlineAccent:hover, QToolButton#outlineAccent:hover { border-color: $accent; }
QPushButton#navTab, QPushButton#textAction { background: transparent; border-color: transparent; }
QPushButton#navTab:hover, QPushButton#textAction:hover { background: $hover; color: $text; }
QPushButton#navTab[selected="true"] { background: $accent_muted; color: $accent; }
QFrame#navigationIndicator { background: $accent; border: 0; }
QToolButton#windowControl, QToolButton#windowClose { padding: 0; font-size: 18px; }
QToolButton#windowClose:hover { background: $danger_muted; color: $danger; }
QToolButton#sessionTool, QPushButton#sessionTool { padding: 5px 8px; }
QPushButton#featureTile { background: $surface; border-radius: ${container}px; padding: 0; }
QPushButton#featureTile:hover { background: $popover; border-color: $accent; }
QPushButton#featureTile:pressed { background: $accent_muted; }
QLabel#tileTitle { color: $text; font-size: 16px; font-weight: 600; }
QLabel#tileAction { color: $accent; font-size: 13px; font-weight: 600; }
QToolButton::menu-indicator { image: none; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background: $body; border: 1px solid $control; border-radius: ${element}px;
    padding: 7px 10px; selection-background-color: $info_muted; selection-color: $text;
}
QLineEdit#remoteAddress { min-height: 20px; }
QLineEdit#localAddress {
    background: transparent; color: $text; font-size: 34px; font-weight: 700;
    border: 1px solid transparent; padding: 2px 4px;
}
QLineEdit#localAddress:hover { background: $accent_muted; border-color: $line; }
QLineEdit#localAddress[copied="true"] { background: $success_muted; color: $success; }
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border-color: $focus;
}
QPushButton#primary:focus, QPushButton#acceptConnection:focus, QToolButton#outlineAccent:focus,
QPushButton#featureTile:focus, QPushButton#navTab:focus, QLineEdit#localAddress:focus {
    border-color: $focus;
}
QCheckBox, QRadioButton { spacing: 8px; padding: 4px 0; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px; background: $body; border: 1px solid $control;
}
QCheckBox::indicator { border-radius: 4px; }
QCheckBox::indicator:checked { background: $accent_muted; border-color: $accent; image: url("$check"); }
QRadioButton::indicator { border-radius: 8px; }
QRadioButton::indicator:checked {
    border-color: $accent;
    background: qradialgradient(cx:.5,cy:.5,radius:.5,stop:0 $accent,stop:.49 $accent,stop:.55 $body);
}
QCheckBox:focus, QRadioButton:focus { color: $focus; }
QCheckBox:disabled, QRadioButton:disabled { color: $disabled; }
QTabWidget::pane { border: 0; }
QTabWidget#homeSections::pane, QTabWidget#sessionSide::pane { border-top: 1px solid $line; }
QTabBar::tab {
    background: transparent; color: $muted; padding: 10px 14px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: $text; background: $surface; }
QTabBar::tab:selected { color: $accent; border-color: $accent; font-weight: 600; }
QTabBar::tab:focus { border-bottom-color: $focus; }
QListWidget, QAbstractItemView {
    background: $surface; border: 1px solid $line; border-radius: ${element}px; padding: 4px;
}
QListWidget::item { padding: 9px 10px; border-radius: ${element}px; }
QListWidget::item:selected { background: $accent_muted; color: $accent; }
QListWidget::item:hover { background: $hover; }
QListWidget::item:selected:hover { background: $accent_muted; }
QListWidget#deviceCards { background: $body; border: 0; padding: 2px 0; }
QWidget#settingsSidebar { background: $surface; border-right: 1px solid $line; }
QLabel#settingsTitle { font-size: 17px; font-weight: 600; padding: 0 16px 8px; }
QListWidget#settingsNavigation { background: $surface; border: 0; padding: 4px 8px; }
QListWidget#settingsNavigation::item { padding: 12px 10px; border-left: 3px solid transparent; }
QListWidget#settingsNavigation::item:selected { background: $accent_muted; border-left-color: $accent; }
QLabel#imageSection { font-size: 16px; font-weight: 600; padding: 8px 0 4px; }
QLabel#connectionDevice { color: $accent; }
QMenu, QDialog { background: $surface; }
QMenu { border: 1px solid $control; padding: 5px; }
QMenu::item { padding: 8px 24px; border-radius: 4px; }
QMenu::item:selected { background: $hover; }
QMenu::item:disabled { color: $disabled; }
QMenu::separator { height: 1px; background: $line; margin: 5px 8px; }
QProgressBar { background: $popover; color: $text; border: 0; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: $accent; border-radius: 4px; }
QToolTip { background: $popover; color: $text; border: 1px solid $control; padding: 5px; }
QScrollArea { border: 0; }
QStatusBar { color: $muted; background: $body; border-top: 1px solid $line; font-size: 12px; }
QScrollBar { background: $body; }
QScrollBar:vertical { width: 10px; }
QScrollBar:horizontal { height: 10px; }
QScrollBar::handle { background: $control; border-radius: 4px; }
QScrollBar::handle:vertical { min-height: 32px; }
QScrollBar::handle:horizontal { min-width: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: $line; width: 3px; }
""").substitute(COLORS, element=ELEMENT_RADIUS, container=CONTAINER_RADIUS,
                check=(ASSETS / "check.svg").as_posix())
