## built-in libaries
import typing
import base64
import re
import time
import typing
import asyncio
import os

## third party modules
from kairyou import KatakanaUtil

import tiktoken
import backoff

## custom modules
from handlers.json_handler import JsonHandler

from modules.common.file_ensurer import FileEnsurer
from modules.common.logger import Logger
from modules.common.toolkit import Toolkit
from modules.common.exceptions import AuthenticationError, MaxBatchDurationExceededException, AuthenticationError, InternalServerError, RateLimitError, APIError, APIConnectionError, APITimeoutError
from modules.common.decorators import permission_error_decorator

from custom_classes.messages import SystemTranslationMessage, ModelTranslationMessage

from translation_services.openai_service import OpenAIService

##-------------------start-of-Kijiku--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class Kijiku:

    """
    
    Kijiku is a secondary class that is used to interact with the OpenAI API and translates the text by batch.
    
    """
    
    text_to_translate:typing.List[str] = []

    translated_text:typing.List[str] = []

    je_check_text:typing.List[str] = []

    error_text:typing.List[str] = []

    ## the messages that will be sent to the api, contains a system message and a model message, system message is the instructions,
    ## model message is the text that will be translated  
    translation_batches = []

    num_occurred_malformed_batches = 0

    ## semaphore to limit the number of concurrent batches
    _semaphore = asyncio.Semaphore(30)

    ##--------------------------------------------------------------------------------------------------------------------------

    translation_print_result = ""

    ##--------------------------------------------------------------------------------------------------------------------------

    model = ""
    translation_instructions = ""
    message_mode = 0 
    prompt_size = 0
    sentence_fragmenter_mode = 0
    je_check_mode = 0
    num_of_malform_retries = 0
    max_batch_duration = 0
    num_concurrent_batches = 0

##-------------------start-of-get_max_batch_duration()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    
    @staticmethod
    def get_max_batch_duration() -> float:

        """
        
        Returns the max batch duration.
        Structured as a function so that it can be used as a lambda function in the backoff decorator. As decorators call the function when they are defined/runtime, not when they are called.

        Returns:
        max_batch_duration (float) : the max batch duration.

        """

        return Kijiku.max_batch_duration
    
##-------------------start-of-log_retry()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def log_retry(details) -> None:

        """

        Logs the retry message.

        Parameters:
        details (dict) : the details of the retry.

        """

        retry_msg = f"Retrying translation after {details['wait']} seconds after {details['tries']} tries {details['target']} due to {details['exception']}."

        Logger.log_barrier()
        Logger.log_action(retry_msg)
        Logger.log_barrier()

##-------------------start-of-log_failure()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def log_failure(details) -> None:

        """
        
        Logs the translation batch failure message.

        Parameters:
        details (dict) : the details of the failure.

        """

        error_msg = f"Exceeded duration, returning untranslated text after {details['tries']} tries {details['target']}."

        Logger.log_barrier()
        Logger.log_error(error_msg)
        Logger.log_barrier()

        raise MaxBatchDurationExceededException(error_msg)

##-------------------start-of-translate()--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    async def translate() -> None:

        """

        Translate the text in the file at the path given.

        """

        Logger.clear_batch()

        ## set this here cause the try-except could throw before we get past the settings configuration
        time_start = time.time()

        try:
        
            await Kijiku.initialize()

            JsonHandler.validate_json()

            await Kijiku.check_settings()

            ## set actual start time to the end of the settings configuration
            time_start = time.time()

            await Kijiku.commence_translation()

        except Exception as e:
            
            Kijiku.translation_print_result += "An error has occurred, outputting results so far..."

            FileEnsurer.handle_critical_exception(e)

        finally:

            time_end = time.time() 

            Kijiku.assemble_results(time_start, time_end)

##-------------------start-of-initialize()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    async def initialize() -> None:

        """

        Sets the open api key.
    
        """

        await Kijiku.init_api_key()

        ## try to load the kijiku rules
        try: 

            JsonHandler.load_kijiku_rules()

        ## if the kijiku rules don't exist, create them
        except: 
            
            JsonHandler.reset_kijiku_rules_to_default()

            JsonHandler.load_kijiku_rules()
            
        Toolkit.clear_console()

