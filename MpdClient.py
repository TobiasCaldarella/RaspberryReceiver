'''
Created on 08.08.2019

@author: tobias
'''

from mpd import MPDClient
import sys
import threading
import time

class _connection:
    def __init__(self, parent):
        self.parent = parent
    def __enter__(self):
        try:
            self.parent.client.ping()
        except:
            self.parent.connect()
    def __exit__(self, type, value, traceback):
        self.parent.disconnect()
        #return True # do not throw any exceptions from here... but we need logging!

class MpdClientEventListener(object):
    def __init__(self, config, coordinator):
        self.config = config
        self.coordinator = coordinator
        self.listen = True
        self.listenerThread = threading.Thread(target=self.do_listen)
        self.client = MPDClient()
        self.client.idletimeout = 60
        
    def connect(self):
        try:
            self.client.connect("127.0.0.1", 6600)
        except:
            self.config.logger.warn("MpdClientEventListener.connect() failed: '%s'" % (sys.exc_info()[0]))
    
    def disconnect(self):
        try:
            self.client.close()
        except:
            self.config.logger.warn("Exception during MpdClientEventListener.close(): '%s'" % (sys.exc_info()[0])) 
        try:
            self.client.disconnect()
        except:
            self.config.logger.warn("Exception during MpdClientEventListener.disconnect(): '%s'" % (sys.exc_info()[0])) 
            
    def do_listen(self):
        while self.listen is True:
            try:
                self.config.logger.debug("getting mpd player status...")
                stat = self.client.status()
                if 'bitrate' in stat and int(stat['bitrate']) > 0:
                    # currently streaming
                    self.config.logger.info("MPD playing")
                    self.coordinator.currentlyPlaying(True)
                else:
                    self.config.logger.info("MPD not playing")
                self.config.logger.debug("waiting for mpd player status update...")
                self.client.idle('player') # todo: catch exception here!
            except:
                self.config.logger.debug("idle/status failed, will try again")
                self.disconnect()
                self.connect()
                time.sleep(1)
    
    def startListener(self):
        self.listenerThread.start()


class MpdClient(object):
    '''
    classdocs
    '''
    def __init__(self, config, coordinator):
        '''
        Constructor
        '''
        client = MPDClient()
        client.idletimeout = 1
        self.client = client
        self.config = config
        self.connection = _connection(self)
        self.coordinator = coordinator
        if coordinator is not None:
            coordinator.mpdClient = self
        self.listener = MpdClientEventListener(config, coordinator)
        self.listener.startListener()
        
    def connect(self):
        self.client.connect("127.0.0.1", 6600)
    
    def disconnect(self):
        try:
            self.client.close()
        except:
            self.config.logger.warn("Exception during MpdClient.close(): '%s'" % (sys.exc_info()[0])) 
        try:
            self.client.disconnect()
        except:
            self.config.logger.warn("Exception during MpdClient.disconnect(): '%s'" % (sys.exc_info()[0])) 
    
    def getNumTracksInRadioPlaylist(self):
        with self.connection:
            pl = self.client.playlistinfo()
            return len(pl)
    
    def loadPlaylist(self):
        self.config.logger.debug("loading playlist '%s'" % (self.config.mpd_radio_playlist))
        try:
            with self.connection:
                self.client.clear()
                self.client.load(self.config.mpd_radio_playlist)
                return True
        except:
            self.config.logger.error("Error loading mpd playlist!") 
            # todo: signal errors to coordinator
            return False
        
    def playTitle(self, title):
        self.coordinator.currentlyPlaying(False)
        with self.connection:
            self.client.play(title)                
        
    def stop(self):
        with self.connection:
            self.client.stop()
            self.coordinator.currentlyPlaying(False)
            
    