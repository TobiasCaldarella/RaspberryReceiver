'''
Created on 08.08.2019

@author: tobias
'''

from mpd import MPDClient
import sys
import threading
import time
import json

class _connection:
    def __init__(self, parent):
        self.parent = parent
    def __enter__(self):
        try:
            self.parent.client.ping()
        except:
            try:
                self.parent.disconnect()
            except:
                pass
            self.parent.connect()
    def __exit__(self, type, value, traceback):
        pass

class MpdClientEventListener(object):
    def __init__(self, config, coordinator):
        self.config = config
        self.coordinator = coordinator
        self.listen = True
        self.listenerThread = threading.Thread(target=self.do_listen)
        self.client = MPDClient()
        
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
            #try:
                self.config.logger.debug("getting mpd player status...")
                stat = self.client.status()
                playing = False
                currentSongInfo = None
                while ('state' in stat) and (stat['state'] == 'play'):
                    # mpd wants to play but maybe waits for stream to start, we have to poll
                    if ('bitrate' in stat and int(stat['bitrate']) > 0) or ('elapsed' in stat and float(stat['elapsed']) > 0):
                        # currently streaming
                        currentSongInfo = self.client.currentsong()
                        self.config.logger.info("MPD playing %s" % json.dumps(currentSongInfo))
                        playing = True
                        break # can go and idle
                    else:
                        self.config.logger.debug("MPD not streaming (yet?)")
                        time.sleep(0.1)
                        stat = self.client.status()
                
                if ('state' not in stat) or (stat['state'] != 'play'):
                    self.config.logger.info("MPD not playing")
                
                if self.coordinator:
                    currentSongId = None
                    currentVolume = None
                    if 'song' in stat:
                        currentSongId = int(stat['song'])
                    if 'volume' in stat:
                        currentVolume = int(stat['volume'])
                    self.coordinator.currentlyPlaying(playing, currentSongId, currentVolume, currentSongInfo)
                        
                try:
                    self.config.logger.debug("waiting for next mpd player status update...")
                    self.client.idle()
                except:
                    self.config.logger.debug("Exception during idle()")
            #except:
                #self.config.logger.debug("Could not get status from MPD, will reconnect")
                #self.disconnect()
                #time.sleep(1)
                #self.connect()
    
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
        self.logger = config.logger
        self.connection = _connection(self)
        self.coordinator = coordinator
        if coordinator is not None:
            coordinator.mpdClient = self
        self.listener = MpdClientEventListener(config, coordinator)
        self.listener.startListener()
        
    def connect(self):
        try:
            self.client.connect("127.0.0.1", 6600)
            return True
        except:
            self.logger.error("Caught exception in MpdClient.connct(): '%s'" % (sys.exc_info()[0]))
            return False
    
    def disconnect(self):
        #try:
        #    self.client.close()
        #except:
        #    self.config.logger.warn("Exception during MpdClient.close(): '%s'" % (sys.exc_info()[0])) 
        try:
            self.client.disconnect()
            return True
        except:
            self.logger.warn("Exception during MpdClient.disconnect(): '%s'" % (sys.exc_info()[0])) 
            return False
    
    def getNumTracksInPlaylist(self):
        with self.connection:
            try:
                pl = self.client.playlistinfo()
                return len(pl)
            except:
                self.logger.error("Caught exception in MpdClient.pubInfo(): '%s'" % (sys.exc_info()[0]))
                return 0
    
    def loadRadioPlaylist(self):
        self.logger.debug("loading playlist '%s'" % (self.config.mpd_radio_playlist))
        i = 1
        while i < 10:
            try:
                with self.connection:
                    self.client.clear()
                    self.client.load(self.config.mpd_radio_playlist)
                    self.client.single(1)
                    return True
            except:
                self.logger.error("Error loading mpd playlist, attempt %i/10" % i)
                time.sleep(10)
        return False
        
    def playTitle(self, title):
        self.logger.info("starting...")
        self.coordinator.currentlyPlaying(False)
        with self.connection:
            try:
                self.client.send_play(title)
                self.logger.info("...started!")
                return True
            except:
                self.logger.error("Caught exception in MpdClient.playTitle(): '%s'" % (sys.exc_info()[0]))
                return False
                
        
    def stop(self):
        self.logger.info("stopping...")
        with self.connection:
            try:
                self.client.send_stop()
                self.logger.info("...stopped!")
                return True
            except:
                self.logger.error("Caught exception in MpdClient.stop(): '%s'" % (sys.exc_info()[0]))
                return False
            #self.coordinator.currentlyPlaying(False)
            
    def setVolume(self, vol):
        with self.connection:
            try:
                self.client.send_setvol(vol)
                return True
            except:
                self.logger.error("Caught exception in MpdClient.setVolume(): '%s'" % (sys.exc_info()[0]))
                return False