##-------------------start-of-setup_api_key()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    async def init_api_key() -> None:

        """
        
        Sets up the api key.

        """

        ## get saved API key if exists
        try:
            with open(FileEnsurer.openai_api_key_path, 'r', encoding='utf-8') as file: 
                api_key = base64.b64decode((file.read()).encode('utf-8')).decode('utf-8')

            OpenAIService.set_api_key(api_key)

            is_valid, e = await OpenAIService.test_api_key_validity()

            ## if not valid, raise the exception that caused the test to fail
            if(not is_valid and e is not None):
                raise e
        
            Logger.log_action("Used saved API key in " + FileEnsurer.openai_api_key_path, output=True)
            Logger.log_barrier()

            time.sleep(2)

        ## else try to get API key manually
        except:

            Toolkit.clear_console()
                
            api_key = input("DO NOT DELETE YOUR COPY OF THE API KEY\n\nPlease enter the OpenAI API key you have : ")

            ## if valid save the API key
            try: 

                OpenAIService.set_api_key(api_key)

                is_valid, e = await OpenAIService.test_api_key_validity()

                if(not is_valid and e is not None):
                    raise e

                FileEnsurer.standard_overwrite_file(FileEnsurer.openai_api_key_path, base64.b64encode(api_key.encode('utf-8')).decode('utf-8'), omit=True)
                
            ## if invalid key exit
            except AuthenticationError: 
                    
                Toolkit.clear_console()
                        
                Logger.log_action("Authorization error while setting up OpenAI, please double check your API key as it appears to be incorrect.", output=True)

                Toolkit.pause_console()
                        
                exit()

            ## other error, alert user and raise it
            except Exception as e: 

                Toolkit.clear_console()
                        
                Logger.log_action("Unknown error while setting up OpenAI, The error is as follows " + str(e)  + "\nThe exception will now be raised.", output=True)

                Toolkit.pause_console()

                raise e

##-------------------start-of-reset_static_variables()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def reset_static_variables() -> None:

        """

        Resets the static variables.
        Done to prevent issues with the webgui.

        """

        Logger.clear_batch()

        Kijiku.text_to_translate = []
        Kijiku.translated_text = []
        Kijiku.je_check_text = []
        Kijiku.error_text = []
        Kijiku.translation_batches = []
        Kijiku.num_occurred_malformed_batches = 0
        Kijiku.translation_print_result = ""

##-------------------start-of-check-settings()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    async def check_settings() -> None:

        """

        Prompts the user to confirm the settings in the kijiku rules file.

        """

        print("Are these settings okay? (1 for yes or 2 for no) : \n\n")

        for key, value in JsonHandler.current_kijiku_rules["open ai settings"].items():
            print(key + " : " + str(value))

        if(input("\n") == "1"):
            pass
        else:
            JsonHandler.change_kijiku_settings()

        Toolkit.clear_console()

        print("Do you want to change your API key? (1 for yes or 2 for no) : ")

        if(input("\n") == "1"):
            os.remove(FileEnsurer.openai_api_key_path)
            await Kijiku.init_api_key()

        Toolkit.clear_console()

