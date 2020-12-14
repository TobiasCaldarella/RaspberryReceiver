'''
Created on 08.08.2019

@author: tobias
'''
from GpioController import PowerState
import MpdClient
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

from enum import Enum
import sys
from threading import Event, Lock
from _queue import Empty
from MpdClient import MpdState
import traceback

class eStates(Enum):
    ERROR = 0
    POWERED_OFF = 1
    STOPPED = 2
    RADIO_ACTIVE = 3
    BLUETOOTH_PLAYING = 4
    UPNP_PLAYING = 5
    MPD_MUTED = 6
    SPEAKING = 7
    IN_TRANSIT = 8

class State(object):
    def __init__(self, coordinator, eState: eStates, transitionsFrom): # transitions: {eStates.ERROR: gotoErrorState, eStates.POWERED_OFF: gotoPoweredOff}
        self.properties = {}
        self.eState = eState
        self.transitionsFrom = transitionsFrom # new eState/state type -> transition function
        self.logger = coordinator.logger
        self.coordinator = coordinator
        self.mpdClient = coordinator.mpdClient
        self.gpioController = coordinator.gpioController
        
    def getEstate(self):
        return self.eState
    
    def getString(self):
        return self.getEstate().name
    
    def transitInto(self):
        oldState = self.coordinator.currentState
        if not oldState.getEstate() in self.transitionsFrom:
            self.logger.error("Coordinator: No transition from state '%s' to '%s'" % (oldState.getEstate(), self.eState))
        self.logger.info("Coordinator: Trying transition '%s' => '%s'" % (oldState.getEstate(), self.eState))
        self.coordinator.currentState = StateInTransit()
        try:
            if self.transitionsFrom[oldState.getEstate()]() is True: # call registered transition function
                self.logger.info("Coordinator: Transition '%s' => '%s' successful" % (oldState.getEstate(), self.eState))
                self.coordinator.currentState = self
                return True
            else:
                self.logger.error("Coordinator: Transition failed with bad return value")
        except Exception as ex:
            self.logger.error("Coordinator: Transition failed with exception: '%s'" % ex)
        return False
    
class StateInTransit(object):
    def __init__(self):
        pass
    
    def getEstate(self):
        return eStates.IN_TRANSIT
    
    def getString(self):
        return eStates.IN_TRANSIT.name
    
