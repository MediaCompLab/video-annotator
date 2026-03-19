from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QLineEdit, QFileDialog
)
from PySide6.QtCore import Signal

class MainWindow(QMainWindow):
    start_annotation = Signal(str, str, str, str) # video_file, srt_file, char_file, vat_file

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CIGA Annotator - Setup")
        self.resize(500, 250)

        self.video_file = ""
        self.srt_file = ""
        self.char_file = ""

        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # Open Project Section
        open_proj_layout = QHBoxLayout()
        self.open_proj_button = QPushButton("Open Existing Project (.vat)")
        self.open_proj_button.setStyleSheet("font-weight: bold; padding: 10px;")
        self.open_proj_button.clicked.connect(self.open_project_file)
        open_proj_layout.addWidget(self.open_proj_button)
        main_layout.addLayout(open_proj_layout)

        main_layout.addWidget(QLabel("--- OR Create New Project ---"))

        video_layout = QHBoxLayout()
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setPlaceholderText("Select Video File (*.mp4, ...)")
        self.video_browse_button = QPushButton("Browse")
        self.video_browse_button.clicked.connect(self.select_video_file)
        video_layout.addWidget(self.video_path_edit)
        video_layout.addWidget(self.video_browse_button)
        main_layout.addLayout(video_layout)

        srt_layout = QHBoxLayout()
        self.srt_path_edit = QLineEdit()
        self.srt_path_edit.setPlaceholderText("Select Subtitle File (*.srt)")
        self.srt_browse_button = QPushButton("Browse")
        self.srt_browse_button.clicked.connect(self.select_srt_file)
        srt_layout.addWidget(self.srt_path_edit)
        srt_layout.addWidget(self.srt_browse_button)
        main_layout.addLayout(srt_layout)

        char_layout = QHBoxLayout()
        self.char_path_edit = QLineEdit()
        self.char_path_edit.setPlaceholderText("Character File (Optional)")
        self.char_browse_button = QPushButton("Browse")
        self.char_browse_button.clicked.connect(self.select_char_file)
        char_layout.addWidget(self.char_path_edit)
        char_layout.addWidget(self.char_browse_button)
        main_layout.addLayout(char_layout)

        self.start_button = QPushButton("Start Annotation")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_annotation_clicked)
        main_layout.addWidget(self.start_button)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def select_video_file(self):
        video_file, _ = QFileDialog.getOpenFileName(self, "Select Video File", "", "Video Files (*.mp4 *.avi *.mov *.mkv)")
        if video_file:
            self.video_file = video_file
            self.video_path_edit.setText(video_file)
            self.check_start_condition()

    def select_srt_file(self):
        srt_file, _ = QFileDialog.getOpenFileName(self, "Select SRT File", "", "Subtitle Files (*.srt)")
        if srt_file:
            self.srt_file = srt_file
            self.srt_path_edit.setText(srt_file)
            self.check_start_condition()

    def select_char_file(self):
        char_file, _ = QFileDialog.getOpenFileName(self, "Select Character List File", "", "Text Files (*.txt)")
        if char_file:
            self.char_file = char_file
            self.char_path_edit.setText(char_file)
            
    def check_start_condition(self):
        if self.video_file and self.srt_file:
            self.start_button.setEnabled(True)
        else:
            self.start_button.setEnabled(False)

    def start_annotation_clicked(self):
        self.start_annotation.emit(self.video_file, self.srt_file, self.char_file, "")

    def open_project_file(self):
        vat_file, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "VAT Projects (*.vat)")
        if vat_file:
            self.start_annotation.emit("", "", "", vat_file)
