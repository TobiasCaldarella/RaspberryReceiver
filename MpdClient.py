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
from Configuration import _RadioState
from enum import Enum
from GpioController import PowerState
from datetime import datetime

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
                self.logger.info("MpdConnection: Ping failed")
                self.disconnect()
            except:
                pass
            self.connect()
    def __exit__(self, type, value, traceback):
        pass
    
    def connect(self):
        try:
            self.client.connect("/run/mpd/socket")
            self.client.timeout = 600
            self.client.idletimeout = None
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
    def __init__(self, config, coordinator, mpdClient):
        self.config = config
        self.logger = config.logger
        self.coordinator = coordinator
        self.listen = False
        self.notifyCoordinator = False
        self.listenerThread = None
        self.client = MPDClient()
        self.connection = _Connection(self)
        self.mpdClient = mpdClient
        
    def connect(self):
        self.connection.connect()
    
    def disconnect(self):
        self.connection.disconnect()
            
        # todo :stop thread
            
    def do_listen(self):
        self.config.logger.debug("Listener thread started")
        alreadyRestarted = 0
        while self.listen is True:
            with self.connection:
                self.config.logger.debug("getting mpd player status...")
                stat = self.client.status()
                playing = False
                error = False
                currentSongInfo = None
                while ('state' in stat) and (stat['state'] == 'play') and 'error' not in stat:
                    # mpd wants to play but maybe waits for stream to start, we have to poll
                    if ('bitrate' in stat and int(stat['bitrate']) > 0) or ('elapsed' in stat and float(stat['elapsed']) > 0):
                        # currently streaming
                        currentSongInfo = self.client.currentsong()
                        self.config.logger.info("MPD playing currentSongInfo: %s" % json.dumps(currentSongInfo))
                        self.config.logger.debug("MPD playing stats: %s" % json.dumps(stat))                                 
                        playing = True
                        if ('volume' not in stat or int(stat['volume']) is None):
                            #if (False):
                            self.config.logger.info("However, no volume control was available. Pause and restart, maybe soundcard/mixer was not ready?")
                            if alreadyRestarted < time.time()-10:
                                alreadyRestarted = time.time()
                                self.client.pause()
                                self.client.play()
                            else:
                                self.config.logger.warning("Not restarting after volume not in stat, already restarted @%i" % alreadyRestarted)
                        break # can go and idle
                    else:
                        self.config.logger.debug("MPD not streaming (yet?)")
                        time.sleep(0.1)
                        stat = self.client.status()
                
                if playing:
                    self.config.logger.info("MPD playing")
                else:
                    self.config.logger.info("MPD not playing")
                    
                if 'error' in stat:
                    self.config.logger.warning("MPD reported an error: '%s'" % stat['error'])
                    if alreadyRestarted < time.time()-30:
                        self.config.logger.warning("Trying to restart after one second")
                        alreadyRestarted = time.time()
                        self.client.pause()
                        self.client.play()
                    else:
                        self.logger.error("Not restarting, playback failed, already restarted @%i" % alreadyRestarted)
                        error = True
                        self.coordinator.gotoErrorState("Not restarting, playback failed, already restarted @%i" % alreadyRestarted)
                    
                self.coordinator.currentSongId = None
                if 'song' in stat:
                    self.coordinator.currentSongId = int(stat['song'])
                self.coordinator.currentSongInfo = currentSongInfo
                        
                if playing:
                    self.mpdClient._updateMpdState(MpdState.STARTED)  
                elif error:
                    self.mpdClient._updateMpdState(MpdState.ERROR)
                else:
                    self.mpdClient._updateMpdState(MpdState.STOPPED)
                
                if self.notifyCoordinator: 
                    self.coordinator.mpdUpdateCallback()
    
                try:
                    self.config.logger.debug("waiting for next mpd player status update...")
                    self.client.idle()
                except:
                    self.config.logger.debug("Exception during idle()")
        self.config.logger.debug("Listener thread stopped")
    
    def setNotifyCoordinator(self, notifyCoordinator):
        self.logger.info("Setting notifyCoordinator to '%s'" % notifyCoordinator)
        #self.stopListener()
        self.notifyCoordinator = notifyCoordinator
        #self.startListener()
        
    def startListener(self):
        self.listen = True
        self.logger.info("4 connecting")
        self.connect()
        self.logger.info("5 connected")
        self.listenerThread = threading.Thread(target=self.do_listen, name="MpdClient.Listener")
        self.listenerThread.start()
        self.logger.info("6 started")
        
    def stopListener(self):
        if self.listenerThread is None:
            return
        self.listen = False
        self.logger.info("0 disconnecting")
        self.disconnect()
        self.logger.info("1 disconnected")
        if self.listenerThread.is_alive():
            self.logger.info("2 alive")
            self.listenerThread.join(timeout=2)
            self.logger.info("3 joined")
    
