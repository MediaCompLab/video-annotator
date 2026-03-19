import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QFileDialog, QPushButton, QLineEdit, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QSizePolicy, QMessageBox, QHeaderView,
    QSplitter, QAbstractItemView, QSlider
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import Qt, QUrl, Slot, Signal, QEvent, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence

from src.core.app_settings import AppSettings
from src.ui.settings_dialog import SettingsDialog
from src.ui.char_dialog import ManageCharactersDialog
from src.core.parsers import parse_srt, milliseconds_to_srt_time
from src.core.characters import read_characters, save_characters
from src.core.csv_utils import write_rows_to_csv_atomic

class VideoAnnotator(QMainWindow):
    request_new_project = Signal()
    request_open_project = Signal(str)

    def __init__(self, video_file, srt_file, char_file, vat_file=""):
        super().__init__()
        self.setWindowTitle("CIGA Annotator")
        
        self.app_settings = AppSettings()

        self.current_subtitle_index = 0
        self.paused_at_subtitle_end = False
        
        self.vat_file = vat_file
        self.is_dirty = False
        self.annotations = {}

        if self.vat_file:
            # Load project details from .vat JSON
            try:
                with open(self.vat_file, 'r', encoding='utf-8') as f:
                    project_data = json.load(f)
                video_file = project_data.get('video_file', '')
                srt_file = project_data.get('srt_file', '')
                self.char_file = project_data.get('char_file', '')
                self.characters = project_data.get('characters', [])
                
                # Convert string keys to int indices
                loaded_ann = project_data.get('annotations', {})
                self.annotations = {int(k): v for k, v in loaded_ann.items()}
                
                # Make paths absolute relative to the vat file folder if they are relative
                vat_dir = Path(self.vat_file).parent
                if not Path(video_file).is_absolute():
                    video_file = str(vat_dir / video_file)
                if not Path(srt_file).is_absolute():
                    srt_file = str(vat_dir / srt_file)
                if self.char_file and not Path(self.char_file).is_absolute():
                    self.char_file = str(vat_dir / self.char_file)
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load project file: {e}")
                QTimer.singleShot(0, self.request_new_project.emit)
                return
        else:
            if not char_file:
                def get_base_dir():
                    if getattr(sys, 'frozen', False):
                        return Path(sys.executable).parent
                    else:
                        return Path(__file__).parent.parent.parent
                char_file = str(get_base_dir() / "characters.txt")
            self.char_file = char_file
            self.characters = read_characters(self.char_file)

        self.video_file = video_file
        self.srt_file = srt_file

        if self.vat_file:
            self.setWindowTitle(f"CIGA Annotator - {Path(self.vat_file).name}")
        else:
            self.setWindowTitle(f"CIGA Annotator - {Path(self.srt_file).name}")

        self.subtitles = parse_srt(self.srt_file)
        if not self.subtitles:
            QMessageBox.critical(self, "Error", "No subtitles found or failed to parse the SRT file.")
            QTimer.singleShot(0, self.request_new_project.emit)
            return

        self.current_speakers = []
        self.current_listeners = []
        self.current_targets = []
        self.active_role = 'speakers'
        self._updating_table = False
        self.slider_is_dragging = False
        
        srt_base = Path(self.srt_file).name
        self.autosave_path = str(Path(self.srt_file).parent / f".{srt_base}.autosave.vat")

        # Media Player
        self.mediaPlayer = QMediaPlayer()
        self.videoWidget = QVideoWidget()
        self.audioOutput = QAudioOutput()
        self.mediaPlayer.setAudioOutput(self.audioOutput)
        self.mediaPlayer.setVideoOutput(self.videoWidget)
        self.mediaPlayer.setSource(QUrl.fromLocalFile(video_file))

        self.mediaPlayer.positionChanged.connect(self.position_changed)
        self.mediaPlayer.durationChanged.connect(self.duration_changed)
        self.mediaPlayer.mediaStatusChanged.connect(self.media_status_changed)
        self.mediaPlayer.errorOccurred.connect(self.handle_error)
        self.mediaPlayer.playbackStateChanged.connect(self.update_play_button_text)

        # UI Subtitle Overlay
        self.subtitle_label = QLabel("")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 5px;")

        # Controls UI
        self.character_table = QTableWidget()
        self.setup_character_table(self.character_table)

        self.manage_char_btn = QPushButton("Manage Characters && Shortcuts")
        self.manage_char_btn.clicked.connect(self.open_manage_characters_dialog)

        self.speaker_summary = QLineEdit()
        self.speaker_summary.setReadOnly(True)
        self.listener_summary = QLineEdit()
        self.listener_summary.setReadOnly(True)
        self.target_summary = QLineEdit()
        self.target_summary.setReadOnly(True)
        self.active_role_label = QLabel("")
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("Optional note for current subtitle line")
        self.note_edit.textChanged.connect(self.on_note_text_changed)

        management_layout = QVBoxLayout()
        management_layout.addWidget(self.manage_char_btn)
        management_layout.addWidget(self.character_table)
        management_widget = QWidget()
        management_widget.setLayout(management_layout)

        coding_layout = QVBoxLayout()
        coding_layout.addWidget(QLabel("Active Coding Role (Ctrl+1/2/3/Q to switch):"))
        coding_layout.addWidget(self.active_role_label)
        
        self.speaker_label = QLabel("Speaker:")
        coding_layout.addWidget(self.speaker_label)
        coding_layout.addWidget(self.speaker_summary)
        
        self.listener_label = QLabel("Listener:")
        coding_layout.addWidget(self.listener_label)
        coding_layout.addWidget(self.listener_summary)
        
        self.target_label = QLabel("Target:")
        coding_layout.addWidget(self.target_label)
        coding_layout.addWidget(self.target_summary)
        
        coding_layout.addWidget(QLabel("Note:"))
        coding_layout.addWidget(self.note_edit)
        coding_widget = QWidget()
        coding_widget.setLayout(coding_layout)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(management_widget)
        right_splitter.addWidget(coding_widget)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)

        controls_widget = QWidget()
        controls_outer_layout = QVBoxLayout()
        controls_outer_layout.addWidget(right_splitter)
        controls_widget.setLayout(controls_outer_layout)
        controls_widget.setMinimumWidth(320)

        # Video Section
        self.play_pause_btn = QPushButton("Pause")
        self.play_pause_btn.clicked.connect(self.handle_spacebar)
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self.on_seek_slider_pressed)
        self.seek_slider.sliderReleased.connect(self.on_seek_slider_released)
        self.seek_slider.sliderMoved.connect(self.on_seek_slider_moved)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setMinimumWidth(110)

        player_controls_layout = QHBoxLayout()
        player_controls_layout.addWidget(self.play_pause_btn)
        player_controls_layout.addWidget(self.seek_slider, 1)
        player_controls_layout.addWidget(self.time_label)

        video_layout = QVBoxLayout()
        video_layout.addWidget(self.videoWidget)
        video_layout.addWidget(self.subtitle_label)
        video_layout.addLayout(player_controls_layout)
        video_layout.setStretch(0, 1)
        video_layout.setStretch(1, 0)
        video_layout.setStretch(2, 0)
        video_container = QWidget()
        video_container.setLayout(video_layout)

        # Top Splitter (Video vs Controls)
        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.addWidget(video_container)
        top_splitter.addWidget(controls_widget)
        top_splitter.setStretchFactor(0, 4)
        top_splitter.setStretchFactor(1, 1)

        # Bottom Subtitle List
        self.subtitle_list = QTableWidget()
        self.subtitle_list.setAlternatingRowColors(True)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search subtitle text...")
        self.search_edit.textChanged.connect(self.apply_subtitle_filters)
        self.next_uncoded_btn = QPushButton("Next Uncoded")
        self.next_uncoded_btn.clicked.connect(self.jump_to_next_uncoded)
        self.next_uncoded_btn.setMaximumWidth(120)
        self.clear_filters_btn = QPushButton("Clear")
        self.clear_filters_btn.clicked.connect(self.clear_subtitle_filters)
        self.clear_filters_btn.setMaximumWidth(80)

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(self.search_edit, 1)
        filter_bar.addWidget(self.next_uncoded_btn)
        filter_bar.addWidget(self.clear_filters_btn)

        subtitle_panel = QWidget()
        subtitle_panel_layout = QVBoxLayout()
        subtitle_panel_layout.addLayout(filter_bar)
        subtitle_panel_layout.addWidget(self.subtitle_list)
        subtitle_panel.setLayout(subtitle_panel_layout)

        self.setup_subtitle_list()

        # Main Splitter (Top vs Bottom)
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(subtitle_panel)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 1)

        main_layout = QVBoxLayout()
        main_layout.addWidget(main_splitter)
        
        widget = QWidget()
        widget.setLayout(main_layout)
        self.setCentralWidget(widget)

        self.create_menu_bar()
        self.installEventFilter(self)
        self.resize(1100, 750)

        # Status bar with live progress and shortcut hints.
        self.progress_label = QLabel("")
        self.hint_label = QLabel("Active role coding enabled")
        self.statusBar().addPermanentWidget(self.progress_label, 1)
        self.statusBar().addPermanentWidget(self.hint_label, 2)
        self.update_active_role_ui()

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(15000)
        self.autosave_timer.timeout.connect(self.autosave_annotations)
        self.autosave_timer.start()

        QTimer.singleShot(0, self.try_restore_autosave)

        self.mediaPlayer.play()
        self.jump_to_subtitle(self.current_subtitle_index)

    def create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        tools_menu = menu_bar.addMenu("Tools")
        help_menu = menu_bar.addMenu("Help")
        
        new_action = QAction("New Project", self)
        new_action.triggered.connect(self.request_new_project.emit)
        file_menu.addAction(new_action)

        open_action = QAction("Open Project (.vat)", self)
        open_action.triggered.connect(self.open_project_dialog)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        save_action = QAction("Save Project", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save Project As...", self)
        save_as_action.triggered.connect(self.save_project_as_dialog)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        export_csv_action = QAction("Export to CSV", self)
        export_csv_action.triggered.connect(self.export_csv_dialog)
        file_menu.addAction(export_csv_action)

        import_csv_action = QAction("Import from CSV", self)
        import_csv_action.triggered.connect(self.import_csv_dialog)
        file_menu.addAction(import_csv_action)
        
        file_menu.addSeparator()

        preferences_action = QAction("Preferences", self)
        preferences_action.triggered.connect(self.show_preferences)
        file_menu.addAction(preferences_action)

        self.next_uncoded_action = QAction("Jump to Next Uncoded", self)
        self.next_uncoded_action.setShortcut(self.app_settings.get_hotkey("next_uncoded"))
        self.next_uncoded_action.triggered.connect(self.jump_to_next_uncoded)
        tools_menu.addAction(self.next_uncoded_action)

        self.shortcuts_help_action = QAction("Shortcuts", self)
        self.shortcuts_help_action.setShortcut(self.app_settings.get_hotkey("shortcuts_help"))
        self.shortcuts_help_action.triggered.connect(self.show_shortcuts_help)
        help_menu.addAction(self.shortcuts_help_action)

        help_menu.addSeparator()
        self.about_action = QAction("About CIGA", self)
        self.about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(self.about_action)

    def show_about_dialog(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("About CIGA Annotator")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(
            "<h3>CIGA: Character Interaction and Graph Analysis</h3>"
            "<p><b>Video Annotator</b></p>"
            "<p>A powerful tool for annotating video character interactions.</p>"
            "<p><i>Developed by: <a href='http://mediacomplab.com'>Media Comprehension Lab</a></i></p>"
            "<p>For more information, visit our <a href='https://github.com/MediaComprehensionLab/CIGA'>GitHub Repository</a>.</p>"
            "<p>If you find CIGA useful, please consider citing our work:"
            "<pre>@article{mcl2025ciga,\n  title={CIGA: Character Interaction and Graph Analysis for Video},\n  author={Media Comprehension Lab},\n  year={2025}\n}</pre></p>"
        )
        msg_box.exec()

    def setup_character_table(self, table):
        num_characters = len(self.characters)
        columns = 4
        rows = (num_characters + columns - 1) // columns
        if rows == 0: rows = 1
        table.setRowCount(rows)
        table.setColumnCount(columns)
        table.setSelectionMode(QTableWidget.MultiSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().hide()
        table.verticalHeader().hide()
        table.setShowGrid(True)
        table.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        for row in range(rows):
            table.setRowHeight(row, 25)
        table.setMaximumHeight((rows * 25) + 2)

        idx = 0
        for row in range(rows):
            for col in range(columns):
                if idx < num_characters:
                    char_info = self.characters[idx]
                    display_text = f"{char_info['name']} ({char_info['key']})" if char_info.get('key') else char_info['name']
                    item = QTableWidgetItem(display_text)
                    item.setData(Qt.UserRole, char_info['name'])
                    item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, col, item)
                else:
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.NoItemFlags)
                    table.setItem(row, col, item)
                idx += 1

    def refresh_role_summary(self):
        self.speaker_summary.setText(', '.join(self.current_speakers))
        self.listener_summary.setText(', '.join(self.current_listeners))
        self.target_summary.setText(', '.join(self.current_targets))

    def update_active_role_ui(self):
        role_name = {
            'speakers': 'Speaker',
            'listeners': 'Listener',
            'targets': 'Target'
        }.get(self.active_role, 'Speaker')
        self.active_role_label.setText(role_name)
        self.hint_label.setText(
            f"Active: {role_name}  |  Ctrl+1/2/3/Q: switch role  Alt+[character key]: code  Left/Right: seek  Up/Down: prev/next"
        )

        active_style = "font-weight: bold; color: #4DA6FF;" # Bright blue
        active_edit_style = "font-weight: bold; color: #4DA6FF; border: 1px solid #4DA6FF;"
        inactive_style = "font-weight: normal;"
        inactive_edit_style = "font-weight: normal;"
        
        # Reset all labels
        self.speaker_label.setStyleSheet(inactive_style)
        self.listener_label.setStyleSheet(inactive_style)
        self.target_label.setStyleSheet(inactive_style)
        
        self.speaker_summary.setStyleSheet(inactive_edit_style)
        self.listener_summary.setStyleSheet(inactive_edit_style)
        self.target_summary.setStyleSheet(inactive_edit_style)
        
        # Apply active label style
        if self.active_role == 'speakers':
            self.speaker_label.setStyleSheet(active_style)
            self.speaker_summary.setStyleSheet(active_edit_style)
        elif self.active_role == 'listeners':
            self.listener_label.setStyleSheet(active_style)
            self.listener_summary.setStyleSheet(active_edit_style)
        elif self.active_role == 'targets':
            self.target_label.setStyleSheet(active_style)
            self.target_summary.setStyleSheet(active_edit_style)

    def set_active_role(self, role):
        if role in ['speakers', 'listeners', 'targets']:
            self.active_role = role
            self.update_active_role_ui()

    def cycle_active_role(self):
        roles = ['speakers', 'listeners', 'targets']
        idx = roles.index(self.active_role)
        self.active_role = roles[(idx + 1) % len(roles)]
        self.update_active_role_ui()

    def sanitize_role_values(self):
        valid_names = {char['name'] for char in self.characters}
        self.current_speakers = [name for name in self.current_speakers if name in valid_names]
        self.current_listeners = [name for name in self.current_listeners if name in valid_names]
        self.current_targets = [name for name in self.current_targets if name in valid_names]
        self.refresh_role_summary()

    def open_manage_characters_dialog(self):
        dialog = ManageCharactersDialog(self.characters, self)
        if dialog.exec():
            new_chars = dialog.get_data()
            
            used_keys = set()
            for c in new_chars:
                k = (c['key'] or "").strip().upper()
                if k in [' ']:
                    QMessageBox.warning(self, "Invalid Shortcut", f"Shortcut '{k}' is reserved.")
                    return
                if k and len(k) != 1:
                    QMessageBox.warning(self, "Invalid Shortcut", f"Shortcut '{k}' must be a single key.")
                    return
                if k and not k.isprintable():
                    QMessageBox.warning(self, "Invalid Shortcut", "Shortcut must be a printable key.")
                    return
                if k:
                    if k in used_keys:
                        QMessageBox.warning(self, "Duplicate Shortcut", f"Shortcut '{k}' is used multiple times.")
                        return
                    used_keys.add(k)
                c['key'] = k if k else None
                    
            self.characters = new_chars
            save_characters(self.char_file, self.characters)

            self.setup_character_table(self.character_table)
            self.sanitize_role_values()
            self.is_dirty = True
            self.update_progress_status()

    def setup_subtitle_list(self):
        self.subtitle_list.setColumnCount(9)
        self.subtitle_list.setHorizontalHeaderLabels(["#", "Start", "End", "Text", "Speaker", "Listener", "Target", "Status", "Note"])
        self.subtitle_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.subtitle_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.subtitle_list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.subtitle_list.setFocusPolicy(Qt.NoFocus) # Keeps playback/navigation shortcuts available.
        
        self.subtitle_list.setRowCount(len(self.subtitles))
        for i, sub in enumerate(self.subtitles):
            self.subtitle_list.setItem(i, 0, self._make_readonly_item(str(sub['index'])))
            self.subtitle_list.setItem(i, 1, self._make_readonly_item(milliseconds_to_srt_time(sub['start_time'])))
            self.subtitle_list.setItem(i, 2, self._make_readonly_item(milliseconds_to_srt_time(sub['end_time'])))
            self.subtitle_list.setItem(i, 3, self._make_readonly_item(sub['text']))
            self.subtitle_list.setItem(i, 4, self._make_readonly_item(""))
            self.subtitle_list.setItem(i, 5, self._make_readonly_item(""))
            self.subtitle_list.setItem(i, 6, self._make_readonly_item(""))
            self.subtitle_list.setItem(i, 7, self._make_readonly_item("Uncoded"))
            self.subtitle_list.setItem(i, 8, QTableWidgetItem(""))

        self.subtitle_list.setColumnWidth(0, 45)
        self.subtitle_list.setColumnWidth(1, 90)
        self.subtitle_list.setColumnWidth(2, 90)
        self.subtitle_list.setColumnWidth(4, 140)
        self.subtitle_list.setColumnWidth(5, 140)
        self.subtitle_list.setColumnWidth(6, 140)
        self.subtitle_list.setColumnWidth(7, 90)
        self.subtitle_list.setColumnWidth(8, 220)
        self.subtitle_list.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.subtitle_list.itemClicked.connect(self.on_subtitle_clicked)
        self.subtitle_list.itemChanged.connect(self.on_subtitle_item_changed)
        self.apply_subtitle_filters()

    def _make_readonly_item(self, text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def clear_subtitle_filters(self):
        self.search_edit.clear()
        self.app_settings.set("only_uncoded", False)
        self.apply_subtitle_filters()

    def apply_subtitle_filters(self):
        query = self.search_edit.text().strip().lower()
        only_uncoded = self.app_settings.get("only_uncoded", False)
        for i, sub in enumerate(self.subtitles):
            status = self.get_annotation_status(i)
            match_text = query in sub['text'].lower() if query else True
            match_coded = (status == "Uncoded") if only_uncoded else True
            self.subtitle_list.setRowHidden(i, not (match_text and match_coded))

    def apply_inheritance_to_current(self):
        if self.current_subtitle_index <= 0:
            return
        if self.current_subtitle_index in self.annotations:
            return
        prev_ann = self.annotations.get(self.current_subtitle_index - 1, {})
        if self.app_settings.get("inherit_listener", False):
            self.current_listeners = list(prev_ann.get('listeners', []))        
        if self.app_settings.get("inherit_target", False):
            self.current_targets = list(prev_ann.get('targets', []))
        self.refresh_role_summary()

    def _extract_shortcut(self, event):
        key = event.key()
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(ord('0') + (key - Qt.Key_0))
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(ord('A') + (key - Qt.Key_A))
        text = event.text().upper()
        if len(text) == 1 and text.isprintable():
            return text
        return ""

    def _toggle_role_name(self, role, name):
        if role == 'speakers':
            target_list = self.current_speakers
        elif role == 'listeners':
            target_list = self.current_listeners
        else:
            target_list = self.current_targets

        if name in target_list:
            target_list.remove(name)
        else:
            target_list.append(name)
        self.refresh_role_summary()

    def on_note_text_changed(self, text):
        if self._updating_table:
            return
        self.record_annotation(self.current_subtitle_index, clear_selections=False)

    def on_subtitle_item_changed(self, item):
        if self._updating_table:
            return
        if item.column() != 8:
            return
        row = item.row()
        ann = self.annotations.get(row, {'speakers': [], 'listeners': [], 'targets': [], 'note': ''})
        ann['note'] = item.text().strip()
        self.annotations[row] = ann
        if row == self.current_subtitle_index:
            self._updating_table = True
            self.note_edit.setText(ann.get('note', ''))
            self._updating_table = False
            self.current_speakers = list(ann.get('speakers', []))
            self.current_listeners = list(ann.get('listeners', []))
            self.current_targets = list(ann.get('targets', []))
            self.refresh_role_summary()
        self.is_dirty = True
        self.refresh_subtitle_row(row)
        self.apply_subtitle_filters()
        self.update_progress_status()
        
    def on_subtitle_clicked(self, item):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        row = item.row()
        self.jump_to_subtitle(row)

    def jump_to_subtitle(self, index):
        if 0 <= index < len(self.subtitles):
            self.current_subtitle_index = index
            subtitle = self.subtitles[self.current_subtitle_index]
            self.mediaPlayer.setPosition(subtitle['start_time'])
            self.paused_at_subtitle_end = False
            self.subtitle_label.setText(subtitle['text'])
            self.subtitle_list.selectRow(index)
            self.subtitle_list.scrollToItem(self.subtitle_list.item(index, 0), QAbstractItemView.PositionAtCenter)
            
            # Restore panel selections
            ann = self.annotations.get(index, {})
            self.current_speakers = list(ann.get('speakers', []))
            self.current_listeners = list(ann.get('listeners', []))
            self.current_targets = list(ann.get('targets', []))
            self._updating_table = True
            self.note_edit.setText(ann.get('note', ''))
            self._updating_table = False
            self.apply_inheritance_to_current()
            self.refresh_role_summary()
            self.update_progress_status()
            
            self.mediaPlayer.play()

    def get_annotation_status(self, index):
        ann = self.annotations.get(index, {})
        speakers = ann.get('speakers', [])
        listeners = ann.get('listeners', [])
        targets = ann.get('targets', [])
        filled = int(bool(speakers)) + int(bool(listeners)) + int(bool(targets))
        if filled == 0:
            return "Uncoded"
        if filled == 3:
            return "Done"
        return "Partial"

    def refresh_subtitle_row(self, index):
        if index < 0 or index >= len(self.subtitles):
            return
        ann = self.annotations.get(index, {})
        speakers = ann.get('speakers', [])
        listeners = ann.get('listeners', [])
        targets = ann.get('targets', [])
        note = ann.get('note', '')
        status = self.get_annotation_status(index)

        self._updating_table = True
        self.subtitle_list.setItem(index, 4, self._make_readonly_item(', '.join(speakers)))
        self.subtitle_list.setItem(index, 5, self._make_readonly_item(', '.join(listeners)))
        self.subtitle_list.setItem(index, 6, self._make_readonly_item(', '.join(targets)))
        self.subtitle_list.setItem(index, 7, self._make_readonly_item(status))
        self.subtitle_list.setItem(index, 8, QTableWidgetItem(note))

        if status == "Done":
            status_color = QColor(40, 167, 69, 50)
        elif status == "Partial":
            status_color = QColor(255, 193, 7, 50)
        else:
            status_color = None

        for col in range(9):
            if self.subtitle_list.item(index, col):
                if col == 7 and status_color:
                    self.subtitle_list.item(index, col).setBackground(status_color)
                else:
                    self.subtitle_list.item(index, col).setData(Qt.BackgroundRole, None)
        self._updating_table = False

    def jump_to_next_uncoded(self):
        start = self.current_subtitle_index + 1
        for i in range(start, len(self.subtitles)):
            if self.get_annotation_status(i) == "Uncoded":
                self.record_annotation(self.current_subtitle_index, clear_selections=False)
                self.jump_to_subtitle(i)
                return
        for i in range(0, start):
            if self.get_annotation_status(i) == "Uncoded":
                self.record_annotation(self.current_subtitle_index, clear_selections=False)
                self.jump_to_subtitle(i)
                return
        QMessageBox.information(self, "All Coded", "No uncoded subtitle line remains.")

    def show_shortcuts_help(self):
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "Space: Play/Pause and step subtitle\n"
            "Up / Down: Previous / Next subtitle\n"
            "Left / Right: Rewind / Forward 2 seconds\n"
            "N: Jump to next uncoded line\n"
            "Ctrl+F: Focus search\n"
            "F1: Show this help\n"
            "Ctrl+1, 2, 3: Set active coding role (Speaker, Listener, Target)\n"
            "Ctrl+Q: Cycle active coding role\n"
            "Alt + [Character key]: Toggle character in active role\n\n"
            "(Shortcuts can be customized in File -> Preferences)"
        )

    def show_preferences(self):
        dialog = SettingsDialog(self, self.app_settings)
        if dialog.exec():
            # Apply changes
            self.apply_subtitle_filters()
            self.next_uncoded_action.setShortcut(self.app_settings.get_hotkey("next_uncoded"))
            self.shortcuts_help_action.setShortcut(self.app_settings.get_hotkey("shortcuts_help"))

    def record_annotation(self, index, clear_selections=True):
        if index >= len(self.subtitles): return
        
        speakers = list(self.current_speakers)
        listeners = list(self.current_listeners)
        targets = list(self.current_targets)
        note = self.note_edit.text().strip()
        
        if not speakers and not listeners and not targets and not note and index not in self.annotations:
            return # nothing to record
            
        self.annotations[index] = {
            'speakers': speakers,
            'listeners': listeners,
            'targets': targets,
            'note': note
        }
        self.is_dirty = True
        
        self.refresh_subtitle_row(index)

        if clear_selections:
            self.current_speakers = []
            self.current_listeners = []
            self.current_targets = []
            self.refresh_role_summary()
        self.apply_subtitle_filters()
        self.update_progress_status()

    def _is_hotkey(self, event, action_name):
        hotkey_str = self.app_settings.get_hotkey(action_name)
        if not hotkey_str: return False
        seq = QKeySequence(hotkey_str)
        if not seq.count(): return False
        
        # In PySide6, QKeySequence can be matched against an event's key combination
        event_key_combination = event.keyCombination()
        return seq.matches(QKeySequence(event_key_combination)) == QKeySequence.ExactMatch

    def eventFilter(self, source, event):
        if event.type() == QEvent.KeyPress:
            if event.isAutoRepeat():
                return True
            active_modal = QApplication.activeModalWidget()
            if active_modal and active_modal is not self:
                return False
            
            if self._is_hotkey(event, "focus_search"):
                self.search_edit.setFocus()
                self.search_edit.selectAll()
                return True
            if self._is_hotkey(event, "shortcuts_help"):
                self.show_shortcuts_help()
                return True
                
            focused = QApplication.focusWidget()
            if focused in [self.search_edit, self.note_edit]:
                return False
                
            if self._is_hotkey(event, "next_uncoded"):
                self.jump_to_next_uncoded()
                return True
            if self._is_hotkey(event, "play_pause"):
                self.handle_spacebar()
                return True
                
            key_text = self._extract_shortcut(event)
            if self._is_hotkey(event, "prev_subtitle"):
                self.go_to_previous_subtitle()
                return True
            if self._is_hotkey(event, "next_subtitle"):
                self.go_to_next_subtitle()
                return True
            if self._is_hotkey(event, "seek_back"):
                self.seek_relative(-2000)
                return True
            if self._is_hotkey(event, "seek_forward"):
                self.seek_relative(2000)
                return True

            if self._is_hotkey(event, "role_speakers"):
                self.set_active_role('speakers')
                return True
            if self._is_hotkey(event, "role_listeners"):
                self.set_active_role('listeners')
                return True
            if self._is_hotkey(event, "role_targets"):
                self.set_active_role('targets')
                return True
            if self._is_hotkey(event, "cycle_role"):
                self.cycle_active_role()
                return True

            modifiers = event.modifiers()
            is_alt = bool(modifiers & Qt.AltModifier)

            if is_alt and key_text:
                for char_info in self.characters:
                    if char_info.get('key') and char_info['key'] == key_text:
                        self._toggle_role_name(self.active_role, char_info["name"])
                        self.record_annotation(self.current_subtitle_index, clear_selections=False)
                        return True

        return False

    def go_to_previous_subtitle(self):
        if self.current_subtitle_index <= 0:
            return
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        self.jump_to_subtitle(self.current_subtitle_index - 1)
            
    def go_to_next_subtitle(self):
        if self.current_subtitle_index >= len(self.subtitles) - 1:
            return
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        self.jump_to_subtitle(self.current_subtitle_index + 1)

    def seek_relative(self, delta_ms):
        new_pos = self.mediaPlayer.position() + delta_ms
        new_pos = max(0, min(self.mediaPlayer.duration(), new_pos))
        self.mediaPlayer.setPosition(new_pos)
        self.paused_at_subtitle_end = False
        self.sync_subtitle_index_from_position(new_pos)

    def on_seek_slider_pressed(self):
        self.slider_is_dragging = True

    def on_seek_slider_released(self):
        self.slider_is_dragging = False
        pos = self.seek_slider.value()
        self.mediaPlayer.setPosition(pos)
        self.paused_at_subtitle_end = False
        self.sync_subtitle_index_from_position(pos)

    def on_seek_slider_moved(self, value):
        self.time_label.setText(f"{self.format_time(value)} / {self.format_time(self.mediaPlayer.duration())}")

    def duration_changed(self, duration):
        self.seek_slider.setRange(0, max(0, duration))
        self.time_label.setText(f"{self.format_time(self.mediaPlayer.position())} / {self.format_time(duration)}")

    def update_play_button_text(self):
        if self.mediaPlayer.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause_btn.setText("Pause")
        else:
            self.play_pause_btn.setText("Play")

    def format_time(self, milliseconds):
        seconds = max(0, milliseconds) // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02}:{seconds:02}"

    def sync_subtitle_index_from_position(self, position):
        if not self.subtitles:
            return
        chosen = self.current_subtitle_index
        for i, subtitle in enumerate(self.subtitles):
            if subtitle['start_time'] <= position <= subtitle['end_time']:
                chosen = i
                break
            if subtitle['start_time'] <= position:
                chosen = i
        if chosen != self.current_subtitle_index:
            self.record_annotation(self.current_subtitle_index, clear_selections=False)
            self.current_subtitle_index = chosen
            self.subtitle_label.setText(self.subtitles[chosen]['text'])
            self.subtitle_list.selectRow(chosen)
            self.subtitle_list.scrollToItem(self.subtitle_list.item(chosen, 0), QAbstractItemView.PositionAtCenter)
            ann = self.annotations.get(chosen, {})
            self.current_speakers = list(ann.get('speakers', []))
            self.current_listeners = list(ann.get('listeners', []))
            self.current_targets = list(ann.get('targets', []))
            self._updating_table = True
            self.note_edit.setText(ann.get('note', ''))
            self._updating_table = False
            self.apply_inheritance_to_current()
            self.refresh_role_summary()
        self.update_progress_status()

    def handle_spacebar(self):
        if self.mediaPlayer.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.mediaPlayer.pause()
        else:
            if self.paused_at_subtitle_end:
                self.record_annotation(self.current_subtitle_index, clear_selections=True)
                self.jump_to_subtitle(self.current_subtitle_index + 1)
            else:
                self.mediaPlayer.play()
        self.update_play_button_text()

    @Slot(QMediaPlayer.MediaStatus)
    def media_status_changed(self, status):
        pass

    @Slot(int)
    def position_changed(self, position):
        if not self.slider_is_dragging:
            self.seek_slider.setValue(position)
        self.time_label.setText(f"{self.format_time(position)} / {self.format_time(self.mediaPlayer.duration())}")
        if self.current_subtitle_index < len(self.subtitles):
            subtitle = self.subtitles[self.current_subtitle_index]
            end_time = subtitle['end_time']

            if position > end_time and not self.paused_at_subtitle_end:
                if self.app_settings.get("auto_pause", True):
                    self.mediaPlayer.pause()
                    self.update_play_button_text()
                    self.paused_at_subtitle_end = True
                else:
                    self.sync_subtitle_index_from_position(position)
                    self.paused_at_subtitle_end = False
                self.update_progress_status()
        else:
            self.subtitle_label.setText("")

    def open_project_dialog(self):
        vat_file, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "VAT Projects (*.vat)")
        if vat_file:
            self.request_open_project.emit(vat_file)

    def save_project(self):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        if hasattr(self, 'vat_file') and self.vat_file:
            self._write_project_file(self.vat_file)
            self.is_dirty = False
            self.update_progress_status()
        else:
            self.save_project_as_dialog()

    def save_project_as_dialog(self):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Project", "project.vat", "VAT Projects (*.vat)")
        if save_path:
            self.vat_file = save_path
            self._write_project_file(self.vat_file)
            self.is_dirty = False
            self.update_progress_status()
            
    def _write_project_file(self, file_path):
        try:
            # We must use paths relative to the vat file where possible, or just store absolute.
            # Storing absolute is easier but less portable. Let's use pure filenames if in same dir, or absolute.
            vat_dir = Path(file_path).parent
            
            def rel_path(p):
                if not p: return ""
                try:
                    return str(Path(p).relative_to(vat_dir))
                except ValueError:
                    return str(Path(p).absolute())

            project_data = {
                "video_file": rel_path(self.video_file),
                "srt_file": rel_path(self.srt_file),
                "char_file": rel_path(self.char_file),
                "characters": self.characters,
                "annotations": self.annotations
            }
            target = Path(file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
            os.close(fd)
            try:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, indent=4)
                os.replace(tmp_path, file_path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save project: {e}")

    def export_csv_dialog(self):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        if not self.annotations:
            reply = QMessageBox.question(self, "No Annotations", "No annotations recorded. Export anyway?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No: return

        save_path, _ = QFileDialog.getSaveFileName(self, "Export to CSV", "annotations.csv", "CSV Files (*.csv)")
        if save_path:
            self.export_csv(save_path)

    def export_csv(self, file_path):
        try:
            rows = []
            for i, sub in enumerate(self.subtitles):
                ann = self.annotations.get(i, {})
                spk = ', '.join(ann.get('speakers', []))
                lst = ', '.join(ann.get('listeners', []))
                tgt = ', '.join(ann.get('targets', []))
                note = ann.get('note', '')
                if spk or lst or tgt or note:
                    rows.append({
                        'line': sub['text'],
                        'start_time': milliseconds_to_srt_time(sub['start_time']),
                        'end_time': milliseconds_to_srt_time(sub['end_time']),
                        'speakers': spk,
                        'listeners': lst,
                        'targets': tgt,
                        'note': note
                    })
            write_rows_to_csv_atomic(file_path, rows)
            self.is_dirty = False
            self.update_progress_status()
            QMessageBox.information(self, "Success", f"Annotations saved to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export CSV: {e}")

    def import_csv_dialog(self):
        load_path, _ = QFileDialog.getOpenFileName(self, "Import from CSV", "", "CSV Files (*.csv)")
        if load_path:
            self.import_csv(load_path)

    def import_csv(self, file_path):
        try:
            with open(file_path, 'r', newline='', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                loaded_data = list(reader)
                
            self.annotations.clear()
            for i in range(len(self.subtitles)):
                self.subtitle_list.setItem(i, 4, self._make_readonly_item(""))
                self.subtitle_list.setItem(i, 5, self._make_readonly_item(""))
                self.subtitle_list.setItem(i, 6, self._make_readonly_item(""))
                self.subtitle_list.setItem(i, 7, self._make_readonly_item("Uncoded"))
                self.subtitle_list.setItem(i, 8, QTableWidgetItem(""))
                for col in range(9):
                    if self.subtitle_list.item(i, col):
                        self.subtitle_list.item(i, col).setBackground(QColor(255, 255, 255))

            for row in loaded_data:
                for i, sub in enumerate(self.subtitles):
                    if (milliseconds_to_srt_time(sub['start_time']) == row.get('start_time') and 
                        milliseconds_to_srt_time(sub['end_time']) == row.get('end_time')):
                        
                        self.annotations[i] = {
                            'speakers': [s.strip() for s in row.get('speakers', '').split(',')] if row.get('speakers') else [],
                            'listeners': [s.strip() for s in row.get('listeners', '').split(',')] if row.get('listeners') else [],
                            'targets': [s.strip() for s in row.get('targets', '').split(',')] if row.get('targets') else [],
                            'note': row.get('note', '').strip()
                        }
                        
                        self.refresh_subtitle_row(i)
                        break

            self.is_dirty = False
            self.jump_to_subtitle(self.current_subtitle_index)
            self.apply_subtitle_filters()
            self.update_progress_status()
            QMessageBox.information(self, "Success", f"Annotations loaded from {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load annotations: {e}")

    def update_progress_status(self):
        total = len(self.subtitles)
        done = 0
        partial = 0
        for i in range(total):
            status = self.get_annotation_status(i)
            if status == "Done":
                done += 1
            elif status == "Partial":
                partial += 1
        coded = done + partial
        pct = int((done / total) * 100) if total else 0
        dirty_tag = " (unsaved)" if self.is_dirty else ""
        self.progress_label.setText(
            f"Line {self.current_subtitle_index + 1}/{total}  |  Done: {done}  Partial: {partial}  Coded: {coded}/{total} ({pct}%)" + dirty_tag
        )

    def autosave_annotations(self):
        if not self.is_dirty:
            return
        
        # Determine the target autosave path
        save_target = self.vat_file if hasattr(self, 'vat_file') and self.vat_file else self.autosave_path
            
        try:
            self.record_annotation(self.current_subtitle_index, clear_selections=False)
            self._write_project_file(save_target)
        except Exception:
            # Autosave should never interrupt annotation flow.
            pass

    def try_restore_autosave(self):
        # We don't need to restore autosave if we are explicitly opening a vat project,
        # since the vat project is the autosave target itself if it exists.
        if hasattr(self, 'vat_file') and self.vat_file:
            return
            
        if not os.path.exists(self.autosave_path):
            return
        reply = QMessageBox.question(
            self,
            "Restore Autosave",
            f"Found autosave project:\n{self.autosave_path}\n\nRestore it now?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.request_open_project.emit(self.autosave_path)

    def closeEvent(self, event):
        if self.is_dirty:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Save before exit?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Yes:
                if hasattr(self, 'vat_file') and self.vat_file:
                    self.save_project()
                else:
                    save_path, _ = QFileDialog.getSaveFileName(self, "Save Project", "project.vat", "VAT Projects (*.vat)")
                    if not save_path:
                        event.ignore()
                        return
                    self.vat_file = save_path
                    self.save_project()
        self.autosave_timer.stop()
        event.accept()

    @Slot(str)
    def handle_error(self, error):
        print(f"Error occurred: {error}")
        QMessageBox.critical(self, "Media Error", f"Error occurred: {error}")