##-------------------start-of-commence_translation()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    async def commence_translation(is_webgui:bool=False) -> None:

        """

        Uses all the other functions to translate the text provided by Kudasai.

        """
        
        Logger.log_barrier()
        Logger.log_action("Kijiku Activated, Settings are as follows : ")
        Logger.log_barrier()

        for key,value in JsonHandler.current_kijiku_rules["open ai settings"].items():
            Logger.log_action(key + " : " + str(value))

        Kijiku.model = JsonHandler.current_kijiku_rules["open ai settings"]["model"]
        Kijiku.translation_instructions = JsonHandler.current_kijiku_rules["open ai settings"]["system_message"]
        Kijiku.message_mode = int(JsonHandler.current_kijiku_rules["open ai settings"]["message_mode"])
        Kijiku.prompt_size = int(JsonHandler.current_kijiku_rules["open ai settings"]["num_lines"])
        Kijiku.sentence_fragmenter_mode = int(JsonHandler.current_kijiku_rules["open ai settings"]["sentence_fragmenter_mode"])
        Kijiku.je_check_mode = int(JsonHandler.current_kijiku_rules["open ai settings"]["je_check_mode"])
        Kijiku.num_of_malform_retries = int(JsonHandler.current_kijiku_rules["open ai settings"]["num_malformed_batch_retries"])
        Kijiku.max_batch_duration = float(JsonHandler.current_kijiku_rules["open ai settings"]["batch_retry_timeout"])
        Kijiku.num_concurrent_batches = int(JsonHandler.current_kijiku_rules["open ai settings"]["num_concurrent_batches"])

        OpenAIService.model = Kijiku.model
        OpenAIService.temperature = float(JsonHandler.current_kijiku_rules["open ai settings"]["temp"])
        OpenAIService.top_p = float(JsonHandler.current_kijiku_rules["open ai settings"]["top_p"])
        OpenAIService.n = int(JsonHandler.current_kijiku_rules["open ai settings"]["n"])
        OpenAIService.stop = JsonHandler.current_kijiku_rules["open ai settings"]["stop"]
        OpenAIService.stream = bool(JsonHandler.current_kijiku_rules["open ai settings"]["stream"])
        OpenAIService.stop = JsonHandler.current_kijiku_rules["open ai settings"]["stop"]
        OpenAIService.presence_penalty = float(JsonHandler.current_kijiku_rules["open ai settings"]["presence_penalty"])
        OpenAIService.frequency_penalty = float(JsonHandler.current_kijiku_rules["open ai settings"]["frequency_penalty"])
        OpenAIService.max_tokens = JsonHandler.current_kijiku_rules["open ai settings"]["max_tokens"]

        decorator_to_use = backoff.on_exception(backoff.expo, max_time=lambda: Kijiku.get_max_batch_duration(), exception=(AuthenticationError, InternalServerError, RateLimitError, APIError, APIConnectionError, APITimeoutError), on_backoff=lambda details: Kijiku.log_retry(details), on_giveup=lambda details: Kijiku.log_failure(details), raise_on_giveup=False)

        OpenAIService.set_decorator(decorator_to_use)

        Kijiku._semaphore = asyncio.Semaphore(Kijiku.num_concurrent_batches)

        Toolkit.clear_console()

        Logger.log_barrier()
        Logger.log_action("Starting Prompt Building")
        Logger.log_barrier()

        Kijiku.build_translation_batches()

        ## get cost estimate and confirm
        await Kijiku.handle_cost_estimate_prompt(omit_prompt=is_webgui)

        Toolkit.clear_console()

        Logger.log_barrier()
        
        Logger.log_action("Starting Translation...", output=not is_webgui)
        Logger.log_barrier()

        ## requests to run asynchronously
        async_requests = []
        length = len(Kijiku.translation_batches)

        for i in range(0, length, 2):
            async_requests.append(Kijiku.handle_translation(i, length, Kijiku.translation_batches[i], Kijiku.translation_batches[i+1]))

        ## Use asyncio.gather to run tasks concurrently/asynchronously and wait for all of them to complete
        results = await asyncio.gather(*async_requests)

        Logger.log_barrier()
        Logger.log_action("Translation Complete!", output=not is_webgui)

        Logger.log_barrier()
        Logger.log_action("Starting Redistribution...", output=not is_webgui)

        Logger.log_barrier()

        ## Sort results based on the index to maintain order
        sorted_results = sorted(results, key=lambda x: x[0])

        ## Redistribute the sorted results
        for index, translated_prompt, translated_message in sorted_results:
            Kijiku.redistribute(translated_prompt, translated_message)

        ## try to pair the text for j-e checking if the mode is 2
        if(Kijiku.je_check_mode == 2):
            Kijiku.je_check_text = Kijiku.fix_je()

        Toolkit.clear_console()

        Logger.log_action("Done!", output=not is_webgui)
        Logger.log_barrier()

        ## assemble error text based of the error list
        Kijiku.error_text = Logger.errors

