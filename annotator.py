# annotation tool - media comprehension lab

import sys
import csv
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QFileDialog, QPushButton, QLineEdit, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QSizePolicy, QMessageBox, QHeaderView
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import Qt, QUrl, Slot, Signal, QEvent
from PySide6.QtGui import QAction
import chardet

def parse_srt(srt_file):
    """Parse the SRT file into a list of subtitles."""
    print('srt_file', srt_file)
    pattern = re.compile(
        r'(\d+)\s+([\d:,]+)\s*-->\s*([\d:,]+)\s*(.*?)\s*(?=\n\d+|\Z)',
        re.DOTALL
    )

    # Read the file in binary mode to detect encoding
    with open(srt_file, 'rb') as f:
        raw_data = f.read()

    # Detect the encoding
    result = chardet.detect(raw_data)
    encoding = result['encoding']
    confidence = result['confidence']
    print(f'Detected encoding: {encoding} (Confidence: {confidence})')

    if not encoding:
        # Default to UTF-8 if encoding detection fails
        encoding = 'utf-8'
        print('Encoding detection failed, defaulting to UTF-8.')

    # Read the content with the detected encoding
    try:
        content = raw_data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        # Fallback to 'latin-1' if decoding fails
        print(f'Failed to decode with encoding {encoding}, trying latin-1.')
        content = raw_data.decode('latin-1')

    # Normalize line endings to '\n'
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    matches = re.findall(pattern, content)
    subtitles = []
    for match in matches:
        index = int(match[0])
        start_time = srt_time_to_milliseconds(match[1])
        end_time = srt_time_to_milliseconds(match[2])
        text = match[3].replace('\n', ' ').strip()
        subtitles.append({
            'index': index,
            'start_time': start_time,
            'end_time': end_time,
            'text': text
        })
    return subtitles

def srt_time_to_milliseconds(srt_time):
    """Convert SRT time format to milliseconds."""
    try:
        h, m, s_ms = srt_time.split(':')
        s, ms = s_ms.replace(',', '.').split('.')
        total_ms = (
            int(h) * 3600 + int(m) * 60 + int(s)
        ) * 1000 + int(ms.ljust(3, '0')[:3])
        return int(total_ms)
    except ValueError:
        return 0  # Return 0 if time parsing fails

def read_characters(char_file):
    """Read the character list from the text file."""
    try:
        with open(char_file, 'r', encoding='utf-8') as f:
            characters = [line.strip() for line in f if line.strip()]
    except UnicodeDecodeError:
        with open(char_file, 'r', encoding='latin-1') as f:
            characters = [line.strip() for line in f if line.strip()]
    return characters

def milliseconds_to_srt_time(milliseconds):
    """Convert milliseconds to SRT time format."""
    hours = milliseconds // 3600000
    minutes = (milliseconds % 3600000) // 60000
    seconds = (milliseconds % 60000) // 1000
    ms = milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"

class MainWindow(QMainWindow):
    start_annotation = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Annotation Tool - Select Files")

        # Initialize file paths
        self.video_file = ""
        self.srt_file = ""
        self.char_file = ""

        # UI elements
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # Video file selection
        video_layout = QHBoxLayout()
        self.video_label = QLabel("Video File:")
        self.video_path_edit = QLineEdit()
        self.video_browse_button = QPushButton("Browse")
        self.video_browse_button.clicked.connect(self.select_video_file)
        video_layout.addWidget(self.video_label)
        video_layout.addWidget(self.video_path_edit)
        video_layout.addWidget(self.video_browse_button)
        main_layout.addLayout(video_layout)

        # SRT file selection
        srt_layout = QHBoxLayout()
        self.srt_label = QLabel("Subtitle File:")
        self.srt_path_edit = QLineEdit()
        self.srt_browse_button = QPushButton("Browse")
        self.srt_browse_button.clicked.connect(self.select_srt_file)
        srt_layout.addWidget(self.srt_label)
        srt_layout.addWidget(self.srt_path_edit)
        srt_layout.addWidget(self.srt_browse_button)
        main_layout.addLayout(srt_layout)

        # Character list file selection
        char_layout = QHBoxLayout()
        self.char_label = QLabel("Character List File:")
        self.char_path_edit = QLineEdit()
        self.char_browse_button = QPushButton("Browse")
        self.char_browse_button.clicked.connect(self.select_char_file)
        char_layout.addWidget(self.char_label)
        char_layout.addWidget(self.char_path_edit)
        char_layout.addWidget(self.char_browse_button)
        main_layout.addLayout(char_layout)

        # Start button
        self.start_button = QPushButton("Start Annotation")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_annotation_clicked)
        main_layout.addWidget(self.start_button)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def select_video_file(self):
        video_file, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "", "Video Files (*.mp4 *.avi *.mov *.mkv)"
        )
        if video_file:
            self.video_file = video_file
            self.video_path_edit.setText(video_file)
            self.check_start_condition()

    def select_srt_file(self):
        srt_file, _ = QFileDialog.getOpenFileName(
            self, "Select SRT File", "", "Subtitle Files (*.srt)"
        )
        if srt_file:
            self.srt_file = srt_file
            self.srt_path_edit.setText(srt_file)
            self.check_start_condition()

    def select_char_file(self):
        char_file, _ = QFileDialog.getOpenFileName(
            self, "Select Character List File", "", "Text Files (*.txt)"
        )
        if char_file:
            self.char_file = char_file
            self.char_path_edit.setText(char_file)
            self.check_start_condition()

    def check_start_condition(self):
        if self.video_file and self.srt_file and self.char_file:
            self.start_button.setEnabled(True)
        else:
            self.start_button.setEnabled(False)

    def start_annotation_clicked(self):
        self.start_annotation.emit(self.video_file, self.srt_file, self.char_file)

