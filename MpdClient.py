'''
Created on 08.08.2019

@author: tobias
'''

from mpd import MPDClient
import sys
import threading
import time
import json
import queue
from time import sleep

class _Connection:
    def __init__(self, parent):
        self.parent = parent
        self.logger = parent.config.logger
        self.client = parent.client
    def __enter__(self):
        try:
            self.client.ping()
        except:
            try:
                self.disconnect()
            except:
                pass
            self.connect()
    def __exit__(self, type, value, traceback):
        pass
    
    def connect(self):
        try:
            self.client.connect("127.0.0.1", 6600)
            return True
        except:
            self.logger.error("Caught exception in MpdClient.connct(): '%s'" % (sys.exc_info()[0]))
            return False
            
    def disconnect(self):
        try:
            self.client.disconnect()
            return True
        except:
            self.logger.warn("Exception during MpdClient.disconnect(): '%s'" % (sys.exc_info()[0])) 
            return False
        
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
            
        # todo :stop thread
            
    def do_listen(self):
        while self.listen is True:
            #try:
                self.config.logger.debug("getting mpd player status...")
                stat = self.client.status()
                playing = False
                currentSongInfo = None
                alreadyRestarted = False
                while ('state' in stat) and (stat['state'] == 'play') and 'error' not in stat:
                    # mpd wants to play but maybe waits for stream to start, we have to poll
                    if ('bitrate' in stat and int(stat['bitrate']) > 0) or ('elapsed' in stat and float(stat['elapsed']) > 0):
                        # currently streaming
                        currentSongInfo = self.client.currentsong()
                        self.config.logger.info("MPD playing %s" % json.dumps(currentSongInfo))
                        self.config.logger.debug("MPD playing %s" % json.dumps(stat))
                        if alreadyRestarted is False and ('volume' not in stat or int(stat['volume']) is None):
                            self.config.logger.info("However, no volume control was available. Pause and restart once, maybe soundcard/mixer was not ready?")
                            alreadyRestarted = True
                            if self.coordinator:
                                self.coordinator.radioRestart()
                        playing = True
                        break # can go and idle
                    else:
                        self.config.logger.debug("MPD not streaming (yet?)")
                        time.sleep(0.1)
                        stat = self.client.status()
                
                if ('state' not in stat) or (stat['state'] != 'play'):
                    self.config.logger.info("MPD not playing")
                    
                if 'error' in stat:
                    self.config.logger.warning("MPD reported an error: '%s'" % stat['error'])
                    if alreadyRestarted is False:
                        self.config.logger.warning("Trying to restart after one second")
                        alreadyRestarted = True
                        sleep(1)
                        if self.coordinator:
                            self.coordinator.radioRestart()
                
                if self.coordinator:
                    currentSongId = None
                    currentVolume = None
                    if 'song' in stat:
                        currentSongId = int(stat['song'])
                    if 'volume' in stat:
                        currentVolume = int(stat['volume'])
                    self.coordinator.currentlyPlaying(mpdPlaying=playing, channel=currentSongId, 
                                                      volume=currentVolume, currentSongInfo=currentSongInfo)
                        
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
        self.connection = _Connection(self)
        self.coordinator = coordinator
        if coordinator is not None:
            coordinator.mpdClient = self
        self.listener = MpdClientEventListener(config, coordinator)
        self.listener.startListener()
        self.queue = queue.Queue(10)
        self.queueHandlerThread = None
        
    def connect(self):
        self._startQueueHandler()
        return self.connection.connect()
    
    def disconnect(self):
        self._stopQueueHandler()
        self.listener.disconnect()
        self._stopQueueHandler()
        return self.connection.disconnect()
    
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
    
    def _stopQueueHandler(self):
        if self.queueHandlerThread is None:
            return True
        try:
            self.queue.put(item=None, block=True, timeout=10)
        except:
            self.logger.error("Error putting stop-job into queue. Queue maybe stuck")
            return False
        # todo: join queue handler thread
        self.queueHandlerThread.join(10)
        if self.queueHandlerThread.is_alive():
            self.logger.error("Queue handler thread did not stop! Queue stuck!!")
        self.queueHandlerThread = None
            
    def _startQueueHandler(self):
        if self.queueHandlerThread is not None:
            self.logger.error("Queue handler already active!")
            return False
        self.queueHandlerThread = threading.Thread(target=self._queueHandlerFct)
        self.queueHandlerThread.start()
        
    def _queueHandlerFct(self):
        ''' to stop queue handler, put an empty message in the queue '''
        self.logger.debug("Queue handler started...")
        while True:
            queue_item = self.queue.get(block=True, timeout=None)
            if queue_item is None:
                return
            self.logger.debug("Running job from queue...")
            queue_item()
        self.logger.debug("Queue handler stopped")
    
    def playTitle(self, title):
        self.logger.info("putting playTitle(%s) into queue..." % title)
        try:
            self.queue.put(item= lambda: self._playTitle(title), block = True, timeout=0.5)
            return True
        except:
            self.logger.error("Error putting job into queue!")
            return False
    
    def stop(self):
        self.logger.info("putting stop() into queue...")
        try:
            self.queue.put(item= lambda: self._stop(), block = True, timeout=0.5)
            return True
        except:
            self.logger.error("Error putting job into queue!")
            return False            
    
    def setVolume(self, vol):
        self.logger.info("putting setVolume(%i) into queue..." % vol)
        try:
            self.queue.put(item= lambda: self._setVolume(vol), block = True, timeout=0.5)
            return True
        except:
            self.logger.error("Error putting job into queue!")
            return False 
        
    def pause(self):
        self.logger.info("putting pause() into queue...")
        try:
            self.queue.put(item= lambda: self._pause(), block = True, timeout=0.5)
            return True
        except:
            self.logger.error("Error putting job into queue!")
            return False
            
    def _setVolume(self, vol):
        self.logger.info("setting volume to %i" % vol)
        with self.connection:
            try:
                self.client.send_setvol(vol)
                return True
            except:
                self.logger.error("Caught exception in MpdClient.setVolume(): '%s'" % (sys.exc_info()[0]))
                return False
            
    def _stop(self):
        self.logger.info("stopping...")
        with self.connection:
            try:
                self.client.send_stop()
                self.logger.info("...stop sent!")
                return True
            except:
                self.logger.error("Caught exception in MpdClient.stop(): '%s'" % (sys.exc_info()[0]))
                return False
            
    def _pause(self):
        self.logger.info("pausing...")
        with self.connection:
            try:
                self.client.send_pause()
                self.logger.info("...paused!")
                return True
            except:
                self.logger.error("Caught exception in MpdClient.stop(): '%s'" % (sys.exc_info()[0]))
                return False
    
    def _playTitle(self, title):
        self.logger.info("starting play...")
        self.coordinator.currentlyPlaying(mpdPlaying=False)
        with self.connection:
            try:
                self.client.send_play(title)
                self.logger.info("...play sent!")
                return True
            except:
                self.logger.error("Caught exception in MpdClient.playTitle(): '%s'" % (sys.exc_info()[0]))
                return False
            
