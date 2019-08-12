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

class MpdClientEventListener(object):
    def __init__(self, config, coordinator):
        self.config = config
        self.coordinator = coordinator
        self.listen = True
        self.listenerThread = threading.Thread(target=self.do_listen)
        self.client = MPDClient()
        #self.client.idletimeout = 1
        
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
                if ('bitrate' in stat and int(stat['bitrate']) > 0) or ('elapsed' in stat and float(stat['elapsed']) > 0):
                    # currently streaming
                    currentSongId = int(stat['song'])
                    currentVolume = int(stat['volume'])
                    currentSongInfo = self.client.currentsong()
                    self.config.logger.info("MPD playing track %i" % currentSongId)
                    if self.coordinator:
                        self.coordinator.currentlyPlaying(True, currentSongId, currentVolume, currentSongInfo)
                else:
                    self.config.logger.info("MPD not playing")
                    if self.coordinator:
                        self.coordinator.currentlyPlaying(False)
                        
                self.config.logger.debug("waiting for next mpd player status update...")
                try:
                    self.client.idle()
                except:
                    self.config.logger.debug("Exception during idle()")
            except:
                self.config.logger.debug("mpd.status() failed, will try again")
                self.disconnect()
                self.connect()
                time.sleep(1)
    
    def startListener(self):
        self.connect()
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
        #try:
        #    self.client.close()
        #except:
        #    self.config.logger.warn("Exception during MpdClient.close(): '%s'" % (sys.exc_info()[0])) 
        try:
            self.client.disconnect()
        except:
            self.config.logger.warn("Exception during MpdClient.disconnect(): '%s'" % (sys.exc_info()[0])) 
    
    def getNumTracksInPlaylist(self):
        with self.connection:
            pl = self.client.playlistinfo()
            return len(pl)
    
    def loadRadioPlaylist(self):
        self.config.logger.debug("loading playlist '%s'" % (self.config.mpd_radio_playlist))
        try:
            with self.connection:
                self.client.clear()
                self.client.load(self.config.mpd_radio_playlist)
                self.client.single(1)
                return True
        except:
            self.config.logger.error("Error loading mpd playlist!") 
            # todo: signal errors to coordinator
            return False
        
    def playTitle(self, title):
        self.coordinator.currentlyPlaying(False)
        with self.connection:
            self.client.send_play(title)                
        
    def stop(self):
        with self.connection:
            self.client.send_stop()
            self.coordinator.currentlyPlaying(False)
            
    def volumeUp(self):
        with self.connection:
            stat = self.client.state()
            vol = stat['volume']
            vol+=10
            if vol > 100:
                vol = 100
            self.client.send_setVol(vol)
        
    def volumeDown(self):
        with self.connection:
            stat = self.client.state()
            vol = stat['volume']
            vol-=10
            if vol < 0:
                vol = 0
            self.client.send_setVol(vol)
            pass
    