class StateError(State):
    def __init__(self, coordinator, errorInfo):
        self.errorInfo = errorInfo
        transitionsFrom = {
            eStates.POWERED_OFF: self.fromAny,
            eStates.STOPPED: self.fromAny,
            eStates.RADIO_ACTIVE: self.fromAny,
            eStates.SPEAKING: self.fromAny,
            eStates.MPD_MUTED: self.fromAny,
            eStates.UPNP_PLAYING: self.fromAny,
            eStates.BLUETOOTH_PLAYING: self.fromAny,
            eStates.IN_TRANSIT: self.fromAny
        }
        State.__init__(self, coordinator, eStates.ERROR, transitionsFrom)
        
    def printError(self):
        self.logger.error("StateError: " + self.errorInfo)
    
    def fromAny(self):
        # reset everything and go to an error state
        try:    
            self.mpdClient.setCoordinatorNotification(False)
        except Exception as ex:
                self.logger.error("StateError: setCoordinatorNotification failed")
                self.logger.error(ex)
        try:
            self.mpdClient.stop()
        except Exception as ex:
            self.logger.error("StateError: mpdClient.stop failed")
            self.logger.error(ex)
            
        try:
            self.mpdClient.stopQueueHandler() 
        except Exception as ex:
            self.logger.error("StateError: mpdClient.stopQueueHandler failed")
            self.logger.error(ex)
            
        try:
            self.coordinator.setBrightness(self.coordinator.config.backlight_default_brightness)
        except Exception as ex:
            self.logger.error("StateError: set brightness failed")
            self.logger.error(ex)
            
        try:
            self.gpioController.setBacklightBlink(True)
        except Exception as ex:
            self.logger.error("StateError: setBacklightBlink failed")
            self.logger.error(ex)
            
        try:
            self.gpioController.setStereoBlink(True)
        except Exception as ex:
            self.logger.error("StateError: setStereoBlink failed")
            self.logger.error(ex)
            
        try:
            self.gpioController.setNeedlelight(PowerState.OFF)
        except Exception as ex:
            self.logger.error("StateError: setNeedlelight failed")
            self.logger.error(ex)
            
        try:
            self.coordinator.signal_strength_meter.disable()
        except Exception as ex:
            self.logger.error("StateError: signal_strength_meter failed")
            self.logger.error(ex)
            
        try:
            self.coordinator.powerState = _RadioPowerState.POWERED_UP
        except Exception as ex:
            self.logger.error("StateError: _RadioPowerState failed")
            self.logger.error(ex)
            
        #try:
        #    self.mpdClient.startQueueHandler()
        #except Exception as ex:
        #    self.logger.error("StateError: startQueueHandler failed")
        #    self.logger.error(ex)
            
        #try:
        #    self.mpdClient.setVolume(100) # set this before accepting any feedback from mpd
        #except Exception as ex:
        #    self.logger.error("StateError: setVolume failed")
        #    self.logger.error(ex)
            
        try:
            self.coordinator.needle.setNeedleForChannel(ch=self.coordinator.currentChannel, relative=False)
        except Exception as ex:
            self.logger.error("StateError: setNeedleForChannel failed")
            self.logger.error(ex)
            
        if self.coordinator.bluetooth:
            try:
                self.coordinator.bluetooth.disable()
            except Exception as ex:
                self.logger.error("StateError: bluetooth failed")
                self.logger.error(ex)
                
        if self.coordinator.wheel:
            try:
                self.coordinator.wheel.disable()
            except Exception as ex:
                self.logger.error("StateError: wheel failed")
                self.logger.error(ex)
                
        if self.coordinator.volumeKnob:
            try:
                self.coordinator.volumeKnob.disable()
            except Exception as ex:
                self.logger.error("StateError: volumeKnob failed")
                self.logger.error(ex)
                
        return True
    
class StatePoweredOff(State):
    def __init__(self, coordinator):
        transitionsFrom = {
            eStates.STOPPED: self.fromStopped,
            eStates.ERROR: self.fromStopped,
            eStates.IN_TRANSIT: self.fromStopped
        }
        State.__init__(self, coordinator, eStates.POWERED_OFF, transitionsFrom)
        
    def fromStopped(self):
        self.coordinator.powerState = _RadioPowerState.POWERING_DOWN
        if self.coordinator.sleepTimer:
            self.coordinator.sleepTimer.cancel()
        self.coordinator._bluetoothControl(False, False, True)
        if self.coordinator.wheel:
            self.coordinator.wheel.disable()
        if self.coordinator.volumeKnob:
            self.coordinator.volumeKnob.disable()
        if self.coordinator.dlnaRenderer:
            self.coordinator.dlnaRenderer.stop()
        self.mpdClient.stopQueueHandler()
        self.mpdClient.setCoordinatorNotification(False)
        self.logger.info("Powering down amp...")
        self.gpioController.setStereolight(PowerState.OFF)
        self.gpioController.setBacklight(PowerState.OFF)
        self.gpioController.setNeedlelight(PowerState.OFF)
        self.gpioController.setPowerAndSpeaker(PowerState.OFF) # speakers disconnected, amp powered down. But there is still enough power in the capacitors for the volume control board to work and gracefully shut down
        self.coordinator.vcb.powerOff()
        self.gpioController.setStereoBlink(active=True, pause_s=10)
        self.coordinator.signal_strength_meter.disable()
        self.coordinator.setBrightness(self.coordinator.config.backlight_default_brightness)
        self.coordinator.powerState = _RadioPowerState.POWERED_DOWN
        self.coordinator.sendStateToMqtt()
        return True
    
