'''
Created on 23.10.2019

@author: tobias
'''
import urllib
import requests
import threading
from os.path import sys
import os
import subprocess
from threading import Event

class TextToSpeech(object):
    '''
    ...not really threadsafe!
    '''


    def __init__(self, config, coordinator):
        self.coordinator = coordinator
        self.logger = config.logger
        self.config = config
        self.apiKey = config.tts_api_key
        coordinator.textToSpeech = self
        self.proc = None
        self.interrupted = False
        self.downloadEvent = Event()
        
    def _playOgg(self, file):
        cmd = "ogg123 -q -d alsa -o dev:'plug:dmix' " + file
        self.logger.info("TextToSpeech: calling '%s'" % cmd)
        self.proc = subprocess.Popen([cmd], shell=True)
        try:
            self.proc.wait(10.0)
        except:
            pass
        
    ''' this is the only method that might be called from another thread! '''
    def interruptSpeech(self):
        self.logger.info("TextToSpeech: interrupting")
        self.interrupted = True
        self.downloadEvent.set() # stop waiting for download
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(3.0)
            except:
                self.logger.error("TextToSpeech: thread did not terminate!")
                pass
        self.interrupted = False
        
    ''' always call this from the same thread! '''
    def speak(self, text, lang):
        self.logger.info("Speak: '%s'" % text)
        textEncoded = urllib.parse.quote(text, safe='')
        
        cacheUrl = self._get_from_cache(textEncoded, lang)
        
        if cacheUrl is not None and self.interrupted is False:
            self._playOgg(cacheUrl)
        
    def _get_from_cache(self, filename, lang):
        try:
            cacheFile = self.config.tts_cache_dir + "/" + lang + "." + filename + ".ogg"
            if os.path.isfile(cacheFile):
                self.logger.debug("Cache hit for file '%s'" % filename)
            else:
                self.logger.debug("Cache miss for file '%s'" % filename)
                
                url = 'https://api.voicerss.org/?key=' + self.apiKey + '&hl=' + lang + \
                '&c=OGG&f=44khz_16bit_mono&src=' + filename
                
                self.downloadEvent.clear()
                t = threading.Thread(target = lambda: self._download_file(url, cacheFile), name = "TTS_download_thread")
                t.start()
                if not self.downloadEvent.wait(3.0):
                    self.logger.warn("Timeout waiting for download")
            return cacheFile
        except:
            self.logger.error("Exception while searching cache for '%s'" % (filename))
            return None
    
    def _download_file(self, url, cacheFile):
        try:
            target = cacheFile + ".tmp"
            f = open(target, 'w+b')
            r = requests.get(url)
            self.logger.debug("Got status code '%i'" % r.status_code)
            if r.status_code < 200 or r.status_code > 299:
                self.logger.warning("Error getting file '%s': Status code %i" % (url, r.status_code))
                return False
            bytesRead = f.write(r.content)
            if bytesRead > 0:
                self.logger.info("Downloaded %i bytes to '%s'" % (bytesRead, target))
            else:
                self.logger.error("Error writing data to file: %i" % bytesRead)
            f.close()
            os.rename(target, cacheFile)
            return True
        except:
            self.logger.error("Exception while downloading/saving file '%s' to '%s': '%s'" % (url, target, sys.exc_info()[0]))
            return False
        finally:
            self.downloadEvent.set()
    