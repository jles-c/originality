import requests
from bs4 import BeautifulSoup
from collections.abc import MutableMapping
import concurrent.futures
from concurrent.futures import as_completed
import streamlit as st
from streamlit.web.server.websocket_headers import _get_websocket_headers
import pandas as pd
import yaml
import os
import time


class Originality:
    def __init__(self):
        self.logged = False

        HERE = os.path.realpath(os.path.dirname(__file__))
        CONFIG_PATH = os.path.join(HERE,f"config_files/settings.yaml",)

        # with open(CONFIG_PATH,"r",) as ymlfile:
        with open("config_files/settings.yaml","r",) as ymlfile:
                    self.settings = yaml.safe_load(ymlfile)
                    

        self.API_KEY = self.settings['API_KEY']
        self.API_URL = self.settings['API_URL']

    def login(self, api_key, st):
        if self.logged:
            st.write(f":green[Already logged in]")
        
        else:
            st.write("Testing API key...")
            self.API_KEY = api_key
            self.get_credit_balance()
        
            if self.status > 200:
                st.write(f":red[Login failed] : {self.api_result}")
                self.API_KEY = ""
                self.logged = False
            else:
                self.logged = True
                st.write(f":green[Login complete]. Current balance : {self.api_result['balance']}")

        return self.logged    
    
    def test_login(self, *args, **kargs):
        print(args, kargs)
        return args, kargs
               
    def _api_headers(self, api_key):
        return {
            'Accept': 'application/json',
            'X-OAI-API-KEY': api_key,
            'Content-Type': 'application/json'
            }
    
    def get_credit_balance(self):
        url = self._build_api_url('account/credits/balance')
        self.API_HEADERS = self._api_headers(self.API_KEY)
        response = requests.get(url, headers=self.API_HEADERS)
        self.status, self.api_result, _ = self._get_api_result(response)
        return self.status, self.api_result

    def get_credit_usage(self):
        url = self._build_api_url('account/credits/content_scan_usage')
        self.API_HEADERS = self._api_headers()
        response = requests.get(url, headers=self.API_HEADERS)
        self.status, self.api_result, _ = self._get_api_result(response)
        return self.status, self.api_result

    def _build_api_url(self, endpoint):
        return '/'.join([self.API_URL, endpoint])  
    
    def _get_api_result(self, response):
        status = response.status_code
        res_json = response.json()
        if status == 200:
            api_result = res_json
        else:
            api_result = res_json['error']
        
        return status, api_result, res_json      
 
