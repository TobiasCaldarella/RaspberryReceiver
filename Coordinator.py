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
import urllib.request 
from time import sleep
from Configuration import _RadioState

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
        self.currentVolume = 70
        self.sleepTimer = None
        self.playStateCnd = threading.Condition()
        self.currentSongInfo = {}
        self.textToSpeech = None
        
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
            self.mpdClient.playSingleFile("silence.mp3")
            self.needle.setNeedleForChannel(ch=self.currentChannel, cb=self.radioPlay)
            self.bluetooth.enable()
            self.wheel.enable()
        self.mpdClient.notifyCoordinator = True # now we are ready to receive status updates
            
    def sleep(self, time_m):
        with self.playStateCnd:
            if self.sleepTimer:
                self.sleepTimer.cancel()
            self.lightSignal()
            
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
            
        self.ir.connect()
        self.connectWifi()
            
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
        self.ir.enable()
        self.gpioController.setStereoBlink(active=True, pause_s=10)
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
        
    def invertNeedleLightState(self, restore = False):
        with self.playStateCnd:
            if restore == True:
                if self.radioState == _RadioState.PLAYING:
                    self.gpioController.setNeedlelight(PowerState.ON)
                else:
                    self.gpioController.setNeedlelight(PowerState.OFF)
            else:    
                if self.gpioController.needleLightState == PowerState.ON:
                    self.gpioController.setNeedlelight(PowerState.OFF)
                else:
                    self.gpioController.setNeedlelight(PowerState.ON)
    
    def setChannel(self, channel, relative = False, setIfPowerOff = False):
        with self.playStateCnd:
            if self.radioState == _RadioState.BLUETOOTH:
                self.logger.debug("Bluetooth active, not changing channel")
                return
            
            if relative is True:
                newChannel = self.currentChannel + channel
            else:
                newChannel = channel
                
            if (newChannel < (self.numChannels-1)) and (newChannel >= 0):
                if not self.poweredOn:
                    if setIfPowerOff:
                        self.logger.info("not powered on, only setting selected channel %i" % newChannel)
                        self.currentChannel = newChannel
                    else:
                        self.logger.info("not powered on, not setting channel")
                    return
                self.logger.info("setting channel to %i" % newChannel)
                self._radioStop(False)
                self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
                self.currentChannel = newChannel
                self.gpioController.setNeedlelight(PowerState.ON)
                self.needle.setNeedleForChannel(ch=self.currentChannel,cb=lambda: self.radioPlay(announceChannel=True))
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
        
    def radioPlay(self, announceChannel = False):
        with self.playStateCnd:
            self._radioPlay(announceChannel=announceChannel)
    
    def _radioPause(self):
        if not self.poweredOn:
            self.logger.error("Cannot send pause if not powered up")
            return
        self.gpioController.setNeedlelight(PowerState.OFF)
        self.mpdClient.pause()
    
    def _radioPlay(self, announceChannel = False):
        if self.radioState is _RadioState.BLUETOOTH:
            self.logger.info("Not playing, bluetooth is active!")
            return
        if not self.poweredOn:
            self.logger.error("Will not start play, not in powered up state")
            return
        self.gpioController.setNeedlelight(PowerState.ON)
        self.mpdClient.setVolume(self.currentVolume)
        if announceChannel:
            channelName = self.channels[self.currentChannel]
            lang='de-de'
            if channelName.find('|lang=') >= 0:
                channelName = channelName.split('|lang=')
                lang = channelName[1]
                channelName = channelName[0]
                
            self.textToSpeech.speak(text=channelName,lang=lang);
        self.mpdClient.playTitle(self.currentChannel)
    
    def isPoweredOn(self):
        return self.poweredOn
    
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
        self.logger.debug("setting radio state to '%s'" % state)
        self.radioState = state
        self.playStateCnd.notify_all() # update done, notify
        if (state == _RadioState.PLAYING):
            self.gpioController.setStereolight(PowerState.ON)
            self.gpioController.setNeedlelight(PowerState.ON)
        elif (state == _RadioState.STOPPED):
            self.gpioController.setStereolight(PowerState.OFF)  
        elif (state == _RadioState.BLUETOOTH):
            self.gpioController.setStereoBlink(active=True, pause_s=1)          
    
    def playSingleFile(self, file):
        self.logger.debug("playSingleFile('%s')" % file)
        with self.playStateCnd:
            self.mpdClient.playSingleFile(file)
    
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
                radioState = self.radioState
                currentChannel = self.currentChannel
                currentVolume = self.currentVolume
                currentSongInfo = self.currentSongInfo
                numChannels = self.numChannels
                if self.gpioController is not None:
                    brightness = self.gpioController.backlightIntensity
                else:
                    brightness = None
                poweredOn = self.poweredOn
                    
            self.mqttClient.pubInfo(radioState, currentChannel+1, currentVolume, currentSongInfo, numChannels, brightness, poweredOn)  # human-readable channel

    def setBrightness(self, brightness):
        if self.gpioController:
            self.gpioController.setBacklight(intensity = brightness)
        self.sendStateToMqtt()