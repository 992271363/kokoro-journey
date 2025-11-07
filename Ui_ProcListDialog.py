# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ProcListDialog.ui'
##
## Created by: Qt User Interface Compiler version 6.2.4
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QHeaderView,
    QPushButton, QSizePolicy, QSpacerItem, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)

class Ui_ProcList(object):
    def setupUi(self, ProcList):
        if not ProcList.objectName():
            ProcList.setObjectName(u"ProcList")
        ProcList.resize(564, 429)
        self.verticalLayout = QVBoxLayout(ProcList)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.procTable = QTableWidget(ProcList)
        if (self.procTable.columnCount() < 3):
            self.procTable.setColumnCount(3)
        __qtablewidgetitem = QTableWidgetItem()
        self.procTable.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.procTable.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        __qtablewidgetitem2.setTextAlignment(Qt.AlignLeading|Qt.AlignVCenter);
        self.procTable.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        self.procTable.setObjectName(u"procTable")

        self.verticalLayout.addWidget(self.procTable)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.pushButton_accept = QPushButton(ProcList)
        self.pushButton_accept.setObjectName(u"pushButton_accept")

        self.horizontalLayout.addWidget(self.pushButton_accept)

        self.pushButton_reject = QPushButton(ProcList)
        self.pushButton_reject.setObjectName(u"pushButton_reject")

        self.horizontalLayout.addWidget(self.pushButton_reject)


        self.verticalLayout.addLayout(self.horizontalLayout)


        self.retranslateUi(ProcList)

        QMetaObject.connectSlotsByName(ProcList)
    # setupUi

    def retranslateUi(self, ProcList):
        ProcList.setWindowTitle(QCoreApplication.translate("ProcList", u"\u8fdb\u7a0b\u5217\u8868", None))
        ___qtablewidgetitem = self.procTable.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("ProcList", u"PID", None));
        ___qtablewidgetitem1 = self.procTable.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("ProcList", u"\u8fdb\u7a0b\u540d", None));
        ___qtablewidgetitem2 = self.procTable.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("ProcList", u"\u8fdb\u7a0b\u8def\u5f84", None));
        self.pushButton_accept.setText(QCoreApplication.translate("ProcList", u"\u786e\u8ba4", None))
        self.pushButton_reject.setText(QCoreApplication.translate("ProcList", u"\u53d6\u6d88", None))
    # retranslateUi

