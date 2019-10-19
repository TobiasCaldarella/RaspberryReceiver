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
        self.logger.info("Power down requested...")
        with self.playStateCnd:
            if self.sleepTimer:
                self.sleepTimer.cancel()
            if self.poweredOn is False:
                return
            self.bluetooth.disable(wait_for_stop = False)
            self.wheel.disable()
            self.gpioController.disable_power_button()
            self._radioStop()
            self.poweredOn = False
            self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd) # bluetooth and radio are stopped, wait for play state to become stopped
            self.logger.info("Powering down...")
            self.gpioController.setStereolight(PowerState.OFF)
            self.gpioController.setBacklight(PowerState.OFF)
            self.gpioController.setNeedlelight(PowerState.OFF)
            self.gpioController.setPowerAndSpeaker(PowerState.OFF)
            self.gpioController.setStereoBlink(active=True, pause_s=10)
            self.mqttClient.publish_power_state(PowerState.OFF)
            self.gpioController.enable_power_button()
    
    def powerOn(self):
        self.logger.info("Power up requested...")
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
            self.needle.setNeedleForChannel(ch=self.currentChannel, cb=self.radioPlay)
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
            if self.needle:
                self.needle.init(self.numChannels)
            
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
            if self.radioState == _RadioState.BLUETOOTH:
                self.logger.debug("Bluetooth active, not changing channel")
                return
            if self.currentChannel < (self.numChannels-1):
                self._radioStop(False)
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
                self.currentChannel+=1
                self.needle.setNeedleForChannel(ch=self.currentChannel,cb=self.radioPlay)
            else:
                self.lightSignal()
                self.logger.info("Invalid channel requested")
    
    def channelDown(self):
        with self.playStateCnd:
            if not self.poweredOn:
                self.logger.info("not powered on, not chanigng channel")
                return
            if self.radioState == _RadioState.BLUETOOTH:
                self.logger.debug("Bluetooth active, not changing channel")
                return
            if self.currentChannel > 0:
                self._radioStop(False)
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
                self.currentChannel-=1
                self.needle.setNeedleForChannel(ch=self.currentChannel,cb=self.radioPlay)
            else:
                self.lightSignal()
                self.logger.info("Invalid channel requested")
    
    def setChannel(self, ch):
        with self.playStateCnd:
            if not self.poweredOn:
                self.logger.info("not powered on, not setting channel")
                return
            if self.radioState == _RadioState.BLUETOOTH:
                self.logger.debug("Bluetooth active, not changing channel")
                return
            if ch >= 0 and ch < self.numChannels:
                self._radioStop(False)
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
                self.currentChannel=ch
                self.needle.setNeedleForChannel(ch=self.currentChannel,cb=self.radioPlay)
            else:
                self.lightSignal()
                self.logger.info("Invalid channel requested")
                
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
                
    def radioRestart(self):
        with self.playStateCnd:
            self._radioPause()
            self._radioPlay()
    
    def _radioStop(self, needleLightOff=True):
        self.mpdClient.stop()
        if needleLightOff:
            self.gpioController.setNeedlelight(PowerState.OFF)
        
    def radioPlay(self):
        with self.playStateCnd:
            self._radioPlay()
    
    def _radioPause(self):
        if not self.poweredOn:
            self.logger.error("Cannot send pause if not powered up")
            return
        self.gpioController.setNeedlelight(PowerState.OFF)
        self.mpdClient.pause()
    
    def _radioPlay(self):
        if self.radioState is _RadioState.BLUETOOTH:
            self.logger.info("Not playing, bluetooth is active!")
            return
        if not self.poweredOn:
            self.logger.error("Will start play, not in powered up state")
            return
        self.gpioController.setNeedlelight(PowerState.ON)
        self.mpdClient.playTitle(self.currentChannel)
    
    def isPoweredOn(self):
        return self.poweredOn
    
    def waitForRadioState(self, desiredState, lock=None):
        if lock is None:
            self.logger.error("Need a lock!!")
            return False
        
        self.logger.debug("radioState is '%s'" % self.radioState)
        while self.radioState != desiredState:
            self.logger.debug("waiting for radioState to become '%s'..." % desiredState)
            if self.playStateCnd.wait(timeout=10) is False:
                self.logger.warn("timeout while waiting for state update!")
                return False
            self.logger.debug("radioState is '%s'" % self.radioState)
        return True
    
    def bluetoothPlaying(self, active):
        self.logger.info("Coordinator.bluetoothPlaying called with active = '%i'" % active)
        with self.playStateCnd:
            if active is True and self.radioState is not _RadioState.BLUETOOTH:
                if not self.poweredOn:
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
        self.radioState = state
        self.playStateCnd.notify_all() # update done, notify
        if (state == _RadioState.PLAYING):
            self.gpioController.setStereolight(PowerState.ON)
        elif (state == _RadioState.STOPPED):
            self.gpioController.setStereolight(PowerState.OFF)  
        elif (state == _RadioState.BLUETOOTH):
            self.gpioController.setStereoBlink(active=True, pause_s=1)          
    
    def currentlyPlaying(self, mpdPlaying, channel = None, volume = None, currentSongInfo = None):
        self.logger.debug("updating playing-state...")
        with self.playStateCnd:
            if volume is not None:
                self.currentVolume = volume
            
            if self.radioState is not _RadioState.BLUETOOTH:
                if mpdPlaying is True:
                    self._setRadioState(_RadioState.PLAYING)
                else:
                    self._setRadioState(_RadioState.STOPPED)
            state = self.radioState

            if channel is not None and channel != self.currentChannel and state is _RadioState.PLAYING:
                self.logger.warn("Unexpected channel change, adjusting needle and informing mqtt...")
                self.currentChannel = channel
                self.needle.setNeedleForChannel(channel)
                
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
            self.logger.debug("playing-state updated, notification sent")

    def setBrightness(self, brightness):
        if self.gpioController:
            self.gpioController.setBacklight(intensity = brightness)
        if self.mqttClient:
            self.mqttClient.pubInfo(brightness=brightness)