import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from src.ui.setup_window import MainWindow
from src.ui.annotator_window import VideoAnnotator

def main():
    app = QApplication(sys.argv)
    
    # Set Logo based on dark/light mode
    is_dark = app.palette().window().color().lightness() < 128
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ciga_root = os.path.dirname(os.path.dirname(current_dir))
    logo_path = os.path.join(ciga_root, "logo_white.png" if is_dark else "logo_black.png")
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    app.main_window = MainWindow()
    app.main_window.show()

    def start_annotation(video_file, srt_file, char_file, vat_file):
        if hasattr(app, 'video_annotator') and app.video_annotator:
            app.removeEventFilter(app.video_annotator)
            app.video_annotator.close()
            
        app.video_annotator = VideoAnnotator(video_file, srt_file, char_file, vat_file)
        # Hook up "New Project" signal from main window to reset
        app.video_annotator.request_new_project.connect(reset_to_main_window)
        app.video_annotator.request_open_project.connect(lambda f: start_annotation("", "", "", f))
        app.video_annotator.show()
        app.main_window.hide()
        app.installEventFilter(app.video_annotator)

    def reset_to_main_window():
        app.removeEventFilter(app.video_annotator)
        app.video_annotator.close()
        app.video_annotator = None
        app.main_window.show()

    app.main_window.start_annotation.connect(start_annotation)
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
