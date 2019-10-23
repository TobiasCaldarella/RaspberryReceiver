'''
Created on 23.10.2019

@author: tobias
'''
import urllib

class TextToSpeech(object):
    '''
    classdocs
    '''


    def __init__(self, config, coordinator):
        self.coordinator = coordinator
        self.logger = config.logger
        self.apiKey = config.tts_api_key
        coordinator.textToSpeech = self
        
    def speak(self, text, lang):
        self.logger.info("Speak: '%s'" % text)
        textEncoded = urllib.parse.quote(text, safe='')
        url = 'https://api.voicerss.org/?key=' + self.apiKey + '&hl=' + lang + \
            '&c=OGG&f=44khz_16bit_mono&src=' + textEncoded
        self.coordinator.playSingleFile(url)
        