class StateStopped(State):
    def __init__(self, coordinator):
        transitionsFrom = {
            eStates.POWERED_OFF: self.fromPoweredOff,
            eStates.STOPPED: self.fromStopped,
            eStates.RADIO_ACTIVE: self.fromRadioActive,
            eStates.MPD_MUTED: self.fromMpdMuted,
            eStates.UPNP_PLAYING: self.fromUpnpPlaying
        }
        State.__init__(self, coordinator, eStates.STOPPED, transitionsFrom)
    
    def fromStopped(self):
        self.logger.info("Already stopped, not doing anything")
        return True
    
    def fromPoweredOff(self):
        if self.coordinator.sleepTimer:
            self.coordinator.sleepTimer.cancel()
        self.logger.info("Powering up amp...")
        self.coordinator.signal_strength_meter.enable()
        self.coordinator.setBrightness(self.coordinator.config.backlight_default_brightness)
        self.gpioController.setBacklight(PowerState.ON)
        self.gpioController.setStereolight(PowerState.OFF)
        self.gpioController.setNeedlelight(PowerState.ON)
        self.gpioController.setPowerAndSpeaker(PowerState.ON) #async, returns before speakers are connected but after amp has power
        self.coordinator.powerState = _RadioPowerState.POWERING_UP
        self.coordinator.loudness = self.gpioController.getLoudnessEnabled()
        self.coordinator.vcb.setLoudness(self.coordinator.loudness)
        self.coordinator.vcb.setVolume(self.coordinator.currentVolume)
        self.coordinator.vcb.powerOn()
        self.mpdClient.startQueueHandler()
        self.mpdClient.setVolume(100) # set this before accepting any feedback from mpd
        self.coordinator.needle.setNeedleForChannel(ch=self.coordinator.currentChannel, relative=False)
        if self.coordinator.wheel:
            self.coordinator.wheel.enable()
        if self.coordinator.volumeKnob:
            self.coordinator.volumeKnob.enable()
        
        #if self.coordinator.upmp:
        #    self.coordinator.upmp.enable()
        
        self.mpdClient.setCoordinatorNotification(True) # now we are ready to receive status updates
        self.mpdClient.setVolume(100) # and this just triggers an update of the mpd state so we can get a current status now
        self.coordinator.powerState = _RadioPowerState.POWERED_UP # ok, not really correct but ok as a workaround
        self.coordinator._bluetoothControl(self.gpioController.getBluetoothEnabled(), False, True)
        self.coordinator._setSkipMqttUpdates(False)
        return True
    
    def fromRadioActive(self):
        self.mpdClient.stop()
        return self.mpdClient.waitForMpdState(MpdState.STOPPED)
    
    def fromMpdMuted(self):
        self.mpdClient.stop()
        return self.mpdClient.waitForMpdState(MpdState.STOPPED)
    
    def fromUpnpPlaying(self):
        self.mpdClient.stop()
        self.gpioController.setNeedlelight(PowerState.ON)
        return self.mpdClient.waitForMpdState(MpdState.STOPPED)
    
class StateRadioActive(State):
    def __init__(self, coordinator, channel):
        transitionsFrom = {
            eStates.STOPPED: self.fromStopped,
            eStates.MPD_MUTED: self.fromMpdMuted
        }
        State.__init__(self, coordinator, eStates.RADIO_ACTIVE, transitionsFrom)
        self.channel = channel
        
    def fromStopped(self):
        # needle position already set by caller, we just start playing right away
        mpdVolume = 100
        self.gpioController.setStereoBlink(True)
        self.gpioController.setNeedlelight(PowerState.ON)
        self.mpdClient.setVolume(mpdVolume)
        self.mpdClient.loadRadioPlaylist()
        self.mpdClient.playTitle(playlistPosition=self.channel)
        # wir warten hier nicht darauf, dass mpd mit dem abspielen beginnt. Das kann länger dauern und ist auch egal.
        # fehlerfall sollte durch timeouts in mpdclient abgefangen und signalisiert werden
        return True
    
    def fromMpdMuted(self):
        self.mpdClient.mute(False)
        return True
    
