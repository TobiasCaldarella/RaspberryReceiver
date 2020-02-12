'''
Created on 08.08.2019

@author: tobias
'''
from GpioController import PowerState
from MpdClient import MpdClient
#from IR import IR
import threading
from enum import Enum
import time
from Bluetooth import Bluetooth
import urllib.request 
from time import sleep
from Configuration import _RadioState, _RadioPowerState
import queue
from MotorPoti import MotorPoti

class Coordinator(object):
    '''
    classdocs
    '''
    def __init__(self, logger, config):
        '''
        Constructor
        '''
        self.config = config
        self.mqttClient = None
        self.gpioController = None
        self.mpdClient = None
        self.bluetooth = None
        self.bluetoothEnabled = False
        self.needle = None
        self.wheel = None
        self.poti = None
        self.logger = logger
        self.ir = None
        self.signal_strength_meter = None
        self.numChannels = 0
        self.currentChannel = 0
        self.needleStepsPerChannel = 0
        self.radioState = _RadioState.STOPPED
        self.powerState = _RadioPowerState.POWERED_DOWN
        self.currentVolume = 0
        self.sleepTimer = None
        self.playStateCnd = threading.Condition()
        self.currentSongInfo = {}
        self.textToSpeech = None
        self.workerThread = threading.Thread(target=self.do_work, name="Coordinator.WorkerThread")
        self.running = False
        self.skipMqttUpdates = False
        self.job_queue = queue.Queue(30)
        self.announceTimer = None
        
    def do_work(self):
        self.logger.debug("Worker thread started")
        while self.running:
            try:
                self.logger.debug("Worker thread waiting for jobs in queue")
                job = self.job_queue.get(block=True)
                if job is not None:
                    self.logger.debug("Running job: '%s'" % job)
                    job()
            except Exception as ex:
                self.logger.error("Exception in worker thread: '%s'" % ex)
        self.logger.debug("Worker thread stopped") 
    
    def connectWifi(self):
        self.gpioController.setStereoBlink(active=True, pause_s=2)
        pass
        
    def connectMqtt(self):
        if self.mqttClient is None:
            return False
        self.gpioController.setStereoBlink(active=True, pause_s=1)
        if self.mqttClient.connect() is True and self.mqttClient.waitForSubscription() is True:
            self.gpioController.setStereolight(PowerState.OFF)
            return True
        self.logger.warn("Connection to mqtt failed, will retry immediately")
        self.mqttClient.reconnect()
        return True

    def _putJobIntoQueue(self, job):
        try:
            self.job_queue.put(job, True, 2)
        except:
            self.logger.error("Could not put job into queue, queue full?")
    
    def powerOff(self):
        self.logger.info("Power down requested...")
        if self.announceTimer:
            self.announceTimer.cancel()
        self._putJobIntoQueue(self._powerOff)
        
    def _powerOff(self):
        self.logger.info("Power down sequence started")
        with self.playStateCnd:
            if not self.isPoweredOn():
                self.logger.debug("Not powered up, ignoring request")
                return
            self.powerState = _RadioPowerState.POWERING_DOWN
            if self.sleepTimer:
                self.sleepTimer.cancel()
            self.bluetooth.disable(wait_for_stop = False)
            self.wheel.disable()
            self._radioStop()
            self.mpdClient.stopQueueHandler()
            self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd) # bluetooth and radio are stopped, wait for play state to become stopped
            self.logger.info("Powering down amp...")
            self.gpioController.setStereolight(PowerState.OFF)
            self.gpioController.setBacklight(PowerState.OFF)
            self.gpioController.setNeedlelight(PowerState.OFF)
            self.gpioController.setPowerAndSpeaker(PowerState.OFF)
            self.gpioController.setStereoBlink(active=True, pause_s=10)
            self.signal_strength_meter.disable()
            self.setBrightness(self.config.backlight_default_brightness)
            self.powerState = _RadioPowerState.POWERED_DOWN
        self.sendStateToMqtt()
    
    def powerOn(self):
        self.logger.info("Power on requested...")
        self.setSkipMqttUpdates(True)
        self._putJobIntoQueue(self._powerOn)
    
    def _powerOn(self):
        self.logger.info("Power up sequence started...")
        with self.playStateCnd:
            if self.sleepTimer:
                self.sleepTimer.cancel()
            if self.powerState is not _RadioPowerState.POWERED_DOWN:
                self.logger.debug("Not powered down, ignoring request")
                return
            self.logger.info("Powering up amp...")
            self.powerState = _RadioPowerState.POWERING_UP
            self.signal_strength_meter.enable()
            self.setBrightness(self.config.backlight_default_brightness)
            self.gpioController.setBacklight(PowerState.ON)
            self.gpioController.setStereolight(PowerState.OFF)
            self.gpioController.setPowerAndSpeaker(PowerState.ON)
            self.mpdClient.startQueueHandler()
            self._radioStop()
            self.radioState = _RadioState.STOPPED
            self.mpdClient.setVolume(self.currentVolume) # set this before accepting any feedback from mpd
            self.needle.setNeedleForChannel(ch=self.currentChannel, relative=False, drivingThread=True, mtx=self.playStateCnd)
            self.powerState = _RadioPowerState.POWERED_UP
            self.radioPlay(announceChannel=False) # put this into queue 
            if self.bluetoothEnabled:
                self.bluetooth.enable()
            self.wheel.enable()
        self.mpdClient.listener.notifyCoordinator = True # now we are ready to receive status updates
        self.mpdClient.setVolume(self.currentVolume) # and this just triggers an update of the mpd state so we can get a current status now
        self.setSkipMqttUpdates(False) 
            
    def sleep(self, time_m):
        self.logger.info("Sleep requested...")
        self._putJobIntoQueue(lambda: self._sleep(time_m))
    
    def _sleep(self, time_m):
        with self.playStateCnd:
            if not self.isPoweredOn():
                self.logger.debug("Not powered up, ignoring request")
                return
            if self.sleepTimer:
                self.sleepTimer.cancel()
            
            if time_m > 0:
                self.logger.info("Sleep set to %i minutes" % time_m)
                self.textToSpeech.speak(text=("Schalte in %i Minuten aus." % time_m), lang='de-de')
                self.sleepTimer = threading.Timer(time_m * 60, self.powerOff)
                self.sleepTimer.start()
                self.setBrightness(self.config.backlight_sleep_brightness)
            else:
                self.logger.info("Sleep cancelled")
                self.setBrightness(self.config.backlight_default_brightness)
            
    def initialize(self):
        self.gpioController.setStereoBlink(active=True, pause_s=0)
        # todo: maybe do this in background?
        if self.signal_strength_meter:
            self.signal_strength_meter.init()
            
        if self.ir:
            self.ir.connect()
        
        self.connectWifi()
        if self.poti:
            self.poti.reset()
        # connect MPD client and load playlist
        if self.mpdClient.connect() is not True:
            self.logger.warn("Could not connect to MPD. Disabled...");
            self.mpdClient = None
        else:
            self.gpioController.setStereoBlink(active=True, pause_s=3)
            self.downloadPlaylist()
            if self.mpdClient.loadRadioPlaylist():
                self.channels = self.mpdClient.getTitlesFromPlaylist()
                self.numChannels = len(self.channels)
            self.logger.info("%i channels in radio playlist" % self.numChannels)
        
        if self.config.needle_steps > 0 and self.numChannels > 0:
            if self.needle:
                self.needle.init(self.numChannels)
        else:
            self.needle = None
            
        if self.bluetooth is not None:
            self.bluetooth.initialize()
        
        if self.connectMqtt() is not True:
            self.logger.warn("Could not connect to MQTT. Disabled...")
            self.mqttClient = None
            
        self.gpioController.enable_power_button()
        if self.ir:
            self.ir.enable()
        self.gpioController.setStereoBlink(active=True, pause_s=10)
        self.running = True
        self.gpioController.do_bluetooth_switch(None) # get correct switch position at init
        self.workerThread.start()
        self.sendStateToMqtt()
        
    def downloadPlaylist(self):
        for i in range(1,10):
            try:
                urllib.request.urlretrieve(self.config.mpd_radio_playlist, self.config.mpd_local_playlist)
                return
            except:
                self.logger.error("Could not download '%s' to '%s'! Attempt %i/10" % 
                                  (self.config.mpd_radio_playlist, self.config.mpd_local_playlist, i))
                sleep(5)
                self.gpioController.setStereoBlink(active=True, pause_s=1)
        
    def lightSignal(self):
        intensity = self.gpioController.backlightIntensity
        if intensity == 0:
            self.gpioController.setBacklight(PowerState.ON, self.config.backlight_default_brightness)
        else:
            self.gpioController.setBacklight(PowerState.OFF)
        self.gpioController.setBacklight(PowerState.ON, intensity)
        
    def blinkNeedleLight(self, blink = True):
        with self.playStateCnd:
            if blink == False:
                if self.radioState == _RadioState.PLAYING:
                    self.gpioController.setNeedlelight(PowerState.ON)
                else:
                    self.gpioController.setNeedlelight(PowerState.OFF)
            else:
                self.gpioController.setNeedleLightBlink(active=True, pause_s = 0)
    
    def setChannel(self, channel, relative = False, setIfPowerOff = False):
        self.logger.info("channel change requested (channel=%i, relative = %s)" % (channel, relative))
        with self.playStateCnd:
            if self.announceTimer:
                self.announceTimer.cancel()
            if self.needle.isMoving:
                self.logger.debug("Needle already moving, only updating needle destination")
                self.needle.setNeedleForChannel(ch=channel, relative=relative, drivingThread=False, mtx=self.playStateCnd)
            else:
                self._putJobIntoQueue(lambda: self._setChannel(channel, relative, setIfPowerOff))
        
    def _setChannel(self, channel, relative = False, setIfPowerOff = False):
        with self.playStateCnd:
            if self.radioState == _RadioState.BLUETOOTH:
                self.logger.debug("Bluetooth active, not changing channel")
                return
                
            if not self.isPoweredOn() and not setIfPowerOff:
                self.logger.info("not powered on, not setting channel")
                return
            self.logger.info("setting channel to %i, relative %s" % (channel, relative))
            self.__radioStop(needleLightOff=False)
            self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
            # the needle periodically unlocks the mtx to allow other threads to do stuff
            # get new current channel from needle since it collected all the updates 
            # that occured in the meantime
            self.currentChannel = self.needle.setNeedleForChannel(ch=channel, relative=relative, drivingThread=True, mtx=self.playStateCnd)
            if self.isPoweredOn():
                self.gpioController.setNeedlelight(PowerState.ON)
                self.__radioPlay(announceChannel=True)
    
    def volumeUp(self):
        self.logger.info("volumeUp requested")
        self.poti.moveCW(self.config.motorpoti_speed)
        self._putJobIntoQueue(self._volumeUp)
                
    def _volumeUp(self):
        with self.playStateCnd:
            if not self.isPoweredOn():
                self.logger.info("not powered on, not changing volume")
                return
            vol = self.currentVolume
            vol+=10
            if vol > 100:
                vol = 100
            self.mpdClient.setVolume(vol)
            
    def volumeDown(self):
        self.logger.info("volumeDown requested")
        self.poti.moveCCW(self.config.motorpoti_speed)
        self._putJobIntoQueue(self._volumeDown)
    
    def _volumeDown(self):
        with self.playStateCnd:
            if not self.isPoweredOn():
                self.logger.info("not powered on, not changing volume")
                return
            vol = self.currentVolume
            vol-=10
            if vol < 0:
                vol = 0
            self.mpdClient.setVolume(vol)
    
    def setVolume(self, vol, waitForPoti = False):
        self.logger.info("setVolume requested (volume = %i)" % vol)
        self._putJobIntoQueue(lambda: self._setVolume(vol, waitForPoti))
    
    def _setVolume(self, vol, waitForPoti):
        with self.playStateCnd:
            if vol < 0 or vol > 100:
                self.logger.warn("Received invalid volume: %i", vol)
            else:
                if self.isPoweredOn():
                    self.mpdClient.setVolume(vol)
                self.poti.set(vol, waitForPoti)
                self.currentVolume = vol
        self.sendStateToMqtt()
    
    def radioStop(self):
        self.logger.info("radioStop requested")
        if self.announceTimer:
            self.announceTimer.cancel()
        self._putJobIntoQueue(self._radioStop)
    
    def _radioStop(self, waitForStop = True):
        with self.playStateCnd:
            self.__radioStop()
            if waitForStop:
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)    
    
    def __radioStop(self, needleLightOff=True):
        if self.announceTimer:
            self.announceTimer.cancel()
        self.mpdClient.stop()
        if needleLightOff:
            self.gpioController.setNeedlelight(PowerState.OFF)
        
    def radioPlay(self, announceChannel = False):
        self.logger.info("RadioPlay requested (announceChannel='%s')" % announceChannel)
        if self.announceTimer:
            self.announceTimer.cancel()
        self._putJobIntoQueue(lambda: self._radioPlay(announceChannel))
    
    def _radioPlay(self, announceChannel = False):
        with self.playStateCnd:
            self.__radioPlay(announceChannel=announceChannel)
    
    def __radioPause(self):
        if not self.isPoweredOn():
            self.logger.error("Cannot send pause if not powered up")
            return
        self.gpioController.setNeedlelight(PowerState.OFF)
        self.mpdClient.pause()
    
    def __radioPlay(self, announceChannel = False):
        if self.radioState is _RadioState.BLUETOOTH:
            self.logger.info("Not playing, bluetooth is active!")
            return
        if not self.isPoweredOn():
            self.logger.error("Will not start play, not in powered up state")
            return
        if self.announceTimer:
            self.announceTimer.cancel()
            
        self.gpioController.setNeedlelight(PowerState.ON)
        self.mpdClient.setVolume(self.currentVolume)
        self.mpdClient.playTitle(playlistPosition=self.currentChannel)
        if announceChannel:
            channelName = self.channels[self.currentChannel]
            lang='de-de'
            if channelName.find('|lang=') >= 0:
                channelName = channelName.split('|lang=')
                lang = channelName[1]
                channelName = channelName[0]
                
            self.announceTimer = threading.Timer(self.config.announceTime_s, lambda: self.speak(text=channelName,lang=lang))
            self.announceTimer.start()
            
    def isPoweredOn(self):
        return (self.powerState is _RadioPowerState.POWERED_UP)
    
    def waitForRadioState(self, desiredState, lock=None):
        if lock is None:
            with self.playStateCnd:
                return self._waitForRadioState(desiredState)
        else:
            return self._waitForRadioState(desiredState)
    
    def _waitForRadioState(self, desiredState):
        self.logger.debug("radioState is '%s', desired: '%s'" % (self.radioState, desiredState))
        while self.radioState != desiredState:
            self.logger.debug("waiting for radioState to become '%s'..." % desiredState)
            if self.playStateCnd.wait(timeout=10) is False:
                self.logger.warn("timeout while waiting for state update!")
                return False
            self.logger.debug("radioState is '%s'" % self.radioState)
        return True
    
    #todo make this async?
    def bluetoothPlaying(self, active):
        self.logger.info("Coordinator.bluetoothPlaying called with active = '%i'" % active)
        with self.playStateCnd:
            if active is True and self.radioState is not _RadioState.BLUETOOTH:
                if not self.isPoweredOn():
                    self.logger.error("Cannot enable bluetooth if not if not powered up!")
                    return
                self._radioStop()
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
                self._setRadioState(_RadioState.BLUETOOTH) # bluetooth state won't be overwritten by status updates
                self.gpioController.setBacklight(PowerState.OFF)
                self.gpioController.setBacklight(PowerState.ON)
            elif active is False and self.radioState is _RadioState.BLUETOOTH:
                self.gpioController.setBacklight(PowerState.OFF)
                self.gpioController.setBacklight(PowerState.ON)
                self._setRadioState(_RadioState.STOPPED)
                self._radioPlay() 
            self.playStateCnd.notify_all()           
    
    def _setRadioState(self, state):
        self.logger.debug("setting radio state to '%s'" % state)
        oldState = self.radioState
        self.radioState = state
        self.playStateCnd.notify_all() # update done, notify
        
        if oldState == state:
            self.logger.debug("radio state was already '%s', not updating lights" % state)
        else:
            if (state == _RadioState.PLAYING):
                self.gpioController.setStereolight(PowerState.ON)
                self.gpioController.setNeedlelight(PowerState.ON)
            elif (state == _RadioState.STOPPED):
                self.gpioController.setStereolight(PowerState.OFF)  
            elif (state == _RadioState.BLUETOOTH):
                self.gpioController.setStereoBlink(active=True, pause_s=1)
        
    # mutes or unmutes radio (and maybe other sources like bluetooth in future?)    
    def mute(self, mute):
        self.mpdClient.mute(mute)
    
    def speak(self, text, lang, block=False):
        self.logger.debug("Speak '%s', lang '%s'" % (text, lang))
        if block is True:
            self._speak(text, lang)
        else:
            self._putJobIntoQueue(lambda: self._speak(text, lang))
            
    def _speak(self, text, lang):
        if not self.isPoweredOn():
            self.logger.info("Cannot speak if not powered on. Should have said: '%s'" % text)
            return
        self.textToSpeech.speak(text, lang)
    
    #todo: make this async
    def playSingleFile(self, file):
        self.logger.debug("playSingleFile('%s')" % file)
        with self.playStateCnd:
            if self.isPoweredOn():
                self.mpdClient.playSingleFile(file)
            else:
                self.logger.info("Not powered on, cannot play!")
    
    def currentlyPlaying(self, mpdPlaying = None, channel = None, volume = None, currentSongInfo = None):
        self.logger.debug("updating coordinator-state...")
        with self.playStateCnd:
            if volume is not None:
                self.currentVolume = volume
            
            if self.radioState is not _RadioState.BLUETOOTH:
                if mpdPlaying is True:
                    self._setRadioState(_RadioState.PLAYING)
                elif mpdPlaying is False:
                    self._setRadioState(_RadioState.STOPPED)

            if channel is not None and channel != self.currentChannel and self.radioState is _RadioState.PLAYING:
                self.logger.warn("Unexpected channel change, adjusting needle and informing mqtt...")
                self.currentChannel = channel
                self.needle.setNeedleForChannel(channel)
                
            if currentSongInfo:
                self.currentSongInfo = currentSongInfo
            
        self.logger.debug("coordinator-state updated")
        self.sendStateToMqtt()
    
    def sendStateToMqtt(self):
        if self.mqttClient:
            self.logger.debug("Sending current state to mqtt")
            with self.playStateCnd:
                if self.skipMqttUpdates:
                    self.logger.debug("Skipping MQTT update")
                    return
                radioState = self.radioState
                currentChannel = self.currentChannel
                currentVolume = self.currentVolume
                currentSongInfo = self.currentSongInfo
                numChannels = self.numChannels
                if self.gpioController is not None:
                    brightness = self.gpioController.backLight.intensity
                else:
                    brightness = None
                poweredOn = self.isPoweredOn()
                bluetooth = self.bluetoothEnabled
                    
            self.mqttClient.pubInfo(radioState, currentChannel+1, currentVolume, currentSongInfo, numChannels, brightness, poweredOn, bluetooth)  # human-readable channel
            if self.isPoweredOn():
                self.mqttClient.publish_power_state(PowerState.ON)
            else:
                self.mqttClient.publish_power_state(PowerState.OFF)                
            
    def setBrightness(self, brightness):
        self.logger.info("Setting brightness to %i" % brightness)
        if self.gpioController:
            self.gpioController.setBacklight(intensity = brightness)
            self.gpioController.setNeedlelight(intensity = min(brightness + 30,100))
            self.gpioController.setStereolight(intensity = brightness)
        self.sendStateToMqtt()
        
    def bluetoothControl(self, enabled):
        self._putJobIntoQueue(lambda: self._bluetoothControl(enabled))
        
    def _bluetoothControl(self, enabled):
        with self.playStateCnd:
            if self.bluetoothEnabled == enabled:
                self.logger.info("BT already in desired state (%s)" % self.bluetoothEnabled)
                return
            self.bluetoothEnabled = enabled
        if enabled:
            self.logger.info("Activating bluetooth")
            self.speak("Aktiviere Bluetooth","de-de",True)
            if self.isPoweredOn():
                self.bluetooth.enable()
        else:
            self.logger.info("Deactivating bluetooth")
            self.speak("Deaktiviere Bluetooth","de-de",True)
            if self.isPoweredOn():
                self.bluetooth.disable()
    
    def setSkipMqttUpdates(self, skip):
        self.logger.debug("setSkipMqttUpdates(skip='%s')" % skip)
        self._putJobIntoQueue(lambda: self._setSkipMqttUpdates(skip))
                        
    def _setSkipMqttUpdates(self, skip):
        self.logger.debug("_setSkipMqttUpdates(skip='%s')" % skip)
        with self.playStateCnd:
            self.skipMqttUpdates = skip
            
        if self.skipMqttUpdates is False:
            self.sendStateToMqtt()
        