class MpdState(Enum):
    STOPPED = 0,
    STOPPING = 1,
    STARTING = 2,
    STARTED = 3,
    ERROR = 4

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
        self.listener = MpdClientEventListener(config, coordinator, self)
        self.queue = queue.Queue(100)
        self.queueHandlerThread = None
        self.mpdVolume = 100
        self.mpdState = MpdState.STOPPED
        self.mpdStateUpdateEvent = threading.Condition()
        self.currentSongId = None
        self.currentSongInfo = None
        self.currentPlaylist = None
        self.interruptEvent = threading.Condition()
        self.isInterrupted = False
        self.isFading = False
        
    def _updateMpdState(self, newState: MpdState):
        with self.mpdStateUpdateEvent:
            self.__updateMpdState(newState)
            
    def __updateMpdState(self, newState: MpdState):
        self.mpdState = newState
        self.mpdStateUpdateEvent.notifyAll()
            
    def getMpdState(self):
        with self.mpdStateUpdateEvent:
            return self.mpdState
        
    def waitForMpdState(self, desiredState: MpdState, timeout = 5.0):
        startTime = datetime.now()
        with self.mpdStateUpdateEvent:
            while True:
                self.logger.info("MpdClient.waitForMpdState: desired: %s current: %s" % (desiredState, self.mpdState))
                if self.mpdState is desiredState:
                    return True
                #if desiredState is MpdState.STARTED:
                    #if self.mpdState in [MpdState.ERROR, MpdState.STOPPING]:
                    #    return False # will never reach desired state
                #if desiredState is MpdState.STOPPED:
                    #if self.mpdState in [MpdState.ERROR, MpdState.STARTING]:
                    #    return False # will never reach desired state
                ttimeout = timeout - (datetime.now() - startTime).seconds #Todo: make this interruptable!
                if not self.mpdStateUpdateEvent.wait(ttimeout) or self.isInterrupted:
                    return False
       
    def interrupt_set(self):
        with self.interruptEvent:
            if self.isFading is False:
                return
            self.logger.info("Interrupting")
            self.isInterrupted = True
            self.interruptEvent.notify_all()
        with self.mpdStateUpdateEvent:
            self.mpdStateUpdateEvent.notify_all() # also interrupt, someone might be waiting there as well!
            
    def interrupt_clear(self):
        with self.interruptEvent:
            self.isInterrupted = False
        
    def connect(self):
        self.listener.startListener()
        self.startQueueHandler()
        return self.connection.connect()
    
    def disconnect(self):
        self.stopQueueHandler()
        self.listener.stopListener()
        self.stopQueueHandler()
        return self.connection.disconnect()
    
    def getTitlesFromPlaylist(self):
        with self.connection:
            try:
                titles = [i['name'] for i in self.currentPlaylist]
                return titles
            except Exception as x:
                self.logger.error("Caught exception in MpdClient.playlistinfo(): '%s'" % x)
                return []
    
    def load(self, url):
        self.logger.debug("loading url '%s'" % url)
        ret = False
        for i in range(1,10):
            try:
                with self.connection:
                    self.client.clear()
                    self.client.load(url)
                    self.client.single(1)
                    self.client.consume(0)
                    self.client.repeat(1)
                    ret = True
                    break
            except:
                self.logger.error("Error loading '%s', attempt %i/10" % (url,i))
                time.sleep(1)
        
        for i in range(1,10):
            try:
                with self.connection:
                    self.currentPlaylist = self.client.playlistinfo()
                    self.logger.info(self.currentPlaylist)
                    return ret
            except:
                self.logger.error("Exception getting playlist, attempt %i/10" % (i))
                time.sleep(0.1)
        return False
    
    def loadRadioPlaylist(self):
        self.logger.debug("loading playlist '%s'" % (self.config.mpd_playlist_name))
        return self.load(self.config.mpd_playlist_name)
    
    def stopQueueHandler(self):
        self.logger.info("Stopping queue handler...")
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
            
    def startQueueHandler(self):
        self.logger.info("Starting queue handler...")
        if self.queueHandlerThread is not None:
            self.logger.error("Queue handler already active!")
            return False
        self.queueHandlerThread = threading.Thread(target=self._queueHandlerFct, name='MpdClient.QueueHandler')
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
    
    def playTitle(self, playlistPosition, muted = False):
        self.logger.info("putting playTitle(%s) into queue..." % playlistPosition)
        with self.mpdStateUpdateEvent:
            if self.mpdState == MpdState.STARTED:
                return True
            self.__updateMpdState(MpdState.STARTING)
            return self.__playTitle(playlistPosition, muted)
    
    def stop(self):
        self.logger.info("putting stop() into queue...")
        with self.mpdStateUpdateEvent:
            if self.mpdState == MpdState.STOPPED:
                return True
            self.__updateMpdState(MpdState.STOPPING)
            return self.__stop()
    
    def setVolume(self, vol):
        #if self.config.mpd_change_volume is False:
        #    self.logger.debug("mpd_change_volume is False, not setting global volume via mpd")
        #    return
        if vol is self.mpdVolume:
            self.logger.debug("Volume already at %d" % vol)
            return
            
        self.logger.info("putting setVolume(%i) into queue..." % vol)
        return self._setVolume(vol)
    
    def _setVolume(self, vol):
        self.logger.info("setting volume to %i" % vol)
        with self.connection:
            try:
                self.client.send_setvol(vol)
                self.mpdVolume = vol
                return True
            except:
                self.logger.error("Caught exception in MpdClient.setVolume(): '%s'" % (sys.exc_info()[0]))
                return False
            
    def __stop(self):
        self.logger.info("stopping...")
        with self.connection:
            try:
                #if self.config.mpd_change_volume is False:
                #    for vol in range(60,-1,-20):
                #        self.client.send_setvol(vol)
                #        time.sleep(0.1)
                self.client.send_stop()
                self.logger.info("...stop sent!")
                return True
            except:
                self.logger.error("Caught exception in MpdClient.stop(): '%s'" % (sys.exc_info()[0]))
                return False
            
    def __playTitle(self, playlistPosition, muted):
        self.logger.info("starting play...")
        with self.connection:
            try:
                self.client.send_setvol(0)
                self.client.send_play(playlistPosition)
                if not muted:
                    self._fadeIn()
                self.logger.info("...play sent!")
                return True
            except:
                self.logger.error("Caught exception in MpdClient.playTitle(): '%s'" % (sys.exc_info()[0]))
                return False
    
    def _fadeIn(self, immediately=False):
        with self.interruptEvent:
            try:
                with self.connection:
                    if immediately is False:
                        self.isFading = True
                        for vol in range(10,self.mpdVolume,10):
                            self.client.send_setvol(vol)
                            if self.interruptEvent.wait(0.1) or self.isInterrupted:
                                self.client.send_setvol(0)
                                return
                    self.client.send_setvol(self.mpdVolume)
            finally:
                self.isFading = False
            
    def _fadeOut(self, immediately=False):
        with self.interruptEvent:
            try:
                with self.connection:
                    if immediately is False:
                        self.isFading = True
                        for vol in range(self.mpdVolume-10,0,10):
                            self.client.send_setvol(vol)
                            if self.interruptEvent.wait(0.1) or self.isInterrupted:
                                break
                    self.client.send_setvol(0)
            finally:
                self.isFading = False
            
    # this one is not async. not sure if it's a good idea...
    def mute(self, muted, immediately = False):
        try:
            self.logger.info("Muting/Unmuting mpd. mute: %s" % muted)
            if muted == True:
                self._fadeOut(immediately)
            else:
                self._fadeIn(immediately)
        except:
            self.logger.error("Caught exception in MpdClient.mute(): '%s'" % (sys.exc_info()[0]))
            return False
        
    def setCoordinatorNotification(self, enabled):
        self.logger.info("setCoordinatorNotification called with enabled=%s" % enabled)
        self.listener.setNotifyCoordinator(enabled)