# class StateMpdPlaying(State):
#     def __init__(self, coordinator):
#         transitionsFrom = {
#             eStates.RADIO_ACTIVE: self.fromRadioActive
#         }
#         State.__init__(self, coordinator, eStates.MPD_PLAYING, transitionsFrom)
#         
#     def fromRadioStarting(self):
#         self.gpioController.setStereolight(PowerState.ON)
#         return True
#     
# class StateMpdStopped(State):
#     def __init__(self, coordinator):
#         transitionsFrom = {
#             eStates.MPD_PLAYING: self.fromMpdPlaying
#         }
#         State.__init__(self, coordinator, eStates.MPD_MUTED, transitionsFrom)
#         
#     def fromMpdPlaying(self):
#         self.gpioController.setStereolight(PowerState.OFF)
#         return True
#     
# mpd ist eigentlich mehr oder weniger aktiv aber mpd volume auf 0 gesetzt. nicht kompatibel mit BT
class StateMuted(State):
    def __init__(self, coordinator):
        transitionsFrom = {
            eStates.RADIO_ACTIVE: self.fromRadioActive,
            eStates.STOPPED: self.fromStopped,
            eStates.SPEAKING: self.fromSpeaking
        }
        State.__init__(self, coordinator, eStates.MPD_MUTED, transitionsFrom)
        
    def fromRadioActive(self):
        self.mpdClient.mute(True)
        return True
    
    def fromSpeaking(self):
        return True
    
    def fromStopped(self):
        return True
    
class StateSpeaking(State):
    def __init__(self, coordinator):
        transitionsFrom = {
            eStates.MPD_MUTED: self.fromMpdMuted
        }
        State.__init__(self, coordinator, eStates.SPEAKING, transitionsFrom)
        
    def fromMpdMuted(self):
        #self.coordinator.textToSpeech.speak(self.text, self.language) # wir sollten nicht im übergang sprechen (und blockieren!)
        # sprechen methode muss asynchron werden
        # und abbrechbar beim übergang in andere stati
        return True
    
