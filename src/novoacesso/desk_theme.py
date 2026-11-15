"""Desk's compact desktop styling, based on public interface references."""
STYLE='''
QFrame#titleStrip{background:#292727;border-bottom:0;}
QFrame#titleStrip QLabel{background:transparent;}
QFrame#addressBar{background:#2e2c2c;border-bottom:1px solid #424040;}
QPushButton#navTab{border:1px solid transparent;border-radius:2px;background:#242222;padding:5px 14px;}
QPushButton#navTab:hover{background:#3a3737;}
QPushButton#navTab[selected="true"]{background:#3b3838;border-color:#595454;}
QPushButton#navTab:focus{border-color:#ef857d;}
QToolButton#windowControl,QToolButton#windowClose{font-size:18px;background:transparent;border:0;border-radius:0;padding:0;}
QToolButton#windowControl:hover{background:#454141;}
QToolButton#windowClose:hover,QToolButton#windowClose:pressed{background:#d9443b;color:white;}
QPushButton#featureTile{border:1px solid #666060;border-radius:3px;padding:0;min-height:154px;text-align:left;}
QPushButton#featureTile:hover{border-color:#c4b9b9;}
QPushButton#featureTile:pressed{border-color:#fff;}
QPushButton#featureTile:focus{border:1px solid #ffc0b9;}
QLabel#tileTitle{font-size:18px;font-weight:600;color:white;background:transparent;}
QLabel#tileDescription{font-size:13px;color:#eee7e7;background:transparent;}
QLabel#tileAction{font-size:12px;color:white;text-decoration:underline;background:transparent;}
QLabel#deviceLabel{font-size:16px;color:#d4d0d0;}
QLineEdit#localAddress{font-size:38px;font-weight:600;color:#ff554c;}
QLineEdit#localAddress{border:1px solid transparent;border-radius:3px;}
QLineEdit#localAddress:hover,QLineEdit#localAddress:focus{background:rgba(239,68,59,22);border-color:#89504b;}
QLineEdit#localAddress[copied="true"]{background:rgba(63,157,97,26);border-color:#54906b;}
QLineEdit#remoteAddress{background:#211f1f;border-color:#555050;border-radius:2px;}
QPushButton#primary{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f4574b,stop:1 #df3d33);border-color:#ed5045;border-radius:3px;}
QPushButton#primary:hover{background:#fb6559;border-color:#ff9d93;}
QPushButton#primary:pressed{background:#b9332b;border-color:#ffbeb7;}
QPushButton#primary:disabled{background:#703c37;border-color:#703c37;color:#bfa19d;}
QToolButton#sessionTool{font-size:13px;padding:6px 9px;border-radius:2px;}
QFrame#sessionToolbar{background:#2e2b2b;border:1px solid #4f4949;border-radius:2px;}
QFrame#connectorCard{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #40566b,stop:1 #25313d);border-color:#657b8c;border-radius:2px;}
QFrame#acceptHeader,QFrame#acceptFooter{background:#2e2b2b;}
QPushButton#acceptConnection{border-radius:2px;min-height:22px;background:#31924f;border-color:#3eaa60;}
QPushButton#acceptConnection:hover{background:#3da85d;}
QPushButton#dangerOutline{border-radius:2px;}
QWidget#settingsSidebar{background:#2b2828;border-right:1px solid #4c4646;}
QLabel#settingsTitle{background:transparent;color:#f5685e;font-size:23px;padding:2px 18px 10px;}
QLabel#settingsHeading{font-size:25px;font-weight:400;border-bottom:1px solid #575151;padding-bottom:12px;}
QListWidget#settingsNavigation{background:#2b2828;border:0;padding:2px 6px;}
QListWidget#settingsNavigation::item{padding:13px 12px;border-left:3px solid transparent;}
QListWidget#settingsNavigation::item:selected{background:#3b3030;border-left-color:#f4564c;color:#ff8177;}
QFrame#connectionCard{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #353132,stop:1 #262424);border-color:#615859;border-radius:3px;}
QFrame#fullscreenBar{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #454b5c,stop:1 #2d3545);border:1px solid #6d7588;border-radius:0;}
QFrame#fullscreenBar QPushButton,QFrame#fullscreenBar QToolButton{background:#b7443e;border:1px solid #e2665c;border-radius:0;padding:5px;min-height:17px;}
QFrame#fullscreenBar QPushButton:hover,QFrame#fullscreenBar QToolButton:hover{background:#ef554a;border-color:#ffbab1;}
QFrame#fullscreenBar QPushButton:checked{background:#ef554a;border-color:#ffbab1;}
QFrame#fullscreenBar QPushButton:disabled,QFrame#fullscreenBar QToolButton:disabled{background:#53424a;border-color:#695761;color:#999;}
'''