class Plagiarism(Originality):
    def __init__(self):
        super().__init__()
        
        self.MAX_WORKERS = self.settings['MAX_WORKERS']
        self.NB_WORDS = self.settings['NB_WORDS']
        self.MIN_WORDS_COUNT = self.settings['MIN_WORDS_COUNT']
        self.aiModelVersion = self.settings['aiModelVersion']
        self.CSV_COLUMNS = self.settings['CSV_COLUMNS']
        
        self.status_list = []
        self.api_result_list = []
        
        if not self.logged:
            print("Not logged. Please log in.")
        

    def get_text_from_url(self, url, nb_words):
        """
        Extracts text content from a given URL and returns the concatenated text until the specified number of words is reached.

        Args:
            url (str): The URL of the webpage to extract text from.
            nb_words (int): The maximum number of words to include in the output text.

        Returns:
            str: The concatenated text from the webpage, truncated to contain at most 'nb_words' words.

        Note:
            - The function makes use of the 'requests' library and 'BeautifulSoup' to fetch and parse the webpage content.
            - HTML tags' text that exactly matches another tag's text is excluded.
            - Tags' text with a word count less than or equal to Plagiarism.MIN_WORDS_COUNT (default to 3) is excluded.
        """
        
        text_split = []
        words_split = []
        self.url = url
        headers={
            "User-Agent" : "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.55 Safari/537.36",
            "referer" : "https://www.google.com/",
            "Accept-Language" : "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7,es;q=0.6",
            "Accept_Encoding" : "gzip, deflate, br",
            "Accept" : "*/*"
            }
        res = requests.get(url, headers = headers)
        soup = BeautifulSoup(res.content, 'html.parser')
        soup_text = soup.get_text(separator="||", strip=True)
        soup_split = soup_text.split("||")

        for text in soup_split:
            if text in text_split:  # Exclude tags's text if it matches exactly with another one
                continue
            elif len(text.split()) <= self.MIN_WORDS_COUNT:  # Exclude tags' text if it's too short
                continue
            else:
                text_split.append(text)
                words_split.extend(text.split())
                if len(words_split) >= nb_words:
                    break

        self.text = clean_text = " ".join(text_split)
        return clean_text

    def get_plagiarism_from_url(self, url, title, aiModelVersion):

        text = self.get_text_from_url(url = url, nb_words = self.NB_WORDS)

        # Call the originality.ai API
        url_api = self._build_api_url('scan/plag')
        api_headers = self._api_headers(self.API_KEY)
        payload = {
            "content": text,
            "aiModelVersion": aiModelVersion
        }
        
        if title:
            self.title = payload['title'] = title

        response = requests.post(url_api, headers=api_headers, json=payload)
        status, api_result, _ = self._get_api_result(response)
        self.status_list.append(status)
        self.api_result_list.append(api_result)
        
        return status, api_result
    
    def get_plagiarism_from_urls(self, urls, st):
        summaries = []
        all_matchs = []
        if not urls:
            st.write(f':red[Please upload urls]')
            return
        for url in urls:
            
            status, api_result = self.get_plagiarism_from_url(url, title = url, aiModelVersion = self.aiModelVersion, st = st)
            st.write(f'Done, {status}, {url}')

            if status == 200:
                summary, matchs = self.process_result(api_result)
                summaries.append(summary)
                all_matchs.extend(matchs)
            
        
        self.summaries = summaries
        self.all_matchs = all_matchs

        return summaries, all_matchs
    
    def get_plagiarism_from_urls_concurrent(self, urls, st):
        start = time.time()
        summaries = []
        all_matchs = []
        if not urls:
            st.write(f':red[Please upload urls]')
            return
        
        with concurrent.futures.ThreadPoolExecutor(max_workers = self.MAX_WORKERS) as executor:
        
                # submit tasks and collect futures
                futures = [executor.submit(self.get_plagiarism_from_url, url = url, title = url, aiModelVersion = self.aiModelVersion) for url in urls]
                # process task results as they are available
                for future in as_completed(futures):
                # retrieve the result
                    future.result()
        
                for status, api_result in zip(self.status_list, self.api_result_list):
                    if status == 200:
                        summary, matchs = self.process_result(api_result)
                        summaries.append(summary)
                        all_matchs.extend(matchs)
                
        
        self.summaries = summaries
        self.all_matchs = all_matchs

        end = time.time()
        self.duration = duration = end - start
        return summaries, all_matchs, duration
    
    def process_result(self, api_result):
        matchs = []
        summary = {k:v for k,v in api_result.items() if k not in ['results', 'readability']}

        for p_ind,plag in enumerate(api_result['results'], start = 1):
            
            for m_ind, matched in enumerate(plag['matches'], start =1):

                details = {
                    'title':api_result['title'],
                    'phrase_ind':p_ind,
                    'match_ind':m_ind,
                    'score':matched['score'],
                    'phrase':plag['phrase'],
                    'pText':matched['pText'],
                    'website':matched['website'],
                }
                matchs.append(details)
        
        return summary, matchs

    def load_urls_from_csv(self,file):
        df = pd.read_csv(file)
        cols = df.columns.to_list()
        urls = []
        check = False
        
        if cols == self.CSV_COLUMNS:
            check = True
            for col in self.CSV_COLUMNS:
                urls = df[col].to_list()
                break
        
        return check, cols, urls
            
def reset_session_state_value(session_state_key, value ):
    st.session_state[session_state_key] = value

# Adjust layout to remove padding
st.markdown("""
        <style>
               .block-container {
                    padding-top: 0rem;
                    padding-bottom: 0rem;
                    padding-left: 0rem;
                    padding-right: 0rem;
                }
               .css-1y4p8pa {
                    width: 90%;
                    padding: 6rem 1rem 10rem;
                    max-width: 100%;
                }
        </style>
        """, unsafe_allow_html=True)

