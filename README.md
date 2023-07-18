Subtitle Translator
Subtitle Translator is a Python application built with tkinter that allows you to translate subtitle files (.srt) from one language to another using the DeepL translation API. The application provides a GUI for user interaction and allows you to manage translations through various settings.

Prerequisites
Before you can use Subtitle Translator, you need to have the following installed:

Python 3.7 or later: You can download it from here.
Python libraries: tkinter, requests, pysrt, concurrent.futures, configparser, os, time, dotenv, logging.
You can install the necessary Python libraries using pip:
pip install tk requests pysrt python-dotenv configparser

Usage
Here's how to use Subtitle Translator:

Run the application. A GUI window will open.

Click on "Browse..." to select the subtitle file (.srt) you want to translate.

Click on "Browse..." to select the output directory where the translated file will be saved.

Select the source language of your subtitle file and the target language to which you want to translate.

Click "Start Translation" to begin the translation process. The progress will be displayed on the progress bar.

If you wish to stop the translation process at any point, click "Stop Translation".

DeepL API Key
This application uses the DeepL API for translation. To use it, you need a DeepL API key, which is a paid service. You can get an API key from the DeepL Pro website.

The API key can be stored in a .env file or input manually when running the program. There are also options in the GUI to update or delete the stored API key.

Configuration
The number of threads used for translation can be adjusted through the GUI. Increasing the number of threads may increase the speed of translation but will also use more system resources.

Limitations
The application currently only supports .srt subtitle files.
Depending on the length of the subtitles and the limit of your DeepL API quota, you may not be able to translate all your subtitles.
Contributing
Contributions to the project are welcome. Please create a pull request with your changes.

License
Subtitle Translator is licensed under the MIT License.
