'''
Created on 23.10.2019

@author: tobias
'''
import urllib
import requests
import threading
from os.path import sys
import os
from keyrings.alt import file

class TextToSpeech(object):
    '''
    classdocs
    '''


    def __init__(self, config, coordinator):
        self.coordinator = coordinator
        self.logger = config.logger
        self.config = config
        self.apiKey = config.tts_api_key
        coordinator.textToSpeech = self
        self.lock = threading.Lock()
        
    def playOgg(self, file):
        cmd = "ogg123 -d alsa -o dev:'plug:dmix' " + file
        self.logger.info("TextToSpeech: calling '%s'" % cmd)
        os.system(cmd)
    
    def speak(self, text, lang, mute=True):
        with self.lock:
            self.logger.info("Speak: '%s'" % text)
            textEncoded = urllib.parse.quote(text, safe='')
            cacheUrl = self._get_from_cache(textEncoded, lang)
            if cacheUrl is not None:
                if mute:
                    self.coordinator.mute(mute=True)
                self.playOgg(cacheUrl)
                if mute:
                    self.coordinator.mute(mute=False)
        
    def _get_from_cache(self, filename, lang):
        try:
            cacheFile = self.config.tts_cache_dir + "/" + lang + "." + filename + "." + ".ogg"
            if os.path.isfile(cacheFile):
                self.logger.debug("Cache hit for file '%s'" % filename)
            else:
                self.logger.debug("Cache miss for file '%s'" % filename)
                
                url = 'https://api.voicerss.org/?key=' + self.apiKey + '&hl=' + lang + \
                '&c=OGG&f=44khz_16bit_mono&src=' + filename
                
                self._download_file(url, cacheFile)
            return cacheFile
        except:
            self.logger.error("Exception while searching cache for '%s'" % (filename))
            return None
    
    def _download_file(self, url, cacheFile):
        try:
            target = cacheFile
            f = open(target, 'x+b')
            r = requests.get(url)
            self.logger.debug("Got status code '%i'" % r.status_code)
            if r.status_code < 200 or r.status_code > 299:
                self.logger.warning("Error getting file '%s': Status code %i" % (url, r.status_code))
                return False
            bytesRead = f.write(r.content)
            if bytesRead > 0:
                self.logger.debug("Wrote %i byes" % bytesRead)
            else:
                self.logger.error("Error writing data to file: %i" % bytesRead)
            f.close()
            return True
            
        except:
            self.logger.error("Exception while downloading/saving file '%s' to '%s': '%s'" % (url, target, sys.exc_info()[0]))
            return False