##-------------------start-of-generate_prompt()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def generate_prompt(index:int) -> tuple[typing.List[str],int]:

        """

        Generates prompts for the messages meant for the API.

        Parameters:
        index (int) : An int representing where we currently are in the text file.

        Returns:
        prompt (list - string) : A list of Japanese lines that will be assembled into messages.
        index (int) : An updated int representing where we currently are in the text file.

        """

        prompt = []

        non_word_pattern = re.compile(r'^[\W_\s\n-]+$')
        alphanumeric_pattern = re.compile(r'^[A-Za-z0-9\s\.,\'\?!]+\n*$')

        while(index < len(Kijiku.text_to_translate)):

            sentence = Kijiku.text_to_translate[index]
            is_part_in_sentence = "part" in sentence.lower()

            if(len(prompt) < Kijiku.prompt_size):

                if(any(char in sentence for char in ["▼", "△", "◇"])):
                    prompt.append(sentence + '\n')
                    Logger.log_action("Sentence : " + sentence + ", Sentence is a pov change... leaving intact.")
                    index += 1

                elif(is_part_in_sentence or all(char in ["１","２","３","４","５","６","７","８","９", " "] for char in sentence) and not all(char in [" "] for char in sentence)):
                    prompt.append(sentence + '\n') 
                    Logger.log_action("Sentence : " + sentence + ", Sentence is part marker... leaving intact.")
                    index += 1

                elif(non_word_pattern.match(sentence) or KatakanaUtil.is_punctuation(sentence)):
                    Logger.log_action("Sentence : " + sentence + ", Sentence is punctuation... skipping.")
                    index += 1
                    
                elif(alphanumeric_pattern.match(sentence) and not is_part_in_sentence):
                    Logger.log_action("Sentence is empty... skipping translation.")
                    index += 1
                else:
                    prompt.append(sentence + "\n")
            else:
                return prompt, index

            index += 1

        return prompt, index
    
##-------------------start-of-build_translation_batches()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def build_translation_batches() -> None:

        """

        Builds translations batches dict for the API prompts.
        
        """

        i = 0

        while i < len(Kijiku.text_to_translate):
            prompt, i = Kijiku.generate_prompt(i)

            prompt = ''.join(prompt)

            ## message mode one structures the first message as a system message and the second message as a model message
            if(Kijiku.message_mode == 1):
                system_msg = SystemTranslationMessage(role="system", content=Kijiku.translation_instructions)

            ## while message mode two structures the first message as a model message and the second message as a model message too, typically used for non-gpt-4 models if at all
            else:
                system_msg = ModelTranslationMessage(role="user", content=Kijiku.translation_instructions)

            Kijiku.translation_batches.append(system_msg)

            model_msg = ModelTranslationMessage(role="user", content=prompt)

            Kijiku.translation_batches.append(model_msg)

        Logger.log_barrier()
        Logger.log_action("Built Messages : ")
        Logger.log_barrier()

        i = 0

        for message in Kijiku.translation_batches:

            i+=1

            if(i % 2 == 0):

                Logger.log_action(str(message))
        
            else:

                Logger.log_action(str(message))
                Logger.log_barrier()

