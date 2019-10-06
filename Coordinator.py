'''
Created on 08.08.2019

@author: tobias
'''
from GpioController import PowerState
from MpdClient import MpdClient
from IR import IR
import threading
from enum import Enum
import time
from Bluetooth import Bluetooth

class _RadioState(Enum):
    STOPPED = 0
    PLAYING = 1
    BLUETOOTH = 2

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
        self.needle = None
        self.wheel = None
        self.logger = logger
        self.ir = None
        self.numChannels = 0
        self.currentChannel = 0
        self.needleStepsPerChannel = 0
        self.radioState = _RadioState.STOPPED
        self.poweredOn = False
        self.currentVolume = 0
        self.sleepTimer = None
        self.playStateCnd = threading.Condition()
        
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

    def powerOff(self):
        with self.playStateCnd:
            if self.sleepTimer:
                self.sleepTimer.cancel()
            if self.poweredOn is False:
                return
            self.bluetooth.disable(wait_for_stop = False)
            self.wheel.disable()
            self.gpioController.disable_power_button()
            self._radioStop()
            self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd) # bluetooth and radio are stopped, wait for play state to become stopped
            self.poweredOn = False
            self.logger.info("Powering down...")
            self.gpioController.setStereolight(PowerState.OFF)
            self.gpioController.setBacklight(PowerState.OFF)
            self.gpioController.setNeedlelight(PowerState.OFF)
            self.gpioController.setPowerAndSpeaker(PowerState.OFF)
            self.gpioController.setStereoBlink(active=True, pause_s=10)
            self.mqttClient.publish_power_state(PowerState.OFF)
            self.gpioController.enable_power_button()
    
    def powerOn(self):
        with self.playStateCnd:
            if self.sleepTimer:
                self.sleepTimer.cancel()
            if self.poweredOn is True:
                return
            self.poweredOn = True
            self.logger.info("Powering up...")
            self.gpioController.disable_power_button()
            self.gpioController.setBacklight(PowerState.ON)
            self.gpioController.setStereolight(PowerState.OFF)
            self.gpioController.setPowerAndSpeaker(PowerState.ON)
            if self.mqttClient is not None:
                self.mqttClient.publish_power_state(PowerState.ON)
            self._radioStop()
            self.radioState = _RadioState.STOPPED
            self.gpioController.enable_power_button()
            self._radioPlay()
            self.bluetooth.enable()
            self.wheel.enable()
            
    def sleep(self, time_m):
        with self.playStateCnd:
            if self.sleepTimer:
                self.sleepTimer.cancel()
            self.lightSignal()
            
            if time_m > 0:
                self.logger.info("Sleep set to %i minutes" % time_m)
                self.sleepTimer = threading.Timer(time_m * 60, self.powerOff)
                self.sleepTimer.start()
                self.setBrightness(self.config.backlight_sleep_brightness)
            else:
                self.logger.info("Sleep cancelled")
                self.setBrightness(self.config.backlight_default_brightness)
            
    def initialize(self):
        self.gpioController.setStereoBlink(active=True, pause_s=0)
        # todo: maybe do this in background?
        if self.needle is not None:
            self.needle.moveLeft(self.config.needle_steps)
            self.needle.moveRight(self.config.needle_left_margin)
            
        self.ir.connect()
        self.connectWifi()
        
        # connect MPD client and load playlist
        if self.connectMqtt() is not True:
            self.logger.warn("Could not connect to MQTT. Disabled...")
            self.mqttClient = None
            
        if self.mpdClient.connect() is not True:
            self.logger.warn("Could not connect to MPD. Disabled...");
            self.mpdClient = None
        else:
            self.gpioController.setStereoBlink(active=True, pause_s=3)
            if self.mpdClient.loadRadioPlaylist():
                self.numChannels = self.mpdClient.getNumTracksInPlaylist()
            self.logger.info("%i channels in radio playlist" % self.numChannels)
        
        if self.numChannels > 0 and self.config.needle_steps > 0:
            self.needleStepsPerChannel = int((self.config.needle_steps-self.config.needle_left_margin)/self.numChannels)
            self.logger.debug("%i needleStepsPerChannel" % self.needleStepsPerChannel)
            
        if self.bluetooth is not None:
            self.bluetooth.initialize()
            
        self.gpioController.enable_power_button()
        self.ir.enable()
        self.gpioController.setStereoBlink(active=True, pause_s=10)
        
    def lightSignal(self):
        intensity = self.gpioController.backlightIntensity
        if intensity == 0:
            self.gpioController.setBacklight(PowerState.ON, self.config.backlight_default_brightness)
        else:
            self.gpioController.setBacklight(PowerState.OFF)
        self.gpioController.setBacklight(PowerState.ON, intensity)
    
    def channelUp(self):
        with self.playStateCnd:
            if not self.poweredOn:
                self.logger.info("not powered on, not changing channel")
                return
            if self.currentChannel < (self.numChannels-1):
                self._radioStop(False)
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
                self._setNeedleForChannel(self.currentChannel+1) # this sets self.currentChannel!
                self._radioPlay()
            else:
                self.lightSignal()
                self.logger.info("Invalid channel requested")
    
    def channelDown(self):
        with self.playStateCnd:
            if not self.poweredOn:
                self.logger.info("not powered on, not chanigng channel")
                return
            if self.currentChannel > 0:
                self._radioStop(False)
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
                self._setNeedleForChannel(self.currentChannel-1) # this sets self.currentChannel!
                self._radioPlay()
            else:
                self.lightSignal()
                self.logger.info("Invalid channel requested")
    
    def setChannel(self, ch):
        ch-=1 # channel starts with 1 (human friendly numbering), mpd and neelde however start counting at 0
        with self.playStateCnd:
            if not self.poweredOn:
                self.logger.info("not powered on, not setting channel")
                return
            if ch >= 0 and ch < self.numChannels:
                self._radioStop(False)
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
                self._setNeedleForChannel(ch)
                self._radioPlay()
            else:
                self.lightSignal()
                self.logger.info("Invalid channel requested")
                
    def _setNeedleForChannel(self, ch):
        if self.needle is None:
            return
        if ch < 0 or ch > self.numChannels:
            self.logger.warn("_setNeedleForChannel(%i): invalid channel" % ch)
            return
        
        channelDiff = ch - self.currentChannel
        if channelDiff > 0:
            self.needle.moveRight(channelDiff * self.needleStepsPerChannel)
        else:
            self.needle.moveLeft(-channelDiff * self.needleStepsPerChannel)
        self.currentChannel = ch
        #self.currentlyPlaying() # update mqtt, will be done quite late otherwise

    def volumeUp(self):
        with self.playStateCnd:
            if not self.poweredOn:
                self.logger.info("not powered on, not changing volume")
                return
            vol = self.currentVolume
            vol+=10
            if vol > 100:
                vol = 100
            self.mpdClient.setVolume(vol)

    def volumeDown(self):
        with self.playStateCnd:
            if not self.poweredOn:
                self.logger.info("not powered on, not changing volume")
                return
            vol = self.currentVolume
            vol-=10
            if vol < 0:
                vol = 0
            self.mpdClient.setVolume(vol)
    
    def setVolume(self, vol):
        with self.playStateCnd:
            if not self.poweredOn:
                self.logger.info("not powered on, not setting volume")
                return
            if vol < 0 or vol > 100:
                self.logger.warn("Received invalid volume: %i", vol)
            else:
                self.mpdClient.setVolume(vol)
                self.currentVolume = vol
    
    def radioStop(self, waitForStop = True):
        with self.playStateCnd:
            self._radioStop()
            if waitForStop:
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
    
    def _radioStop(self, needleLightOff=True):
        self.mpdClient.stop()
        if needleLightOff:
            self.gpioController.setNeedlelight(PowerState.OFF)
        
    def radioPlay(self):
        with self.playStateCnd:
            self._radioPlay()
    
    def _radioPlay(self):
        if self.radioState is _RadioState.BLUETOOTH:
            self.logger.info("Not playing, bluetooth is active!")
            return
        self.gpioController.setNeedlelight(PowerState.ON)
        self.mpdClient.playTitle(self.currentChannel)
    
    def isPoweredOn(self):
        return self.poweredOn
    
    def waitForRadioState(self, desiredState, lock=None):
        if lock is None:
            lock = self.playStateCnd
        while self.radioState != desiredState:
            self.logger.debug("waiting for radioState to become '%s'..." % desiredState)
            if self.playStateCnd.wait(timeout=10) is False:
                self.logger.warn("timeout while waiting for state update!")
                return False
        self.logger.debug("radioState is '%s'" % desiredState)
        return True
    
    def bluetoothPlaying(self, active):
        self.logger.info("Coordinator.bluetoothPlaying called with active = '%i'" % active)
        with self.playStateCnd:
            if not self.poweredOn:
                return
            if active is True and self.radioState is not _RadioState.BLUETOOTH:
                self._radioStop()
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
                self.radioState = _RadioState.BLUETOOTH # bluetooth state won't be overwritten by status updates
                self.gpioController.setBacklight(PowerState.OFF)
                self.gpioController.setBacklight(PowerState.ON)
                self.gpioController.setStereoBlink(active=True, pause_s=1)
            elif active is False and self.radioState is _RadioState.BLUETOOTH:
                self.gpioController.setBacklight(PowerState.OFF)
                self.gpioController.setBacklight(PowerState.ON)
                self.gpioController.setStereolight(PowerState.OFF)
                self.radioState = _RadioState.STOPPED
                self._radioPlay() 
            self.playStateCnd.notify_all()           
    
    def currentlyPlaying(self, mpdPlaying=None, channel = None, volume = None, currentSongInfo = None):
        # todo: set condition variable to wait for updates, especially on playing state and check with double check anti pattern
        self.logger.debug("updating playing-state...")
        with self.playStateCnd:
            if volume is not None:
                self.currentVolume = volume
            
            if mpdPlaying is not None and self.radioState is not _RadioState.BLUETOOTH: # do not overwrite bluetooth if volume etc. was changed
                if mpdPlaying is True:
                    self.radioState = _RadioState.PLAYING
                    self.gpioController.setStereolight(PowerState.ON)            
                else:
                    self.radioState = _RadioState.STOPPED
                    self.gpioController.setStereolight(PowerState.OFF) 
            state = self.radioState
            
            if channel is not None and channel != self.currentChannel and state is _RadioState.PLAYING:
                self.logger.warn("Unexpected channel change, adjusting needle and informing mqtt...")
                self._setNeedleForChannel(channel) # also sets self.currentChannel
                
            if self.mqttClient is not None:
                if self.isPoweredOn():
                    self.mqttClient.publish_power_state(PowerState.ON)
                else:
                    self.mqttClient.publish_power_state(PowerState.OFF)
                    
                if self.gpioController is not None:
                    brightness = self.gpioController.backlightIntensity
                else:
                    brightness = None
                    
                self.mqttClient.pubInfo(state, self.currentChannel+1, self.currentVolume, currentSongInfo, self.numChannels, brightness)  # human-readable channel
            self.playStateCnd.notify_all() # update done, notify
            self.logger.debug("playing-state updated, notification sent")

    def setBrightness(self, brightness):
        if self.gpioController:
            self.gpioController.setBacklight(intensity = brightness)
        if self.mqttClient:
            self.mqttClient.pubInfo(brightness=brightness)