class VideoAnnotator(QMainWindow):
    def __init__(self, video_file, srt_file, char_file):
        super().__init__()
        self.setWindowTitle("Video Annotator")

        # Variables to track state
        self.current_subtitle_index = 0
        self.paused_at_subtitle_end = False  # Flag to track automatic pause at subtitle end

        # Parse files
        self.subtitles = parse_srt(srt_file)
        if not self.subtitles:
            print("No subtitles found or failed to parse the SRT file.")
            QMessageBox.critical(self, "Error", "No subtitles found or failed to parse the SRT file.")
            self.close()
            return

        self.characters = read_characters(char_file)
        self.annotations = []

        # Setup media player
        self.mediaPlayer = QMediaPlayer()
        self.videoWidget = QVideoWidget()
        self.audioOutput = QAudioOutput()
        self.mediaPlayer.setAudioOutput(self.audioOutput)
        self.mediaPlayer.setVideoOutput(self.videoWidget)
        self.mediaPlayer.setSource(QUrl.fromLocalFile(video_file))

        # Connect signals
        self.mediaPlayer.positionChanged.connect(self.position_changed)
        self.mediaPlayer.mediaStatusChanged.connect(self.media_status_changed)
        self.mediaPlayer.errorOccurred.connect(self.handle_error)

        # UI elements
        self.subtitle_label = QLabel("")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet("font-size: 16px;")  # Adjust styling as needed

        # Speaker Table
        self.speaker_label = QLabel("Select Speaker(s):")
        self.speaker_table = QTableWidget()
        self.setup_character_table(self.speaker_table)

        # Listener Table
        self.listener_label = QLabel("Select Listener(s):")
        self.listener_table = QTableWidget()
        self.setup_character_table(self.listener_table)

        # Controls Layout
        controls_layout = QVBoxLayout()
        controls_layout.addWidget(self.speaker_label)
        controls_layout.addWidget(self.speaker_table)
        controls_layout.addWidget(self.listener_label)
        controls_layout.addWidget(self.listener_table)

        # Wrap controls_layout in a widget
        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        controls_widget.setMaximumHeight(controls_widget.sizeHint().height())

        # Main Layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.videoWidget)
        main_layout.addWidget(self.subtitle_label)
        main_layout.addWidget(controls_widget)

        # Set stretch factors
        main_layout.setStretch(0, 1)  # videoWidget expands
        main_layout.setStretch(1, 0)  # subtitle_label does not expand
        main_layout.setStretch(2, 0)  # controls_widget does not expand

        widget = QWidget()
        widget.setLayout(main_layout)
        self.setCentralWidget(widget)

        # Add Menu Bar
        self.create_menu_bar()

        # Install event filter on the application
        self.installEventFilter(self)

        # Set initial window size
        self.resize(800, 600)

        # Start playback when media is ready
        self.mediaPlayer.play()

    def create_menu_bar(self):
        """Create the menu bar with File menu containing Save and Load actions."""
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        # Save Annotations Action
        save_action = QAction("Save Annotations", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_annotations_dialog)
        file_menu.addAction(save_action)

        # Load Annotations Action
        load_action = QAction("Load Annotations", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.load_annotations_dialog)
        file_menu.addAction(load_action)

    def save_annotations_dialog(self):
        """Open a file dialog to save annotations to a CSV file."""
        # If paused at subtitle end, record current selections before saving
        if self.paused_at_subtitle_end and self.current_subtitle_index < len(self.subtitles):
            subtitle = self.subtitles[self.current_subtitle_index]
            self.record_annotation(subtitle, clear_selections=False)
            # Do not clear subtitle or change index
            # The flag remains True to indicate that an annotation has been recorded
        # Proceed to save
        if not self.annotations:
            reply = QMessageBox.question(
                self, "No Annotations", "There are no annotations to save. Do you want to save anyway?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Annotations", "", "CSV Files (*.csv)"
        )
        if save_path:
            self.save_annotations(save_path)

    def save_annotations(self, file_path):
        """Save the collected annotations to a specified CSV file with UTF-8 BOM."""
        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ['line', 'start_time', 'end_time', 'speakers', 'listeners']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for anno in self.annotations:
                    writer.writerow(anno)
            QMessageBox.information(self, "Success", f"Annotations saved to {file_path}")
            print(f"Annotations saved to {file_path} with UTF-8 BOM.")
        except Exception as e:
            print(f"Failed to save annotations: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save annotations: {e}")

    def load_annotations_dialog(self):
        """Open a file dialog to load annotations from a CSV file."""
        load_path, _ = QFileDialog.getOpenFileName(
            self, "Load Annotations", "", "CSV Files (*.csv)"
        )
        if load_path:
            self.load_annotations(load_path)

    def load_annotations(self, file_path):
        """Load annotations from a specified CSV file."""
        try:
            with open(file_path, 'r', newline='', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                loaded_annotations = []
                for row in reader:
                    # Validate that the row has all required fields
                    if all(field in row for field in ['line', 'start_time', 'end_time', 'speakers', 'listeners']):
                        loaded_annotations.append({
                            'line': row['line'],
                            'start_time': row['start_time'],
                            'end_time': row['end_time'],
                            'speakers': row['speakers'],
                            'listeners': row['listeners']
                        })
            # Replace existing annotations with loaded ones
            self.annotations = loaded_annotations
            QMessageBox.information(self, "Success", f"Annotations loaded from {file_path}")
            print(f"Annotations loaded from {file_path}.")

            # Optionally, update the current_subtitle_index to skip already annotated subtitles
            # This requires matching the loaded annotations with the current subtitles
            annotated_indices = []
            for anno in self.annotations:
                for idx, subtitle in enumerate(self.subtitles):
                    if (subtitle['text'] == anno['line'] and
                        milliseconds_to_srt_time(subtitle['start_time']) == anno['start_time'] and
                        milliseconds_to_srt_time(subtitle['end_time']) == anno['end_time']):
                        annotated_indices.append(idx)
                        break
            if annotated_indices:
                last_index = max(annotated_indices)
                self.current_subtitle_index = last_index + 1
                last_annotation = self.annotations[-1]
                last_end_time_ms = srt_time_to_milliseconds(last_annotation['end_time'])
                self.mediaPlayer.setPosition(last_end_time_ms)
                self.paused_at_subtitle_end = False  # Ensure no accidental flag
                self.subtitle_label.setText("")  # Clear subtitle display
                self.mediaPlayer.play()
                print(f"Current subtitle index set to {self.current_subtitle_index}")
        except Exception as e:
            print(f"Failed to load annotations: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load annotations: {e}")

    def setup_character_table(self, table):
        """Set up the character selection table."""
        num_characters = len(self.characters)
        columns = 6  # Adjust as needed to make tables shorter
        rows = (num_characters + columns - 1) // columns
        table.setRowCount(rows)
        table.setColumnCount(columns)
        table.setSelectionMode(QTableWidget.MultiSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().hide()
        table.verticalHeader().hide()
        table.setShowGrid(True)
        table.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Set row and column resizing modes
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        row_height = 20  # Adjust as needed
        for row in range(rows):
            table.setRowHeight(row, row_height)

        # Set maximum height for the table
        table.setMaximumHeight(table.verticalHeader().length() + 2)

        # Populate the table with character names
        idx = 0
        for row in range(rows):
            for col in range(columns):
                if idx < num_characters:
                    item = QTableWidgetItem(self.characters[idx])
                    item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, col, item)
                else:
                    # Hide unused cells
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.NoItemFlags)
                    table.setItem(row, col, item)
                idx += 1

    def eventFilter(self, source, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            self.handle_spacebar()
            return True  # Event handled
        return False  # Let other events pass through

    def handle_spacebar(self):
        if self.mediaPlayer.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.mediaPlayer.pause()
        else:
            if self.paused_at_subtitle_end:
                # Record annotation before resuming playback
                if self.current_subtitle_index < len(self.subtitles):
                    subtitle = self.subtitles[self.current_subtitle_index]
                    self.record_annotation(subtitle)
                    self.subtitle_label.setText("")
                    self.current_subtitle_index += 1
                    self.paused_at_subtitle_end = False
            self.mediaPlayer.play()

    def record_annotation(self, subtitle, clear_selections=True):
        """Record the current selections for the given subtitle."""
        speakers = self.get_selected_characters(self.speaker_table)
        listeners = self.get_selected_characters(self.listener_table)
        self.annotations.append({
            'line': subtitle['text'],
            'start_time': milliseconds_to_srt_time(subtitle['start_time']),
            'end_time': milliseconds_to_srt_time(subtitle['end_time']),
            'speakers': ', '.join(speakers),
            'listeners': ', '.join(listeners)
        })
        if clear_selections:
            # Clear selections for the next subtitle
            self.speaker_table.clearSelection()
            self.listener_table.clearSelection()

    @Slot(QMediaPlayer.MediaStatus)
    def media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            print("Media loaded, starting playback.")
            self.mediaPlayer.play()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            print("Failed to load media.")
            self.handle_error(self.mediaPlayer.error())

    @Slot(int)
    def position_changed(self, position):
        # Update the subtitle display
        if self.current_subtitle_index < len(self.subtitles):
            subtitle = self.subtitles[self.current_subtitle_index]
            start_time = subtitle['start_time']
            end_time = subtitle['end_time']

            if start_time <= position <= end_time:
                self.subtitle_label.setText(subtitle['text'])
            elif position > end_time and not self.paused_at_subtitle_end:
                # Reached the end of the current subtitle
                self.mediaPlayer.pause()
                self.paused_at_subtitle_end = True  # Set the flag
                # Subtitle remains displayed
        else:
            # No more subtitles
            self.subtitle_label.setText("")
            if position >= self.mediaPlayer.duration():
                # Video ended
                self.mediaPlayer.stop()
                self.save_annotations_final()

    def get_selected_characters(self, table):
        """Return a list of selected character names from the table."""
        selected_items = table.selectedItems()
        return [item.text() for item in selected_items]

    def save_annotations_final(self):
        """Save the collected annotations to a CSV file with UTF-8 BOM."""
        try:
            with open('annotations.csv', 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ['line', 'start_time', 'end_time', 'speakers', 'listeners']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for anno in self.annotations:
                    writer.writerow(anno)
            print("Annotations saved to annotations.csv with UTF-8 BOM.")
            QMessageBox.information(self, "Success", "Annotations saved to annotations.csv")
            # Close the window after saving annotations
            self.close()
        except Exception as e:
            print(f"Failed to save annotations: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save annotations: {e}")

    def load_annotations(self, file_path):
        """Load annotations from a specified CSV file."""
        try:
            with open(file_path, 'r', newline='', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                loaded_annotations = []
                for row in reader:
                    # Validate that the row has all required fields
                    if all(field in row for field in ['line', 'start_time', 'end_time', 'speakers', 'listeners']):
                        loaded_annotations.append({
                            'line': row['line'],
                            'start_time': row['start_time'],
                            'end_time': row['end_time'],
                            'speakers': row['speakers'],
                            'listeners': row['listeners']
                        })
            # Replace existing annotations with loaded ones
            self.annotations = loaded_annotations
            QMessageBox.information(self, "Success", f"Annotations loaded from {file_path}")
            print(f"Annotations loaded from {file_path}.")

            # Optionally, update the current_subtitle_index to skip already annotated subtitles
            # This requires matching the loaded annotations with the current subtitles
            annotated_indices = []
            for anno in self.annotations:
                for idx, subtitle in enumerate(self.subtitles):
                    if (subtitle['text'] == anno['line'] and
                        milliseconds_to_srt_time(subtitle['start_time']) == anno['start_time'] and
                        milliseconds_to_srt_time(subtitle['end_time']) == anno['end_time']):
                        annotated_indices.append(idx)
                        break
            if annotated_indices:
                last_index = max(annotated_indices)
                self.current_subtitle_index = last_index + 1
                if last_index < len(self.subtitles):
                    last_annotation = self.annotations[-1]
                    last_end_time_ms = srt_time_to_milliseconds(last_annotation['end_time'])
                    self.mediaPlayer.setPosition(last_end_time_ms)
                    self.paused_at_subtitle_end = False  # Ensure no accidental flag
                    self.subtitle_label.setText("")  # Clear subtitle display
                    print(f"Current subtitle index set to {self.current_subtitle_index}")
        except Exception as e:
            print(f"Failed to load annotations: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load annotations: {e}")

    @Slot(str)
    def handle_error(self, error):
        print(f"Error occurred: {error}")
        QMessageBox.critical(self, "Media Error", f"Error occurred: {error}")

def main():
    app = QApplication(sys.argv)

    main_window = MainWindow()
    main_window.show()

    def start_annotation(video_file, srt_file, char_file):
        print('start_annotation')

        # Store video_annotator as an attribute of the app
        app.video_annotator = VideoAnnotator(video_file, srt_file, char_file)
        app.video_annotator.show()
        print('going to close the main_window')
        main_window.close()

        # Install the event filter on the application
        app.installEventFilter(app.video_annotator)

    main_window.start_annotation.connect(start_annotation)

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
