from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton

class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        btn = QPushButton('test!',self)
        btn.setGeometry(100,100,200,100)
        btn.setToolTip('test!!')
        btn.setText('test!!!')

if __name__ == "__main__":
    app = QApplication([])
    window = MyWindow()
    window.show()
    app.exec()