class StateUpnpPlaying(State):
    def __init__(self, coordinator):
        transitionsFrom = {
            eStates.STOPPED: self.fromStopped
        }
        State.__init__(self, coordinator, eStates.UPNP_PLAYING, transitionsFrom)
    
    def fromStopped(self):
        self.gpioController.setNeedleLightBlink(True)
        self.gpioController.setStereoBlink(True)
        return True

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
        self.volumeKnob = None
        self.poti = None
        self.vcb = None
        self.logger = logger
        self.ir = None
        self.signal_strength_meter = None
        self.numChannels = 0
        self.currentChannel = 0
        self.needleStepsPerChannel = 0
        self.powerState = _RadioPowerState.POWERED_DOWN
        self.currentVolume = 1
        self.loudness = False
        self.sleepTimer = None
        self.playStateCnd = threading.Condition()
        self.currentSongInfo = {}
        self.textToSpeech = None
        self.workerThread = threading.Thread(target=self.__do_work, name="Coordinator.WorkerThread")
        self.workerThreadInterrupt = Event()
        self.skipMqttUpdates = True
        self.job_queue = queue.Queue(30)
        self.job_queue_mtx = Lock()
        self.announceTimer = None
        self.dlnaRenderer = None
        self.upmp = None
    
        self.currentState = None
        
    def __do_work(self):
        self.logger.debug("Worker thread started")
        while True:
            self.logger.debug("Waiting for item in queue")
            job = self.job_queue.get(block=True)
            if job is not None:
                self.logger.info("Running job: '%s'" % job)
                try:
                    job()
                except Exception as ex:
                    st = ""
                    for line in traceback.format_stack():
                        st = st + "\n" + line
                    self.logger.error("Exception in worker thread: '%s' @%s" % (ex, st))
                    self.currentState = StateError(self, "Exception in worker thread")
            self.job_queue.task_done()
            if job is None:
                self.logger.debug("Worker thread ended")
                return
                
    ''' clears all pending jobs and interrupts long-running jobs (for now only speech, mpd fading & needle movement) '''
    def __clearJobQueue(self):
        self.logger.info("Clearing job queue")
        with self.job_queue_mtx:
            while not self.job_queue.empty(): # todo protect this against someone else putting stuff in here
                self.job_queue.get(block=False)
                self.job_queue.task_done()
            self.textToSpeech.interrupt_set()
            self.needle.interrupt_set()
            self.mpdClient.interrupt_set()
            self.job_queue.join()
            self.logger.info("job queue empty")
            self.textToSpeech.interrupt_clear()
            self.needle.interrupt_clear()
            self.mpdClient.interrupt_clear()

    def _putJobIntoQueue(self, job):
        try:
            with self.job_queue_mtx:
                self.job_queue.put(job, True, 2)
        except:
            self.logger.error("Could not put job into queue, queue full?")
                
    
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
        
    def gotoErrorState(self, errorDescription):
        self.logger.info("Goto error state requested, flushing coordinator queue...")
        # TODO: 
        #    1. stop queue worker thread
        #    2. trash all items in queue
        #    3. do transition to error in seperate thread
        #    4. restart worker queue thread after transition ->error->stopped
        self._putJobIntoQueue(lambda: self._gotoErrorState(errorDescription))
    
    def _gotoErrorState(self, errorDescription):
        errorState = StateError(self, errorDescription)
        errorState.transitInto()
        # Todo: wait and switch from error to stopped after some time and restart queue worker thread
    
    def gotoStoppedState(self):
        self.logger.info("Goto stopped state requested!")
        self._putJobIntoQueue(self._gotoStoppedState)
        
    def _gotoStoppedState(self):
        newState = StateStopped(self)
        if not newState.transitInto():
            self.currentState = StateError(self, "Failed to stop")
            return False
        
    def gotoRadioActiveState(self):
        self.logger.info("Goto radio active state requested!")
        self._putJobIntoQueue(self._gotoRadioActiveState)
        
    def _gotoRadioActiveState(self):
        newState = StateRadioActive(self, self.currentChannel)
        if newState.transitInto():
            self.logger.info("Radio playing")
        else:
            self.currentState = StateError(self, "Failed to go to radio active state")
            return False
        return True
    
    def _gotoMutedState(self):
        newState = StateMuted(self)
        if newState.transitInto():
            pass
        else:
            self.currentState = StateError(self, "Failed to go to muted state")
            return False
        return True
            
    def _gotoSpeakingState(self):
        newState = StateSpeaking(self)
        if newState.transitInto():
            pass
        else:
            self.currentState = StateError(self, "Failed to go to speaking state")
            return False
        return True
            
    def powerOff(self):
        self.logger.info("Power down requested...")
        if self.announceTimer:
            self.announceTimer.cancel()
        self.__clearJobQueue()
        self._putJobIntoQueue(self._powerOff)
        
    def _powerOff(self):
        self.logger.info("Power down sequence started")
        if self.currentState.getEstate() is eStates.POWERED_OFF:
            self.logger.info("Already powered off, not doing anything")
            return True
        
        if self._gotoStoppedState() is False:
            pass # try to power off anyhow, we might be in error state and this likely will work

        newState = StatePoweredOff(self)
        if not newState.transitInto():
            self.currentState = StateError(self, "Failed to power off")
            return False
        self.logger.info("Powered down")
        return True
    
    def powerOn(self):
        self.logger.info("Power on requested...")                
        self._putJobIntoQueue(self._powerOn)
    
    def _powerOn(self):
        self.logger.info("Power up sequence started...")
        if self.currentState.getEstate() not in [eStates.POWERED_OFF, eStates.ERROR]:
            self.logger.info("Already powered on, not doing anything")
            return True
        
        if self._gotoStoppedState() is False:
            return False
        
        if self._gotoRadioActiveState() is False:
            return False
        return True    
        
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
                self.speak(text=("Schalte in %i Minuten aus." % time_m), lang='de-de')
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
        if self.vcb:
            self.vcb.init()
            
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
        self.currentState = StatePoweredOff(self)
        self.setSkipMqttUpdates(False) # this will send the first update
        
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
        
    def blinkNeedleLight(self, blink = True):
        with self.playStateCnd:
            if blink == False:
                if isinstance(self.currentState, StateRadioActive):
                    self.gpioController.setNeedlelight(PowerState.ON)
                else:
                    self.gpioController.setNeedlelight(PowerState.OFF)
            else:
                self.gpioController.setNeedleLightBlink(active=True, pause_s = 0)
                
    def startRadio(self):
        self.logger.info("restarting radio")
        self.__clearJobQueue() # interrupt anything else
        self._putJobIntoQueue(lambda: self._setChannel(self.currentChannel, False))
    
    def setChannel(self, channel, relative = False, setIfPowerOff = False):
        self.logger.info("channel change requested (channel=%i, relative = %s)" % (channel, relative))
        # wenn sich needle bereits bewegt, bewegung updaten
        if self.needle.updateIfNeedleMoving(ch=channel, relative=relative) is False:
            self.__clearJobQueue() # interrupt anything else
            self._putJobIntoQueue(lambda: self._setChannel(channel, relative))
        return
        
    def _setChannel(self, channel, relative = False):
        if (relative is True and channel is 0) or (relative is False and channel == self.currentChannel and self.currentState.getEstate() is eStates.RADIO_ACTIVE):
            self.logger.info("Coordinator: already in desired channel, not doing anything")
            return

        self._gotoStoppedState()
        newChannel = self.needle.setNeedleForChannel(ch=channel, relative=relative)
        if newChannel is None:
            self.logger.info("Coordinator: setNeedleForChannel cancelled, aborting")
            return
        self.currentChannel = newChannel
        self._gotoRadioActiveState()
        
        # announce channel
        channels = self.mpdClient.getTitlesFromPlaylist()
        channelName = channels[self.currentChannel]
        lang='de-de'
        if channelName.find('|lang=') >= 0:
            channelName = channelName.split('|lang=')
            lang = channelName[1]
            channelName = channelName[0]
        self._speak(channelName, lang)
    
    def volumeUp(self):
        self.logger.info("volumeUp requested")
        self._volumeUp()

    def _volumeUp(self):
        #with self.playStateCnd:
            if not self.isPoweredOn():
                self.logger.info("not powered on, not changing volume")
                return
            vol = self.currentVolume
            vol+=1
            if vol > 66:
                vol = 66
                self.logger.debug("maximum volume reached")
            self.__setVcbAndMpdVolume(vol)
            self.currentVolume = vol
            
    def volumeDown(self):
        self.logger.info("volumeDown requested")
        self._volumeDown()

    def _volumeDown(self):
        #with self.playStateCnd:
            if not self.isPoweredOn():
                self.logger.info("not powered on, not changing volume")
                return
            vol = self.currentVolume
            vol-=1
            if vol < 0:
                self.logger.debug("minimum volume reached")
                vol = 0
            self.__setVcbAndMpdVolume(vol)
            self.currentVolume = vol                
    
    def setVolume(self, vol, waitForPoti = False):
        self.logger.info("setVolume requested (volume = %i)" % vol)
        self._putJobIntoQueue(lambda: self._setVolume(vol, waitForPoti))
    
    def _setVolume(self, vol, waitForPoti):
        with self.playStateCnd:
            if vol < 0 or vol > 66:
                self.logger.warn("Received invalid volume: %i", vol)
            else:
                if self.isPoweredOn():
                    if self.vcb:
                        self.__setVcbAndMpdVolume(vol)
                self.currentVolume = vol
        self.sendStateToMqtt()
        
    def __setVcbAndMpdVolume(self, vol):
        self.mpdClient.setVolume(100)
        self.vcb.setVolume(vol)
            
    def isPoweredOn(self):
        return (self.powerState is _RadioPowerState.POWERED_UP)
    
    #todo make this async?
