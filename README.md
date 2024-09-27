# Video Annotation Tool

A user-friendly tool for annotating video subtitles by selecting speakers and listeners. Supports UTF-16 encoded SRT files and exports annotations to CSV files compatible with Excel.

## Features

- **Subtitle Display:** Shows subtitles beneath the video.
- **Character Selection:** Choose speakers and listeners from a list.
- **Automatic Pausing:** Pauses at the end of each subtitle for annotation.
- **Manual Control:** Use the space bar to play/pause the video.
- **Save and Load:** Save progress anytime and load existing annotations.
- **UTF-16 Support:** Handles UTF-16 encoded SRT files.
- **CSV Export:** Saves annotations in CSV with UTF-8 BOM for compatibility.

## Installation

1. **Clone the Repository**  
   ```
   git clone https://github.com/yourusername/video-annotation-tool.git  
   ```
   Navigate into the directory: cd video-annotation-tool

2. **Install Dependencies** 
   ```
   pip install -r requirements.txt
   ```

## Getting Started

1. **Run the Application** 
   ```
   python annotator.py
   ```

2. **Select Files**  
   Select your video, srt, and txt files.
   The txt files should contain one character at each line.

3. **Start Annotation**  
   Click "Start Annotation" to begin. The video will play and pause at each subtitle. Select speakers and listeners, then press the space bar to continue.

## Contributing

Contributions are welcome! To contribute:

1. **Fork the Repository**
2. **Create a New Branch**  
   Run: git checkout -b feature/YourFeatureName
3. **Make Your Changes**
4. **Commit Your Changes**  
   Run: git commit -m "Add Your Feature Description"
5. **Push to Your Fork**  
   Run: git push origin feature/YourFeatureName
6. **Create a Pull Request**

Please ensure your code follows the project's coding standards and includes appropriate documentation.

## License

This project is licensed under the GPL 3 License.