##-------------------start-of-estimate_cost()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def estimate_cost(model:str, price_case:int | None = None) -> typing.Tuple[int, float, str]:

        """

        Attempts to estimate cost.

        Parameters:
        model (string) : the model used to translate the text.
        price_case (int) : the price case used to calculate the cost.

        Returns:
        num_tokens (int) : the number of tokens used.
        min_cost (float) : the minimum cost of translation.
        model (string) : the model used to translate the text.

        """
    
        assert model in FileEnsurer.allowed_models, f"""Kudasai does not support : {model}. See https://github.com/OpenAI/OpenAI-python/blob/main/chatml.md for information on how messages are converted to tokens."""

        ## default models are first, then the rest are sorted by price case
        if(price_case is None):

            if(model == "gpt-3.5-turbo"):
                print("Warning: gpt-3.5-turbo may change over time. Returning num tokens assuming gpt-3.5-turbo-1106 as it is the most recent version of gpt-3.5-turbo.")
                return Kijiku.estimate_cost("gpt-3.5-turbo-1106", price_case=2)
            
            elif(model == "gpt-4"):
                print("Warning: gpt-4 may change over time. Returning num tokens assuming gpt-4-1106-preview as it is the most recent version of gpt-4.")
                return Kijiku.estimate_cost("gpt-4-1106-preview", price_case=4)
            
            elif(model == "gpt-4-turbo-preview"):
                print("Warning: gpt-4-turbo-preview may change over time. Returning num tokens assuming gpt-4-0125-preview as it is the most recent version of gpt-4-turbo-preview.")
                return Kijiku.estimate_cost("gpt-4-0125-preview", price_case=4)
            
            elif(model == "gpt-3.5-turbo-0613"):
                print("Warning: gpt-3.5-turbo-0613 is considered depreciated by OpenAI as of November 6, 2023 and could be shutdown as early as June 13, 2024. Consider switching to gpt-3.5-turbo-1106.")
                return Kijiku.estimate_cost(model, price_case=1)

            elif(model == "gpt-3.5-turbo-0301"):
                print("Warning: gpt-3.5-turbo-0301 is considered depreciated by OpenAI as of June 13, 2023 and could be shutdown as early as June 13, 2024. Consider switching to gpt-3.5-turbo-1106 unless you are specifically trying to break the filter.")
                return Kijiku.estimate_cost(model, price_case=1)
            
            elif(model == "gpt-3.5-turbo-1106"):
                return Kijiku.estimate_cost(model, price_case=2)
            
            elif(model == "gpt-3.5-turbo-0125"):
                return Kijiku.estimate_cost(model, price_case=7)
            
            elif(model == "gpt-3.5-turbo-16k-0613"):
                print("Warning: gpt-3.5-turbo-16k-0613 is considered depreciated by OpenAI as of November 6, 2023 and could be shutdown as early as June 13, 2024. Consider switching to gpt-3.5-turbo-1106.")
                return Kijiku.estimate_cost(model, price_case=3)
            
            elif(model == "gpt-4-1106-preview"):
                return Kijiku.estimate_cost(model, price_case=4)
            
            elif(model == "gpt-4-0125-preview"):
                return Kijiku.estimate_cost(model, price_case=4)
            
            elif(model == "gpt-4-0314"):
                print("Warning: gpt-4-0314 is considered depreciated by OpenAI as of June 13, 2023 and could be shutdown as early as June 13, 2024. Consider switching to gpt-4-0613.")
                return Kijiku.estimate_cost(model, price_case=5)
            
            elif(model == "gpt-4-0613"):
                return Kijiku.estimate_cost(model, price_case=5)
            
            elif(model == "gpt-4-32k-0314"):
                print("Warning: gpt-4-32k-0314 is considered depreciated by OpenAI as of June 13, 2023 and could be shutdown as early as June 13, 2024. Consider switching to gpt-4-32k-0613.")
                return Kijiku.estimate_cost(model, price_case=6)
            
            elif(model == "gpt-4-32k-0613"):
                return Kijiku.estimate_cost(model, price_case=6)
            
        else:
            encoding = tiktoken.encoding_for_model(model)

            cost_per_thousand_input_tokens = 0
            cost_per_thousand_output_tokens = 0

            ## gpt-3.5-turbo-0301
            ## gpt-3.5-turbo-0613
            if(price_case == 1):
                cost_per_thousand_input_tokens = 0.0015
                cost_per_thousand_output_tokens = 0.0020

            ## gpt-3.5-turbo-1106
            elif(price_case == 2):
                cost_per_thousand_input_tokens = 0.0010
                cost_per_thousand_output_tokens = 0.0020

            ## gpt-3.5-turbo-16k-0613
            elif(price_case == 3):
                cost_per_thousand_input_tokens = 0.0030
                cost_per_thousand_output_tokens = 0.0040

            ## gpt-4-1106-preview
            ## gpt-4-0125-preview
            ## gpt-4-turbo-preview 
            elif(price_case == 4):
                cost_per_thousand_input_tokens = 0.01
                cost_per_thousand_output_tokens = 0.03

            ## gpt-4-0314
            ## gpt-4-0613
            elif(price_case == 5):
                cost_per_thousand_input_tokens = 0.03
                cost_per_thousand_output_tokens = 0.06

            ## gpt-4-32k-0314
            ## gpt-4-32k-0613
            elif(price_case == 6):
                cost_per_thousand_input_tokens = 0.06
                cost_per_thousand_output_tokens = 0.012

            ## gpt-3.5-turbo-0125
            elif(price_case == 7):
                cost_per_thousand_input_tokens = 0.0005
                cost_per_thousand_output_tokens = 0.0015

            ## break down the text into a string than into tokens
            text = ''.join(Kijiku.text_to_translate)

            num_tokens = len(encoding.encode(text))

            min_cost_for_input = round((float(num_tokens) / 1000.00) * cost_per_thousand_input_tokens, 5)
            min_cost_for_output = round((float(num_tokens) / 1000.00) * cost_per_thousand_output_tokens, 5)

            min_cost = round(min_cost_for_input + min_cost_for_output, 5)

            return num_tokens, min_cost, model
        
        raise Exception("An unknown error occurred while calculating the minimum cost of translation.")
    