#     def bluetoothPlaying(self, active):
#         self.logger.info("Coordinator.bluetoothPlaying called with active = '%i'" % active)
#         with self.playStateCnd:
#             if active is True and self.radioState is not _RadioState.BLUETOOTH:
#                 if not self.isPoweredOn():
#                     self.logger.error("Cannot enable bluetooth if not if not powered up!")
#                     return
#                 self._radioStop()
#                 self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
#                 self._setRadioState(_RadioState.BLUETOOTH) # bluetooth state won't be overwritten by status updates
#                 self.gpioController.setBacklight(PowerState.OFF)
#                 self.gpioController.setBacklight(PowerState.ON)
#             elif active is False and self.radioState is _RadioState.BLUETOOTH:
#                 self.gpioController.setBacklight(PowerState.OFF)
#                 self.gpioController.setBacklight(PowerState.ON)
#                 self._setRadioState(_RadioState.STOPPED)
#                 self._radioPlay() 
#             self.playStateCnd.notify_all()           
    
#     def _setRadioState(self, state):
#         self.logger.debug("setting radio state to '%s'" % state)
#         oldState = self.radioState
#         self.radioState = state
#         self.playStateCnd.notify_all() # update done, notify
#         
#         if oldState == state:
#             self.logger.debug("radio state was already '%s', not updating lights" % state)
#         else:
#             if (state == _RadioState.PLAYING):
#                 self.gpioController.setStereolight(PowerState.ON)
#                 self.gpioController.setNeedlelight(PowerState.ON)
#             elif (state == _RadioState.STOPPED):
#                 self.gpioController.setStereolight(PowerState.OFF)
#             elif (state == _RadioState.BLUETOOTH):
#                 self.gpioController.setStereoBlink(active=True, pause_s=1)
#                 self.gpioController.setNeedlelight(PowerState.OFF)
#             elif (state == _RadioState.DLNA):
#                 self.gpioController.setNeedleLightBlink(active=True, pause_s=1)
#                 self.gpioController.setStereolight(PowerState.OFF)
        
    # mutes or unmutes radio (and maybe other sources like bluetooth in future?)    
    def mute(self, mute):
        self.mpdClient.mute(mute)
    
    def speak(self, text, lang, block=False):
        self.logger.debug("Speak '%s', lang '%s'" % (text, lang))
        self._putJobIntoQueue(lambda: self._speak(text, lang))
            
    def _speak(self, text, lang):
        prevState = self.currentState
        if self._gotoMutedState() is False:
            return False
        if self._gotoSpeakingState() is False:
            return False
        # this one here will block the queue, so make it interruptable
        wasInterrupted = False
        if self.textToSpeech.speak(text, lang) is False:
            wasInterrupted = True
        self._gotoMutedState()
        if wasInterrupted:
            return True
        if prevState.transitInto():
            return True
        else:
            self.currentState = StateError(self, "Failed to go back to previous state")
            return False
    
    def mpdUpdateCallback(self):
        self.logger.info("Got update from mpd")
        channel = self.mpdClient.currentSongId
        if channel is not None and channel != self.currentChannel and self.getCurrentState() == eStates.RADIO_ACTIVE:
            self.logger.warn("Unexpected channel change, adjusting needle and informing mqtt...")
            self.currentChannel = channel
            self.needle.setNeedleForChannel(channel)
        
        mpdState = self.mpdClient.getMpdState()
        if mpdState is MpdState.STARTED:
            self.gpioController.setStereolight(PowerState.ON)
        elif mpdState is MpdState.ERROR:
            self.gpioController.setStereoBlink(active=True, pause_s=0)
        elif mpdState is MpdState.STOPPED:
            self.gpioController.setStereolight(PowerState.OFF)
        
        self.sendStateToMqtt()
        
    def getCurrentState(self):
        return self.currentState.getEstate()

    def sendStateToMqtt(self):
        if self.mqttClient:
            self.logger.debug("Sending current state to mqtt")
            with self.playStateCnd:
                if self.skipMqttUpdates:
                    self.logger.info("Skipping MQTT update (skipMqttUpdates=true)")
                    return
                currentChannel = self.currentChannel
                currentVolume = self.currentVolume
                currentSongInfo = self.mpdClient.currentSongInfo
                numChannels = self.numChannels
                if self.gpioController is not None:
                    brightness = self.gpioController.backLight.intensity
                else:
                    brightness = None
                poweredOn = self.isPoweredOn()
                bluetooth = self.bluetoothEnabled
                    
                self.mqttClient.pubInfo(self.getCurrentState().name, currentChannel+1, currentVolume, currentSongInfo, numChannels, brightness, poweredOn, bluetooth)  # human-readable channel
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
        
