import sys; sys.path.insert(0,'.')
import test_filename_parse_dialog as T; from test_filename_parse_dialog import FilenameParseDialog; _fake_history=T._fake_history; _FakeBook=T._FakeBook
from PyQt6.QtWidgets import QWidget
with _fake_history([]):
    dlg = FilenameParseDialog([_FakeBook("/x/Author - Title.epub")])
dlg.adjustSize()
print("dlg", dlg.sizeHint().width())
for w in dlg.findChildren(QWidget):
    if w.parent() is dlg or w.sizeHint().width()>200:
        print(type(w).__name__, w.objectName(), w.sizeHint().width(), w.minimumSizeHint().width())
from PyQt6.QtWidgets import QApplication
print(QApplication.font().family(), QApplication.font().pointSizeF(), dlg.fontMetrics().averageCharWidth(), dlg.logicalDpiX())
from PyQt6.QtWidgets import QLabel
for l in dlg.findChildren(QLabel):
    print("LABEL", l.text()[:30], l.wordWrap(), l.sizeHint().width(), l.fontMetrics().averageCharWidth(), l.font().family(), l.font().pointSizeF())
print("style", QApplication.style().name(), "platform", QApplication.platformName())
lay = dlg.layout()
for i in range(lay.count()):
    it = lay.itemAt(i); print("outer item", i, it.sizeHint().width())