##-------------------start-of-handle_cost_estimate_prompt()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    async def handle_cost_estimate_prompt(omit_prompt:bool=False) -> None:

        ## get cost estimate and confirm
        num_tokens, min_cost, Kijiku.model = Kijiku.estimate_cost(Kijiku.model)

        print("\nNote that the cost estimate is not always accurate, and may be higher than the actual cost. However cost calculation now includes output tokens.\n")

        Logger.log_barrier()
        Logger.log_action("Calculating cost")
        Logger.log_barrier()
        
        Logger.log_action("Estimated number of tokens : " + str(num_tokens), output=True, omit_timestamp=True)
        Logger.log_action("Estimated minimum cost : " + str(min_cost) + " USD", output=True, omit_timestamp=True)
        Logger.log_barrier()

        if(not omit_prompt):
            if(input("\nContinue? (1 for yes or 2 for no) : ") == "1"):
                Logger.log_action("User confirmed translation.")

            else:
                Logger.log_action("User cancelled translation.")
                exit()
    
##-------------------start-of-handle_translation()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    async def handle_translation(index:int, length:int, translation_instructions:SystemTranslationMessage | ModelTranslationMessage, translation_prompt:ModelTranslationMessage) -> tuple[int, ModelTranslationMessage, str]:

        """

        Handles the translation for a given system and user message.

        Parameters:
        index (int) : The index of the message in the original list.
        length (int) : The length of the original list.
        translation_instructions (object - SystemTranslationMessage | ModelTranslationMessage) : The system message also known as the instructions.
        translation_prompt (object - ModelTranslationMessage) : The user message also known as the prompt.
        
        Returns:\n
        index (int) : the index of the message in the original list.
        translation_prompt (object - ModelTranslationMessage) : the user message also known as the prompt.
        translated_message (str) : the translated message.

        """

        ## For the webgui
        if(FileEnsurer.do_interrupt == True):
            raise Exception("Interrupted by user.")

        ## Basically limits the number of concurrent batches
        async with Kijiku._semaphore:
            num_tries = 0

            while True:
            
                message_number = (index // 2) + 1
                Logger.log_action(f"Trying translation for batch {message_number} of {length//2}...", output=True)


                try:
                    translated_message = await OpenAIService.translate_message(translation_instructions, translation_prompt)

                ## will only occur if the max_batch_duration is exceeded, so we just return the untranslated text
                except MaxBatchDurationExceededException:
                    translated_message = translation_prompt["content"]
                    Logger.log_error(f"Batch {message_number} of {length//2} was not translated due to exceeding the max request duration, returning the untranslated text...", output=True)
                    break

                ## do not even bother if not a gpt 4 model, because gpt-3 seems unable to format properly
                if("gpt-4" not in Kijiku.model):
                    break

                if(await Kijiku.check_if_translation_is_good(translated_message, translation_prompt)):
                    Logger.log_action(f"Translation for batch {message_number} of {length//2} successful!", output=True)
                    break

                if(num_tries >= Kijiku.num_of_malform_retries):
                    Logger.log_action(f"Batch {message_number} of {length//2} was malformed, but exceeded the maximum number of retries, Translation successful!", output=True)
                    break

                else:
                    num_tries += 1
                    Logger.log_error(f"Batch {message_number} of {length//2} was malformed, retrying...", output=True)
                    Kijiku.num_occurred_malformed_batches += 1

            return index, translation_prompt, translated_message
    
##-------------------start-of-check_if_translation_is_good()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    async def check_if_translation_is_good(translated_message:str, translation_prompt:ModelTranslationMessage) -> bool:

        """
        
        Checks if the translation is good, i.e. the number of lines in the prompt and the number of lines in the translated message are the same.

        Parameters:
        translated_message (string) : the translated message.
        translation_prompt (object - ModelTranslationMessage) : the user message also known as the prompt.

        Returns:
        is_valid (bool) : whether or not the translation is valid.

        """

        prompt = translation_prompt["content"]
        is_valid = False

        jap = [line for line in prompt.split('\n') if line.strip()]  ## Remove blank lines
        eng = [line for line in translated_message.split('\n') if line.strip()]  ## Remove blank lines

        if(len(jap) == len(eng)):
            is_valid = True
    
        return is_valid
    
##-------------------start-of-redistribute()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def redistribute(translation_prompt:dict, translated_message:str) -> None:

        """

        Puts translated text back into the text file.

        Parameters:
        translation_prompt (dict) : the user message also known as the prompt.
        translated_message (string) : the translated message.

        """

        ## Separates with hyphens if the mode is 1 
        if(Kijiku.je_check_mode == 1):
            Kijiku.je_check_text.append("\n-------------------------\n"+ str(translation_prompt["content"]) + "\n\n")
            Kijiku.je_check_text.append(translated_message + '\n')
        
        ## Mode two tries to pair the text for j-e checking, see fix_je() for more details
        elif(Kijiku.je_check_mode == 2):
            Kijiku.je_check_text.append(str(translation_prompt["content"]))
            Kijiku.je_check_text.append(translated_message)

        ## mode 1 is the default mode, uses regex and other nonsense to split sentences
        if(Kijiku.sentence_fragmenter_mode == 1): 

            sentences = re.findall(r"(.*?(?:(?:\"|\'|-|~|!|\?|%|\(|\)|\.\.\.|\.|---|\[|\])))(?:\s|$)", translated_message)

            patched_sentences = []
            build_string = None

            for sentence in sentences:
                if(sentence.startswith("\"") and not sentence.endswith("\"") and build_string is None):
                    build_string = sentence
                    continue
                elif(not sentence.startswith("\"") and sentence.endswith("\"") and build_string is not None):
                    build_string += f" {sentence}"
                    patched_sentences.append(build_string)
                    build_string = None
                    continue
                elif(build_string is not None):
                    build_string += f" {sentence}"
                    continue

                Kijiku.translated_text.append(sentence + '\n')

            for i in range(len(Kijiku.translated_text)):
                if Kijiku.translated_text[i] in patched_sentences:
                    index = patched_sentences.index(Kijiku.translated_text[i])
                    Kijiku.translated_text[i] = patched_sentences[index]

        ## mode 2 uses spacy to split sentences (deprecated, will do 3 instead)
        ## mode 3 just assumes gpt formatted it properly
        elif(Kijiku.sentence_fragmenter_mode == 2 or Kijiku.sentence_fragmenter_mode == 3): 
            
            Kijiku.translated_text.append(translated_message + '\n\n')
        
##-------------------start-of-fix_je()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def fix_je() -> typing.List[str]:

        """

        Fixes the J->E text to be more j-e check friendly.

        Note that fix_je() is not always accurate, and may use standard j-e formatting instead of the corrected formatting.

        Returns:
        final_list (list - str) : the 'fixed' J->E text.

        """
        
        i = 1
        final_list = []

        while i < len(Kijiku.je_check_text):
            jap = Kijiku.je_check_text[i-1].split('\n')
            eng = Kijiku.je_check_text[i].split('\n')

            jap = [line for line in jap if line.strip()]  ## Remove blank lines
            eng = [line for line in eng if line.strip()]  ## Remove blank lines    

            final_list.append("-------------------------\n")

            if(len(jap) == len(eng)):

                for jap_line,eng_line in zip(jap,eng):
                    if(jap_line and eng_line): ## check if jap_line and eng_line aren't blank
                        final_list.append(jap_line + '\n\n')
                        final_list.append(eng_line + '\n\n')

                        final_list.append("--------------------------------------------------\n")
     

            else:

                final_list.append(Kijiku.je_check_text[i-1] + '\n\n')
                final_list.append(Kijiku.je_check_text[i] + '\n\n')

                final_list.append("--------------------------------------------------\n")

            i+=2

        return final_list

##-------------------start-of-assemble_results()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    
    @staticmethod
    def assemble_results(time_start:float, time_end:float) -> None:

        """

        Outputs results to a string.

        Parameters:
        time_start (float) : When the translation started.
        time_end (float) : When the translation finished.

        """

        Kijiku.translation_print_result += "Time Elapsed : " + Toolkit.get_elapsed_time(time_start, time_end)
        Kijiku.translation_print_result += "\nNumber of malformed batches : " + str(Kijiku.num_occurred_malformed_batches)

        Kijiku.translation_print_result += "\n\nDebug text have been written to : " + FileEnsurer.debug_log_path
        Kijiku.translation_print_result += "\nJ->E text have been written to : " + FileEnsurer.je_check_path
        Kijiku.translation_print_result += "\nTranslated text has been written to : " + FileEnsurer.translated_text_path
        Kijiku.translation_print_result += "\nErrors have been written to : " + FileEnsurer.error_log_path + "\n"

##-------------------start-of-write_kijiku_results()---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    @permission_error_decorator()
    def write_kijiku_results() -> None:

        """
        
        This function is called to write the results of the Kijiku translation module to the output directory.

        """

        ## ensures the output directory exists, cause it could get moved or fucked with.
        FileEnsurer.standard_create_directory(FileEnsurer.output_dir)

        with open(FileEnsurer.error_log_path, 'a+', encoding='utf-8') as file:
            file.writelines(Kijiku.error_text)

        with open(FileEnsurer.je_check_path, 'w', encoding='utf-8') as file:
            file.writelines(Kijiku.je_check_text)

        with open(FileEnsurer.translated_text_path, 'w', encoding='utf-8') as file:
            file.writelines(Kijiku.translated_text)

        ## Instructions to create a copy of the output for archival
        FileEnsurer.standard_create_directory(FileEnsurer.archive_dir)

        timestamp = Toolkit.get_timestamp(is_archival=True)

        ## pushes the tl debug log to the file without clearing the file
        Logger.push_batch()
        Logger.clear_batch()

        list_of_result_tuples = [('kijiku_translated_text', Kijiku.translated_text), 
                                 ('kijiku_je_check_text', Kijiku.je_check_text), 
                                 ('kijiku_error_log', Kijiku.error_text),
                                 ('debug_log', FileEnsurer.standard_read_file(Logger.log_file_path))]

        FileEnsurer.archive_results(list_of_result_tuples, 
                                    module='kijiku', timestamp=timestamp)