#     def toggleDlna(self):
#         if (self.radioState is _RadioState.DLNA):
#             self.stopDlna()
#         else: 
#             self.playDlna()
#                 
#     def playDlna(self):
#         self._putJobIntoQueue(self._playDlna)
#     
#     def stopDlna(self):
#         self._putJobIntoQueue(self._stopDlna)
#     
#     def _playDlna(self):
#         with self.playStateCnd:
#             if self.radioState is not _RadioState.PLAYING and self.radioState is not _RadioState.STOPPED:
#                 self.logger.error("Cannot play dlna if radio state is not playing nor stopped")
#                 return
#             elif not self.isPoweredOn():
#                 self.logger.error("Cannot play dlna if not powered up!")
#                 return
#             else:
#                 self._radioStop()
#                 self.gpioController.setBacklight(PowerState.OFF)
#                 self.gpioController.setBacklight(PowerState.ON)
#                 self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
#                 self._speak("DLNA aktiviert", "de-de")
#                 self.dlnaRenderer.start()
#                 self._setRadioState(_RadioState.DLNA) # dlna state won't be overwritten by status updates
#             self.playStateCnd.notify_all()
#     
#     def _stopDlna(self, speak = True):
#         with self.playStateCnd:
#             if self.radioState is _RadioState.DLNA:
#                 self.gpioController.setBacklight(PowerState.OFF)
#                 self.gpioController.setBacklight(PowerState.ON)
#                 self.dlnaRenderer.stop()
#                 if speak is True:
#                     self._speak("DLNA deaktiviert", "de-de")
#                 self._setRadioState(_RadioState.STOPPED)
#                 self.waitForRadioState(_RadioState.STOPPED, self.playStateCnd)
#                 self._radioPlay()
#             else:
#                 self.logger.info("not in state dlna, cannot stop dlna")
#                 return
#             self.playStateCnd.notify_all()        
#             
    def bluetoothControl(self, enabled):
        self._putJobIntoQueue(lambda: self._bluetoothControl(enabled))
           
    def _bluetoothControl(self, enabled, speak=True, force=False):
        if self.bluetoothEnabled == enabled and force is False:
            self.logger.info("BT already in desired state (%s)" % self.bluetoothEnabled)
            return
        self.bluetoothEnabled = enabled
        if enabled:
            self.logger.info("Activating bluetooth/upnp")
            if self.isPoweredOn() or force:
                if speak:
                    self._speak("Aktiviere UPNP", "de-de")
                if self.bluetooth:
                    self.bluetooth.enable()
                if self.upmp:
                    self.upmp.enable()
            else:
                self.logger.info("Not powered on, not activating bluetooth/upnp")
        else:
            if self.isPoweredOn() or force:
                self.logger.info("Deactivating bluetooth/upnp")
                if speak:
                    self.speak("Deaktiviere UPNP", "de-de")
            if self.bluetooth:
                self.bluetooth.disable()
            if self.upmp:
                self.upmp.disable()
    
    def setSkipMqttUpdates(self, skip):
        self.logger.info("setSkipMqttUpdates(skip='%s')" % skip)
        self._putJobIntoQueue(lambda: self._setSkipMqttUpdates(skip))
                        
    def _setSkipMqttUpdates(self, skip):
        self.logger.info("_setSkipMqttUpdates(skip='%s')" % skip)
        with self.playStateCnd:
            self.skipMqttUpdates = skip
            
        if self.skipMqttUpdates is False:
            self.sendStateToMqtt()
            
    def setLoudness(self, state):
        self.logger.info("Loudness set to %i" % state)
        self.loudness = state
        if self.vcb:
            self.vcb.setLoudness(state)
            
    def upnpStopCallback(self):
        if self.currentState.getEstate() == eStates.UPNP_PLAYING:
            self.logger.info("Coordinator: Upnp playback stopped")
            self.startRadio()
        else:
            self.logger.info("Coordinator: Not in state eStates.UPNP_PLAYING, not doing anything")
        
    def upnpPlaybackStartCallback(self):
        self.logger.info("Coordinator: Upnp playback starts")
        self.__clearJobQueue()
        self._putJobIntoQueue(self._upnpupnpPlaybackStartCallback)
        
    def _upnpupnpPlaybackStartCallback(self):
        if self.currentState.getEstate() is eStates.UPNP_PLAYING:
            self.info("Coordinator: Already in state UPNP_PLAYING")
            return
        newState = StateStopped(self)
        if newState.transitInto():
            pass
        else:
            self.logger.error("Transition failed")
        
        self._speak("UPNP Wiedergabe beginnt", "de-de")
        newState = StateUpnpPlaying(self)
        if newState.transitInto() is False:
            self.currentState = StateError(self, "Upnp Playing failed")
            return      
