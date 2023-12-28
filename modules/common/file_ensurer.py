## built-in libaries
import os
import traceback
import json
import typing

## custom modules
from modules.common.logger import Logger

class FileEnsurer():

    """
    
    FileEnsurer is a class that is used to ensure that the required files and directories exist.
    Also serves as a place to store the paths to the files and directories. Some file related functions are also stored here.
    As well as some variables that are used to store the default kijiku rules and the allowed models across Kudasai.

    """

    ## main dirs
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    output_dir = os.path.join(script_dir, "output")
    archive_dir = os.path.join(output_dir, "archive")

    if(os.name == 'nt'):  ## Windows
        config_dir = os.path.join(os.environ['USERPROFILE'],"KudasaiConfig")
    else:  ## Linux
        config_dir = os.path.join(os.path.expanduser("~"), "KudasaiConfig")

    Logger.log_file_path = os.path.join(output_dir, "debug_log.txt")

    ##----------------------------------/

    ## sub dirs
    lib_dir = os.path.join(script_dir, "lib")
    sudachi_lib = os.path.join(lib_dir, "sudachi")
    dic_lib = os.path.join(lib_dir, "dicts")
    gui_lib = os.path.join(lib_dir, "gui")

    ##----------------------------------/

    ## output files
    preprocessed_text_path = os.path.join(output_dir, "preprocessed_text.txt") ## path for the preprocessed text
    translated_text_path = os.path.join(output_dir, "translated_text.txt") ## path for translated text

    je_check_path = os.path.join(output_dir, "je_check_text.txt") ## path for je check text (text generated by the translation modules to compare against the translated text)

    kairyou_log_path = os.path.join(output_dir, "preprocessing_results.txt")  ## path for kairyou log (the results of preprocessing)
    error_log_path = os.path.join(output_dir, "error_log.txt") ## path for the error log (errors generated by the preprocessing and translation modules)
    debug_log_path = Logger.log_file_path ## path for the debug log (debug info generated by the preprocessing and translation modules)

    ## sudachi files (not in use)
    system_zip = os.path.join(dic_lib, "system.zip")
    sudachi_config_json = os.path.join(sudachi_lib, "sudachi.json")
    sudachi_system_dic = os.path.join(dic_lib, "system.dic") 

    ## kairyou files
    katakana_words_path = os.path.join(sudachi_lib, "katakana_words.txt")

    ## kijiku rules
    external_kijiku_rules_path = os.path.join(script_dir,'kijiku_rules.json')
    config_kijiku_rules_path = os.path.join(config_dir,'kijiku_rules.json')

    ## api keys
    deepl_api_key_path = os.path.join(config_dir, "deepl_api_key.txt")
    openai_api_key_path = os.path.join(config_dir,'openai_api_key.txt')

    ## favicon
    favicon_path = os.path.join(gui_lib, "Kudasai_Logo.png")

    ## default kijiku rules
    default_kijiku_rules = {
    "open ai settings": 
    {
        "model":"gpt-3.5-turbo",
        "system_message":"You are a Japanese To English translator. Please remember that you need to translate the narration into English simple past. Try to keep the original formatting and punctuation as well.",
        "temp":0.3,
        "top_p":1,
        "n":1,
        "stream":False,
        "stop":None,
        "logit_bias":None,
        "max_tokens":9223372036854775807,
        "presence_penalty":0,
        "frequency_penalty":0,
        "message_mode":1,
        "num_lines":13,
        "sentence_fragmenter_mode":3,
        "je_check_mode":2,
        "num_malformed_batch_retries":1,
        "batch_retry_timeout":300,
        "num_concurrent_batches":30
    }
    }

    allowed_models = [
        "gpt-3.5-turbo",
        "gpt-4",
        "gpt-3.5-turbo-0301",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-3.5-turbo-1106",
        "gpt-4-0613",
        "gpt-4-32k-0613",
        "gpt-4-1106-preview"
    ]

    invalid_kijiku_rules_placeholder = {
    "open ai settings": 
    {
        "model":"INVALID JSON",
        "system_message":"You are a Japanese To English translator. Please remember that you need to translate the narration into English simple past. Try to keep the original formatting and punctuation as well.",
        "temp":0.3,
        "top_p":1,
        "n":1,
        "stream":False,
        "stop":None,
        "logit_bias":None,
        "max_tokens":9223372036854775807,
        "presence_penalty":0,
        "frequency_penalty":0,
        "message_mode":1,
        "num_lines":13,
        "sentence_fragmenter_mode":3,
        "je_check_mode":2,
        "num_malformed_batch_retries":1,
        "batch_retry_timeout":300,
        "num_concurrent_batches":30
    }
    }

    do_interrupt = False