if 'plag' not in st.session_state:
    st.session_state['plag'] = Plagiarism()

plag = st.session_state['plag']


# st.write(_get_websocket_headers())

with st.sidebar:
    st.title(':robot_face: :violet[Plagiarism] for SEO :robot_face:')
    st.write(f'streamlit version : {st.__version__}')
    st.divider()

    API_KEY = st.session_state['API_KEY'] = st.text_input('**API KEY**')
    if API_KEY:
        login_disabled = False
    else:
        login_disabled = True

    if plag.logged:
        scan_disabled = False
    else:
        scan_disabled = True
    
    cols_top = st.columns([1,3])
    cols_bot = st.columns(1)
    with cols_top[0]:
        st.button('Log in', on_click = plag.login, args = [API_KEY,cols_bot[0]], disabled=login_disabled)
    with cols_top[1]:
        st.markdown(f"logged : **{plag.logged}**")

    st.divider()

    uploaded_file = st.file_uploader('**Upload urls csv**', type='csv', help="Only one column named 'url'")
    if uploaded_file:
        check_file, cols, urls = plag.load_urls_from_csv(uploaded_file)
        
        if check_file:
            st.markdown(":green[File uploaded correctly!]")
        else:
            st.markdown(f":red[File not valid!]")
            st.markdown(f"Columns in file : {cols}")
            st.markdown(f"Columns needed : ['urls']")
    else:
        urls = []

st.header("Plagiarism scan")
st.caption("Using urls from csv file")

cols_main_top = st.columns([2,2,4])
cols_main_top[1].button("Reset plagiarism value", on_click=reset_session_state_value, args = ['plag', Plagiarism()])
plag.NB_WORDS = cols_main_top[2].slider("Nb words :", min_value = 100, max_value = 4000, value = plag.NB_WORDS, step = 50)
cols_main_top[2].write(plag.NB_WORDS)
st.divider()

download_container = st.container()
donwload_cols_top = download_container.columns(1)
donwload_cols_bot = download_container.columns([1,5])

tab1, tab2, tab3, tab4 = st.tabs([':file_folder: URLs', ':pushpin: Summary per url', ':mag_right: All matchs', ':gear: Logs'])
# tab1, tab2, tab3 = st.tabs([':file_folder: URLs', ':pushpin: Summary per url', ':mag_right: All matchs'])

if urls:
    urls = tab1.data_editor(
        urls, 
        num_rows = 'dynamic', 
        # hide_index = False, 
        use_container_width = True,
        column_config={
        "value": st.column_config.LinkColumn(
            "url",
            help="Urls to scan for plagiarism. You can edit, delete (check box on the left), or add ('+' below) urls",
            validate="^https://.*",
            max_chars=100,)
            }
        )
    
    tab1.write(urls)
else:
    tab1.caption('Upload urls to see them here')

if 'summaries' in plag.__dict__:
    summary_df = pd.DataFrame.from_records(plag.summaries)
    donwload_cols_bot[0].download_button("Download summary", data = summary_df.to_csv(), file_name = 'summary.csv')
    tab2.write(summary_df)
else:
    tab2.subheader('Nothing here ... :eyes: ')

if 'all_matchs' in plag.__dict__:
    matches_df = pd.DataFrame.from_records(plag.all_matchs)
    donwload_cols_bot[1].download_button("Download matches", data = matches_df.to_csv(), file_name = 'matches.csv')
    tab3.write(matches_df)
else:
    tab3.subheader('Nothing here ... :eyes: ')


cols_main_top[0].button("scan", on_click=plag.get_plagiarism_from_urls, args = [urls, tab4], disabled=scan_disabled)
cols_main_top[0].button("scan (fast)", on_click=plag.get_plagiarism_from_urls_concurrent, args = [urls, cols_main_top[0]], disabled=scan_disabled)

if 'duration' in plag.__dict__:
    cols_main_top[0].write(f'duration : {round(plag.duration)} secs')

