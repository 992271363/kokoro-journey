# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'PidSelect.ui'
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
from PySide6.QtWidgets import (QApplication, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget)

class Ui_KokoroJourney(object):
    def setupUi(self, KokoroJourney):
        if not KokoroJourney.objectName():
            KokoroJourney.setObjectName(u"KokoroJourney")
        KokoroJourney.resize(277, 146)
        self.pushButton_procs = QPushButton(KokoroJourney)
        self.pushButton_procs.setObjectName(u"pushButton_procs")
        self.pushButton_procs.setGeometry(QRect(70, 100, 131, 31))
        self.layoutWidget = QWidget(KokoroJourney)
        self.layoutWidget.setObjectName(u"layoutWidget")
        self.layoutWidget.setGeometry(QRect(90, 20, 181, 62))
        self.verticalLayout = QVBoxLayout(self.layoutWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.proc_name_show = QLabel(self.layoutWidget)
        self.proc_name_show.setObjectName(u"proc_name_show")

        self.verticalLayout.addWidget(self.proc_name_show)

        self.proc_path_show = QLabel(self.layoutWidget)
        self.proc_path_show.setObjectName(u"proc_path_show")

        self.verticalLayout.addWidget(self.proc_path_show)

        self.proc_start_time_show = QLabel(self.layoutWidget)
        self.proc_start_time_show.setObjectName(u"proc_start_time_show")

        self.verticalLayout.addWidget(self.proc_start_time_show)

        self.layoutWidget1 = QWidget(KokoroJourney)
        self.layoutWidget1.setObjectName(u"layoutWidget1")
        self.layoutWidget1.setGeometry(QRect(1, 20, 81, 62))
        self.verticalLayout_2 = QVBoxLayout(self.layoutWidget1)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.proc_name_label = QLabel(self.layoutWidget1)
        self.proc_name_label.setObjectName(u"proc_name_label")
        self.proc_name_label.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)

        self.verticalLayout_2.addWidget(self.proc_name_label)

        self.proc_path_label = QLabel(self.layoutWidget1)
        self.proc_path_label.setObjectName(u"proc_path_label")
        self.proc_path_label.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)

        self.verticalLayout_2.addWidget(self.proc_path_label)

        self.label = QLabel(self.layoutWidget1)
        self.label.setObjectName(u"label")
        self.label.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)

        self.verticalLayout_2.addWidget(self.label)


        self.retranslateUi(KokoroJourney)

        QMetaObject.connectSlotsByName(KokoroJourney)
    # setupUi

    def retranslateUi(self, KokoroJourney):
        KokoroJourney.setWindowTitle(QCoreApplication.translate("KokoroJourney", u"KokoroJourney", None))
        self.pushButton_procs.setText(QCoreApplication.translate("KokoroJourney", u"\u9009\u62e9\u8fdb\u7a0b", None))
        self.proc_name_show.setText(QCoreApplication.translate("KokoroJourney", u"N/A", None))
        self.proc_path_show.setText(QCoreApplication.translate("KokoroJourney", u"N/A", None))
        self.proc_start_time_show.setText(QCoreApplication.translate("KokoroJourney", u"N/A", None))
        self.proc_name_label.setText(QCoreApplication.translate("KokoroJourney", u"\u6e38\u620f\u540d\uff1a", None))
        self.proc_path_label.setText(QCoreApplication.translate("KokoroJourney", u"\u8def\u5f84\uff1a", None))
        self.label.setText(QCoreApplication.translate("KokoroJourney", u"\u542f\u52a8\u65f6\u95f4\uff1a", None))
    # retranslateUi