##-------------------start-of-setup_needed_files()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def setup_needed_files() -> None:

        """

        Ensures that the required files and directories exist.

        """

        ## creates the output directory and config directory if they don't exist
        FileEnsurer.standard_create_directory(FileEnsurer.config_dir)
        FileEnsurer.standard_create_directory(FileEnsurer.output_dir)

        ## creates and clears the log file
        Logger.clear_log_file()

        ## creates the 5 output files
        FileEnsurer.standard_create_file(FileEnsurer.preprocessed_text_path)
        FileEnsurer.standard_create_file(FileEnsurer.translated_text_path)
        FileEnsurer.standard_create_file(FileEnsurer.je_check_path)
        FileEnsurer.standard_create_file(FileEnsurer.kairyou_log_path)
        FileEnsurer.standard_create_file(FileEnsurer.error_log_path)

        ## creates the kijiku rules file if it doesn't exist
        if(os.path.exists(FileEnsurer.config_kijiku_rules_path) == False):
            with open(FileEnsurer.config_kijiku_rules_path, 'w+', encoding='utf-8') as file:
                json.dump(FileEnsurer.default_kijiku_rules, file)
        
        if(not os.path.exists(FileEnsurer.katakana_words_path)):
           raise FileNotFoundError(f"Katakana words file not found at {FileEnsurer.katakana_words_path}. Can not continue, preprocess failed.")

##--------------------start-of-standard_create_directory()------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def standard_create_directory(directory_path:str) -> None:

        """

        Creates a directory if it doesn't exist, as well as logs what was created.

        Parameters:
        directory_path (str) : path to the directory to be created.

        """

        if(os.path.isdir(directory_path) == False):
            os.mkdir(directory_path)
            Logger.log_action(directory_path + " created due to lack of the folder")

##--------------------start-of-standard_create_file()------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def standard_create_file(file_path:str) -> None:

        """

        Creates a file if it doesn't exist, truncates it,  as well as logs what was created.

        Parameters:
        file_path (str) : path to the file to be created.

        """

        if(os.path.exists(file_path) == False):
            Logger.log_action(file_path + " was created due to lack of the file")
            with open(file_path, "w+", encoding="utf-8") as file:
                file.truncate()

##--------------------start-of-modified_create_file()------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def modified_create_file(file_path:str, content_to_write:str) -> bool:

        """

        Creates a path if it doesn't exist or if it is blank or empty, writes to it, as well as logs what was created.

        Parameters:
        file_path (str) : path to the file to be created.
        content to write (str) : content to be written to the file.

        Returns:
        bool : whether or not the file was overwritten.

        """

        did_overwrite = False

        if(os.path.exists(file_path) == False or os.path.getsize(file_path) == 0):
            Logger.log_action(file_path + " was created due to lack of the file or because it is blank")
            with open(file_path, "w+", encoding="utf-8") as file:
                file.write(content_to_write)

            did_overwrite = True

        return did_overwrite

##--------------------start-of-standard_overwrite_file()------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def standard_overwrite_file(file_path:str, content_to_write:str, omit:bool = True) -> None:

        """

        Writes to a file, creates it if it doesn't exist, overwrites it if it does, as well as logs what occurred.

        Parameters:
        file_path (str) : path to the file to be overwritten.
        content to write (str) : content to be written to the file.
        omit (bool | optional) : whether or not to omit the content from the log.

        """

        with open(file_path, "w+", encoding="utf-8") as file:
            file.write(content_to_write)

        if(omit):
            content_to_write = "(Content was omitted)"
        
        Logger.log_action(file_path + " was overwritten with the following content: " + content_to_write)

##--------------------start-of-clear_file()------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def clear_file(file_path:str) -> None:

        """

        Clears a file, as well as logs what occurred.

        Parameters:
        file_path (str) : path to the file to be cleared.

        """

        with open(file_path, "w+", encoding="utf-8") as file:
            file.truncate()

        Logger.log_action(file_path + " was cleared")

##--------------------start-of-standard_read_file()------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def standard_read_file(file_path:str) -> str:

        """

        Reads a file.

        Parameters:
        file_path (str) : path to the file to be read.

        Returns:
        content (str) : the content of the file.

        """

        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()

        return content

##-------------------start-of-handle_critical_exception()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def handle_critical_exception(critical_exception:Exception) -> None:

        """

        Handles a critical exception by logging it and then throwing it.

        Parameters:
        critical_exception (object - Exception) : the exception to be handled.

        """

        ## if crash, catch and log, then throw
        Logger.log_action("--------------------------------------------------------------")
        Logger.log_action("Please send the following to the developer on github at https://github.com/Bikatr7/Kudasai/issues :")  
        Logger.log_action("Kudasai has crashed")

        traceback_str = traceback.format_exc()
        
        Logger.log_action(traceback_str)

        Logger.push_batch()

        raise critical_exception
    
##-------------------start-of-archive_results()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------


    @staticmethod
    def archive_results(list_of_result_tuples:typing.List[typing.Tuple[str,str]], module:str, timestamp:str) -> None:

        """

        Creates a directory in the archive folder and writes the results to files in that directory.

        Parameters:
        list_of_result_tuples (list - tuple - str, str) : list of tuples containing the filename and content of the results to be archived.
        module (str) : name of the module that generated the results.
        timestamp (str) : timestamp of when the results were generated.

        """

        archival_path = os.path.join(FileEnsurer.archive_dir, f'{module}_run_{timestamp}')
        FileEnsurer.standard_create_directory(archival_path)

        for result in list_of_result_tuples:
            (filename, content) = result
            result_file_path = os.path.join(archival_path, f'{filename}_{timestamp}.txt')

            with open(result_file_path, "w", encoding="utf-8") as file:
                file.writelines(content)

