'''
Created on 25.01.2020

@author: tobias
'''
import smbus
import sys
import threading
import time
from math import sqrt
from Coordinator import Coordinator
from Configuration import Configuration, _RadioPowerState

class I2cThing(object):
    def __init__(self, logger, address, i2cMtx):
        '''
        Constructor
        '''
        self.address = address
        self.bus = smbus.SMBus(1)
        self.i2cMtx = i2cMtx
        self.logger = logger
    
    def _send(self, value):
        with self.i2cMtx:
            self.bus.write_byte(self.address,value)
            
    def _read(self):
        with self.i2cMtx:
            return self.bus.read_byte(self.address)

class DS1882(I2cThing):
    def __init__(self, logger, address, i2cMtx):
        super().__init__(logger, address, i2cMtx)
        self.potiConfig = 0x86
        self.logger = logger

    def init(self):
        super()._send(self.potiConfig)
        
    def setPoti(self, volume):
        if volume <= 0x3f:
            val = 0x3f - volume
            self.logger.debug("Setting poti @%x to: %x" % (self.address, val))
            super()._send(0x00 + val)
            super()._send(0x40 + val)
        else:
            self.logger.error("Invalid value: %x" % volume)
        
class PCF8574(I2cThing):
    def __init__(self, logger, address, i2cMtx):
        super().__init__(logger, address, i2cMtx)
        self.logger = logger
        self.downMask = 0x0

    def setPin(self, pin, value):
        if pin > 7:
            self.logger.error("Pin %i invalid!" % pin)
            return
        
        if value is False:
            self.downMask = self.downMask | (1<<pin)
        else:
            self.downMask = self.downMask & ~(1<<pin) & 0xff
        val = ~self.downMask & 0xff
        self.logger.info("sending %x" % val)
        super()._send(val)
    
    def init(self):
        super()._send(0xff)
        
class VolumeControlBoard(object):
    def __init__(self, config, coordinator, i2cMtx):
        self.mtx = threading.Lock()
        self.logger = config.logger
        self.loudnessPoint = config.loudnessPoint
        self.maxLoudness = config.maxLoudness
        coordinator.vcb = self
        self.coordinator = coordinator
        self.volPoti = DS1882(self.logger, config.volPotiAddress, i2cMtx)
        self.ldsPoti = DS1882(self.logger, config.ldsPotiAddress, i2cMtx)
        self.mpx = PCF8574(self.logger, config.vcbPortMpxAddress, i2cMtx)
        self.powerPinHigh = 7
        self.powerPinLow = 6
        self.i2cEnablePinLow = 0
        self.i2cLoudnessRelaisPinLow = 3
        self.loudnessEnabled = False
        self.currentVolume = 0
        self.poweredOn = False

        self.startLoudness = 10
        self.volExtraLowSteps = int(sqrt(self.startLoudness))
        self.maxVolumePhy = 63
        self.maxVolume = self.maxVolumePhy + self.volExtraLowSteps
        
    def init(self):
        with self.mtx:
            self.mpx.init()
        
    def powerOn(self):
        # check that device is powered on via gpio controller
        if (self.coordinator.powerState != _RadioPowerState.POWERING_UP):
            self.logger.error("Not powering on VCB board if not in state _RadioPowerState.POWERING_UP. Current state: %s" % self.coordinator.powerState)
        with self.mtx:
            self.mpx.setPin(self.powerPinHigh, True)
            self.mpx.setPin(self.powerPinLow, False)
            time.sleep(0.3)
            self._updateVolume()
            self.poweredOn = True # set after updateVolume to trigger poti init
            self.logger.info("VCB powered on")
        
    def powerOff(self):
        with self.mtx:
            self.currentVolume = 0
            self._updateVolume()
            self.mpx.setPin(self.powerPinHigh, False)
            self.mpx.setPin(self.powerPinLow, True)
            self.poweredOn = False
            self.logger.info("VCB powered off")
        
    def _updateVolume(self):
        try:
            self.mpx.setPin(self.i2cEnablePinLow, False)
            time.sleep(0.01)
            if self.poweredOn is False:
                self.volPoti.init()
                self.ldsPoti.init()
            volExtraLowSteps = self.volExtraLowSteps
            if self.currentVolume <= 0:
                volVal = 0
            elif self.currentVolume <= volExtraLowSteps:
                volVal = 1
            else:
                volVal = self.currentVolume - volExtraLowSteps
            ldsVal = 0
            maxVolume = self.maxVolumePhy
            maxLoudness = self.maxLoudness
            startLoudness = self.startLoudness
            endLoudness = 10
            loudnessPoint = self.loudnessPoint
            diffFromPoint = volVal - loudnessPoint

            if self.currentVolume <= volExtraLowSteps: # "ab"use loudness against zero to lower volume even more in three steps
                ldsVal = int(pow(2,(self.currentVolume-1))-1)
                #ldsVal = int(startLoudness * ((self.currentVolume-1)/volExtraLowSteps))
            elif diffFromPoint > 0:
                steep = (maxLoudness-endLoudness)/(maxVolume-loudnessPoint)
                ldsVal = int(maxLoudness-steep*diffFromPoint)
            else: #if self.currentVolume > volExtraLowSteps:
                steep = (maxLoudness-startLoudness)/(loudnessPoint-1)
                ldsVal = int(maxLoudness-steep*(-diffFromPoint))

            if self.loudnessEnabled is True and volVal > 0:
                self.mpx.setPin(self.i2cLoudnessRelaisPinLow, False)
            else:
                self.mpx.setPin(self.i2cLoudnessRelaisPinLow, True)

            ldsVal = self.maxVolumePhy - ldsVal # poti inverted to better match with log scale

            self.logger.info("VCB set values: volume %i, loudness %i" % (volVal, ldsVal))
            self.volPoti.setPoti(volVal)
            self.ldsPoti.setPoti(ldsVal)
        except Exception as ex:
            self.logger.error("VCB: Exception setting volume: %s" % ex)
        finally:
            self.mpx.setPin(self.i2cEnablePinLow, True)
        
    def setVolume(self, volume):
        if volume < 0:
            self.logger.error("VCB: volume % is invalid. using 0!" % volume)
            volume = 0
        if volume > self.maxVolume:
            self.logger.error("VCB: volume %d is invalid. using %d!" % (volume, self.maxVolume))
            volume = self.maxVolume
        9 
        with self.mtx:
            self.currentVolume = volume
            if self.poweredOn is True:
                self._updateVolume()

    def setLoudness(self, lds):
        with self.mtx:
            self.loudnessEnabled = lds
            if self.poweredOn is True:
                self._updateVolume()
        
        
        
        
