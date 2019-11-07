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
            self.client.connect("/run/mpd/socket")
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
        self.logger = config.logger
        self.coordinator = coordinator
        self.listen = False
        self.status = {"started": False, "ended": False, "error": False}
        self.notifyCoordinator = False
        self.listenerThread = None
        self.client = MPDClient()
        self.statusCnd = threading.Condition()
        
    def connect(self):
        try:
            self.client.connect("/run/mpd/socket")
        except:
            self.logger.warn("MpdClientEventListener.connect() failed: '%s'" % (sys.exc_info()[0]))
    
    def disconnect(self):
        try:
            self.client.close()
        except:
            self.logger.warn("Exception during MpdClientEventListener.close(): '%s'" % (sys.exc_info()[0])) 
        try:
            self.client.disconnect()
        except:
            self.logger.warn("Exception during MpdClientEventListener.disconnect(): '%s'" % (sys.exc_info()[0])) 
            
        # todo :stop thread
            
    def do_listen(self):
        self.config.logger.debug("Listener thread started")
        alreadyRestarted = 0
        while self.listen is True:
            self.config.logger.debug("getting mpd player status...")
            stat = self.client.status()
            playing = False
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
                        self.config.logger.info("However, no volume control was available. Pause and restart, maybe soundcard/mixer was not ready?")
                        if alreadyRestarted < time.time()-10:
                            alreadyRestarted = time.time()
                            self.client.pause()
                            self.client.play()
                        else:
                            self.config.warning("Not restarting after volume not in stat, already restarted @%i" % alreadyRestarted)
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
                    self.status['error'] = True
            
            if self.coordinator:
                currentSongId = None
                currentVolume = None
                if 'song' in stat:
                    currentSongId = int(stat['song'])
                if 'volume' in stat:
                    currentVolume = int(stat['volume'])
                if self.notifyCoordinator:
                    self.coordinator.currentlyPlaying(mpdPlaying=playing, channel=currentSongId, 
                                                  volume=currentVolume, currentSongInfo=currentSongInfo)
            
            with self.statusCnd:
                if playing:
                    self.status['started'] = True
                elif self.status['started']:
                    self.status['ended'] = True
                self.statusCnd.notify_all()

            try:
                self.config.logger.debug("waiting for next mpd player status update...")
                self.client.idle()
            except:
                self.config.logger.debug("Exception during idle()")
        self.config.logger.debug("Listener thread stopped")
        
    def resetStatus(self):
        self.status['started'] = False
        self.status['ended'] = False
        self.status['error'] = False
        
    def waitForStatus(self, status, timeout):
        self.logger.debug("Waiting for status '%s'..." % status)
        if self.status[status] is False:
            with self.statusCnd:
                while self.status[status] is False:
                    self.logger.debug("Waiting for status update")
                    if self.statusCnd.wait(timeout) is False:
                        self.logger.warning("Timeout waiting for status '%s'!" % status)
                        return False
        self.logger.debug("Status '%s' reached" % status)
        return True
    
    def checkStatus(self, status):
        return self.status[status]
    
    def setNotifyCoordinator(self, notifyCoordinator):
        self.logger.info("Setting notifyCoordinator to '%s'" % notifyCoordinator)
        self.stopListener()
        self.notifyCoordinator = notifyCoordinator
        self.startListener()
        
    def startListener(self):
        self.listen = True
        self.connect()
        self.listenerThread = threading.Thread(target=self.do_listen, name="MpdClient.Listener")
        self.listenerThread.start()
        
    def stopListener(self):
        self.listen = False
        self.disconnect()
        if self.listenerThread.is_alive():
            self.listenerThread.join(timeout=2)


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
        self.queue = queue.Queue(100)
        self.queueHandlerThread = None
        
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
                pl = self.client.playlistinfo()
                titles = [i['name'] for i in pl]
                return titles
            except:
                self.logger.error("Caught exception in MpdClient.playlistinfo(): '%s'" % (sys.exc_info()[0]))
                return []
    
    def load(self, url):
        self.logger.debug("loading url '%s'" % url)
        for i in range(1,10):
            try:
                with self.connection:
                    self.client.clear()
                    self.client.load(url)
                    self.client.single(1)
                    self.client.consume(0)
                    self.client.repeat(1)
                    return True
            except:
                self.logger.error("Error loading '%s', attempt %i/10" % (url,i))
                time.sleep(10)
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
    
    def playSingleFile(self, file, vol = None):
        self.logger.info("putting playSingleFile(%s) into queue..." % file)
        try:
            self.queue.put(item= lambda: self._playSingleFile(file, vol), block = True, timeout=0.5)
            return True
        except:
            self.logger.error("Error putting job into queue!")
            return False
        
    def _playSingleFile(self, file, vol):
        self.logger.info("Playing single file '%s'..." % file)
        try:
            # what if radio state not playing nor stopped?
            resumeRadio = (self.coordinator.radioState == _RadioState.PLAYING)
            self._stop()
            # Todo: disable/pause bluetooth?
            self.coordinator.waitForRadioState(_RadioState.STOPPED)
            self.listener.setNotifyCoordinator(False)
            self.listener.resetStatus()
            with self.connection:
                self.client.send_clear()
                self.client.send_add(file)
                self.client.send_consume(1)
                if vol is not None:
                    self.client.send_setvol(vol)
                self.client.send_play()
                # todo: wait for playback to start and finish
            if self.listener.waitForStatus('started', 10):
                self.listener.waitForStatus('ended', 60) # do not wait for end if started already timed out!
                self.logger.info("Playback of '%s' done" % file)
            if self.listener.checkStatus('error'):
                self.logger.warning("Playback of '%s' failed!" % file)
                return
        finally:
            self.listener.resetStatus()
            self.listener.setNotifyCoordinator(True)
            self.loadRadioPlaylist() # and load radio playlist to leave everything as it was before 
            if resumeRadio:
                self.logger.debug("Resuming radio")
                self.coordinator.radioPlay()
                #self.listener.waitForStatus('started', 30)
            else:
                self.logger.debug("Not resuming radio")
            # todo: reenable bluetooth?
    
    def playTitle(self, playlistPosition):
        self.logger.info("putting playTitle(%s) into queue..." % playlistPosition)
        try:
            self.queue.put(item= lambda: self._playTitle(playlistPosition), block = True, timeout=0.5)
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
    
    def _playTitle(self, playlistPosition):
        self.logger.info("starting play...")
        self.coordinator.currentlyPlaying(mpdPlaying=False)
        with self.connection:
            try:
                self.client.send_play(playlistPosition)
                self.logger.info("...play sent!")
                return True
            except:
                self.logger.error("Caught exception in MpdClient.playTitle(): '%s'" % (sys.exc_info()[0]))
                return False
            
