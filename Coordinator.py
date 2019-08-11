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
        self.mpdClient.connect()  
        if self.mpdClient.loadRadioPlaylist():
            self.numChannels = self.mpdClient.getNumTracksInPlaylist()
        self.logger.info("%i channels in radio playlist" % self.numChannels)
        
        if self.numChannels > 0 and self.config.needle_steps > 0:
            self.needleStepsPerChannel = int((self.config.needle_steps-self.config.needle_left_margin)/self.numChannels)
            self.logger.debug("%i needleStepsPerChannel" % self.needleStepsPerChannel)
            
        self.connectMqtt()
        self.gpioController.enable_power_button()
        self.ir.enable()
        self.gpioController.setStereoBlink(active=True, pause_s=10)
        
    def channelUp(self):
        with self.busy:
            if self.radioState is _RadioState.STOPPED:
                return
            self.mpdClient.stop()
            if self.currentChannel < (self.numChannels-1):
                if self.needle is not None:
                    self.needle.moveRight(self.needleStepsPerChannel)
                self.currentChannel+=1
                self.mpdClient.playTitle(self.currentChannel)
    
    def channelDown(self):
        with self.busy:
            if self.radioState is _RadioState.STOPPED:
                return
            self.mpdClient.stop()
            if self.currentChannel > 0:
                self.currentChannel-=1
                if self.needle is not None:
                    self.needle.moveLeft(self.needleStepsPerChannel)
                self.mpdClient.playTitle(self.currentChannel)
    
    def setChannel(self, ch):
        with self.busy:
            if self.radioState is _RadioState.STOPPED:
                return
            if ch < 0 or ch >= self.numChannels:
                return
            channelDiff = ch - self.currentChannel
            if channelDiff > 0:
                self.needle.moveRight(channelDiff * self.needleStepsPerChannel)
            else:
                self.needle.moveLeft(-channelDiff * self.needleStepsPerChannel)
            self.currentChannel = ch
            self.mpdClient.playTitle(ch)
        
    def radioStop(self):
        with self.busy:
            self._radioStop()
    
    def _radioStop(self):
        self.radioState = _RadioState.STOPPED
        self.mpdClient.stop()
        self.gpioController.setNeedlelight(PowerState.OFF)
        
    def radioPlay(self):
        with self.busy:
            self._radioPlay()
    
    def _radioPlay(self):
        self.gpioController.setNeedlelight(PowerState.ON)
        self.radioState = _RadioState.PLAYING
        self.mpdClient.playTitle(self.currentChannel)
    
    def isPoweredOn(self):
        return self.poweredOn
    
    def currentlyPlaying(self, state):
        if state is True:
            self.gpioController.setStereolight(PowerState.ON)
        else:
            self.gpioController.setStereolight(PowerState.OFF)
        
        
        