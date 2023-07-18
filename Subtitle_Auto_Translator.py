import configparser
import os
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox, ttk, simpledialog
import time
import pysrt
import requests
from requests.exceptions import RequestException, HTTPError
from dotenv import load_dotenv
import logging

# Load environment variables from a .env file, if it exists.
# This is where you might store sensitive information such as API keys
# to prevent them from being exposed in your code.
load_dotenv()

# Create a logger for logging runtime information. This can be helpful for
# debugging, for providing user feedback, and for audit trails.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define some constants to be used throughout the program.
# These include the API endpoint for the translation service, the amount of time
# to wait between requests, and some status strings.
STATUS_IDLE = "Status: Idle"
STATUS_TRANSLATION_COMPLETED = "Translation completed"
DEEPL_API_URL = 'https://api-free.deepl.com/v2/translate'
SLEEP_TIME = 0.1  # time to sleep between requests

# Define a mapping between ISO 639-3 language codes and ISO 639-1 language codes.
# This is necessary because the pysrt library uses ISO 639-3 codes, while the
# DeepL API uses ISO 639-1 codes.
iso_639_3_to_1 = {
    'AFR': 'AF',
    'ARA': 'AR',
    'DEU': 'DE',
    'ENG': 'EN',
    'SPA': 'ES',
    'FRA': 'FR',
    'ITA': 'IT',
    'JPN': 'JA',
    'DUT': 'NL',
    'POL': 'PL',
    'POR': 'PT',
    'RUS': 'RU',
    'CHI': 'ZH',
}


