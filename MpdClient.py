'''
Created on 08.08.2019

@author: tobias
'''

from mpd import MPDClient
import sys
import threading

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
        
    def connect(self):
        self.client.connect("127.0.0.1", 6600)
    
    def disconnect(self):
        try:
            self.listen = False
            self.client.close()
            self.client.disconnect()
        except:
            self.config.logger.warn("Exception during MpdClient.disconnect(): %s" % (sys.exc_info()[0])) 
    
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
            for i in range(10):
                self.config.logger.debug("waiting for mpd status update...")
                try:
                    self.client.idle('player')
                    stat = self.client.status()
                    if 'bitrate' in stat and int(stat['bitrate']) > 0:
                        # currently streaming
                        self.config.logger.info("MPD playing")
                        self.coordinator.currentlyPlaying(True)
                        break
                    else:
                        self.config.logger.info("MPD not playing")
                except:
                    self.config.logger.debug("idle/status failed, will try again")
                    self.disconnect()
                    self.connect()
                    continue
                
        
    def stop(self):
        with self.connection:
            self.client.stop()
            self.coordinator.currentlyPlaying(False)
            
    