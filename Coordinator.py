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

class _RadioState(Enum):
    STOPPED = 0
    PLAYING = 1

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
        self.needle = None
        self.wheel = None
        self.logger = logger
        self.ir = None
        self.numChannels = 0
        self.currentChannel = 0
        self.needleStepsPerChannel = 0
        self.radioState = _RadioState.STOPPED
        self.busy = threading.Lock()
        self.poweredOn = False
        self.currentVolume = 0
        
    def connectWifi(self):
        self.gpioController.setStereoBlink(active=True, pause_s=2)
        pass
        
    def connectMqtt(self):
        if self.mqttClient is None:
            return
        self.gpioController.setStereoBlink(active=True, pause_s=1)
        self.mqttClient.connect()
        self.mqttClient.waitForSubscription()
        self.gpioController.setStereolight(PowerState.OFF)

    def powerOff(self):
        with self.busy:
            if self.poweredOn is False:
                return
            self.wheel.disable()
            self.gpioController.disable_power_button()
            self._radioStop()
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
        with self.busy:
            if self.poweredOn is True:
                return
            self.poweredOn = True
            self.logger.info("Powering up...")
            self.gpioController.disable_power_button()
            self.gpioController.setBacklight(PowerState.ON)
            self.gpioController.setStereolight(PowerState.OFF)
            self.gpioController.setPowerAndSpeaker(PowerState.ON)
            self.mqttClient.publish_power_state(PowerState.ON)
            self.wheel.enable()
            self._radioStop()
            self.gpioController.enable_power_button()
            self._radioPlay()
            
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
            if self.mpdClient.loadRadioPlaylist():
                self.numChannels = self.mpdClient.getNumTracksInPlaylist()
            self.logger.info("%i channels in radio playlist" % self.numChannels)
        
        if self.numChannels > 0 and self.config.needle_steps > 0:
            self.needleStepsPerChannel = int((self.config.needle_steps-self.config.needle_left_margin)/self.numChannels)
            self.logger.debug("%i needleStepsPerChannel" % self.needleStepsPerChannel)
            
        self.gpioController.enable_power_button()
        self.ir.enable()
        self.gpioController.setStereoBlink(active=True, pause_s=10)
        
    def invalidChannel(self):
        self.logger.info("Invalid channel requested")
        self.gpioController.setBacklight(PowerState.OFF)
        self.gpioController.setBacklight(PowerState.ON)
    
    def channelUp(self):
        with self.busy:
            if self.radioState is _RadioState.STOPPED:
                return
            if self.currentChannel < (self.numChannels-1):
                self.mpdClient.stop()
                if self.needle is not None:
                    self.needle.moveRight(self.needleStepsPerChannel)
                self.currentChannel+=1
                self.mpdClient.playTitle(self.currentChannel)
            else:
                self.invalidChannel()
    
    def channelDown(self):
        with self.busy:
            if self.radioState is _RadioState.STOPPED:
                return
            if self.currentChannel > 0:
                self.mpdClient.stop()
                self.currentChannel-=1
                if self.needle is not None:
                    self.needle.moveLeft(self.needleStepsPerChannel)
                self.mpdClient.playTitle(self.currentChannel)
            else:
                self.invalidChannel()
    
    def setChannel(self, ch):
        ch-=1 # channel starts with 1 (human friendly numbering), mpd and neelde however start counting at 0
        with self.busy:
            if self.radioState is _RadioState.STOPPED:
                return
            if ch >= 0 and ch < self.numChannels:
                self.mpdClient.stop()
                self.setNeedleForChannel(ch)
                self.mpdClient.playTitle(ch)
            else:
                self.invalidChannel()
                
    def setNeedleForChannel(self, ch):
        channelDiff = ch - self.currentChannel
        if channelDiff > 0:
            self.needle.moveRight(channelDiff * self.needleStepsPerChannel)
        else:
            self.needle.moveLeft(-channelDiff * self.needleStepsPerChannel)
        self.currentChannel = ch 

    def volumeUp(self):
        with self.busy:
            if self.radioState is _RadioState.STOPPED:
                return
            vol = self.currentVolume
            vol+=10
            if vol > 100:
                vol = 100
            self.mpdClient.setVolume(vol)

    def volumeDown(self):
        with self.busy:
            if self.radioState is _RadioState.STOPPED:
                return
            vol = self.currentVolume
            vol-=10
            if vol < 0:
                vol = 0
            self.mpdClient.setVolume(vol)
    
    def setVolume(self, vol):
        with self.busy:
            if self.radioState is _RadioState.STOPPED:
                return
            if vol < 0 or vol > 100:
                self.logger.warn("Received invalid volume: %i", vol)
            else:
                self.mpdClient.setVolume(vol)
    
    def radioStop(self):
        with self.busy:
            self._radioStop()
    
    def _radioStop(self):
        self.mpdClient.stop()
        self.gpioController.setNeedlelight(PowerState.OFF)
        
    def radioPlay(self):
        with self.busy:
            self._radioPlay()
    
    def _radioPlay(self):
        self.gpioController.setNeedlelight(PowerState.ON)
        self.mpdClient.playTitle(self.currentChannel)
    
    def isPoweredOn(self):
        return self.poweredOn
    
    def currentlyPlaying(self, state, channel = None, volume = 0, currentSongInfo = ""):
        if state is True:
            self.radioState = _RadioState.PLAYING
            self.currentVolume = volume
            self.gpioController.setStereolight(PowerState.ON)
            self.mqttClient.pubInfo(state, channel+1, volume, currentSongInfo)  # human-readable channel
            if channel is not None and channel != self.currentChannel:
                self.logger.warn("Unexpected channel change, adjusting needle...")
                self.setNeedleForChannel(channel) # also sets self.currentChannel
        else:
            self.radioState = _RadioState.STOPPED
            self.gpioController.setStereolight(PowerState.OFF)            
        