class Translator:
    def __init__(self):
        # The ConfigParser object allows us to read and write data from and to a configuration file.
        self.config = configparser.ConfigParser()
        self.config.read('config.ini')
        # The stop flag is used to stop the translation process from outside.
        self.should_stop = False
        # We will keep count of the number of subtitles that have been translated.
        self.translated_count = 0

        # Load the DeepL API key from the configuration file. If it's not there, ask the user for it.
        if 'DeepL' in self.config and 'API_Key' in self.config['DeepL']:
            self.deepl_api_key = self.config['DeepL']['API_Key']
        else:
            self.deepl_api_key = os.getenv('DEEPL_API_KEY')
            if not self.deepl_api_key:
                self.deepl_api_key = simpledialog.askstring("DeepL API Key", "Enter your DeepL API Key:", show="*")
            self.config['DeepL'] = {'API_Key': self.deepl_api_key}

        # Load the number of threads to use from the configuration file. If it's not there, ask the user for it.
        if 'Preferences' in self.config and 'num_threads' in self.config['Preferences']:
            num_threads = int(self.config['Preferences']['num_threads'])
        else:
            num_threads = simpledialog.askinteger("Number of Threads",
                                                  "Enter the number of threads to use (default is 4):",
                                                  initialvalue=4)
            self.config['Preferences'] = {'num_threads': str(num_threads)}

        # Save the configuration file so that we don't have to ask the user for the same information next time.
        with open('config.ini', 'w') as configfile:
            self.config.write(configfile)

        # The ThreadPoolExecutor allows us to run tasks in the background, without blocking the GUI.
        self.executor = ThreadPoolExecutor(max_workers=num_threads)
        # The quota and used_quota variables will be used to keep track of how much of the DeepL API quota we have used.
        self.quota = 500000
        self.used_quota = 0
        # We will keep track of the current translation task in case we need to cancel it.
        self.current_translation = None

    @staticmethod
    def get_supported_languages():
        # Return a dictionary that maps language codes to full language names.
        # This will be used to populate the dropdown menus in the GUI.
        return {
            'AF': 'Afrikaans',
            'AR': 'Arabic',
            'DE': 'German',
            'EN': 'English',
            'ES': 'Spanish',
            'FR': 'French',
            'IT': 'Italian',
            'JA': 'Japanese',
            'NL': 'Dutch',
            'PL': 'Polish',
            'PT': 'Portuguese',
            'RU': 'Russian',
            'ZH': 'Chinese',
        }

    def translate_srt(self, file_path, output_path, src_lang, dest_lang, callback_dict):
        # Check if the file is an SRT file. If not, show an error message and stop.
        _, ext = os.path.splitext(file_path)
        if ext.lower() != '.srt':
            messagebox.showerror("Error", f"The file {file_path} is not an SRT file. Please convert it to SRT format.")
            return

        # Open the SRT file and start translating each subtitle.
        subtitles = pysrt.open(file_path)
        total_subtitles = len(subtitles)
        self.translated_count = 0
        logger.info(f"Total subtitles to translate: {total_subtitles}")

        for i, subtitle in enumerate(subtitles, start=1):
            if self.should_stop:  # check the stop flag before doing any work
                return
            try:
                # Send a POST request to the DeepL API to translate the subtitle.
                response = requests.post(
                    DEEPL_API_URL,
                    data={
                        'auth_key': self.deepl_api_key,
                        'text': subtitle.text,
                        'source_lang': src_lang,
                        'target_lang': dest_lang,
                    },
                )
                response.raise_for_status()  # Raises stored HTTPError, if one occurred.
                translation = response.json()
                subtitle.text = translation['translations'][0]['text']
                # Update the quota and progress.
                self.used_quota += len(subtitle.text)
                self.translated_count += 1
                callback_dict["quota_callback"](self.used_quota)
                callback_dict["progress_callback"](self.translated_count / total_subtitles)
            except HTTPError as http_err:
                logger.error(f"HTTP error occurred: {http_err}")
                continue
            except RequestException as req_err:
                logger.error(f"Error occurred during request: {req_err}")
                continue
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                continue
            time.sleep(SLEEP_TIME)

        # Save the translated subtitles to the output file.
        subtitles.save(output_path, encoding='utf-8')
        logger.info(f"Translated file saved at {output_path}")
        callback_dict["status_callback"](STATUS_TRANSLATION_COMPLETED)

    def start_translation(self, file_path, output_path, src_lang, dest_lang, callback_dict):
        # Start the translation process. If the file is an SRT file, submit the task to the executor.
        # Check if the API key is available and valid before starting the translation
        if not self.deepl_api_key or len(self.deepl_api_key.strip()) == 0:
            callback_dict["error_callback"]("No API key found. Please provide a valid DeepL API Key.")
            return
        self.should_stop = False  # reset the stop flag
        _, ext = os.path.splitext(file_path)
        if ext.lower() == '.srt':
            callback_dict["status_callback"]("Translation started")
            self.current_translation = self.executor.submit(self.translate_srt, file_path, output_path, src_lang,
                                                            dest_lang, callback_dict)
        else:
            messagebox.showerror("Error", "Invalid file type. Only .srt files are supported. You can convert your "
                                          "non-SRT file to SRT using this online tool: "
                                          "https://www.veed.io/subtitle-tools/edit?locale=en&source=%2Ftools"
                                          "%2Fsubtitle-converter%2Fass-to-srt or use your own converter.")

    def stop_translation(self):
        # Stop the translation process by setting the stop flag and cancelling the current task.
        self.should_stop = True
        if self.current_translation:
            self.current_translation.cancel()
        logger.info("Translation cancelled")

    def get_quota(self):
        # Return the quota and how much of it has been used.
        return self.quota, self.used_quota


