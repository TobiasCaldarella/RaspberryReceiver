'''
Created on 25.01.2020

@author: tobias
'''
import smbus
import threading
import time

class PCF8591(object):
    def __init__(self, config, i2cMtx):
        '''
        Constructor
        '''
        self.address = config.signal_strength_dac_address
        self.cmd = 0x40
        self.bus = smbus.SMBus(1)
        self.i2cMtx = i2cMtx
        
    def send(self, value):
        with self.i2cMtx:
            self.bus.write_byte_data(self.address,self.cmd,value)
        
class SignalStrengthMeter(object):
    def __init__(self, config, coordinator, i2cMtx):
        self.logger = config.logger
        self.t = None
        self.lastValue = None
        self.dac = PCF8591(config, i2cMtx)
        self.run = True
        self.lastAvg = 0
        self.numCollectedValues = 0
        coordinator.signal_strength_meter = self
        
    def init(self):
        self.dac.send(0)

    def enable(self):
        self.run = True
        if self.t is not None:
            return
        self.logger.info("SignalStrenghtMeter enabled, thread starting...")
        self.t = threading.Thread(target=self.processStats)
        self.t.start()
    
    def disable(self):
        self.logger.info("SignalStrenghtMeter stopping...")
        self.run = False
        if self.t is None:
            self.logger.info("SignalStrengthMeter Thread already stopped")
            return
        self.logger.info("SignalStrengthMeter Thread joining")
        self.t.join()
        self.logger.info("SignalStrengthMeter Thread joined")
    
    def processStats(self):
        self.logger.info("SignalStrenghtMeter thread started!")
        logCounter = 0
        with open('/proc/net/dev') as f:
            for line in f:
                if 'wlan0' in line:
                    newValue = int(line.split()[1])
                    if self.lastValue is not None:
                        diff = int((newValue - self.lastValue)/32768*10*256) # maximum @256kbit/s=>32kB/s
                        
                        self.lastAvg = 0.9*self.lastAvg + 0.1*diff
                        #if self.numCollectedValues < 99:
                        #    self.numCollectedValues = self.numCollectedValues + 1
                        if logCounter is 100:
                            self.logger.debug("SignalStrengthMeter value %i" % self.lastAvg)
                            logCounter = 0
                        else:
                            logCounter = logCounter + 1
                            
                        self.dac.send(min(int(self.lastAvg),255))
                    self.lastValue = newValue
                    f.seek(0)
                    time.sleep(0.1)
                if not self.run:
                    break
        # write error log, should never ever exit
        
        self.logger.info("SignalStrenghtMeter thread ended")
        self.t = None
