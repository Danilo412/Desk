"""Native Qt theme based on the Astryx semantic token roles."""
from pathlib import Path
from string import Template

ASSETS = Path(__file__).resolve().parents[2] / "assets"
COLORS = {
    "body": "#111112",
    "surface": "#1b1c1f",
    "card": "#212226",
    "popover": "#28292e",
    "hover": "#313339",
    "pressed": "#3a3c44",
    "line": "#2f3138",
    "border_strong": "#43464f",
    "control": "#5c606b",
    "text": "#e4e7eb",
    "muted": "#9fa5ad",
    "disabled": "#777d87",
    "accent": "#ff998e",
    "accent_hover": "#ffb4ab",
    "accent_pressed": "#ee857b",
    "accent_muted": "#3a2629",
    "on_accent": "#241315",
    "focus": "#8db9ff",
    "success": "#8addab",
    "success_hover": "#a5e8bf",
    "success_muted": "#163528",
    "on_success": "#0d2117",
    "danger": "#ffa7ad",
    "danger_muted": "#3f262a",
    "info": "#aad0ff",
    "info_muted": "#1c2c42",
    "warning": "#edc375",
    "warning_muted": "#382c16",
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
QLabel#brand { font-size: 18px; font-weight: 700; letter-spacing: 0.2px; }
QLabel#headline, QLabel#connectionHeading, QLabel#settingsHeading {
    font-size: 24px; font-weight: 600;
}
QLabel#sectionTitle, QLabel#connectorName, QLabel#sessionDevice {
    font-size: 16px; font-weight: 600;
}
QLabel#muted, QLabel#deviceLabel, QLabel#tileDescription, QLabel#imageHint {
    color: $muted;
}
QLabel#status, QLabel#sessionBadge, QLabel#recordingBadge,
QLabel#heroStatusPill, QLabel#accessModePill, QLabel#updateBadge {
    font-size: 12px; font-weight: 600; border-radius: ${element}px; padding: 4px 10px;
}
QLabel#status, QLabel#sessionBadge { background: $popover; color: $text; border: 1px solid $line; }
QLabel#sessionBadge[connected="true"] { background: $success_muted; color: $success; border-color: #265942; }
QLabel#recordingBadge { background: $danger_muted; color: $danger; border: 1px solid #63343a; }
QLabel#heroStatusPill { background: $popover; color: $muted; border: 1px solid $line; }
QLabel#heroStatusPill[state="online"], QLabel#heroStatusPill[state="active"] {
    background: $success_muted; color: $success; border-color: #265942;
}
QLabel#heroStatusPill[state="preparing"] {
    background: $warning_muted; color: $warning; border-color: #5c461f;
}
QLabel#accessModePill { background: $popover; color: $muted; border: 1px solid $line; }
QLabel#accessModePill[password="true"] { background: $info_muted; color: $info; border-color: #2f4b70; }
QLabel#updateBadge { background: $popover; color: $muted; border: 1px solid $line; }
QLabel#updateBadge[variant="success"] { background: $success_muted; color: $success; border-color: #265942; }
QLabel#updateBadge[variant="info"] { background: $info_muted; color: $info; border-color: #2f4b70; }
QLabel#updateBadge[variant="warning"] { background: $warning_muted; color: $warning; border-color: #5c461f; }
QLabel#onlineDot { color: $success; }
QLabel#deviceLabel { font-weight: 600; font-size: 13px; }
QLabel#remotePeerPill {
    background: $popover; border: 1px solid $line; border-radius: ${element}px;
    padding: 8px 12px; font-size: 15px; font-weight: 600; color: $text;
}
QFrame#titleStrip, QFrame#addressBar, QFrame#acceptHeader {
    background: $surface; border-bottom: 1px solid $line;
}
QFrame#acceptFooter { background: $surface; border-top: 1px solid $line; }
QFrame#identityHero, QFrame#permissionsPanel, QFrame#connectionCard,
QFrame#connectorCard, QFrame#sessionToolbar, QFrame#fullscreenBar,
QFrame#deskNotification, QFrame#settingsCard, QFrame#metricsBar {
    background: $surface; border: 1px solid $line; border-radius: ${container}px;
}
QFrame#settingsCard { background: $card; }
QFrame#metricsBar { border-radius: ${element}px; padding: 2px 6px; }
QFrame#identityHero {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 $surface,stop:0.65 #251e22,stop:1 $accent_muted);
    border: 1px solid $border_strong;
}
QFrame#updateBanner {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 $info_muted,stop:1 $surface);
    border: 1px solid #2f4b70; border-left: 3px solid $info; border-radius: ${container}px;
}
QFrame#updateBanner[ready="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 $success_muted,stop:1 $surface);
    border: 1px solid #265942; border-left: 3px solid $success;
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
QFrame#toolbarDivider { background: $line; max-width: 1px; min-width: 1px; margin: 4px 2px; }
QPushButton, QToolButton {
    background: $popover; border: 1px solid $line; border-radius: ${element}px;
    padding: 6px 12px; min-height: 20px; font-weight: 600;
}
QToolButton { background: transparent; border-color: transparent; padding: 5px 9px; }
QToolButton#iconAction {
    background: $popover; border: 1px solid $line; padding: 4px;
    min-width: 24px; min-height: 24px;
}
QToolButton#iconAction:hover { background: $hover; border-color: $border_strong; }
QPushButton:hover, QToolButton:hover { background: $hover; border-color: $border_strong; }
QPushButton:pressed, QToolButton:pressed { background: $pressed; }
QPushButton:checked, QToolButton:checked { background: $accent_muted; color: $accent; border-color: #5b383c; }
QPushButton:disabled, QToolButton:disabled { color: $disabled; border-color: transparent; }
QPushButton#primary {
    background: $accent; color: $on_accent; border-color: $accent;
}
QPushButton#primary:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton#primary:pressed { background: $accent_pressed; }
QPushButton#primary:disabled {
    background: $popover; color: $disabled; border-color: $line;
}
QPushButton#acceptConnection {
    background: $success; color: $on_success; border-color: $success; padding: 7px 18px;
}
QPushButton#acceptConnection:hover { background: $success_hover; border-color: $success_hover; }
QPushButton#acceptConnection:pressed { background: #73c895; }
QPushButton#dangerOutline { background: $danger_muted; color: $danger; border-color: #5c3439; }
QPushButton#dangerOutline:hover { background: #4c2b30; border-color: $danger; }
QPushButton#dangerOutline:focus { border-color: $focus; }
QPushButton#dangerOutline:disabled { background: $surface; color: $disabled; border-color: $line; }
QPushButton#outlineAccent, QToolButton#outlineAccent {
    background: $accent_muted; color: $accent; border-color: #5b383c;
}
QPushButton#outlineAccent:hover, QToolButton#outlineAccent:hover { border-color: $accent; background: #472e32; }
QFrame#identityHero QToolButton#outlineAccent, QToolButton#copyAddress {
    background: $popover; border: 1px solid $border_strong; padding: 6px 12px;
}
QFrame#identityHero QToolButton#outlineAccent:hover, QToolButton#copyAddress:hover {
    background: $hover; border-color: $accent;
}
QFrame#identityHero QToolButton#outlineAccent:focus, QToolButton#copyAddress:focus {
    border-color: $focus;
}
QToolButton#copyAddress[copied="true"] {
    background: $success_muted; color: $success; border-color: #265942;
}
QPushButton#navTab, QPushButton#textAction { background: transparent; border-color: transparent; }
QPushButton#navTab:hover, QPushButton#textAction:hover { background: $hover; color: $text; }
QPushButton#navTab[selected="true"] { background: $accent_muted; color: $accent; }
QFrame#navigationIndicator { background: $accent; border: 0; }
QToolButton#windowControl, QToolButton#windowClose { padding: 0; font-size: 17px; border-radius: 6px; }
QToolButton#windowClose:hover { background: $danger_muted; color: $danger; }
QToolButton#sessionTool, QPushButton#sessionTool {
    background: transparent; border: 1px solid transparent; padding: 5px 10px;
}
QToolButton#sessionTool:hover, QPushButton#sessionTool:hover {
    background: $hover; border-color: $line;
}
QWidget#segmentedGroup {
    background: $body; border: 1px solid $line; border-radius: ${element}px; padding: 2px;
}
QPushButton#segment {
    background: transparent; border: 0; border-radius: 6px; padding: 6px 12px; color: $muted;
}
QPushButton#segment:hover { color: $text; background: $hover; }
QPushButton#segment:checked { background: $accent_muted; color: $accent; }
QPushButton#featureTile {
    background: $card; border: 1px solid $line; border-radius: ${container}px; padding: 0;
}
QPushButton#featureTile:hover { background: $popover; border-color: $accent; }
QPushButton#featureTile:pressed { background: $accent_muted; }
QFrame#tileIconBadge {
    background: $popover; border: 1px solid $line; border-radius: ${element}px;
}
QLabel#tileTitle { color: $text; font-size: 15px; font-weight: 600; }
QLabel#tileAction { color: $accent; font-size: 13px; font-weight: 600; }
QToolButton::menu-indicator { image: none; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background: $body; border: 1px solid $border_strong; border-radius: ${element}px;
    padding: 7px 11px; selection-background-color: $info_muted; selection-color: $text;
}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QComboBox:hover {
    border-color: $control;
}
QComboBox { padding-right: 28px; min-height: 20px; }
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 26px; border: 0; background: transparent;
}
QComboBox::down-arrow {
    image: url("$chevron_down"); width: 14px; height: 14px;
}
QComboBox QAbstractItemView {
    background: $popover; border: 1px solid $border_strong; border-radius: ${element}px;
    padding: 4px; outline: 0; selection-background-color: $accent_muted; selection-color: $accent;
}
QLineEdit#remoteAddress { min-height: 20px; background: $body; }
QLineEdit#localAddress {
    background: transparent; color: $text; font-size: 32px; font-weight: 700;
    border: 1px solid transparent; border-radius: ${element}px; padding: 2px 6px 2px 0px;
}
QLineEdit#localAddress:hover { background: $accent_muted; border-color: #5b383c; }
QLineEdit#localAddress[copied="true"] { background: $success_muted; color: $success; border-color: #265942; }
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border-color: $focus;
}
QPushButton#primary:focus, QPushButton#acceptConnection:focus, QToolButton#outlineAccent:focus,
QPushButton#featureTile:focus, QPushButton#navTab:focus, QLineEdit#localAddress:focus {
    border-color: $focus;
}
QCheckBox, QRadioButton { spacing: 8px; padding: 3px 0; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px; background: $body; border: 1px solid $control;
}
QCheckBox::indicator { border-radius: 4px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: $accent; }
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
QLabel#settingsTitle { font-size: 17px; font-weight: 600; padding: 0 18px 8px; }
QListWidget#settingsNavigation { background: $surface; border: 0; padding: 4px 10px; }
QListWidget#settingsNavigation::item {
    padding: 11px 12px; border-left: 3px solid transparent; margin-bottom: 2px;
}
QListWidget#settingsNavigation::item:selected {
    background: $accent_muted; color: $accent; border-left-color: $accent; font-weight: 600;
}
QLabel#imageSection { font-size: 15px; font-weight: 600; padding: 6px 0 2px; }
QLabel#connectionDevice { color: $accent; }
QMenu, QDialog { background: $surface; }
QMenu { border: 1px solid $border_strong; border-radius: ${element}px; padding: 5px; }
QMenu::item { padding: 8px 24px; border-radius: 5px; }
QMenu::item:selected { background: $hover; }
QMenu::item:disabled { color: $disabled; }
QMenu::separator { height: 1px; background: $line; margin: 5px 8px; }
QProgressBar { background: $popover; color: $text; border: 0; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: $accent; border-radius: 4px; }
QToolTip { background: $popover; color: $text; border: 1px solid $border_strong; padding: 6px 8px; }
QScrollArea { border: 0; }
QStatusBar { color: $muted; background: $body; border-top: 1px solid $line; font-size: 12px; padding: 2px 12px; }
QStatusBar::item { border: 0; }
QScrollBar { background: $body; }
QScrollBar:vertical { width: 10px; }
QScrollBar:horizontal { height: 10px; }
QScrollBar::handle { background: $border_strong; border-radius: 4px; }
QScrollBar::handle:hover { background: $control; }
QScrollBar::handle:vertical { min-height: 32px; }
QScrollBar::handle:horizontal { min-width: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: $line; width: 2px; }
""").substitute(COLORS, element=ELEMENT_RADIUS, container=CONTAINER_RADIUS,
                check=(ASSETS / "check.svg").as_posix(),
                chevron_down=(ASSETS / "chevron-down.svg").as_posix())