class TranslatorGUI:
    def __init__(self, root):
        # Create a Translator object that we will use to perform the translations.
        self.translator = Translator()

        # Create the main window and the frames that will hold the widgets.
        self.root = root
        self.root.title("Subtitle Translator")

        self.file_frame = tk.Frame(self.root)
        self.file_frame.pack(fill='x', padx=15, pady=10)

        self.lang_frame = tk.Frame(self.root)
        self.lang_frame.pack(fill='x', padx=15, pady=10)

        self.btn_frame = tk.Frame(self.root)
        self.btn_frame.pack(fill='x', padx=15, pady=10)

        self.prog_frame = tk.Frame(self.root)
        self.prog_frame.pack(fill='x', padx=15, pady=10)

        self.status_frame = tk.Frame(self.root)
        self.status_frame.pack(fill='x', padx=15, pady=10)

        self.config_frame = tk.Frame(self.root)
        self.config_frame.pack(fill='x', padx=15, pady=10)

        # Create the widgets and pack them into their respective frames.
        tk.Label(self.file_frame, text="Select Subtitle File:").pack(side='left')
        self.file_entry = tk.Entry(self.file_frame, width=50)
        self.file_entry.pack(side='left', padx=5)
        self.file_button = tk.Button(self.file_frame, text="Browse...", command=self.select_file)
        self.file_button.pack(side='left')

        tk.Label(self.file_frame, text="Select Output Directory:").pack(side='left')
        self.output_file_entry = tk.Entry(self.file_frame, width=50)
        self.output_file_entry.pack(side='left', padx=5)
        self.output_file_button = tk.Button(self.file_frame, text="Browse...", command=self.select_output_file)
        self.output_file_button.pack(side='left')

        # More widgets...
        # Language selection
        tk.Label(self.lang_frame, text="Source Language:").pack(side='left')
        self.src_lang_var = tk.StringVar(self.root)
        self.src_lang_var.set(next(iter(self.translator.get_supported_languages().values())))
        self.src_lang_dropdown = tk.OptionMenu(self.lang_frame, self.src_lang_var,
                                               *self.translator.get_supported_languages().values())
        self.src_lang_dropdown.pack(side='left', padx=5)

        tk.Label(self.lang_frame, text="Target Language:").pack(side='left')
        self.dest_lang_var = tk.StringVar(self.root)
        self.dest_lang_var.set(next(iter(self.translator.get_supported_languages().values())))
        self.dest_lang_dropdown = tk.OptionMenu(self.lang_frame, self.dest_lang_var,
                                                *self.translator.get_supported_languages().values())
        self.dest_lang_dropdown.pack(side='left', padx=5)

        # Translation and cancellation buttons
        self.translate_button = tk.Button(self.btn_frame, text="Start Translation", command=self.start_translation)
        self.translate_button.pack(side='left', padx=5)

        self.cancel_button = tk.Button(self.btn_frame, text="Stop Translation", command=self.stop_translation)
        self.cancel_button.pack(side='left', padx=5)

        # Progress bar and labels
        self.progress_bar = ttk.Progressbar(self.prog_frame, length=100, mode="determinate")
        self.progress_bar.pack(fill='x', padx=5)

        self.progress_label = tk.Label(self.prog_frame, text="0.00%")
        self.progress_label.pack(fill='x', padx=5)

        self.quota_label = tk.Label(self.prog_frame,
                                    text=f"Quota Used: {self.translator.used_quota}/{self.translator.quota}")
        self.quota_label.pack(fill='x', padx=5)

        self.status_label = tk.Label(self.status_frame, text=STATUS_IDLE)
        self.status_label.pack(fill='x', padx=5)

        # API Key and thread configuration buttons
        self.api_key_update_button = tk.Button(self.config_frame, text="Update API Key", command=self.update_api_key)
        self.api_key_update_button.pack(side='left', padx=5)

        self.api_key_delete_button = tk.Button(self.config_frame, text="Delete API Key", command=self.delete_api_key)
        self.api_key_delete_button.pack(side='left', padx=5)

        self.thread_button = tk.Button(self.config_frame, text="Set Thread Count", command=self.set_thread_count)
        self.thread_button.pack(side='left', padx=5)

        self.help_button = tk.Button(self.config_frame, text="Help", command=self.show_help)
        self.help_button.pack(side='left', padx=5)

    # Define the event handlers for the buttons.
    def update_api_key(self):
        api_key = simpledialog.askstring("Update API Key", "Enter your new DeepL API Key:", show="*")
        if api_key:
            self.translator.deepl_api_key = api_key
            self.translator.config['DeepL'] = {'API_Key': self.translator.deepl_api_key}
            with open('config.ini', 'w') as configfile:
                self.translator.config.write(configfile)
        else:
            messagebox.showerror("Error", "API Key is missing. Please provide a valid API Key.")

    def delete_api_key(self):
        if messagebox.askyesno("Delete API Key", "Are you sure you want to delete your DeepL API Key?"):
            if 'DeepL' in self.translator.config:
                del self.translator.config['DeepL']
                with open('config.ini', 'w') as configfile:
                    self.translator.config.write(configfile)
                self.translator.deepl_api_key = None
                messagebox.showinfo("Info", "API Key has been deleted.")
            else:
                messagebox.showerror("Error", "No API Key found to delete.")

    def set_thread_count(self):
        thread_count = simpledialog.askinteger("Set Thread Count", "Enter the number of threads:", initialvalue=4)
        self.translator.executor = ThreadPoolExecutor(max_workers=thread_count)

    def select_file(self):
        file_path = filedialog.askopenfilename()
        self.file_entry.delete(0, tk.END)
        self.file_entry.insert(0, file_path)

    def select_output_file(self):
        output_file_path = filedialog.asksaveasfilename()
        self.output_file_entry.delete(0, tk.END)
        self.output_file_entry.insert(0, output_file_path)

    def start_translation(self):
        file_path = self.file_entry.get()
        output_file_path = self.output_file_entry.get()

        # We get the language code by reversing the key-value pairs in the dictionary
        lang_dict = self.translator.get_supported_languages()
        rev_lang_dict = {v: k for k, v in lang_dict.items()}

        src_lang = rev_lang_dict[self.src_lang_var.get()]
        dest_lang = rev_lang_dict[self.dest_lang_var.get()]

        if not file_path or not output_file_path:
            messagebox.showerror("Error", "Both a subtitle file and an output file must be selected.")
            return

        if not src_lang or not dest_lang:
            messagebox.showerror("Error", "Both a source language and a destination language must be selected.")
            return

        callback_dict = {
            "quota_callback": self.update_quota,
            "status_callback": self.update_status,
            "progress_callback": self.update_progress,
            "error_callback": self.show_error_message,
        }

        self.translator.start_translation(file_path, output_file_path, src_lang, dest_lang, callback_dict)

    def stop_translation(self):
        self.translator.stop_translation()
        self.update_status(STATUS_IDLE)

    def show_error_message(self, message):
        # Show an error message to the user
        messagebox.showerror("Error", message)

    def update_quota(self, used_quota):
        self.quota_label.config(text=f"Quota Used: {used_quota}/{self.translator.quota}")

    def update_status(self, status):
        self.status_label.config(text=f"Status: {status}")
        if status == STATUS_TRANSLATION_COMPLETED:
            messagebox.showinfo("Info", STATUS_TRANSLATION_COMPLETED)

    def update_progress(self, progress):
        self.progress_bar['value'] = progress * 100
        self.progress_label.config(text=f"{progress * 100:.2f}%")

    @staticmethod
    def show_help():
        messagebox.showinfo("Help",
                            "This is a simple subtitle translator. You can select a file or directory of subtitle "
                            "files (.srt or .ass) to translate, specify an output file for the translated subtitles, "
                            "select the source and destination languages, and then click 'Translate' to start the "
                            "translation. The 'Cancel' button can be used to stop an ongoing translation. The program "
                            "will display how much of your DeepL API quota has been used.\n\n"
                            "If you don't have a DeepL API key, you can get one from the DeepL Pro website. "
                            "Please note that this is a paid service. Visit the following URL to get a key: "
                            "https://www.deepl.com/pro#developer.")


def main():
    # Create the main window and start the event loop.
    root = tk.Tk()
    TranslatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
